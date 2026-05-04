from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.agent_task_store import AgentTaskStatus, InMemoryAgentTaskStore
from src.agent_task_watchdog import AgentTaskWatchdogConfig, mark_timed_out_if_needed


def test_watchdog_marks_running_task_timeout_after_max_runtime() -> None:
    store = InMemoryAgentTaskStore()
    task = store.create_task(kind="custom_city_collection", request_payload={"city_query": "Tokyo"})
    store.update_task(
        task.task_id,
        status=AgentTaskStatus.RUNNING,
        phase="COLLECTING",
        progress=0.4,
        message="Collecting",
    )
    task = store.get_task(task.task_id)
    assert task is not None

    updated = mark_timed_out_if_needed(
        store,
        task,
        store.list_logs(task.task_id),
        AgentTaskWatchdogConfig(max_runtime_seconds=10, stalled_seconds=999, language="en"),
        now=task.started_at + timedelta(seconds=11),
    )

    assert updated.status == AgentTaskStatus.TIMEOUT
    assert updated.phase == "TIMEOUT"
    assert updated.error == "Task did not finish within 10 seconds."
    assert store.list_logs(task.task_id)[-1].phase == "TIMEOUT"


def test_watchdog_marks_running_task_timeout_when_progress_stalls() -> None:
    store = InMemoryAgentTaskStore()
    created_at = datetime(2026, 5, 4, 1, 0, tzinfo=UTC)
    task = store.create_task(kind="custom_city_collection", request_payload={"city_query": "Tokyo"})
    store.update_task(
        task.task_id,
        status=AgentTaskStatus.RUNNING,
        phase="VALIDATING",
        progress=0.08,
        message="Validating",
    )
    task = store.get_task(task.task_id)
    assert task is not None
    task.started_at = created_at
    task.updated_at = created_at

    updated = mark_timed_out_if_needed(
        store,
        task,
        [],
        AgentTaskWatchdogConfig(max_runtime_seconds=999, stalled_seconds=30, language="en"),
        now=created_at + timedelta(seconds=31),
    )

    assert updated.status == AgentTaskStatus.TIMEOUT
    assert updated.error == "Task had no new progress for 30 seconds and was marked as timed out."


def test_watchdog_ignores_confirmation_tasks() -> None:
    store = InMemoryAgentTaskStore()
    created_at = datetime(2026, 5, 4, 1, 0, tzinfo=UTC)
    task = store.create_task(kind="custom_city_collection", request_payload={"city_query": "Tokyo"})
    store.update_task(
        task.task_id,
        status=AgentTaskStatus.PENDING,
        phase="AWAITING_CONFIRMATION",
        progress=0.12,
        message="Confirm location",
    )
    task = store.get_task(task.task_id)
    assert task is not None
    task.updated_at = created_at

    updated = mark_timed_out_if_needed(
        store,
        task,
        [],
        AgentTaskWatchdogConfig(max_runtime_seconds=10, stalled_seconds=10, language="en"),
        now=created_at + timedelta(hours=1),
    )

    assert updated.status == AgentTaskStatus.PENDING
    assert updated.phase == "AWAITING_CONFIRMATION"
