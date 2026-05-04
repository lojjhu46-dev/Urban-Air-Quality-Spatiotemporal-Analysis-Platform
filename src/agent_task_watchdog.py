from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from src.agent_task_store import AgentTask, AgentTaskLog, AgentTaskStatus, TERMINAL_AGENT_TASK_STATUSES
from src.config import AQ_AGENT_TASK_STALLED_SECONDS, AQ_AGENT_TASK_TIMEOUT_SECONDS
from src.i18n import t


class AgentTaskStore(Protocol):
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
    ): ...

    def append_log(self, task_id: str, *, level: str, phase: str, message: str): ...


@dataclass(frozen=True, slots=True)
class AgentTaskWatchdogConfig:
    max_runtime_seconds: int = AQ_AGENT_TASK_TIMEOUT_SECONDS
    stalled_seconds: int = AQ_AGENT_TASK_STALLED_SECONDS
    language: str = "en"


def mark_timed_out_if_needed(
    store: AgentTaskStore,
    task: AgentTask,
    logs: list[AgentTaskLog],
    config: AgentTaskWatchdogConfig | None = None,
    *,
    now: datetime | None = None,
) -> AgentTask:
    config = config or AgentTaskWatchdogConfig()
    if task.status in TERMINAL_AGENT_TASK_STATUSES or task.phase == "AWAITING_CONFIRMATION":
        return task

    now = _as_aware_utc(now or datetime.now(UTC))
    if task.status == AgentTaskStatus.RUNNING and task.started_at is not None:
        runtime_seconds = (now - _as_aware_utc(task.started_at)).total_seconds()
        if runtime_seconds > config.max_runtime_seconds:
            return _mark_timeout(
                store,
                task,
                t("agent.task_timeout", config.language, seconds=config.max_runtime_seconds),
            )

    latest_activity_at = _latest_activity_at(task, logs)
    idle_seconds = (now - latest_activity_at).total_seconds()
    if task.status in {AgentTaskStatus.PENDING, AgentTaskStatus.RUNNING} and idle_seconds > config.stalled_seconds:
        return _mark_timeout(
            store,
            task,
            t("agent.task_stalled_timeout", config.language, seconds=config.stalled_seconds),
        )

    return task


def _latest_activity_at(task: AgentTask, logs: list[AgentTaskLog]) -> datetime:
    values = [task.updated_at]
    values.extend(log.created_at for log in logs)
    return max(_as_aware_utc(value) for value in values)


def _mark_timeout(store: AgentTaskStore, task: AgentTask, message: str) -> AgentTask:
    updated = store.update_task(
        task.task_id,
        status=AgentTaskStatus.TIMEOUT,
        phase="TIMEOUT",
        progress=1.0,
        message=message,
        error=message,
    )
    if updated.status == AgentTaskStatus.TIMEOUT:
        store.append_log(task.task_id, level="error", phase="TIMEOUT", message=message)
    return updated


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
