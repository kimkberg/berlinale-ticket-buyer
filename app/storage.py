import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from app.config import Config
from app.models import GrabTask


class TaskStorage:
    def __init__(self, file_path: str = Config.TASKS_FILE):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.tasks: list[GrabTask] = self._load()

    def _load(self) -> list[GrabTask]:
        if not self.file_path.exists():
            return []
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
            return [GrabTask(**item) for item in data]
        except (json.JSONDecodeError, ValueError):
            return []

    def _save(self, tasks: list[GrabTask]) -> None:
        self.file_path.write_text(
            json.dumps([t.model_dump() for t in tasks], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def add_task(self, task: GrabTask) -> GrabTask:
        self.tasks.append(task)
        self._save(self.tasks)
        return task

    def get_task(self, task_id: str) -> Optional[GrabTask]:
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def get_all_tasks(self) -> list[GrabTask]:
        return list(self.tasks)

    def update_task(self, task_id: str, **kwargs) -> Optional[GrabTask]:
        kwargs["updated_at"] = datetime.now(ZoneInfo(Config.TIMEZONE)).isoformat()
        for i, task in enumerate(self.tasks):
            if task.id == task_id:
                updated = task.model_copy(update=kwargs)
                self.tasks[i] = updated
                self._save(self.tasks)
                return updated
        return None

    def delete_task(self, task_id: str) -> bool:
        for i, task in enumerate(self.tasks):
            if task.id == task_id:
                self.tasks.pop(i)
                self._save(self.tasks)
                return True
        return False
