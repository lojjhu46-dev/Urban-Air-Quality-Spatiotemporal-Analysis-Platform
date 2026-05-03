from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.agent_task_store import AgentTaskStatus, PostgresAgentTaskStore, task_store_from_config
from src.agent_task_runner import AgentTaskRunConfig, start_background_custom_city_task
from src.agent_interaction import (
    AgentCityOption,
    build_agent_instruction,
    build_city_search_queries,
    candidate_matches_city_option,
    city_display_name,
    city_labels,
    city_option_from_path,
    continent_display_name,
    continent_labels,
    country_display_name,
    country_labels,
    default_city_option,
    option_has_province_step,
    province_display_name,
    province_labels,
)
from src.charts import trend_figure
from src.collection_agent import (
    CollectionRequest,
    build_collection_plan,
    collection_plan_from_dict,
    custom_city_validation_from_dict,
    run_collection_agent,
    search_city_candidates,
    validate_custom_city_with_deepseek,
)
from src.config import AQ_AGENT_DEFAULT_MODEL, AQ_AGENT_POLLUTANTS, DEEPSEEK_BASE_URL
from src.data import load_dataset
from src.i18n import api_language, get_language, render_language_selector, t, weather_label
from src.navigation import render_sidebar_navigation
from src.ui import DATASET_OVERRIDE_KEY, PENDING_DATASET_CHOICE_KEY, dataset_path_from_env, render_dataframe

language = get_language()
st.set_page_config(page_title=t("agent.page_title", language), layout="wide")

with st.sidebar:
    language = render_language_selector(key="language_selector_agent")
    render_sidebar_navigation(language)

dataset_path_from_env()

st.title(t("agent.title", language))
st.caption(t("agent.caption", language))

CURRENT_YEAR = pd.Timestamp.today().year
DEFAULT_CITY_OPTION = default_city_option()
DEFAULT_POLLUTANTS = list(AQ_AGENT_POLLUTANTS)
DEFAULT_WEATHER_FIELDS = ["temp", "humidity", "wind_speed"]

CONTINENT_KEY = "aq_agent_continent"
COUNTRY_KEY = "aq_agent_country"
PROVINCE_KEY = "aq_agent_province"
CITY_KEY = "aq_agent_city"
YEARS_KEY = "aq_agent_year_range"
POLLUTANTS_KEY = "aq_agent_pollutants"
WEATHER_FIELDS_KEY = "aq_agent_weather_fields"
USE_DEEPSEEK_KEY = "aq_agent_use_deepseek"
CUSTOM_CITY_OPTION_VALUE = t("agent.custom_city_option", "en")
CUSTOM_COUNTRY_KEY = "aq_agent_custom_country"
CUSTOM_CITY_NAME_KEY = "aq_agent_custom_city_name"
CUSTOM_VALIDATION_KEY = "aq_agent_custom_city_validation"
CUSTOM_CONFIRMED_KEY = "aq_agent_custom_city_confirmed"
CUSTOM_PENDING_ACTION_KEY = "aq_agent_custom_city_pending_action"
TASK_STORE_KEY = "aq_agent_task_store"
TASK_STORE_URL_KEY = "aq_agent_task_store_url"
CURRENT_TASK_KEY = "aq_agent_current_task_id"
TERMINAL_TASK_STATUSES = {
    AgentTaskStatus.PLANNED,
    AgentTaskStatus.SAVED,
    AgentTaskStatus.FAILED,
    AgentTaskStatus.TIMEOUT,
}


def _safe_secret(key: str) -> str | None:
    try:
        value = st.secrets.get(key)
    except Exception:  # noqa: BLE001
        value = None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _planner_api_key() -> str | None:
    enabled = bool(st.session_state.get(USE_DEEPSEEK_KEY, bool(_safe_secret("deepseek_api_key"))))
    if not enabled:
        return None
    return _safe_secret("deepseek_api_key")


def _planner_model() -> str:
    return str(st.session_state.get("aq_agent_model", AQ_AGENT_DEFAULT_MODEL)).strip() or AQ_AGENT_DEFAULT_MODEL


def _planner_base_url() -> str:
    return str(st.session_state.get("aq_agent_base_url", DEEPSEEK_BASE_URL)).strip() or DEEPSEEK_BASE_URL


def _task_database_url() -> str | None:
    return _safe_secret("database_url") or _safe_secret("DATABASE_URL")


def _task_store_backend_label() -> str:
    store = task_store_from_config(_task_database_url())
    if isinstance(store, PostgresAgentTaskStore):
        return t("agent.task_store_postgres", language)
    return t("agent.task_store_memory", language)


def _task_store():
    database_url = _task_database_url() or ""
    store = st.session_state.get(TASK_STORE_KEY)
    if store is not None and st.session_state.get(TASK_STORE_URL_KEY) == database_url:
        return store
    store = task_store_from_config(database_url)
    st.session_state[TASK_STORE_KEY] = store
    st.session_state[TASK_STORE_URL_KEY] = database_url
    return store


def _custom_task_payload(action: str, request: CollectionRequest | None = None) -> dict[str, object]:
    country, city = _custom_city_inputs()
    start_year, end_year = _selected_years()
    pollutants = _selected_pollutants()
    weather_fields = _selected_weather_fields()
    payload = {
        "kind": "custom_city_collection",
        "action": action,
        "input_country": country,
        "input_city": city,
        "city_query": request.city_query if request is not None else city,
        "country_code": (request.country_code or "") if request is not None else "",
        "start_year": request.start_year if request is not None else start_year,
        "end_year": request.end_year if request is not None else end_year,
        "pollutants": request.normalized_pollutants() if request is not None else pollutants,
        "include_weather": request.include_weather if request is not None else bool(weather_fields),
        "weather_fields": request.normalized_weather_fields() if request is not None else weather_fields,
    }
    validation = _current_custom_validation()
    if validation is not None and st.session_state.get(CUSTOM_CONFIRMED_KEY):
        payload["confirmed_validation"] = validation.to_dict()
    return payload


def _start_custom_task(action: str, request: CollectionRequest | None = None):
    store = _task_store()
    task = store.create_task(kind="custom_city_collection", request_payload=_custom_task_payload(action, request))
    st.session_state[CURRENT_TASK_KEY] = task.task_id
    return store, task.task_id


def _record_task_step(
    store,
    task_id: str,
    *,
    status_value: AgentTaskStatus,
    phase: str,
    progress_value: float,
    message: str,
    result_payload: dict[str, object] | None = None,
    error: str | None = None,
    output_path: str | None = None,
    log: bool = True,
) -> None:
    store.update_task(
        task_id,
        status=status_value,
        phase=phase,
        progress=progress_value,
        message=message,
        result_payload=result_payload,
        error=error,
        output_path=output_path,
    )
    if log:
        store.append_log(task_id, level="error" if status_value == AgentTaskStatus.FAILED else "info", phase=phase, message=message)


def _format_task_timestamp(value) -> str:
    if value is None:
        return "-"
    return str(value).replace("+00:00", " UTC")


def _sync_task_result_to_session(task) -> None:
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


def _render_task_confirmation_controls(task) -> None:
    if task.status != AgentTaskStatus.PENDING or task.phase != "AWAITING_CONFIRMATION":
        return
    validation_data = task.result_payload.get("validation") if isinstance(task.result_payload, dict) else None
    if not isinstance(validation_data, dict):
        return
    validation = custom_city_validation_from_dict(validation_data)
    country, city = _custom_city_inputs()
    if validation.input_country.casefold() != country.casefold() or validation.input_city.casefold() != city.casefold():
        return

    city_label = validation.corrected_city or validation.input_city
    country_label = validation.corrected_country or validation.input_country
    if validation.matching_countries:
        st.info(
            t(
                "agent.custom_city_matching_countries",
                language,
                countries=", ".join(validation.matching_countries),
            )
        )
    confirm_left, confirm_right = st.columns((1, 1))
    if confirm_left.button(t("agent.custom_city_confirm_yes", language), use_container_width=True, key=f"{task.task_id}_confirm_yes"):
        if not validation.country_code:
            st.error(t("agent.custom_city_country_code_missing", language))
            return
        st.session_state[CUSTOM_VALIDATION_KEY] = validation.to_dict()
        st.session_state[CUSTOM_CONFIRMED_KEY] = True
        action = str(task.result_payload.get("action") or task.request_payload.get("action") or "plan")
        next_store, next_task_id = _start_custom_task(action)
        start_background_custom_city_task(
            next_store,
            next_task_id,
            AgentTaskRunConfig(
                api_key=_planner_api_key(),
                model=_planner_model(),
                base_url=_planner_base_url(),
                language=language,
            ),
        )
        st.success(t("agent.custom_city_confirmed", language, city=city_label, country=country_label))
        st.rerun()
    if confirm_right.button(t("agent.custom_city_confirm_no", language), use_container_width=True, key=f"{task.task_id}_confirm_no"):
        _clear_custom_city_validation()
        st.session_state.pop(CURRENT_TASK_KEY, None)
        st.rerun()


def _render_task_status_panel_body() -> None:
    task_id = st.session_state.get(CURRENT_TASK_KEY)
    if not task_id:
        return

    try:
        store = _task_store()
        task = store.get_task(str(task_id))
        logs = store.list_logs(str(task_id), limit=20)
    except Exception as exc:  # noqa: BLE001
        st.warning(t("agent.task_status_unavailable", language, error=exc))
        return

    if task is None:
        st.info(t("agent.task_status_missing", language, task_id=task_id))
        return

    _sync_task_result_to_session(task)

    st.subheader(t("agent.task_status_section", language))
    st.caption(
        t(
            "agent.task_status_caption",
            language,
            task_id=task.task_id,
            updated_at=_format_task_timestamp(task.updated_at),
        )
    )

    status_col, phase_col, progress_col = st.columns(3)
    status_col.metric(t("agent.task_status_label", language), task.status.value)
    phase_col.metric(t("agent.task_phase_label", language), task.phase)
    progress_col.metric(t("agent.task_progress_label", language), f"{task.progress:.0%}")
    st.caption(
        t(
            "agent.task_state_line",
            language,
            status=task.status.value,
            phase=task.phase,
            progress=f"{task.progress:.0%}",
        )
    )
    st.progress(task.progress)

    if task.message:
        st.write(task.message)
    if task.output_path:
        st.success(t("agent.task_output_path", language, path=task.output_path))
    if task.error:
        st.error(t("agent.task_error", language, error=task.error))

    if logs:
        logs_expanded = task.status not in TERMINAL_TASK_STATUSES
        with st.expander(t("agent.task_log_section", language), expanded=logs_expanded):
            for log in logs[-10:]:
                st.caption(
                    t(
                        "agent.task_log_item",
                        language,
                        created_at=_format_task_timestamp(log.created_at),
                        level=log.level,
                        phase=log.phase,
                        message=log.message,
                    )
                )


def _render_task_status_panel_once(container=None) -> None:
    if container is None:
        _render_task_status_panel_body()
        return
    with container.container():
        _render_task_status_panel_body()


def _render_current_task_status_panel(container=None) -> None:
    def _render() -> None:
        _render_task_status_panel_once(container)

    fragment = getattr(st, "fragment", None)
    if fragment is None:
        _render()
        return

    @fragment(run_every="2s")
    def _task_status_fragment() -> None:
        _render()

    _task_status_fragment()


def _render_current_task_confirmation_controls() -> None:
    task_id = st.session_state.get(CURRENT_TASK_KEY)
    if not task_id:
        return
    try:
        store = _task_store()
        task = store.get_task(str(task_id))
    except Exception:  # noqa: BLE001
        return
    if task is not None:
        _render_task_confirmation_controls(task)


def _render_current_task_confirmation_panel() -> None:
    fragment = getattr(st, "fragment", None)
    if fragment is None:
        _render_current_task_confirmation_controls()
        return

    @fragment(run_every="2s")
    def _task_confirmation_fragment() -> None:
        _render_current_task_confirmation_controls()

    _task_confirmation_fragment()


def _ensure_state_value(key: str, options: list[str], default_value: str) -> None:
    if not options:
        st.session_state.pop(key, None)
        return
    if st.session_state.get(key) not in options:
        st.session_state[key] = default_value if default_value in options else options[0]


def _is_custom_city_selected() -> bool:
    return CUSTOM_CITY_OPTION_VALUE in {
        st.session_state.get(COUNTRY_KEY),
        st.session_state.get(PROVINCE_KEY),
        st.session_state.get(CITY_KEY),
    }


def _custom_city_inputs() -> tuple[str, str]:
    return (
        str(st.session_state.get(CUSTOM_COUNTRY_KEY) or "").strip(),
        str(st.session_state.get(CUSTOM_CITY_NAME_KEY) or "").strip(),
    )


def _clear_custom_city_validation() -> None:
    st.session_state.pop(CUSTOM_VALIDATION_KEY, None)
    st.session_state.pop(CUSTOM_CONFIRMED_KEY, None)
    st.session_state.pop(CUSTOM_PENDING_ACTION_KEY, None)


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


def _current_city_option() -> AgentCityOption:
    return city_option_from_path(
        st.session_state[CONTINENT_KEY],
        st.session_state[COUNTRY_KEY],
        st.session_state.get(PROVINCE_KEY) or None,
        st.session_state[CITY_KEY],
    )


def _selected_years() -> tuple[int, int]:
    supported_start_year = 2013 if _is_custom_city_selected() else _current_city_option().supported_start_year
    default_start = max(supported_start_year, CURRENT_YEAR - 2)
    default_value = (default_start, CURRENT_YEAR)
    value = st.session_state.get(YEARS_KEY, default_value)
    start_year = max(int(value[0]), supported_start_year)
    end_year = min(int(value[1]), CURRENT_YEAR)
    if start_year > end_year:
        start_year = supported_start_year
    return start_year, end_year


def _prime_year_state() -> None:
    st.session_state[YEARS_KEY] = _selected_years()


def _selected_pollutants() -> list[str]:
    values = st.session_state.get(POLLUTANTS_KEY, DEFAULT_POLLUTANTS)
    normalized = [str(item) for item in values if str(item) in AQ_AGENT_POLLUTANTS]
    return normalized or ["pm25"]


def _selected_weather_fields() -> list[str]:
    values = st.session_state.get(WEATHER_FIELDS_KEY, DEFAULT_WEATHER_FIELDS)
    normalized = [str(item) for item in values if str(item) in DEFAULT_WEATHER_FIELDS]
    return normalized


def _custom_collection_request(validation) -> CollectionRequest:
    start_year, end_year = _selected_years()
    weather_fields = _selected_weather_fields()
    country, city = _custom_city_inputs()
    return CollectionRequest(
        city_query=validation.corrected_city or city,
        start_year=start_year,
        end_year=end_year,
        pollutants=_selected_pollutants(),
        include_weather=bool(weather_fields),
        country_code=validation.country_code,
        weather_fields=weather_fields,
    )


def _current_request() -> CollectionRequest:
    if _is_custom_city_selected():
        validation = _current_custom_validation()
        if validation is None:
            country, city = _custom_city_inputs()
            start_year, end_year = _selected_years()
            weather_fields = _selected_weather_fields()
            return CollectionRequest(
                city_query=city,
                start_year=start_year,
                end_year=end_year,
                pollutants=_selected_pollutants(),
                include_weather=bool(weather_fields),
                country_code=None,
                weather_fields=weather_fields,
            )
        return _custom_collection_request(validation)

    city_option = _current_city_option()
    start_year, end_year = _selected_years()
    weather_fields = _selected_weather_fields()
    return CollectionRequest(
        city_query=city_option.city_query,
        start_year=start_year,
        end_year=end_year,
        pollutants=_selected_pollutants(),
        include_weather=bool(weather_fields),
        country_code=city_option.country_code,
        weather_fields=weather_fields,
    )


def _current_instruction() -> str:
    if _is_custom_city_selected():
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
            language,
            city=city or t("agent.custom_city_name", language),
            country=country or t("agent.custom_city_country", language),
            start_year=start_year,
            end_year=end_year,
            pollutants=pollutant_text,
            weather_clause=weather_clause,
        )

    city_option = _current_city_option()
    start_year, end_year = _selected_years()
    return build_agent_instruction(
        city_option,
        start_year,
        end_year,
        _selected_pollutants(),
        _selected_weather_fields(),
        language=language,
    )


def _format_province_option(province: str) -> str:
    if province == CUSTOM_CITY_OPTION_VALUE:
        return t("agent.custom_city_option", language)
    return (
        province_display_name(
            st.session_state.get(CONTINENT_KEY) or "",
            st.session_state.get(COUNTRY_KEY) or "",
            province,
            language,
        )
        or province
    )


def _format_city_option(city: str) -> str:
    if city == CUSTOM_CITY_OPTION_VALUE:
        return t("agent.custom_city_option", language)
    return city_display_name(
        st.session_state.get(CONTINENT_KEY) or "",
        st.session_state.get(COUNTRY_KEY) or "",
        st.session_state.get(PROVINCE_KEY) or None,
        city,
        language,
    )


def _format_continent_option(continent: str) -> str:
    return continent_display_name(continent, language)


def _format_country_option(country: str) -> str:
    if country == CUSTOM_CITY_OPTION_VALUE:
        return t("agent.custom_city_option", language)
    return country_display_name(st.session_state.get(CONTINENT_KEY) or "", country, language)


def _resolve_selected_candidate() -> object:
    city_option = _current_city_option()
    latest_candidates = []
    for query in build_city_search_queries(city_option):
        candidates = search_city_candidates(query, country_code=city_option.country_code, count=10, language="en")
        latest_candidates = candidates
        for candidate in candidates:
            if candidate_matches_city_option(
                city_option,
                candidate_name=candidate.name,
                candidate_admin1=candidate.admin1,
                candidate_country_code=candidate.country_code,
            ):
                return candidate
    if latest_candidates:
        return latest_candidates[0]
    raise ValueError(t("agent.city_not_found", language, city=city_option.path_label_for_language(language)))


def _prepare_custom_city_run(api_key: str | None, action: str, task_store=None, task_id: str | None = None):
    country, city = _custom_city_inputs()
    if not country or not city:
        st.warning(t("agent.custom_city_inputs_required", language))
        return None
    if not api_key:
        st.error(t("agent.custom_city_requires_key", language))
        return None

    validation = _current_custom_validation()
    confirmed = bool(st.session_state.get(CUSTOM_CONFIRMED_KEY))
    if validation is None or not confirmed:
        validation = validate_custom_city_with_deepseek(
            country,
            city,
            api_key=api_key,
            model=_planner_model(),
            base_url=_planner_base_url(),
            language=language,
        )
        st.session_state[CUSTOM_VALIDATION_KEY] = validation.to_dict()
        st.session_state[CUSTOM_CONFIRMED_KEY] = validation.status == "valid"
        confirmed = validation.status == "valid"

    if validation.status == "low_confidence":
        message = validation.message or t("agent.custom_city_low_confidence", language)
        st.warning(message)
        if task_store is not None and task_id is not None:
            _record_task_step(
                task_store,
                task_id,
                status_value=AgentTaskStatus.FAILED,
                phase="FAILED",
                progress_value=1.0,
                message=message,
                error=message,
            )
        return None

    if validation.status == "needs_confirmation" and not confirmed:
        st.session_state[CUSTOM_PENDING_ACTION_KEY] = action
        message = validation.message or t(
            "agent.custom_city_confirmation",
            language,
            city=validation.corrected_city or validation.input_city,
            country=validation.corrected_country or validation.input_country,
        )
        if task_store is not None and task_id is not None:
            _record_task_step(
                task_store,
                task_id,
                status_value=AgentTaskStatus.PENDING,
                phase="AWAITING_CONFIRMATION",
                progress_value=0.12,
                message=message,
            )
        st.warning(message)
        st.rerun()
        return None

    if not validation.country_code and validation.status != "valid":
        message = t("agent.custom_city_country_code_missing", language)
        st.error(message)
        if task_store is not None and task_id is not None:
            _record_task_step(
                task_store,
                task_id,
                status_value=AgentTaskStatus.FAILED,
                phase="FAILED",
                progress_value=1.0,
                message=message,
                error=message,
            )
        return None

    return _custom_collection_request(validation)


def _resolve_custom_candidate(request: CollectionRequest) -> object:
    candidates = search_city_candidates(
        request.city_query,
        country_code=request.country_code,
        count=10,
        language=api_language(language),
    )
    if candidates:
        return candidates[0]
    raise ValueError(
        t(
            "agent.city_not_found",
            language,
            city=f"{request.city_query}, {request.country_code or t('agent.custom_city_country', language)}",
        )
    )


def _remember_plan(plan) -> None:
    st.session_state["aq_agent_plan"] = plan.to_dict()


def _remember_collection_result(result) -> None:
    _remember_plan(result.plan)
    st.session_state[DATASET_OVERRIDE_KEY] = result.output_path
    st.session_state[PENDING_DATASET_CHOICE_KEY] = result.output_path
    st.session_state["aq_agent_last_result"] = {
        "output_path": result.output_path,
        "summary_text": result.summary_text,
        "summary_mode": result.summary_mode,
        "runtime_warnings": result.runtime_warnings,
        "coverage_rows": result.coverage_rows,
        "row_count": result.row_count,
        "started_at": result.started_at,
        "ended_at": result.ended_at,
    }


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


continent_options = continent_labels()
_ensure_state_value(CONTINENT_KEY, continent_options, DEFAULT_CITY_OPTION.continent)

country_options = [*country_labels(st.session_state[CONTINENT_KEY]), CUSTOM_CITY_OPTION_VALUE]
_ensure_state_value(COUNTRY_KEY, country_options, DEFAULT_CITY_OPTION.country)

country_is_custom = st.session_state[COUNTRY_KEY] == CUSTOM_CITY_OPTION_VALUE
province_required = (
    not country_is_custom
    and option_has_province_step(st.session_state[CONTINENT_KEY], st.session_state[COUNTRY_KEY])
)
province_options = (
    [*province_labels(st.session_state[CONTINENT_KEY], st.session_state[COUNTRY_KEY]), CUSTOM_CITY_OPTION_VALUE]
    if province_required
    else []
)
if province_required:
    _ensure_state_value(PROVINCE_KEY, province_options, DEFAULT_CITY_OPTION.province or province_options[0])
else:
    st.session_state[PROVINCE_KEY] = ""

province_is_custom = st.session_state.get(PROVINCE_KEY) == CUSTOM_CITY_OPTION_VALUE
available_city_labels = (
    []
    if country_is_custom or province_is_custom
    else city_labels(
        st.session_state[CONTINENT_KEY],
        st.session_state[COUNTRY_KEY],
        st.session_state.get(PROVINCE_KEY) or None,
    )
)
city_select_options = [*available_city_labels, CUSTOM_CITY_OPTION_VALUE]
_ensure_state_value(CITY_KEY, city_select_options, DEFAULT_CITY_OPTION.city)
_prime_year_state()

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

row1_left, row1_right = st.columns((1, 1))
with row1_left:
    st.selectbox(
        t("agent.continent_select", language),
        options=continent_options,
        format_func=_format_continent_option,
        key=CONTINENT_KEY,
    )
with row1_right:
    st.selectbox(
        t("agent.country_select", language),
        options=country_options,
        format_func=_format_country_option,
        key=COUNTRY_KEY,
    )

row2_left, row2_right = st.columns((1, 1))
with row2_left:
    if province_required:
        st.selectbox(
            t("agent.province_select", language),
            options=province_options,
            format_func=_format_province_option,
            key=PROVINCE_KEY,
        )
    else:
        st.text_input(t("agent.province_select", language), value=t("agent.province_skip", language), disabled=True)
with row2_right:
    st.selectbox(
        t("agent.city_select", language),
        options=city_select_options,
        format_func=_format_city_option,
        key=CITY_KEY,
    )

pending_custom_action = None
if _is_custom_city_selected():
    st.caption(t("agent.custom_city_caption", language))
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
            confirm_left, confirm_right = st.columns((1, 1))
            if confirm_left.button(t("agent.custom_city_confirm_yes", language), use_container_width=True):
                if validation.country_code:
                    st.session_state[CUSTOM_CONFIRMED_KEY] = True
                    pending_custom_action = st.session_state.get(CUSTOM_PENDING_ACTION_KEY)
                    st.success(
                        t(
                            "agent.custom_city_confirmed",
                            language,
                            city=city_label,
                            country=country_label,
                        )
                    )
                else:
                    st.error(t("agent.custom_city_country_code_missing", language))
            if confirm_right.button(t("agent.custom_city_confirm_no", language), use_container_width=True):
                _clear_custom_city_validation()
                st.rerun()
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
else:
    selected_city = _current_city_option()
    source_name, source_window = selected_city.source_summary
    st.caption(t("agent.city_catalog_hint", language))
    st.info(
        t(
            "agent.support_window",
            language,
            path=selected_city.path_label_for_language(language),
            source=source_name,
            window=source_window,
        )
    )
    if selected_city.country_code == "CN" and _planner_api_key():
        st.caption(t("agent.deepseek_proxy_hint", language))

left, right = st.columns((1, 1))
with left:
    st.slider(
        t("agent.year_range", language),
        min_value=2013 if _is_custom_city_selected() else selected_city.supported_start_year,
        max_value=CURRENT_YEAR,
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
if pending_custom_action == "plan":
    agent_plan_clicked = True
    st.session_state.pop(CUSTOM_PENDING_ACTION_KEY, None)
elif pending_custom_action == "collect":
    agent_collect_clicked = True
    st.session_state.pop(CUSTOM_PENDING_ACTION_KEY, None)

task_status_slot = st.empty()

if agent_plan_clicked or agent_collect_clicked:
    progress = st.progress(0)
    status = st.empty()
    api_key = _planner_api_key()
    action = "collect" if agent_collect_clicked else "plan"
    active_task_store = None
    active_task_id = None

    def _progress(step: int, total: int, message: str) -> None:
        progress_value = min(step / max(total, 1), 1.0)
        progress.progress(progress_value)
        status.caption(message)
        if active_task_store is not None and active_task_id is not None:
            _record_task_step(
                active_task_store,
                active_task_id,
                status_value=AgentTaskStatus.RUNNING,
                phase="COLLECTING",
                progress_value=progress_value,
                message=message,
            )

    try:
        progress.progress(0.08)
        if _is_custom_city_selected():
            country, city = _custom_city_inputs()
            if not country or not city:
                progress.empty()
                status.warning(t("agent.custom_city_inputs_required", language))
            elif not api_key:
                progress.empty()
                status.error(t("agent.custom_city_requires_key", language))
            else:
                active_task_store, active_task_id = _start_custom_task(action)
                start_background_custom_city_task(
                    active_task_store,
                    active_task_id,
                    AgentTaskRunConfig(
                        api_key=api_key,
                        model=_planner_model(),
                        base_url=_planner_base_url(),
                        language=language,
                    ),
                )
                progress.empty()
                status.success(t("agent.task_started", language))
                _render_task_status_panel_once(task_status_slot)
        else:
            request = _current_request()
            status.caption(t("agent.resolving_city", language))
            candidate = _resolve_selected_candidate()
            progress.progress(0.18)
            status.caption(t("agent.building_plan", language))
            if agent_collect_clicked:
                result = run_collection_agent(
                    request,
                    candidate,
                    api_key=api_key,
                    model=_planner_model(),
                    base_url=_planner_base_url(),
                    progress_callback=_progress,
                    language=language,
                )
                _remember_collection_result(result)
                progress.progress(1.0)
                status.success(t("agent.tool_completed", language))
                st.rerun()
            else:
                plan = build_collection_plan(
                    request,
                    candidate,
                    api_key=api_key,
                    model=_planner_model(),
                    base_url=_planner_base_url(),
                    language=language,
                )
                _remember_plan(plan)
                progress.progress(1.0)
                status.success(t("agent.tool_completed", language))
    except Exception as exc:  # noqa: BLE001
        if active_task_store is not None and active_task_id is not None:
            _record_task_step(
                active_task_store,
                active_task_id,
                status_value=AgentTaskStatus.FAILED,
                phase="FAILED",
                progress_value=1.0,
                message=str(exc),
                error=str(exc),
            )
        status.error(t("agent.tool_failed", language, error=exc))
        st.error(t("agent.tool_failed", language, error=exc))

_render_current_task_status_panel(task_status_slot)
_render_current_task_confirmation_panel()

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

    output_path = Path(last_result["output_path"])
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
                data=preview_df.to_csv(index=False).encode("utf-8"),
                file_name=output_path.with_suffix(".csv").name,
                mime="text/csv",
            )

    nav_left, nav_right = st.columns((1, 1))
    nav_left.page_link("pages/1_Overview.py", label=t("agent.open_overview", language))
    nav_right.page_link("pages/2_Spatiotemporal_Playback.py", label=t("agent.open_playback", language))
