import asyncio
import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger("backend.services.scheduler_service")
TASK_STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "scheduled_tasks.json"
TASK_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class ScheduledTask:
    task_id: str
    callback_name: str
    payload: Dict[str, Any]
    run_at: str
    retries: int = 0
    max_retries: int = 3
    interval_seconds: int = 60
    status: str = "pending"
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SchedulerService:
    def __init__(self) -> None:
        self.callbacks: Dict[str, Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = {}
        self.tasks: Dict[str, ScheduledTask] = {}
        self.lock = asyncio.Lock()
        self.loop_task: Optional[asyncio.Task] = None
        self._load_tasks_from_disk()

    def register_callback(self, name: str, callback: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]) -> None:
        self.callbacks[name] = callback
        logger.info("Registered scheduler callback: %s", name)

    async def start(self) -> None:
        if self.loop_task is None or self.loop_task.done():
            self.loop_task = asyncio.create_task(self._run_loop())
            logger.info("Scheduler service started")

    async def stop(self) -> None:
        if self.loop_task:
            self.loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.loop_task
            logger.info("Scheduler service stopped")

    async def schedule_task(
        self,
        task_id: str,
        callback_name: str,
        payload: Dict[str, Any],
        run_after: Optional[int] = None,
        run_at: Optional[datetime] = None,
        max_retries: int = 3,
        retry_interval: int = 60,
    ) -> ScheduledTask:
        if callback_name not in self.callbacks:
            raise ValueError(f"Callback {callback_name} is not registered")
        scheduled_time = (datetime.now(timezone.utc) + timedelta(seconds=run_after)) if run_after else run_at
        if scheduled_time is None:
            raise ValueError("Either run_after or run_at must be provided")
        task = ScheduledTask(
            task_id=task_id,
            callback_name=callback_name,
            payload=payload,
            run_at=scheduled_time.isoformat(),
            max_retries=max_retries,
            interval_seconds=retry_interval,
        )
        async with self.lock:
            self.tasks[task_id] = task
            self._persist_tasks_to_disk()
        logger.info("Scheduled task %s for %s", task_id, task.run_at)
        return task

    async def cancel_task(self, task_id: str) -> None:
        async with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = "cancelled"
                self._persist_tasks_to_disk()
                logger.info("Cancelled task %s", task_id)

    async def _run_loop(self) -> None:
        while True:
            now = datetime.now(timezone.utc)
            tasks_to_run = []
            async with self.lock:
                for task in list(self.tasks.values()):
                    if task.status != "pending":
                        continue
                    scheduled_time = datetime.fromisoformat(task.run_at)
                    if scheduled_time <= now:
                        tasks_to_run.append(task)
            for task in tasks_to_run:
                await self._execute_task(task)
            await asyncio.sleep(5)

    async def _execute_task(self, task: ScheduledTask) -> None:
        callback = self.callbacks.get(task.callback_name)
        if not callback:
            logger.error("Missing callback for task %s", task.task_id)
            task.status = "failed"
            task.last_error = "missing callback"
            self._persist_tasks_to_disk()
            return
        try:
            await callback(task.payload)
            task.status = "completed"
            logger.info("Executed scheduled task %s", task.task_id)
        except Exception as exc:
            task.retries += 1
            task.last_error = str(exc)
            if task.retries > task.max_retries:
                task.status = "failed"
                logger.error("Task %s failed after retries: %s", task.task_id, exc)
            else:
                task.run_at = (datetime.now(timezone.utc) + timedelta(seconds=task.interval_seconds)).isoformat()
                logger.warning("Retrying task %s after failure: %s", task.task_id, exc)
        finally:
            async with self.lock:
                self.tasks[task.task_id] = task
                self._persist_tasks_to_disk()

    def list_tasks(self) -> List[Dict[str, Any]]:
        return [task.to_dict() for task in self.tasks.values()]

    def _persist_tasks_to_disk(self) -> None:
        with open(TASK_STORE_PATH, "w", encoding="utf-8") as handle:
            json.dump({task_id: task.to_dict() for task_id, task in self.tasks.items()}, handle, indent=2)

    def _load_tasks_from_disk(self) -> None:
        if TASK_STORE_PATH.exists():
            with open(TASK_STORE_PATH, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
                for task_id, payload in raw.items():
                    self.tasks[task_id] = ScheduledTask(**payload)


# Helper for async cancel context manager
class suppress:
    def __init__(self, *exceptions: Any) -> None:
        self.exceptions = exceptions

    def __enter__(self) -> "suppress":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> bool:
        return exc_type is not None and issubclass(exc_type, self.exceptions)
