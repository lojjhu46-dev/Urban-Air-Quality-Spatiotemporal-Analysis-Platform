from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from threading import Lock
from typing import Any
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
            if status is not None:
                task.status = AgentTaskStatus(status)
                if task.status == AgentTaskStatus.RUNNING and task.started_at is None:
                    task.started_at = _utc_now()
                if task.status in {
                    AgentTaskStatus.PLANNED,
                    AgentTaskStatus.SAVED,
                    AgentTaskStatus.FAILED,
                    AgentTaskStatus.TIMEOUT,
                }:
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


def _task_from_row(row: dict[str, Any]) -> AgentTask:
    return AgentTask(
        task_id=str(row["task_id"]),
        kind=str(row["kind"]),
        status=AgentTaskStatus(str(row["status"])),
        phase=str(row["phase"]),
        progress=float(row["progress"]),
        message=str(row["message"] or ""),
        request_payload=dict(row["request_payload"] or {}),
        result_payload=dict(row["result_payload"] or {}),
        error=row.get("error"),
        output_path=row.get("output_path"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
    )


def _log_from_row(row: dict[str, Any]) -> AgentTaskLog:
    return AgentTaskLog(
        task_id=str(row["task_id"]),
        level=str(row["level"]),
        phase=str(row["phase"]),
        message=str(row["message"]),
        created_at=row["created_at"],
    )


class PostgresAgentTaskStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        try:
            import psycopg  # type: ignore[import-not-found]
            from psycopg.rows import dict_row  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Install `psycopg[binary]` to use Supabase Postgres task storage.") from exc
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def _jsonb(self, payload: dict[str, object]):
        try:
            from psycopg.types.json import Jsonb  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Install `psycopg[binary]` to use Supabase Postgres task storage.") from exc
        return Jsonb(payload)

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(AGENT_TASK_SCHEMA_SQL)

    def create_task(self, *, kind: str, request_payload: dict[str, object]) -> AgentTask:
        now = _utc_now()
        task_id = str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into agent_tasks (
                        task_id, kind, status, phase, progress, message,
                        request_payload, result_payload, created_at, updated_at
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    returning *
                    """,
                    (
                        task_id,
                        kind,
                        AgentTaskStatus.PENDING.value,
                        "PENDING",
                        0.0,
                        "Task queued",
                        self._jsonb(dict(request_payload)),
                        self._jsonb({}),
                        now,
                        now,
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Postgres did not return the created agent task.")
        return _task_from_row(dict(row))

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
        current = self.get_task(task_id)
        if current is None:
            raise KeyError(task_id)

        next_status = AgentTaskStatus(status) if status is not None else current.status
        started_at = current.started_at
        finished_at = current.finished_at
        now = _utc_now()
        if next_status == AgentTaskStatus.RUNNING and started_at is None:
            started_at = now
        if next_status in {
            AgentTaskStatus.PLANNED,
            AgentTaskStatus.SAVED,
            AgentTaskStatus.FAILED,
            AgentTaskStatus.TIMEOUT,
        }:
            finished_at = now

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    update agent_tasks
                    set status = %s,
                        phase = %s,
                        progress = %s,
                        message = %s,
                        result_payload = %s,
                        error = %s,
                        output_path = %s,
                        updated_at = %s,
                        started_at = %s,
                        finished_at = %s
                    where task_id = %s
                    returning *
                    """,
                    (
                        next_status.value,
                        phase if phase is not None else current.phase,
                        max(0.0, min(float(progress), 1.0)) if progress is not None else current.progress,
                        message if message is not None else current.message,
                        self._jsonb(result_payload if result_payload is not None else current.result_payload),
                        error if error is not None else current.error,
                        output_path if output_path is not None else current.output_path,
                        now,
                        started_at,
                        finished_at,
                        task_id,
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise KeyError(task_id)
        return _task_from_row(dict(row))

    def append_log(self, task_id: str, *, level: str, phase: str, message: str) -> AgentTaskLog:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into agent_task_logs (task_id, level, phase, message, created_at)
                    values (%s, %s, %s, %s, %s)
                    returning task_id, level, phase, message, created_at
                    """,
                    (task_id, level, phase, message, _utc_now()),
                )
                row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Postgres did not return the created agent task log.")
        return _log_from_row(dict(row))

    def get_task(self, task_id: str) -> AgentTask | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select * from agent_tasks where task_id = %s", (task_id,))
                row = cursor.fetchone()
        return _task_from_row(dict(row)) if row is not None else None

    def list_logs(self, task_id: str, *, limit: int = 100) -> list[AgentTaskLog]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select task_id, level, phase, message, created_at
                    from agent_task_logs
                    where task_id = %s
                    order by created_at desc
                    limit %s
                    """,
                    (task_id, limit),
                )
                rows = cursor.fetchall()
        return [_log_from_row(dict(row)) for row in reversed(rows)]


def task_store_from_config(database_url: str | None) -> InMemoryAgentTaskStore | PostgresAgentTaskStore:
    if database_url and database_url.strip():
        return PostgresAgentTaskStore(database_url.strip())
    return InMemoryAgentTaskStore()


AGENT_TASK_SCHEMA_SQL = """
create table if not exists agent_tasks (
    task_id text primary key,
    kind text not null,
    status text not null,
    phase text not null,
    progress double precision not null default 0,
    message text not null default '',
    request_payload jsonb not null default '{}'::jsonb,
    result_payload jsonb not null default '{}'::jsonb,
    error text,
    output_path text,
    created_at timestamptz not null,
    updated_at timestamptz not null,
    started_at timestamptz,
    finished_at timestamptz
);

create table if not exists agent_task_logs (
    id bigserial primary key,
    task_id text not null references agent_tasks(task_id) on delete cascade,
    level text not null,
    phase text not null,
    message text not null,
    created_at timestamptz not null
);

create index if not exists idx_agent_task_logs_task_created
    on agent_task_logs(task_id, created_at);
"""
