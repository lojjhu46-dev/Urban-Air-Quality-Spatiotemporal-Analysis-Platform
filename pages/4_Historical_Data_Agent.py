from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

import src.agent_task_executor as agent_task_executor
from src.agent_task_store import AgentTaskStatus, task_store_from_config
from src.agent_task_ui import (
    AgentTaskUiContext,
    render_current_task_confirmation_panel,
    render_current_task_status_panel,
    render_task_status_panel_once,
)
from src.agent_task_runner import AgentTaskRunConfig
from src.agent_task_watchdog import AgentTaskWatchdogConfig
from src.agent_interaction import AgentCityOption, all_city_options
from src.charts import trend_figure
from src.collection_agent import custom_city_validation_from_dict, collection_plan_from_dict
from src.config import AQ_AGENT_DEFAULT_MODEL, AQ_AGENT_POLLUTANTS, AQ_AGENT_TASK_STALLED_SECONDS, AQ_AGENT_TASK_TIMEOUT_SECONDS, DEEPSEEK_BASE_URL
from src.data import load_dataset
from src.i18n import get_language, render_language_selector, t, weather_label
from src.navigation import render_sidebar_navigation
from src.ui import dataset_path_from_env, render_dataframe

language = get_language()
st.set_page_config(page_title=t("agent.page_title", language), layout="wide")

with st.sidebar:
    language = render_language_selector(key="language_selector_agent")
    render_sidebar_navigation(language)

dataset_path_from_env()

st.title(t("agent.title", language))
st.caption(t("agent.caption", language))

CURRENT_YEAR = pd.Timestamp.today().year
DEFAULT_POLLUTANTS = list(AQ_AGENT_POLLUTANTS)
DEFAULT_WEATHER_FIELDS = ["temp", "humidity", "wind_speed"]

YEARS_KEY = "aq_agent_year_range"
POLLUTANTS_KEY = "aq_agent_pollutants"
WEATHER_FIELDS_KEY = "aq_agent_weather_fields"
USE_DEEPSEEK_KEY = "aq_agent_use_deepseek"
CUSTOM_COUNTRY_KEY = "aq_agent_custom_country"
CUSTOM_CITY_NAME_KEY = "aq_agent_custom_city_name"
CUSTOM_VALIDATION_KEY = "aq_agent_custom_city_validation"
CUSTOM_CONFIRMED_KEY = "aq_agent_custom_city_confirmed"
STABLE_CITY_OPTION_KEY = "aq_agent_stable_city_option"
STABLE_CITY_APPLIED_KEY = "aq_agent_stable_city_option_applied"
TASK_STORE_KEY = "aq_agent_task_store"
CURRENT_TASK_KEY = "aq_agent_current_task_id"
SYNCED_TASK_RESULT_KEY = "aq_agent_synced_task_result"
def _safe_secret(key: str) -> str | None:
    try:
        value = st.secrets.get(key)
    except Exception:  # noqa: BLE001
        value = None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_secret_int(key: str, default: int) -> int:
    value = _safe_secret(key)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _agent_task_timeout_seconds() -> int:
    return _safe_secret_int("agent_task_timeout_seconds", AQ_AGENT_TASK_TIMEOUT_SECONDS)


def _agent_task_stalled_seconds() -> int:
    return _safe_secret_int("agent_task_stalled_seconds", AQ_AGENT_TASK_STALLED_SECONDS)


def _task_watchdog_config() -> AgentTaskWatchdogConfig:
    return AgentTaskWatchdogConfig(
        max_runtime_seconds=_agent_task_timeout_seconds(),
        stalled_seconds=_agent_task_stalled_seconds(),
        language=language,
    )


def _planner_api_key() -> str | None:
    enabled = bool(st.session_state.get(USE_DEEPSEEK_KEY, bool(_safe_secret("deepseek_api_key"))))
    if not enabled:
        return None
    return _safe_secret("deepseek_api_key")


def _planner_model() -> str:
    return str(st.session_state.get("aq_agent_model", AQ_AGENT_DEFAULT_MODEL)).strip() or AQ_AGENT_DEFAULT_MODEL


def _planner_base_url() -> str:
    return str(st.session_state.get("aq_agent_base_url", DEEPSEEK_BASE_URL)).strip() or DEEPSEEK_BASE_URL


def _agent_task_executor_mode() -> str | None:
    return _safe_secret("agent_task_executor_mode")


def _agent_task_executor():
    return agent_task_executor.agent_task_executor_from_config(_agent_task_executor_mode())


def _task_store_backend_label() -> str:
    return t("agent.task_store_memory", language)


def _task_store():
    store = st.session_state.get(TASK_STORE_KEY)
    if store is not None:
        return store
    store = task_store_from_config()
    st.session_state[TASK_STORE_KEY] = store
    return store


def _custom_task_payload(action: str) -> dict[str, object]:
    country, city = _custom_city_inputs()
    start_year, end_year = _selected_years()
    pollutants = _selected_pollutants()
    weather_fields = _selected_weather_fields()
    payload = {
        "kind": "custom_city_collection",
        "action": action,
        "input_country": country,
        "input_city": city,
        "city_query": city,
        "country_code": "",
        "start_year": start_year,
        "end_year": end_year,
        "pollutants": pollutants,
        "include_weather": bool(weather_fields),
        "weather_fields": weather_fields,
    }
    validation = _current_custom_validation()
    if validation is not None and st.session_state.get(CUSTOM_CONFIRMED_KEY):
        payload["confirmed_validation"] = validation.to_dict()
    return payload


def _stable_city_options() -> list[AgentCityOption]:
    return all_city_options()


def _format_stable_city_option(option: AgentCityOption) -> str:
    return option.path_label_for_language(language)


def _stable_city_option_labels() -> list[str]:
    return [_format_stable_city_option(option) for option in _stable_city_options()]


def _stable_city_option_by_label(label: str | None) -> AgentCityOption | None:
    if not label:
        return None
    for option in _stable_city_options():
        if _format_stable_city_option(option) == label:
            return option
    return None


def _stable_city_option_identity(option: AgentCityOption) -> tuple[str, str, str | None, str]:
    return option.continent, option.country, option.province, option.city


def _selected_stable_city_option() -> AgentCityOption | None:
    return _stable_city_option_by_label(str(st.session_state.get(STABLE_CITY_OPTION_KEY) or ""))


def _apply_stable_city_option(option: AgentCityOption) -> None:
    st.session_state[CUSTOM_COUNTRY_KEY] = option.display_country(language)
    st.session_state[CUSTOM_CITY_NAME_KEY] = option.display_city(language)
    st.session_state[CUSTOM_VALIDATION_KEY] = {
        "input_country": option.display_country(language),
        "input_city": option.display_city(language),
        "status": "valid",
        "corrected_country": option.country,
        "corrected_city": option.city_query,
        "country_code": option.country_code,
        "matching_countries": [option.country],
        "message": t(
            "agent.stable_city_prefill_message",
            language,
            city=option.display_city(language),
            country=option.display_country(language),
        ),
    }
    st.session_state[CUSTOM_CONFIRMED_KEY] = True


def _start_custom_task(action: str):
    store = _task_store()
    task = store.create_task(kind="custom_city_collection", request_payload=_custom_task_payload(action))
    st.session_state[CURRENT_TASK_KEY] = task.task_id
    return store, task.task_id


def _submit_custom_city_task(store, task_id: str, *, api_key: str | None):
    return _agent_task_executor().submit_custom_city_task(
        store,
        task_id,
        AgentTaskRunConfig(
            api_key=api_key,
            model=_planner_model(),
            base_url=_planner_base_url(),
            language=language,
            timeout_seconds=_agent_task_timeout_seconds(),
        ),
    )


def _task_ui_context() -> AgentTaskUiContext:
    return AgentTaskUiContext(
        language=language,
        current_task_key=CURRENT_TASK_KEY,
        synced_task_result_key=SYNCED_TASK_RESULT_KEY,
        custom_validation_key=CUSTOM_VALIDATION_KEY,
        custom_confirmed_key=CUSTOM_CONFIRMED_KEY,
        store_factory=_task_store,
        custom_city_inputs=_custom_city_inputs,
        clear_custom_city_validation=_clear_custom_city_validation,
        start_custom_task=_start_custom_task,
        submit_custom_city_task=lambda store, task_id: _submit_custom_city_task(store, task_id, api_key=_planner_api_key()),
        watchdog_config=_task_watchdog_config(),
    )


def _custom_city_inputs() -> tuple[str, str]:
    return (
        str(st.session_state.get(CUSTOM_COUNTRY_KEY) or "").strip(),
        str(st.session_state.get(CUSTOM_CITY_NAME_KEY) or "").strip(),
    )


def _clear_custom_city_validation() -> None:
    st.session_state.pop(CUSTOM_VALIDATION_KEY, None)
    st.session_state.pop(CUSTOM_CONFIRMED_KEY, None)


def _current_custom_validation():
    data = st.session_state.get(CUSTOM_VALIDATION_KEY)
    if not isinstance(data, dict):
        return None
    validation = custom_city_validation_from_dict(data)
    country, city = _custom_city_inputs()
    if validation.input_country.casefold() != country.casefold() or validation.input_city.casefold() != city.casefold():
        _clear_custom_city_validation()
        return None
    return validation


def _default_year_range() -> tuple[int, int]:
    supported_start_year = 2013
    default_start = max(supported_start_year, CURRENT_YEAR - 2)
    return default_start, CURRENT_YEAR


def _selected_years() -> tuple[int, int]:
    supported_start_year = 2013
    default_value = _default_year_range()
    value = st.session_state.get(YEARS_KEY, default_value)
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        value = default_value
    start_year = max(int(value[0]), supported_start_year)
    end_year = min(int(value[1]), CURRENT_YEAR)
    if start_year > end_year:
        start_year = supported_start_year
    return start_year, end_year


def _selected_pollutants() -> list[str]:
    values = st.session_state.get(POLLUTANTS_KEY, DEFAULT_POLLUTANTS)
    normalized = [str(item) for item in values if str(item) in AQ_AGENT_POLLUTANTS]
    return normalized or ["pm25"]


def _selected_weather_fields() -> list[str]:
    values = st.session_state.get(WEATHER_FIELDS_KEY, DEFAULT_WEATHER_FIELDS)
    normalized = [str(item) for item in values if str(item) in DEFAULT_WEATHER_FIELDS]
    return normalized


def _current_instruction() -> str:
    country, city = _custom_city_inputs()
    start_year, end_year = _selected_years()
    pollutant_text = ", ".join(pollutant.upper() for pollutant in _selected_pollutants())
    weather_fields = _selected_weather_fields()
    weather_clause = (
        t("collection.weather_with_fields", language, fields=", ".join(weather_label(field, language) for field in weather_fields))
        if weather_fields
        else t("collection.weather_without", language)
    )
    return t(
        "agent.custom_instruction",
        language=language,
        city=city or t("agent.custom_city_name", language),
        country=country or t("agent.custom_city_country", language),
        start_year=start_year,
        end_year=end_year,
        pollutants=pollutant_text,
        weather_clause=weather_clause,
    )


def _render_plan(plan) -> None:
    st.subheader(t("agent.plan_section", language))
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(t("common.city", language), plan.city_label)
    col2.metric(t("common.actual_start", language), plan.actual_start_date)
    col3.metric(t("common.actual_end", language), plan.actual_end_date)
    col4.metric(t("common.chunks", language), len(plan.chunks))

    st.info(plan.planner_notes)
    st.caption(
        t(
            "agent.plan_caption",
            language,
            source=plan.source_name,
            domain=plan.source_domain,
            sampling=plan.sampling_step,
            mode=plan.planner_mode,
        )
    )

    if plan.warnings:
        for warning in plan.warnings:
            st.warning(warning)

    left, right = st.columns((1, 1))
    with left:
        st.write(t("agent.planned_pollutants", language))
        st.write(", ".join(pollutant.upper() for pollutant in plan.pollutants))
        st.write(t("agent.weather_fields_label", language))
        if plan.weather_variables:
            st.write(", ".join(variable for variable in plan.weather_variables))
        else:
            st.write(t("agent.no_weather_fields", language))
        if plan.quality_checks:
            st.write(t("agent.quality_checks", language))
            for item in plan.quality_checks:
                st.write(f"- {item}")
    with right:
        if plan.risk_flags:
            st.write(t("agent.risk_flags", language))
            for item in plan.risk_flags:
                st.write(f"- {item}")
        st.write(t("agent.chunk_preview", language))
        render_dataframe(pd.DataFrame(plan.chunks), use_container_width=True, hide_index=True)

with st.expander(t("agent.deepseek_settings", language), expanded=False):
    st.text_input(t("agent.model", language), value=_safe_secret("deepseek_model") or AQ_AGENT_DEFAULT_MODEL, key="aq_agent_model")
    st.text_input(t("agent.base_url", language), value=_safe_secret("deepseek_base_url") or DEEPSEEK_BASE_URL, key="aq_agent_base_url")
    st.caption(t("agent.task_store_backend", language, backend=_task_store_backend_label()))
    if _safe_secret("deepseek_api_key"):
        st.checkbox(t("agent.use_deepseek"), value=True, key=USE_DEEPSEEK_KEY)
        st.success(t("agent.api_key_found", language))
    else:
        st.checkbox(t("agent.use_deepseek"), value=False, key=USE_DEEPSEEK_KEY, disabled=True)
        st.info(t("agent.api_key_optional", language))

st.subheader(t("agent.request_section", language))
st.caption(t("agent.request_caption", language))

st.caption(t("agent.custom_city_caption", language))
stable_city_options = _stable_city_options()
st.selectbox(
    t("agent.stable_city_select", language),
    options=_stable_city_option_labels(),
    index=None,
    placeholder=t("agent.stable_city_placeholder", language),
    key=STABLE_CITY_OPTION_KEY,
)
selected_stable_city_option = _selected_stable_city_option()
if selected_stable_city_option is not None:
    selected_label = str(st.session_state.get(STABLE_CITY_OPTION_KEY) or "")
    if st.session_state.get(STABLE_CITY_APPLIED_KEY) != selected_label:
        _apply_stable_city_option(selected_stable_city_option)
        st.session_state[STABLE_CITY_APPLIED_KEY] = selected_label
        st.rerun()

custom_left, custom_right = st.columns((1, 1))
with custom_left:
    st.text_input(t("agent.custom_city_country", language), key=CUSTOM_COUNTRY_KEY)
with custom_right:
    st.text_input(t("agent.custom_city_name", language), key=CUSTOM_CITY_NAME_KEY)

validation = _current_custom_validation()
if validation is not None:
    if validation.status == "low_confidence":
        st.warning(validation.message or t("agent.custom_city_low_confidence", language))
    elif validation.status == "needs_confirmation" and not st.session_state.get(CUSTOM_CONFIRMED_KEY):
        city_label = validation.corrected_city or validation.input_city
        country_label = validation.corrected_country or validation.input_country
        st.warning(
            validation.message
            or t("agent.custom_city_confirmation", language, city=city_label, country=country_label)
        )
        if validation.matching_countries:
            st.info(
                t(
                    "agent.custom_city_matching_countries",
                    language,
                    countries=", ".join(validation.matching_countries),
                )
            )
    else:
        st.success(
            t(
                "agent.custom_city_confirmed",
                language,
                city=validation.corrected_city or validation.input_city,
                country=validation.corrected_country or validation.input_country,
            )
        )

st.info(t("agent.custom_support_window", language))

left, right = st.columns((1, 1))
with left:
    st.slider(
        t("agent.year_range", language),
        min_value=2013,
        max_value=CURRENT_YEAR,
        value=_default_year_range(),
        key=YEARS_KEY,
    )
with right:
    st.multiselect(
        t("agent.pollutants_select", language),
        options=DEFAULT_POLLUTANTS,
        default=DEFAULT_POLLUTANTS,
        key=POLLUTANTS_KEY,
    )

st.multiselect(
    t("agent.weather_select", language),
    options=DEFAULT_WEATHER_FIELDS,
    default=DEFAULT_WEATHER_FIELDS,
    format_func=lambda key: weather_label(key, language),
    key=WEATHER_FIELDS_KEY,
)

with st.expander(t("agent.request_preview", language), expanded=False):
    st.caption(t("agent.request_preview_caption", language))
    st.code(_current_instruction(), language="text")

agent_left, agent_right = st.columns((1, 1))
agent_plan_clicked = agent_left.button(t("agent.draft_plan", language), use_container_width=True)
agent_collect_clicked = agent_right.button(t("agent.plan_and_collect", language), type="primary", use_container_width=True)

task_status_slot = st.empty()

if agent_plan_clicked or agent_collect_clicked:
    progress = st.progress(0)
    status = st.empty()
    api_key = _planner_api_key()
    action = "collect" if agent_collect_clicked else "plan"
    try:
        progress.progress(0.08)
        country, city = _custom_city_inputs()
        if not country or not city:
            progress.empty()
            status.warning(t("agent.custom_city_inputs_required", language))
        elif not api_key:
            progress.empty()
            status.error(t("agent.custom_city_requires_key", language))
        else:
            active_task_store, active_task_id = _start_custom_task(action)
            _submit_custom_city_task(active_task_store, active_task_id, api_key=api_key)
            progress.empty()
            status.success(t("agent.task_started", language))
            render_task_status_panel_once(_task_ui_context(), task_status_slot)
    except Exception as exc:  # noqa: BLE001
        st.error(t("agent.tool_failed", language, error=exc))

_task_ui = _task_ui_context()
render_current_task_status_panel(_task_ui, task_status_slot)
render_current_task_confirmation_panel(_task_ui)

stored_plan = st.session_state.get("aq_agent_plan")
if stored_plan:
    _render_plan(collection_plan_from_dict(stored_plan))

last_result = st.session_state.get("aq_agent_last_result")
if last_result:
    st.subheader(t("agent.last_run", language))
    st.success(
        t(
            "agent.last_run_saved",
            language,
            row_count=last_result["row_count"],
            path=last_result["output_path"],
            started_at=last_result["started_at"],
            ended_at=last_result["ended_at"],
        )
    )
    st.write(last_result["summary_text"])
    st.caption(t("common.summary_mode", language, mode=last_result["summary_mode"]))

    if last_result["runtime_warnings"]:
        for item in last_result["runtime_warnings"]:
            st.warning(item)

    coverage_df = pd.DataFrame(last_result["coverage_rows"])
    if not coverage_df.empty:
        render_dataframe(coverage_df, use_container_width=True, hide_index=True)

    output_path = Path(str(last_result["output_path"]))
    if output_path.exists():
        preview_df = load_dataset(output_path)
        preview_pollutant = next(
            (
                pollutant
                for pollutant in DEFAULT_POLLUTANTS
                if pollutant in preview_df.columns and preview_df[pollutant].notna().any()
            ),
            "pm25",
        )
        if preview_pollutant in preview_df.columns:
            st.plotly_chart(
                trend_figure(preview_df, preview_pollutant, language=language),
                use_container_width=True,
                config={"displayModeBar": False},
            )
        render_dataframe(preview_df.tail(200), use_container_width=True)
        with output_path.open("rb") as handle:
            if output_path.suffix.lower() == ".parquet":
                st.download_button(
                    t("common.download_parquet", language),
                    data=handle.read(),
                    file_name=output_path.name,
                    mime="application/octet-stream",
                )
            else:
                st.download_button(
                    t("common.download_csv", language),
                    data=handle.read(),
                    file_name=output_path.name,
                    mime="text/csv",
                )
        if output_path.suffix.lower() == ".parquet":
            st.download_button(
                t("common.download_csv", language),
                data=preview_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=output_path.with_suffix(".csv").name,
                mime="text/csv",
            )

    nav_left, nav_right = st.columns((1, 1))
    nav_left.page_link("pages/1_Overview.py", label=t("agent.open_overview", language))
    nav_right.page_link("pages/2_Spatiotemporal_Playback.py", label=t("agent.open_playback", language))
