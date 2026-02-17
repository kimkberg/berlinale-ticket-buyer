"""Atomic clock synchronization with NTP and HTTP fallback support."""
import asyncio
import logging
import socket
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse
import httpx
from app.config import Config

logger = logging.getLogger(__name__)


class TimeSyncProvider(ABC):
    """Abstract base class for time synchronization providers."""
    
    @abstractmethod
    async def sync(self) -> tuple[bool, Optional[float]]:
        """Sync with time source.
        
        Returns:
            Tuple of (success, offset_seconds)
        """
        pass
    
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        pass


class NTPTimeSyncProvider(TimeSyncProvider):
    """NTP-based atomic clock synchronization (highest precision)."""
    
    NTP_SERVERS = [
        "time.google.com",           # Google's NTP (stratum 1)
        "time.cloudflare.com",       # Cloudflare NTP (stratum 3)
        "ptbtime1.ptb.de",          # German atomic clock (PTB Braunschweig)
        "pool.ntp.org",             # NTP pool
    ]
    
    def __init__(self):
        self._ntp_available = False
        try:
            import ntplib
            self._ntp_client = ntplib.NTPClient()
            self._ntp_available = True
            logger.info("NTP provider initialized (ntplib available)")
        except ImportError:
            logger.warning("ntplib not installed, NTP sync unavailable")
    
    def name(self) -> str:
        return "NTP"
    
    async def sync(self) -> tuple[bool, Optional[float]]:
        """Sync using NTP protocol."""
        if not self._ntp_available:
            return False, None
        
        # Configure proxy for NTP if needed
        original_socket = None
        if Config.PROXY_URL:
            original_socket = socket.socket
            if not self._configure_socks_proxy():
                logger.warning("SOCKS proxy configuration failed, trying direct NTP")
        
        try:
            for server in self.NTP_SERVERS:
                try:
                    logger.info(f"Syncing with NTP server: {server}")
                    
                    # Run blocking NTP call in executor
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None,
                        lambda s=server: self._ntp_client.request(s, version=3, timeout=5)
                    )
                    
                    offset = response.offset
                    logger.info(
                        f"✓ NTP sync successful | "
                        f"Server: {server} | "
                        f"Offset: {offset*1000:.2f}ms | "
                        f"Stratum: {response.stratum}"
                    )
                    return True, offset
                    
                except Exception as e:
                    logger.debug(f"NTP server {server} failed: {e}")
                    continue
            
            logger.warning("All NTP servers failed")
            return False, None
            
        finally:
            # Restore original socket if we modified it
            if original_socket:
                socket.socket = original_socket
    
    def _configure_socks_proxy(self) -> bool:
        """Configure SOCKS proxy for NTP traffic."""
        try:
            import socks
            proxy_url = urlparse(Config.PROXY_URL)
            
            if proxy_url.scheme in ("socks5", "socks5h"):
                socks.set_default_proxy(
                    socks.SOCKS5,
                    proxy_url.hostname,
                    proxy_url.port or 1080,
                    username=proxy_url.username,
                    password=proxy_url.password
                )
                socket.socket = socks.socksocket
                logger.info(f"Configured SOCKS5 proxy for NTP: {proxy_url.hostname}:{proxy_url.port}")
                return True
            else:
                logger.warning(f"NTP requires SOCKS proxy, got {proxy_url.scheme}")
                return False
                
        except ImportError:
            logger.warning("PySocks not installed, cannot use proxy with NTP")
            return False


class HTTPTimeSyncProvider(TimeSyncProvider):
    """HTTP-based time synchronization (works with any proxy)."""
    
    @staticmethod
    def _parse_datetime_with_z(data: dict, key: str) -> datetime:
        """Parse datetime string, replacing 'Z' suffix with UTC timezone."""
        return datetime.fromisoformat(data[key].replace("Z", "+00:00"))
    
    TIME_APIS = [
        {
            "url": "https://timeapi.io/api/time/current/zone?timeZone=Europe/Berlin",
            "parser": lambda r: HTTPTimeSyncProvider._parse_datetime_with_z(r, "dateTime")
        },
        {
            "url": "https://worldtimeapi.org/api/timezone/Europe/Berlin",
            "parser": lambda r: datetime.fromisoformat(r["datetime"])
        },
        {
            "url": "https://timeapi.io/api/time/current/zone?timeZone=UTC",
            "parser": lambda r: HTTPTimeSyncProvider._parse_datetime_with_z(r, "dateTime")
        },
    ]
    
    def name(self) -> str:
        return "HTTP"
    
    async def sync(self) -> tuple[bool, Optional[float]]:
        """Sync using HTTP time APIs."""
        client_kwargs = {
            "timeout": 5.0,
            "follow_redirects": True,
        }
        if Config.PROXY_URL:
            client_kwargs["proxy"] = Config.PROXY_URL
            logger.info(f"Using proxy for HTTP time sync: {Config.PROXY_URL}")
        
        async with httpx.AsyncClient(**client_kwargs) as client:
            for api in self.TIME_APIS:
                try:
                    logger.info(f"Syncing with HTTP API: {api['url']}")
                    
                    # Measure round-trip time
                    before = datetime.now(timezone.utc)
                    response = await client.get(api["url"])
                    after = datetime.now(timezone.utc)
                    
                    if response.status_code != 200:
                        logger.debug(f"HTTP time API returned {response.status_code}")
                        continue
                    
                    # Parse atomic time
                    atomic_time = api["parser"](response.json())
                    
                    # Calculate offset with network latency compensation
                    network_delay = (after - before).total_seconds() / 2
                    local_time_mid = before + (after - before) / 2
                    # Ensure atomic_time has timezone info for proper comparison
                    if atomic_time.tzinfo is None:
                        atomic_time = atomic_time.replace(tzinfo=timezone.utc)
                    offset = (atomic_time - local_time_mid).total_seconds()
                    
                    logger.info(
                        f"✓ HTTP sync successful | "
                        f"Offset: {offset*1000:.1f}ms | "
                        f"Latency: {network_delay*1000:.1f}ms"
                    )
                    return True, offset
                    
                except Exception as e:
                    logger.debug(f"HTTP time API failed: {e}")
                    continue
        
        logger.warning("All HTTP time APIs failed")
        return False, None


class AtomicTimeSync:
    """Main time synchronization manager with multiple provider support."""
    
    def __init__(self, method: str = "auto"):
        self._offset: Optional[float] = None
        self._last_sync: Optional[datetime] = None
        self._sync_interval = Config.TIME_SYNC_INTERVAL
        self._method = method.lower()
        self._active_provider: Optional[str] = None
        
        # Initialize providers
        self._providers: dict[str, TimeSyncProvider] = {
            "ntp": NTPTimeSyncProvider(),
            "http": HTTPTimeSyncProvider(),
        }
        
        logger.info(f"AtomicTimeSync initialized with method: {self._method}")
    
    async def sync(self) -> bool:
        """Synchronize with atomic clock using configured method.
        
        Returns:
            True if sync successful, False otherwise.
        """
        if self._method == "ntp":
            return await self._sync_with_provider("ntp")
        elif self._method == "http":
            return await self._sync_with_provider("http")
        elif self._method == "auto":
            # Try NTP first (more accurate), fall back to HTTP
            if await self._sync_with_provider("ntp"):
                return True
            return await self._sync_with_provider("http")
        else:
            logger.error(f"Unknown sync method: {self._method}")
            return False
    
    async def _sync_with_provider(self, provider_name: str) -> bool:
        """Sync with a specific provider."""
        provider = self._providers.get(provider_name)
        if not provider:
            return False
        
        success, offset = await provider.sync()
        if success and offset is not None:
            self._offset = offset
            self._last_sync = datetime.now(timezone.utc)
            self._active_provider = provider_name
            return True
        return False
    
    def now(self, tz=None) -> datetime:
        """Get current atomic time (corrected for offset).
        
        Args:
            tz: Optional timezone, defaults to local
            
        Returns:
            datetime with atomic clock precision.
        """
        if self._offset is None:
            logger.debug("No time sync, using system time")
            return datetime.now(tz)
        
        # Check if we need to re-sync
        if self._should_resync():
            logger.info("Time sync expired, re-syncing in background")
            # Create background task but don't await it
            task = asyncio.create_task(self.sync())
            # Add callback to log any exceptions
            def log_exception(t):
                if not t.cancelled():
                    exc = t.exception()
                    if exc:
                        logger.error(f"Background sync failed: {exc}")
            task.add_done_callback(log_exception)
        
        # Return system time corrected by offset
        if tz:
            base_time = datetime.now(timezone.utc)
            corrected = base_time + timedelta(seconds=self._offset)
            return corrected.astimezone(tz)
        else:
            # For naive datetime (local time), use local clock with offset
            base_time = datetime.now()
            return base_time + timedelta(seconds=self._offset)
    
    def _should_resync(self) -> bool:
        """Check if re-sync is needed."""
        if not self._last_sync:
            return True
        elapsed = (datetime.now(timezone.utc) - self._last_sync).total_seconds()
        return elapsed > self._sync_interval
    
    @property
    def offset_ms(self) -> Optional[float]:
        """Get current time offset in milliseconds."""
        return self._offset * 1000 if self._offset is not None else None
    
    @property
    def is_synced(self) -> bool:
        """Check if time is currently synced."""
        return self._offset is not None
    
    @property
    def provider(self) -> Optional[str]:
        """Get the active sync provider name."""
        return self._active_provider
    
    def get_status(self) -> dict:
        """Get detailed sync status."""
        return {
            "enabled": Config.TIME_SYNC_ENABLED,
            "method": self._method,
            "active_provider": self._active_provider,
            "synced": self.is_synced,
            "offset_ms": self.offset_ms,
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            "atomic_time": self.now().isoformat() if self.is_synced else None,
            "system_time": datetime.now(timezone.utc).isoformat(),
        }


# Global singleton
_time_sync: Optional[AtomicTimeSync] = None


def get_time_sync() -> AtomicTimeSync:
    """Get the global time sync instance."""
    global _time_sync
    if _time_sync is None:
        method = Config.TIME_SYNC_METHOD if Config.TIME_SYNC_ENABLED else "none"
        _time_sync = AtomicTimeSync(method=method)
    return _time_sync


async def init_time_sync() -> bool:
    """Initialize and perform first sync.
    
    Returns:
        True if sync successful or disabled, False if enabled but failed.
    """
    if not Config.TIME_SYNC_ENABLED:
        logger.info("⏰ Time sync disabled")
        return True
    
    time_sync = get_time_sync()
    success = await time_sync.sync()
    
    if success:
        logger.info(
            f"⏰ Time sync enabled | "
            f"Provider: {time_sync.provider.upper()} | "
            f"Offset: {time_sync.offset_ms:.2f}ms"
        )
    else:
        logger.warning("⚠️  Time sync failed, using system time")
    
    return success
