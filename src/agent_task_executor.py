from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.agent_task_runner import AgentTaskRunConfig, AgentTaskStore, start_background_custom_city_task


@dataclass(frozen=True, slots=True)
class AgentTaskSubmission:
    task_id: str
    mode: str
    started: bool
    message: str


@dataclass(frozen=True, slots=True)
class AgentTaskExecutorCapabilities:
    mode: str
    supports_external_worker: bool
    supports_cross_process_recovery: bool
    auto_reruns_running_tasks: bool
    notes: str


class AgentTaskExecutor(Protocol):
    def submit_custom_city_task(
        self,
        store: AgentTaskStore,
        task_id: str,
        config: AgentTaskRunConfig,
    ) -> AgentTaskSubmission: ...


class InProcessAgentTaskExecutor:
    mode = "thread"

    def submit_custom_city_task(
        self,
        store: AgentTaskStore,
        task_id: str,
        config: AgentTaskRunConfig,
    ) -> AgentTaskSubmission:
        thread = start_background_custom_city_task(store, task_id, config)
        return AgentTaskSubmission(
            task_id=task_id,
            mode=self.mode,
            started=thread.is_alive(),
            message="Submitted to in-process background thread.",
        )


class NoOpAgentTaskExecutor:
    mode = "worker"

    def submit_custom_city_task(
        self,
        store: AgentTaskStore,
        task_id: str,
        config: AgentTaskRunConfig,
    ) -> AgentTaskSubmission:
        del config
        task = store.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        return AgentTaskSubmission(
            task_id=task_id,
            mode=self.mode,
            started=False,
            message="Task queued. A worker process will claim and execute it.",
        )


def agent_task_executor_from_config(mode: str | None = None) -> AgentTaskExecutor:
    normalized = (mode or "thread").strip().casefold()
    if normalized in {"", "thread", "inprocess", "in-process", "local"}:
        return InProcessAgentTaskExecutor()
    if normalized in {"worker", "postgres-worker", "postgres_queue", "postgres-queue"}:
        return NoOpAgentTaskExecutor()
    return InProcessAgentTaskExecutor()


def describe_executor_capabilities(mode: str | None = None) -> AgentTaskExecutorCapabilities:
    executor = agent_task_executor_from_config(mode)
    if getattr(executor, "mode", "thread") == "worker":
        return AgentTaskExecutorCapabilities(
            mode="worker",
            supports_external_worker=True,
            supports_cross_process_recovery=True,
            auto_reruns_running_tasks=False,
            notes=(
                "Worker mode queues tasks in the shared task store. "
                "A separate worker process claims PENDING tasks and executes them. "
                "Persisted RUNNING tasks are not automatically rerun; the watchdog should mark stale tasks as TIMEOUT."
            ),
        )
    return AgentTaskExecutorCapabilities(
        mode=getattr(executor, "mode", "thread"),
        supports_external_worker=False,
        supports_cross_process_recovery=False,
        auto_reruns_running_tasks=False,
        notes=(
            "The thread executor runs work inside the current Streamlit process. "
            "Persisted RUNNING tasks are not automatically rerun after process restart; "
            "the watchdog should mark stale tasks as TIMEOUT."
        ),
    )
