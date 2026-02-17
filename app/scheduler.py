from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import Config
from app.models import GrabTask
from app.storage import TaskStorage

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_storage: TaskStorage | None = None

# Callbacks for notifying the main app of status changes
_on_task_update = None  # async callback(task_id, status, message)


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone=Config.TIMEZONE)
    return _scheduler


def set_storage(storage: TaskStorage):
    global _storage
    _storage = storage


def set_on_task_update(callback):
    """Set callback for task status updates: async fn(task_id, status, message)."""
    global _on_task_update
    _on_task_update = callback


def _sanitize(text: str) -> str:
    """Strip ANSI escape codes and control characters from error messages."""
    text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    return text


async def _notify(task_id: str, status: str, message: str):
    """Update task in storage and notify via callback."""
    message = _sanitize(message)
    if _storage:
        _storage.update_task(task_id, status=status, result_message=message)
    if _on_task_update:
        await _on_task_update(task_id, status, message)


async def _run_browser_grab(task: GrabTask):
    """Execute browser-based grab for a task."""
    from app.grabber import browser_manager, ticket_grabber

    task_id = task.id
    await _notify(task_id, "grabbing", "Starting browser grab...")

    try:
        # Ensure browser is ready
        if not browser_manager.is_initialized:
            await _notify(task_id, "grabbing", "Starting browser...")
            await browser_manager.init_browser()

        async def on_status(status, msg):
            await _notify(task_id, status, msg)

        result = await ticket_grabber.grab_ticket(task, on_status=on_status)

        final_status = "success" if result["success"] else "failed"
        await _notify(task_id, final_status, result["message"])

    except Exception as e:
        logger.exception("Browser grab error for task %s", task_id)
        await _notify(task_id, "failed", str(e))


async def _run_api_grab(task: GrabTask):
    """Execute API-based grab for a task."""
    from app.api_grabber import api_grabber

    task_id = task.id
    await _notify(task_id, "grabbing", "Starting API grab...")

    try:
        async def on_status(status, msg):
            await _notify(task_id, status, msg)

        result = await api_grabber.poll_and_grab(task, on_status=on_status)

        final_status = "success" if result["success"] else "failed"
        await _notify(task_id, final_status, result["message"])

    except Exception as e:
        logger.exception("API grab error for task %s", task_id)
        await _notify(task_id, "failed", str(e))


async def _preheat_browser(task: GrabTask):
    """Open Eventim page ahead of sale time to warm up connection."""
    from app.grabber import browser_manager, ticket_grabber

    await _notify(task.id, "grabbing", "Preheating browser...")

    try:
        if not browser_manager.is_initialized:
            await browser_manager.init_browser()

        page = await ticket_grabber.preheat(task)
        if page:
            await _notify(task.id, "grabbing", "Page preheated, waiting for sale time...")

            # Wait until exact sale time, then refresh and grab
            if task.sale_time:
                sale_dt = datetime.fromisoformat(task.sale_time)
                now = datetime.now(ZoneInfo(Config.TIMEZONE))
                wait_seconds = (sale_dt - now).total_seconds()
                if wait_seconds > 0:
                    logger.info("Waiting %.1f seconds until sale time", wait_seconds)
                    await asyncio.sleep(max(0, wait_seconds))

            # Now grab
            async def on_status(status, msg):
                await _notify(task.id, status, msg)

            result = await ticket_grabber.grab_with_refresh(page, task, on_status=on_status)
            final_status = "success" if result["success"] else "failed"
            await _notify(task.id, final_status, result["message"])
        else:
            # Fall back to regular grab
            await _run_browser_grab(task)

    except Exception as e:
        logger.exception("Preheat/grab error for task %s", task.id)
        await _notify(task.id, "failed", str(e))


def schedule_grab(task: GrabTask) -> bool:
    """Schedule a grab task based on its sale_time.

    For browser mode: schedules preheat 30s before sale, then grab at sale time.
    For API mode: schedules poll+grab at sale time.
    """
    scheduler = get_scheduler()

    if not task.sale_time:
        logger.warning("Task %s has no sale_time, cannot schedule", task.id)
        return False

    try:
        sale_dt = datetime.fromisoformat(task.sale_time)
    except ValueError:
        logger.error("Invalid sale_time format: %s", task.sale_time)
        return False

    now = datetime.now(ZoneInfo(Config.TIMEZONE))

    if task.mode == "browser":
        # Schedule preheat (opens page before sale time)
        preheat_time = sale_dt - timedelta(seconds=Config.PRE_SALE_OPEN_PAGE)
        if preheat_time > now:
            scheduler.add_job(
                _preheat_browser,
                "date",
                run_date=preheat_time,
                args=[task],
                id=f"preheat_{task.id}",
                replace_existing=True,
                misfire_grace_time=60,
            )
            logger.info("Scheduled preheat for task %s at %s", task.id, preheat_time)
        else:
            # Sale time already passed or imminent, run immediately
            scheduler.add_job(
                _run_browser_grab,
                "date",
                run_date=now + timedelta(seconds=2),
                args=[task],
                id=f"grab_{task.id}",
                replace_existing=True,
                misfire_grace_time=300,
            )
            logger.info("Scheduled immediate browser grab for task %s", task.id)
    else:
        # API mode: start polling slightly before sale time
        poll_time = sale_dt - timedelta(seconds=Config.PRE_SALE_POLL)
        if poll_time > now:
            scheduler.add_job(
                _run_api_grab,
                "date",
                run_date=poll_time,
                args=[task],
                id=f"api_grab_{task.id}",
                replace_existing=True,
                misfire_grace_time=60,
            )
            logger.info("Scheduled API grab for task %s at %s", task.id, poll_time)
        else:
            scheduler.add_job(
                _run_api_grab,
                "date",
                run_date=now + timedelta(seconds=2),
                args=[task],
                id=f"api_grab_{task.id}",
                replace_existing=True,
                misfire_grace_time=300,
            )
            logger.info("Scheduled immediate API grab for task %s", task.id)

    return True


def cancel_grab(task_id: str) -> bool:
    """Cancel scheduled jobs for a task."""
    scheduler = get_scheduler()
    cancelled = False
    for prefix in ("preheat_", "grab_", "api_grab_"):
        job_id = f"{prefix}{task_id}"
        try:
            scheduler.remove_job(job_id)
            cancelled = True
            logger.info("Cancelled job %s", job_id)
        except Exception:
            pass
    return cancelled


def start_scheduler():
    """Start the APScheduler if not already running."""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


def shutdown_scheduler():
    """Shutdown the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
    _scheduler = None


def reschedule_pending_tasks(storage: TaskStorage):
    """Re-schedule all pending tasks on startup."""
    from app.monitor import ticket_monitor

    tasks = storage.get_all_tasks()
    count = 0
    watch_count = 0
    for task in tasks:
        if task.status == "pending":
            if schedule_grab(task):
                count += 1
        elif task.status == "watching":
            ticket_monitor.add_watch(task)
            watch_count += 1
    logger.info("Re-scheduled %d pending tasks, %d watching tasks", count, watch_count)
