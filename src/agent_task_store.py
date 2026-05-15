from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from threading import Lock
from uuid import uuid4


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AgentTaskStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PLANNED = "PLANNED"
    SAVED = "SAVED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


TERMINAL_AGENT_TASK_STATUSES = frozenset(
    {
        AgentTaskStatus.PLANNED,
        AgentTaskStatus.SAVED,
        AgentTaskStatus.FAILED,
        AgentTaskStatus.TIMEOUT,
    }
)


@dataclass(slots=True)
class AgentTask:
    task_id: str
    kind: str
    status: AgentTaskStatus
    phase: str
    progress: float
    message: str
    request_payload: dict[str, object]
    result_payload: dict[str, object] = field(default_factory=dict)
    error: str | None = None
    output_path: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(slots=True)
class AgentTaskLog:
    task_id: str
    level: str
    phase: str
    message: str
    created_at: datetime = field(default_factory=_utc_now)


class InMemoryAgentTaskStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._tasks: dict[str, AgentTask] = {}
        self._logs: dict[str, list[AgentTaskLog]] = {}

    def create_task(self, *, kind: str, request_payload: dict[str, object]) -> AgentTask:
        now = _utc_now()
        task = AgentTask(
            task_id=str(uuid4()),
            kind=kind,
            status=AgentTaskStatus.PENDING,
            phase="PENDING",
            progress=0.0,
            message="Task queued",
            request_payload=dict(request_payload),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._tasks[task.task_id] = task
            self._logs[task.task_id] = []
        return task

    def update_task(
        self,
        task_id: str,
        *,
        status: AgentTaskStatus | str | None = None,
        phase: str | None = None,
        progress: float | None = None,
        message: str | None = None,
        result_payload: dict[str, object] | None = None,
        error: str | None = None,
        output_path: str | None = None,
    ) -> AgentTask:
        with self._lock:
            task = self._tasks[task_id]
            next_status = AgentTaskStatus(status) if status is not None else task.status
            if task.status in TERMINAL_AGENT_TASK_STATUSES and next_status != task.status:
                return task
            if status is not None:
                task.status = next_status
                if task.status == AgentTaskStatus.RUNNING and task.started_at is None:
                    task.started_at = _utc_now()
                if task.status in TERMINAL_AGENT_TASK_STATUSES:
                    task.finished_at = _utc_now()
            if phase is not None:
                task.phase = phase
            if progress is not None:
                task.progress = max(0.0, min(float(progress), 1.0))
            if message is not None:
                task.message = message
            if result_payload is not None:
                task.result_payload = dict(result_payload)
            if error is not None:
                task.error = error
            if output_path is not None:
                task.output_path = output_path
            task.updated_at = _utc_now()
            return task

    def append_log(self, task_id: str, *, level: str, phase: str, message: str) -> AgentTaskLog:
        log = AgentTaskLog(task_id=task_id, level=level, phase=phase, message=message)
        with self._lock:
            self._logs.setdefault(task_id, []).append(log)
        return log

    def get_task(self, task_id: str) -> AgentTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_logs(self, task_id: str, *, limit: int = 100) -> list[AgentTaskLog]:
        with self._lock:
            return list(self._logs.get(task_id, []))[-limit:]

def task_store_from_config() -> InMemoryAgentTaskStore:
    return InMemoryAgentTaskStore()
