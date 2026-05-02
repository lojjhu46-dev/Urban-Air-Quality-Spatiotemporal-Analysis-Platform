from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.agent_interaction import (
    AgentCityOption,
    build_agent_instruction,
    build_city_search_queries,
    candidate_matches_city_option,
    city_labels,
    city_option_from_path,
    continent_labels,
    country_labels,
    default_city_option,
    option_has_province_step,
    province_labels,
)
from src.charts import trend_figure
from src.china_city_catalog import china_city_display_name, china_province_display_name
from src.collection_agent import CollectionRequest, build_collection_plan, collection_plan_from_dict, run_collection_agent, search_city_candidates
from src.config import AQ_AGENT_DEFAULT_MODEL, AQ_AGENT_POLLUTANTS, DEEPSEEK_BASE_URL
from src.data import load_dataset
from src.i18n import get_language, render_language_selector, t, weather_label
from src.ui import DATASET_OVERRIDE_KEY, PENDING_DATASET_CHOICE_KEY, dataset_path_from_env, render_dataframe

language = get_language()
st.set_page_config(page_title=t("agent.page_title", language), layout="wide")

with st.sidebar:
    language = render_language_selector(key="language_selector_agent")

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


def _ensure_state_value(key: str, options: list[str], default_value: str) -> None:
    if not options:
        st.session_state.pop(key, None)
        return
    if st.session_state.get(key) not in options:
        st.session_state[key] = default_value if default_value in options else options[0]


def _current_city_option() -> AgentCityOption:
    return city_option_from_path(
        st.session_state[CONTINENT_KEY],
        st.session_state[COUNTRY_KEY],
        st.session_state.get(PROVINCE_KEY) or None,
        st.session_state[CITY_KEY],
    )


def _selected_years() -> tuple[int, int]:
    city_option = _current_city_option()
    default_start = max(city_option.supported_start_year, CURRENT_YEAR - 2)
    default_value = (default_start, CURRENT_YEAR)
    value = st.session_state.get(YEARS_KEY, default_value)
    start_year = max(int(value[0]), city_option.supported_start_year)
    end_year = min(int(value[1]), CURRENT_YEAR)
    if start_year > end_year:
        start_year = city_option.supported_start_year
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


def _current_request() -> CollectionRequest:
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
    if st.session_state.get(COUNTRY_KEY) == "China":
        return china_province_display_name(province, language) or province
    return province


def _format_city_option(city: str) -> str:
    if st.session_state.get(COUNTRY_KEY) == "China":
        return china_city_display_name(st.session_state.get(PROVINCE_KEY) or None, city, language)
    return city


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

country_options = country_labels(st.session_state[CONTINENT_KEY])
_ensure_state_value(COUNTRY_KEY, country_options, DEFAULT_CITY_OPTION.country)

province_required = option_has_province_step(st.session_state[CONTINENT_KEY], st.session_state[COUNTRY_KEY])
province_options = province_labels(st.session_state[CONTINENT_KEY], st.session_state[COUNTRY_KEY])
if province_required:
    _ensure_state_value(PROVINCE_KEY, province_options, DEFAULT_CITY_OPTION.province or province_options[0])
else:
    st.session_state[PROVINCE_KEY] = ""

available_city_labels = city_labels(
    st.session_state[CONTINENT_KEY],
    st.session_state[COUNTRY_KEY],
    st.session_state.get(PROVINCE_KEY) or None,
)
_ensure_state_value(CITY_KEY, available_city_labels, DEFAULT_CITY_OPTION.city)
_prime_year_state()

with st.expander(t("agent.deepseek_settings", language), expanded=False):
    st.text_input(t("agent.model", language), value=_safe_secret("deepseek_model") or AQ_AGENT_DEFAULT_MODEL, key="aq_agent_model")
    st.text_input(t("agent.base_url", language), value=_safe_secret("deepseek_base_url") or DEEPSEEK_BASE_URL, key="aq_agent_base_url")
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
    st.selectbox(t("agent.continent_select", language), options=continent_options, key=CONTINENT_KEY)
with row1_right:
    st.selectbox(t("agent.country_select", language), options=country_options, key=COUNTRY_KEY)

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
        options=available_city_labels,
        format_func=_format_city_option,
        key=CITY_KEY,
    )

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
        min_value=selected_city.supported_start_year,
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

if agent_plan_clicked or agent_collect_clicked:
    progress = st.progress(0)
    status = st.empty()
    request = _current_request()
    api_key = _planner_api_key()

    def _progress(step: int, total: int, message: str) -> None:
        progress.progress(min(step / max(total, 1), 1.0))
        status.caption(message)

    try:
        progress.progress(0.08)
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
        progress.empty()
        status.empty()
        st.error(t("agent.tool_failed", language, error=exc))

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
