from __future__ import annotations

import streamlit as st

from src.agent_task_store import AgentTaskStatus, InMemoryAgentTaskStore
from src.agent_task_ui import sync_task_result_to_session, task_confirmation_is_visible
from src.collection_agent import CustomCityValidationResult
from src.ui import DATASET_OVERRIDE_KEY, PENDING_DATASET_CHOICE_KEY


def _clear_session_state() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def test_terminal_task_result_syncs_once() -> None:
    _clear_session_state()
    store = InMemoryAgentTaskStore()
    task = store.create_task(kind="custom_city_collection", request_payload={"city_query": "Tokyo"})
    saved = store.update_task(
        task.task_id,
        status=AgentTaskStatus.SAVED,
        phase="SAVED",
        progress=1.0,
        message="Saved Tokyo dataset.",
        result_payload={
            "plan": {"city_label": "Tokyo, Japan"},
            "row_count": 1,
            "summary_text": "Saved Tokyo dataset.",
            "summary_mode": "deterministic",
            "runtime_warnings": [],
            "coverage_rows": [{"pollutant": "pm25", "non_null_ratio": 1.0}],
            "started_at": "2024-01-01 00:00:00",
            "ended_at": "2024-01-01 00:00:00",
        },
        output_path="data/processed/agent_runs/tokyo_2024_2026_aq.parquet",
    )

    assert sync_task_result_to_session(saved, synced_task_result_key="synced_task") is True
    st.session_state["aq_agent_last_result"]["summary_text"] = "Do not overwrite"

    assert sync_task_result_to_session(saved, synced_task_result_key="synced_task") is False
    assert st.session_state["aq_agent_plan"]["city_label"] == "Tokyo, Japan"
    assert st.session_state["aq_agent_last_result"]["summary_text"] == "Do not overwrite"
    assert st.session_state[DATASET_OVERRIDE_KEY] == "data/processed/agent_runs/tokyo_2024_2026_aq.parquet"
    assert st.session_state[PENDING_DATASET_CHOICE_KEY] == "data/processed/agent_runs/tokyo_2024_2026_aq.parquet"


def test_confirmation_visibility_requires_matching_inputs() -> None:
    validation = CustomCityValidationResult(
        input_country="Japen",
        input_city="Tokio",
        status="needs_confirmation",
        corrected_country="Japan",
        corrected_city="Tokyo",
        country_code="JP",
        matching_countries=["Japan"],
        message="Did you mean Tokyo, Japan?",
    )
    store = InMemoryAgentTaskStore()
    task = store.create_task(kind="custom_city_collection", request_payload={"city_query": "Tokio"})
    pending = store.update_task(
        task.task_id,
        status=AgentTaskStatus.PENDING,
        phase="AWAITING_CONFIRMATION",
        progress=0.12,
        message=validation.message,
        result_payload={"validation": validation.to_dict(), "action": "plan"},
    )

    assert task_confirmation_is_visible(pending, input_country="Japen", input_city="Tokio")
    assert not task_confirmation_is_visible(pending, input_country="Japan", input_city="Tokyo")

    running = store.update_task(task.task_id, status=AgentTaskStatus.RUNNING, phase="RESOLVING")
    assert not task_confirmation_is_visible(running, input_country="Japen", input_city="Tokio")
