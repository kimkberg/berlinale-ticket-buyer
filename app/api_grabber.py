from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import Config
from app.models import GrabTask

logger = logging.getLogger(__name__)


class APIGrabber:
    """Alternative ticket grabber using direct HTTP requests.

    Faster than browser automation but may be blocked by anti-bot measures.
    Requires cookies from a valid Eventim session (obtained via browser login).
    """

    def __init__(self):
        self._cookies: dict[str, str] = {}
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            client_kwargs = {
                "timeout": 15.0,
                "follow_redirects": True,
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
                },
                "cookies": self._cookies,
            }
            if Config.PROXY_URL:
                client_kwargs["proxy"] = Config.PROXY_URL
                logger.info("API Grabber using proxy: %s", Config.PROXY_URL)
            
            self._client = httpx.AsyncClient(**client_kwargs)
        return self._client

    def load_cookies_from_browser(self, browser_manager) -> bool:
        """Extract cookies from the Playwright browser session.

        Must be called after user has logged in via browser.
        """
        try:
            if not browser_manager.is_initialized:
                logger.warning("Browser not initialized, cannot extract cookies")
                return False

            # This is a sync method; cookies will be loaded when the browser context
            # provides them. In practice, call this from an async context.
            logger.info("Cookie loading needs to be done via async method")
            return False
        except Exception:
            logger.exception("Failed to load cookies from browser")
            return False

    async def load_cookies_from_browser_async(self, browser_manager) -> bool:
        """Async version: extract cookies from Playwright browser context."""
        try:
            if not browser_manager.is_initialized:
                return False

            context = browser_manager._context
            cookies = await context.cookies(Config.EVENTIM_BASE_URL)
            self._cookies = {c["name"]: c["value"] for c in cookies}
            # Recreate client with new cookies
            if self._client and not self._client.is_closed:
                await self._client.aclose()
                self._client = None
            logger.info("Loaded %d cookies from browser", len(self._cookies))
            return bool(self._cookies)
        except Exception:
            logger.exception("Failed to extract cookies")
            return False

    async def grab_ticket(self, task: GrabTask, on_status=None) -> dict:
        """Attempt to grab a ticket via direct HTTP requests.

        Args:
            task: Grab task with eventim_url.
            on_status: Optional async callback for progress updates.

        Returns:
            dict with "success" and "message".
        """
        if not task.eventim_url:
            return {"success": False, "message": "No Eventim URL"}

        async def _report(status: str, msg: str):
            if on_status:
                await on_status(status, msg)
            logger.info("API Grab [%s] %s: %s", task.ext_id_screening, status, msg)

        try:
            client = await self._get_client()
            await _report("grabbing", "Sending HTTP request to Eventim...")

            # Step 1: GET the event page
            resp = await client.get(task.eventim_url)
            if resp.status_code != 200:
                await _report("failed", f"HTTP {resp.status_code}")
                return {"success": False, "message": f"HTTP {resp.status_code} from Eventim"}

            page_text = resp.text
            await _report("grabbing", "Page loaded, analyzing...")

            # Step 2: Look for add-to-cart form/API endpoint in the page
            import re
            # Look for cart/purchase URLs in the page
            cart_patterns = [
                r'action="([^"]*(?:cart|warenkorb|basket)[^"]*)"',
                r'href="([^"]*(?:addToCart|add-to-cart)[^"]*)"',
                r'"(https?://[^"]*(?:cart|warenkorb|basket|checkout)[^"]*)"',
            ]

            cart_url = None
            for pattern in cart_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    cart_url = match.group(1)
                    if not cart_url.startswith("http"):
                        cart_url = Config.EVENTIM_BASE_URL + cart_url
                    break

            if cart_url:
                await _report("grabbing", "Found cart URL, adding ticket...")
                cart_resp = await client.post(cart_url, data={
                    "quantity": str(task.ticket_count),
                    "amount": str(task.ticket_count),
                })
                if cart_resp.status_code in (200, 302):
                    await _report("success", "Ticket may have been added to cart!")
                    return {"success": True, "message": "HTTP request sent to cart endpoint"}
                else:
                    await _report("failed", f"Cart request returned HTTP {cart_resp.status_code}")
                    return {"success": False, "message": f"Cart HTTP {cart_resp.status_code}"}

            # If no cart URL found, the page might require JS rendering
            await _report("failed", "Could not find purchase endpoint in HTML. Try browser mode.")
            return {"success": False, "message": "No purchase endpoint found; page may require JavaScript"}

        except Exception as e:
            logger.exception("API grab error for %s", task.ext_id_screening)
            if on_status:
                await on_status("failed", str(e))
            return {"success": False, "message": str(e)}

    async def poll_and_grab(self, task: GrabTask, on_status=None) -> dict:
        """Poll ticket status and grab when available.

        This combines polling /10am/10am_ticket_en.js with immediate purchase
        when status changes to 'available'.
        """
        from app.berlinale_api import fetch_ticket_status

        async def _report(status: str, msg: str):
            if on_status:
                await on_status(status, msg)

        await _report("grabbing", "Polling ticket status via API...")

        max_polls = int(300 / Config.POLL_INTERVAL)  # poll for up to 5 minutes
        for i in range(max_polls):
            try:
                ticket_map = await fetch_ticket_status()
                info = ticket_map.get(task.ext_id_screening)
                if info and info.state == "available":
                    url = info.url or task.eventim_url
                    if url:
                        task_copy = task.model_copy(update={"eventim_url": url})
                        return await self.grab_ticket(task_copy, on_status)
                    await _report("failed", "Available but no URL found")
                    return {"success": False, "message": "Ticket available but no URL"}
            except Exception:
                logger.exception("Poll error")

            await asyncio.sleep(Config.POLL_INTERVAL)

        await _report("failed", "Polling timeout")
        return {"success": False, "message": "Polling timeout after 5 minutes"}

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


# Global singleton
api_grabber = APIGrabber()
