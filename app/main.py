from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app import berlinale_api, scheduler
from app.config import Config
from app.models import GrabTask, StatusMessage, TaskCreate
from app.monitor import ticket_monitor
from app.storage import TaskStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# --- WebSocket connection manager ---

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.info("WebSocket connected (%d total)", len(self.active))

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
        logger.info("WebSocket disconnected (%d total)", len(self.active))

    async def broadcast(self, message: dict):
        data = json.dumps(message, ensure_ascii=False)
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


ws_manager = ConnectionManager()
storage = TaskStorage()


async def on_task_update(task_id: str, status: str, message: str):
    """Callback from scheduler when a task status changes."""
    task = storage.get_task(task_id)
    await ws_manager.broadcast({
        "type": "task_update",
        "data": {
            "task_id": task_id,
            "status": status,
            "message": message,
            "task": task.model_dump() if task else None,
        },
    })


async def on_monitor_change(task_id: str, new_state: str, ticket_url: str):
    """Callback from monitor when a watched screening becomes available."""
    task = storage.get_task(task_id)
    if not task:
        return

    # Update task with new URL and schedule grab
    storage.update_task(task_id, status="pending", eventim_url=ticket_url, result_message="Ticket available! Auto-scheduling grab...")
    task = storage.get_task(task_id)

    # Schedule immediate grab
    if task:
        scheduler.schedule_grab(task)

    # Notify clients
    await ws_manager.broadcast({
        "type": "monitor_alert",
        "data": {
            "task_id": task_id,
            "film_title": task.film_title if task else "",
            "new_state": new_state,
            "ticket_url": ticket_url,
        },
    })
    await ws_manager.broadcast({
        "type": "task_update",
        "data": {
            "task_id": task_id,
            "status": "pending",
            "message": "Ticket available! Grab scheduled.",
            "task": task.model_dump() if task else None,
        },
    })


# --- Lifespan ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Berlinale Ticket Buyer...")
    scheduler.set_storage(storage)
    scheduler.set_on_task_update(on_task_update)
    scheduler.start_scheduler()
    scheduler.reschedule_pending_tasks(storage)
    ticket_monitor.start(storage, on_monitor_change)
    logger.info("Server ready at http://%s:%s", Config.SERVER_HOST, Config.SERVER_PORT)
    yield
    # Shutdown
    logger.info("Shutting down...")
    ticket_monitor.stop()
    scheduler.shutdown_scheduler()
    from app.grabber import browser_manager
    await browser_manager.close()
    from app.api_grabber import api_grabber
    await api_grabber.close()
    await berlinale_api.close()
    logger.info("Shutdown complete")


app = FastAPI(title="Berlinale Ticket Buyer", lifespan=lifespan)

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")


# --- API Routes ---

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/api/programme")
async def get_programme():
    """Get full programme grouped by day with ticket status."""
    days = await berlinale_api.get_day_programmes()
    return {"days": [d.model_dump() for d in days]}


@app.get("/api/programme/{day}")
async def get_programme_day(day: str):
    """Get programme for a specific day (YYYY-MM-DD)."""
    prog = await berlinale_api.get_day_programme(day)
    if prog:
        return prog.model_dump()
    return {"date": day, "weekday": "", "sections": []}


@app.get("/api/today-on-sale")
async def get_today_on_sale():
    """Get films that go on sale today."""
    films = await berlinale_api.fetch_today_on_sale()
    ticket_map = await berlinale_api.fetch_ticket_status()
    films = berlinale_api._merge_ticket_status(films, ticket_map)
    return {"films": [f.model_dump() for f in films]}


@app.get("/api/ticket-status")
async def get_ticket_status():
    """Get current ticket status for all screenings."""
    ticket_map = await berlinale_api.fetch_ticket_status()
    return {"tickets": {k: v.model_dump() for k, v in ticket_map.items()}}


@app.get("/api/tasks")
async def get_tasks():
    """Get all grab tasks."""
    tasks = storage.get_all_tasks()
    return {"tasks": [t.model_dump() for t in tasks]}


@app.post("/api/tasks")
async def create_task(req: TaskCreate):
    """Create a new grab task."""
    now = datetime.now(ZoneInfo(Config.TIMEZONE)).isoformat()
    task = GrabTask(
        film_id=req.film_id,
        film_title=req.film_title,
        ext_id_screening=req.ext_id_screening,
        venue=req.venue,
        screening_time=req.screening_time,
        sale_time=req.sale_time,
        eventim_url=req.eventim_url,
        mode=req.mode,
        ticket_count=req.ticket_count,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    task = storage.add_task(task)

    # Schedule the grab or set to watching mode
    if not task.eventim_url:
        # No URL available - set to watching mode
        storage.update_task(task.id, status="watching")
        task = storage.get_task(task.id)
        ticket_monitor.add_watch(task)
        logger.info("Task %s set to watching mode (no URL)", task.id)
        scheduled = False
    else:
        # Schedule the grab
        scheduled = scheduler.schedule_grab(task)
        if scheduled:
            logger.info("Task %s created and scheduled", task.id)
        else:
            logger.warning("Task %s created but could not be scheduled", task.id)

    # Notify connected clients
    await ws_manager.broadcast({
        "type": "task_update",
        "data": {"task_id": task.id, "status": "pending", "message": "Task created", "task": task.model_dump()},
    })

    return {"task": task.model_dump(), "scheduled": scheduled}


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    """Cancel and delete a grab task."""
    ticket_monitor.remove_watch(task_id)
    scheduler.cancel_grab(task_id)
    storage.update_task(task_id, status="cancelled")
    deleted = storage.delete_task(task_id)

    await ws_manager.broadcast({
        "type": "task_update",
        "data": {"task_id": task_id, "status": "cancelled", "message": "Task cancelled"},
    })

    return {"deleted": deleted}


@app.get("/api/monitor/status")
async def monitor_status():
    """Get monitoring status."""
    watches = ticket_monitor.get_watches()
    return {
        "watching_count": len(watches),
        "watches": [{"task_id": t.id, "film_title": t.film_title, "ext_id_screening": t.ext_id_screening} for t in watches],
        "running": ticket_monitor._poll_task is not None and not ticket_monitor._poll_task.done() if ticket_monitor._poll_task else False,
    }


@app.post("/api/tasks/{task_id}/run")
async def run_task_now(task_id: str):
    """Immediately run a grab task (for testing)."""
    task = storage.get_task(task_id)
    if not task:
        return {"error": "Task not found"}

    # Run in background
    if task.mode == "browser":
        asyncio.create_task(scheduler._run_browser_grab(task))
    else:
        asyncio.create_task(scheduler._run_api_grab(task))

    return {"message": f"Task {task_id} triggered"}


@app.post("/api/browser/login")
async def browser_login():
    """Open Eventim login page in the browser for manual login."""
    from app.grabber import browser_manager
    success = await browser_manager.open_login_page()
    return {"success": success, "message": "Login page opened" if success else "Failed to open login page"}


@app.get("/api/browser/status")
async def browser_status():
    """Check browser session status."""
    from app.grabber import browser_manager
    if not browser_manager.is_initialized:
        return {"initialized": False, "logged_in": False, "message": "Browser not started"}
    status = await browser_manager.check_session()
    return {"initialized": True, **status}


# --- WebSocket ---

@app.websocket("/ws/status")
async def websocket_status(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            # Keep connection alive; client can also send commands
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
                elif msg.get("type") == "refresh_tickets":
                    # Client requests ticket status refresh
                    ticket_map = await berlinale_api.fetch_ticket_status()
                    await ws.send_text(json.dumps({
                        "type": "ticket_status",
                        "data": {k: v.model_dump() for k, v in ticket_map.items()},
                    }, ensure_ascii=False))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
    except Exception:
        ws_manager.disconnect(ws)


# --- Entry point ---

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=Config.SERVER_HOST,
        port=Config.SERVER_PORT,
        reload=False,
        log_level="info",
    )
