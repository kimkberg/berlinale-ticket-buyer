from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import Config
from app.models import GrabTask

logger = logging.getLogger(__name__)


class TicketMonitor:
    """Polls Berlinale ticket status for watched screenings.

    When a watched screening transitions to "available", updates the task
    and hands it off to the scheduler for grabbing.
    """

    def __init__(self) -> None:
        self._watches: dict[str, GrabTask] = {}
        self._poll_task: asyncio.Task | None = None
        self._storage = None
        self._on_change = None

    def add_watch(self, task: GrabTask) -> None:
        self._watches[task.id] = task

    def remove_watch(self, task_id: str) -> None:
        self._watches.pop(task_id, None)

    def get_watches(self) -> list[GrabTask]:
        return list(self._watches.values())

    def start(self, storage, on_change) -> None:
        """Start the monitoring loop.

        Args:
            storage: TaskStorage instance for persisting task updates.
            on_change: Async callback ``(task_id, state, url) -> None``
                       invoked when a screening becomes available.
        """
        self._storage = storage
        self._on_change = on_change
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.create_task(self._poll_loop())
            logger.info("TicketMonitor started")

    def stop(self) -> None:
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            logger.info("TicketMonitor stopped")
        self._poll_task = None

    # ── internal ────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Monitor poll error")

            interval = self._next_interval()
            await asyncio.sleep(interval)

    async def _poll_once(self) -> None:
        if not self._watches:
            return

        from app.berlinale_api import fetch_ticket_status

        ticket_map = await fetch_ticket_status()
        if not ticket_map:
            return

        # Snapshot keys so we can mutate _watches during iteration
        for task_id in list(self._watches):
            task = self._watches.get(task_id)
            if task is None:
                continue

            info = ticket_map.get(task.ext_id_screening)
            if info is None:
                continue

            if info.state == "available":
                url = info.url or ""
                task.eventim_url = url or task.eventim_url
                task.status = "pending"

                if self._storage:
                    self._storage.update_task(
                        task.id,
                        eventim_url=task.eventim_url,
                        status="pending",
                    )

                if self._on_change:
                    await self._on_change(task_id, "available", url)

                self.remove_watch(task_id)
                logger.info(
                    "Screening %s now available — task %s moved to pending",
                    task.ext_id_screening,
                    task_id,
                )

    def _next_interval(self) -> float:
        """Return the poll interval in seconds.

        Uses the fast interval when any watched screening starts within
        the golden-hour window.
        """
        if not self._watches:
            return Config.MONITOR_POLL_INTERVAL

        now = datetime.now(ZoneInfo(Config.TIMEZONE))
        golden = timedelta(minutes=Config.MONITOR_GOLDEN_HOUR_MINUTES)

        for task in self._watches.values():
            if task.screening_time:
                try:
                    screening_dt = datetime.fromisoformat(task.screening_time)
                    if screening_dt - now <= golden:
                        return Config.MONITOR_FAST_POLL_INTERVAL
                except (ValueError, TypeError):
                    pass

        return Config.MONITOR_POLL_INTERVAL


ticket_monitor = TicketMonitor()
