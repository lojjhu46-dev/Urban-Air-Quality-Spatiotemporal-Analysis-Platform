from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.charts import trend_figure
from src.collection_agent import CollectionRequest, collection_plan_from_dict, run_deepseek_tool_agent
from src.config import AQ_AGENT_DEFAULT_MODEL, DEEPSEEK_BASE_URL
from src.data import load_dataset
from src.i18n import api_language, get_language, render_language_selector, t
from src.ui import DATASET_OVERRIDE_KEY, PENDING_DATASET_CHOICE_KEY, dataset_path_from_env, render_dataframe

language = get_language()
st.set_page_config(page_title=t("agent.page_title", language), layout="wide")

with st.sidebar:
    language = render_language_selector(key="language_selector_agent")

dataset_path_from_env()

st.title(t("agent.title", language))
st.caption(t("agent.caption", language))

CURRENT_YEAR = pd.Timestamp.today().year
DEFAULT_YEARS = (max(2022, CURRENT_YEAR - 2), CURRENT_YEAR)
DEFAULT_POLLUTANTS = ["pm25", "pm10", "no2", "so2", "co", "o3"]
default_instruction = t(
    "agent.default_instruction",
    language,
    start_year=DEFAULT_YEARS[0],
    end_year=DEFAULT_YEARS[1],
)


def _safe_secret(key: str) -> str | None:
    try:
        value = st.secrets.get(key)
    except Exception:  # noqa: BLE001
        value = None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _current_request() -> CollectionRequest:
    return CollectionRequest(
        city_query="Beijing",
        start_year=int(DEFAULT_YEARS[0]),
        end_year=int(DEFAULT_YEARS[1]),
        pollutants=DEFAULT_POLLUTANTS,
        include_weather=True,
        country_code="CN",
    )


def _planner_api_key() -> str | None:
    return _safe_secret("deepseek_api_key")


def _planner_model() -> str:
    return str(st.session_state.get("aq_agent_model", AQ_AGENT_DEFAULT_MODEL)).strip() or AQ_AGENT_DEFAULT_MODEL


def _planner_base_url() -> str:
    return str(st.session_state.get("aq_agent_base_url", DEEPSEEK_BASE_URL)).strip() or DEEPSEEK_BASE_URL


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
    if _safe_secret("deepseek_api_key"):
        st.success(t("agent.api_key_found", language))
    else:
        st.warning(t("agent.api_key_missing", language))

st.subheader(t("agent.natural_section", language))
st.caption(t("agent.natural_caption", language))
st.text_area(
    t("agent.instruction", language),
    value=st.session_state.get("aq_agent_instruction", default_instruction),
    key="aq_agent_instruction",
    height=110,
)

agent_left, agent_right = st.columns((1, 1))
agent_plan_clicked = agent_left.button(t("agent.draft_plan", language), use_container_width=True)
agent_collect_clicked = agent_right.button(t("agent.plan_and_collect", language), type="primary", use_container_width=True)

if agent_plan_clicked or agent_collect_clicked:
    api_key = _planner_api_key()
    if not api_key:
        st.error(t("agent.tool_requires_key", language))
    else:
        progress = st.progress(0)
        status = st.empty()

        def _progress(step: int, total: int, message: str) -> None:
            progress.progress(min(step / max(total, 1), 1.0))
            status.caption(message)

        try:
            agent_result = run_deepseek_tool_agent(
                st.session_state.get("aq_agent_instruction", ""),
                api_key=api_key,
                model=_planner_model(),
                base_url=_planner_base_url(),
                default_request=_current_request(),
                allow_run_collection=agent_collect_clicked,
                progress_callback=_progress,
                search_language=api_language(language),
                language=language,
            )
        except Exception as exc:  # noqa: BLE001
            progress.empty()
            status.empty()
            st.error(t("agent.tool_failed", language, error=exc))
        else:
            progress.progress(1.0)
            status.success(t("agent.tool_completed", language))
            st.session_state["aq_agent_tool_reply"] = agent_result.assistant_message
            st.session_state["aq_agent_tool_trace"] = agent_result.tool_trace
            if agent_result.state.last_plan is not None:
                _remember_plan(agent_result.state.last_plan)
            if agent_result.state.last_result is not None:
                _remember_collection_result(agent_result.state.last_result)
                st.rerun()

stored_tool_reply = st.session_state.get("aq_agent_tool_reply")
if stored_tool_reply:
    st.write(stored_tool_reply)
    with st.expander(t("agent.tool_trace", language), expanded=False):
        st.json(st.session_state.get("aq_agent_tool_trace", []), expanded=False)

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
