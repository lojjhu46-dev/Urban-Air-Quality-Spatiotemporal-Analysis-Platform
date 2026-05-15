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


def agent_task_executor_from_config(mode: str | None = None) -> AgentTaskExecutor:
    del mode
    return InProcessAgentTaskExecutor()


def describe_executor_capabilities(mode: str | None = None) -> AgentTaskExecutorCapabilities:
    executor = agent_task_executor_from_config(mode)
    return AgentTaskExecutorCapabilities(
        mode=getattr(executor, "mode", "thread"),
        auto_reruns_running_tasks=False,
        notes=(
            "The thread executor runs work inside the current Streamlit process. "
            "Persisted RUNNING tasks are not automatically rerun after process restart; "
            "the watchdog should mark stale tasks as TIMEOUT."
        ),
    )
