from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import streamlit as st

from src.agent_task_store import AgentTask, AgentTaskStatus
from src.agent_task_watchdog import AgentTaskWatchdogConfig, mark_timed_out_if_needed
from src.collection_agent import custom_city_validation_from_dict
from src.i18n import t
from src.ui import DATASET_OVERRIDE_KEY, PENDING_DATASET_CHOICE_KEY

TERMINAL_TASK_STATUSES = {
    AgentTaskStatus.PLANNED,
    AgentTaskStatus.SAVED,
    AgentTaskStatus.FAILED,
    AgentTaskStatus.TIMEOUT,
}


@dataclass(frozen=True, slots=True)
class AgentTaskUiContext:
    language: str
    current_task_key: str
    synced_task_result_key: str
    custom_validation_key: str
    custom_confirmed_key: str
    store_factory: Callable[[], object]
    custom_city_inputs: Callable[[], tuple[str, str]]
    clear_custom_city_validation: Callable[[], None]
    start_custom_task: Callable[[str], tuple[object, str]]
    submit_custom_city_task: Callable[[object, str], object]
    watchdog_config: AgentTaskWatchdogConfig


def format_task_timestamp(value) -> str:
    if value is None:
        return "-"
    return str(value).replace("+00:00", " UTC")


def task_result_signature(task: AgentTask) -> tuple[str, str, str]:
    return task.task_id, task.status.value, task.output_path or ""


def sync_task_result_to_session(task: AgentTask, *, synced_task_result_key: str) -> bool:
    if task.status not in {AgentTaskStatus.PLANNED, AgentTaskStatus.SAVED} or not task.result_payload:
        return False

    signature = task_result_signature(task)
    if st.session_state.get(synced_task_result_key) == signature:
        return False

    if task.status == AgentTaskStatus.PLANNED and task.result_payload:
        st.session_state["aq_agent_plan"] = dict(task.result_payload)
    if task.status == AgentTaskStatus.SAVED and task.result_payload:
        plan = task.result_payload.get("plan")
        if isinstance(plan, dict):
            st.session_state["aq_agent_plan"] = dict(plan)
        if task.output_path:
            st.session_state[DATASET_OVERRIDE_KEY] = task.output_path
            st.session_state[PENDING_DATASET_CHOICE_KEY] = task.output_path
        st.session_state["aq_agent_last_result"] = {
            "output_path": task.output_path or "",
            "summary_text": str(task.result_payload.get("summary_text") or task.message),
            "summary_mode": str(task.result_payload.get("summary_mode") or "deterministic"),
            "runtime_warnings": list(task.result_payload.get("runtime_warnings") or []),
            "coverage_rows": list(task.result_payload.get("coverage_rows") or []),
            "row_count": int(task.result_payload.get("row_count") or 0),
            "started_at": str(task.result_payload.get("started_at") or ""),
            "ended_at": str(task.result_payload.get("ended_at") or ""),
        }
    st.session_state[synced_task_result_key] = signature
    return True


def task_confirmation_is_visible(task: AgentTask, *, input_country: str, input_city: str) -> bool:
    if task.status != AgentTaskStatus.PENDING or task.phase != "AWAITING_CONFIRMATION":
        return False
    validation_data = task.result_payload.get("validation") if isinstance(task.result_payload, dict) else None
    if not isinstance(validation_data, dict):
        return False
    validation = custom_city_validation_from_dict(validation_data)
    return validation.input_country.casefold() == input_country.casefold() and validation.input_city.casefold() == input_city.casefold()


def render_task_confirmation_controls(task: AgentTask, context: AgentTaskUiContext) -> None:
    country, city = context.custom_city_inputs()
    if not task_confirmation_is_visible(task, input_country=country, input_city=city):
        return

    validation_data = task.result_payload.get("validation") if isinstance(task.result_payload, dict) else None
    validation = custom_city_validation_from_dict(validation_data)
    city_label = validation.corrected_city or validation.input_city
    country_label = validation.corrected_country or validation.input_country
    if validation.matching_countries:
        st.info(
            t(
                "agent.custom_city_matching_countries",
                context.language,
                countries=", ".join(validation.matching_countries),
            )
        )
    confirm_left, confirm_right = st.columns((1, 1))
    if confirm_left.button(t("agent.custom_city_confirm_yes", context.language), use_container_width=True, key=f"{task.task_id}_confirm_yes"):
        if not validation.country_code:
            st.error(t("agent.custom_city_country_code_missing", context.language))
            return
        st.session_state[context.custom_validation_key] = validation.to_dict()
        st.session_state[context.custom_confirmed_key] = True
        action = str(task.result_payload.get("action") or task.request_payload.get("action") or "plan")
        next_store, next_task_id = context.start_custom_task(action)
        context.submit_custom_city_task(next_store, next_task_id)
        st.success(t("agent.custom_city_confirmed", context.language, city=city_label, country=country_label))
        st.rerun()
    if confirm_right.button(t("agent.custom_city_confirm_no", context.language), use_container_width=True, key=f"{task.task_id}_confirm_no"):
        context.clear_custom_city_validation()
        st.session_state.pop(context.current_task_key, None)
        st.rerun()


def render_task_status_panel_body(context: AgentTaskUiContext) -> None:
    task_id = st.session_state.get(context.current_task_key)
    if not task_id:
        return

    try:
        store = context.store_factory()
        task = store.get_task(str(task_id))
        logs = store.list_logs(str(task_id), limit=20)
        if task is not None:
            task = mark_timed_out_if_needed(store, task, logs, context.watchdog_config)
            logs = store.list_logs(str(task_id), limit=20)
    except Exception as exc:  # noqa: BLE001
        st.warning(t("agent.task_status_unavailable", context.language, error=exc))
        return

    if task is None:
        st.info(t("agent.task_status_missing", context.language, task_id=task_id))
        return

    synced_task_result = sync_task_result_to_session(task, synced_task_result_key=context.synced_task_result_key)

    st.subheader(t("agent.task_status_section", context.language))
    st.caption(
        t(
            "agent.task_status_caption",
            context.language,
            task_id=task.task_id,
            updated_at=format_task_timestamp(task.updated_at),
        )
    )

    status_col, phase_col, progress_col = st.columns(3)
    status_col.metric(t("agent.task_status_label", context.language), task.status.value)
    phase_col.metric(t("agent.task_phase_label", context.language), task.phase)
    progress_col.metric(t("agent.task_progress_label", context.language), f"{task.progress:.0%}")
    st.caption(
        t(
            "agent.task_state_line",
            context.language,
            status=task.status.value,
            phase=task.phase,
            progress=f"{task.progress:.0%}",
        )
    )
    st.progress(task.progress)

    if task.message:
        st.write(task.message)
    if task.output_path:
        st.success(t("agent.task_output_path", context.language, path=task.output_path))
    if task.error:
        st.error(t("agent.task_error", context.language, error=task.error))

    if logs:
        logs_expanded = task.status not in TERMINAL_TASK_STATUSES
        with st.expander(t("agent.task_log_section", context.language), expanded=logs_expanded):
            for log in logs[-10:]:
                st.caption(
                    t(
                        "agent.task_log_item",
                        context.language,
                        created_at=format_task_timestamp(log.created_at),
                        level=log.level,
                        phase=log.phase,
                        message=log.message,
                    )
                )

    if synced_task_result:
        st.rerun(scope="app")


def render_task_status_panel_once(context: AgentTaskUiContext, container=None) -> None:
    if container is None:
        render_task_status_panel_body(context)
        return
    with container.container():
        render_task_status_panel_body(context)


def render_current_task_status_panel(context: AgentTaskUiContext, container=None) -> None:
    def _render() -> None:
        render_task_status_panel_once(context, container)

    fragment = getattr(st, "fragment", None)
    if fragment is None:
        _render()
        return

    @fragment(run_every="2s")
    def _task_status_fragment() -> None:
        _render()

    _task_status_fragment()


def render_current_task_confirmation_controls(context: AgentTaskUiContext) -> None:
    task_id = st.session_state.get(context.current_task_key)
    if not task_id:
        return
    try:
        store = context.store_factory()
        task = store.get_task(str(task_id))
    except Exception:  # noqa: BLE001
        return
    if task is not None:
        render_task_confirmation_controls(task, context)


def render_current_task_confirmation_panel(context: AgentTaskUiContext) -> None:
    fragment = getattr(st, "fragment", None)
    if fragment is None:
        render_current_task_confirmation_controls(context)
        return

    @fragment(run_every="2s")
    def _task_confirmation_fragment() -> None:
        render_current_task_confirmation_controls(context)

    _task_confirmation_fragment()
