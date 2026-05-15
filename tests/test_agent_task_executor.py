from __future__ import annotations

from threading import Event

import src.agent_task_runner as agent_task_runner
from src.agent_task_executor import (
    InProcessAgentTaskExecutor,
    agent_task_executor_from_config,
    describe_executor_capabilities,
)
from src.agent_task_runner import AgentTaskRunConfig
from src.agent_task_store import AgentTaskStatus, InMemoryAgentTaskStore


def _custom_payload(action: str = "plan") -> dict[str, object]:
    return {
        "kind": "custom_city_collection",
        "action": action,
        "input_country": "Japan",
        "input_city": "Tokyo",
        "city_query": "Tokyo",
        "country_code": "",
        "start_year": 2024,
        "end_year": 2026,
        "pollutants": ["pm25"],
        "include_weather": False,
        "weather_fields": [],
    }


def test_agent_task_executor_factory_defaults_to_in_process() -> None:
    assert isinstance(agent_task_executor_from_config(), InProcessAgentTaskExecutor)
    assert isinstance(agent_task_executor_from_config("unknown-mode"), InProcessAgentTaskExecutor)


def test_thread_executor_capabilities_do_not_claim_recovery() -> None:
    capabilities = describe_executor_capabilities("unknown-mode")

    assert capabilities.mode == "thread"
    assert not capabilities.auto_reruns_running_tasks
    assert "not automatically rerun" in capabilities.notes


def test_in_process_executor_submits_background_task(monkeypatch) -> None:
    store = InMemoryAgentTaskStore()
    task = store.create_task(kind="custom_city_collection", request_payload=_custom_payload())
    started = Event()
    release = Event()

    def fake_runner(store_arg, task_id_arg: str, config_arg) -> None:  # noqa: ANN001
        assert store_arg is store
        assert task_id_arg == task.task_id
        assert config_arg.api_key == "sk-test"
        started.set()
        release.wait(timeout=2)
        store.update_task(task.task_id, status=AgentTaskStatus.PLANNED, phase="PLANNING", progress=1.0, message="done")

    monkeypatch.setattr(agent_task_runner, "run_custom_city_task", fake_runner)

    submission = InProcessAgentTaskExecutor().submit_custom_city_task(
        store,
        task.task_id,
        AgentTaskRunConfig(api_key="sk-test"),
    )

    assert submission.task_id == task.task_id
    assert submission.mode == "thread"
    assert submission.started
    assert started.wait(timeout=1)
    release.set()


def test_in_process_executor_reuses_active_task_thread(monkeypatch) -> None:
    store = InMemoryAgentTaskStore()
    task = store.create_task(kind="custom_city_collection", request_payload=_custom_payload())
    started = Event()
    release = Event()
    calls: list[str] = []

    def fake_runner(store_arg, task_id_arg: str, config_arg) -> None:  # noqa: ANN001
        del store_arg, config_arg
        calls.append(task_id_arg)
        started.set()
        release.wait(timeout=2)

    monkeypatch.setattr(agent_task_runner, "run_custom_city_task", fake_runner)
    executor = InProcessAgentTaskExecutor()
    config = AgentTaskRunConfig(api_key="sk-test")

    first = executor.submit_custom_city_task(store, task.task_id, config)
    assert started.wait(timeout=1)
    second = executor.submit_custom_city_task(store, task.task_id, config)

    assert first.started
    assert second.started
    assert calls == [task.task_id]
    release.set()
