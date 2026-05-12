from __future__ import annotations

from src.agent_task_store import AgentTaskStatus, InMemoryAgentTaskStore, PostgresAgentTaskStore, task_store_from_config


def test_in_memory_task_store_tracks_status_and_logs() -> None:
    store = InMemoryAgentTaskStore()

    task = store.create_task(
        kind="custom_city_collection",
        request_payload={"city_query": "Tokyo", "country_code": "JP"},
    )
    store.update_task(
        task.task_id,
        status=AgentTaskStatus.RUNNING,
        phase="RESOLVING",
        progress=0.25,
        message="Resolving city coordinates",
    )
    store.append_log(task.task_id, level="info", phase="RESOLVING", message="Resolved Tokyo")

    updated = store.get_task(task.task_id)
    logs = store.list_logs(task.task_id)

    assert updated is not None
    assert updated.status == AgentTaskStatus.RUNNING
    assert updated.phase == "RESOLVING"
    assert updated.progress == 0.25
    assert updated.message == "Resolving city coordinates"
    assert updated.request_payload == {"city_query": "Tokyo", "country_code": "JP"}
    assert len(logs) == 1
    assert logs[0].message == "Resolved Tokyo"


def test_terminal_task_status_cannot_be_overwritten_by_late_runner_update() -> None:
    store = InMemoryAgentTaskStore()
    task = store.create_task(
        kind="custom_city_collection",
        request_payload={"city_query": "Tokyo", "country_code": "JP"},
    )
    store.update_task(
        task.task_id,
        status=AgentTaskStatus.TIMEOUT,
        phase="TIMEOUT",
        progress=1.0,
        message="Timed out",
        error="Timed out",
    )

    updated = store.update_task(
        task.task_id,
        status=AgentTaskStatus.SAVED,
        phase="SAVED",
        progress=1.0,
        message="Late success",
        output_path="data/processed/agent_runs/late.parquet",
    )

    assert updated.status == AgentTaskStatus.TIMEOUT
    assert updated.phase == "TIMEOUT"
    assert updated.message == "Timed out"
    assert updated.output_path is None


def test_in_memory_task_store_claims_only_pending_custom_city_tasks() -> None:
    store = InMemoryAgentTaskStore()
    ignored = store.create_task(kind="other_kind", request_payload={"city_query": "Kyoto"})
    pending = store.create_task(kind="custom_city_collection", request_payload={"city_query": "Tokyo"})

    claimed = store.claim_next_pending_task()
    second_claim = store.claim_next_pending_task()

    assert claimed is not None
    assert claimed.task_id == pending.task_id
    assert claimed.status == AgentTaskStatus.RUNNING
    assert claimed.started_at is not None
    assert store.get_task(pending.task_id).status == AgentTaskStatus.RUNNING
    assert store.get_task(ignored.task_id).status == AgentTaskStatus.PENDING
    assert second_claim is None


def test_in_memory_task_store_updates_running_task_heartbeat() -> None:
    store = InMemoryAgentTaskStore()
    task = store.create_task(kind="custom_city_collection", request_payload={"city_query": "Tokyo"})
    claimed = store.claim_next_pending_task()
    assert claimed is not None
    before = claimed.updated_at

    store.update_heartbeat(task.task_id)

    after = store.get_task(task.task_id)
    assert after is not None
    assert after.updated_at >= before


def test_task_store_from_config_uses_memory_when_database_url_missing() -> None:
    store = task_store_from_config(database_url=None)

    assert isinstance(store, InMemoryAgentTaskStore)


def test_task_store_from_config_uses_postgres_when_database_url_exists() -> None:
    store = task_store_from_config(database_url="postgresql://example")

    assert isinstance(store, PostgresAgentTaskStore)
    assert store.database_url == "postgresql://example"
