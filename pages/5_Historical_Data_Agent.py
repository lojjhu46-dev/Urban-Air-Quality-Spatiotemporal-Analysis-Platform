from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.charts import trend_figure
from src.collection_agent import (
    CollectionRequest,
    build_collection_plan,
    city_candidate_from_dict,
    collection_plan_from_dict,
    run_collection_agent,
    search_city_candidates,
)
from src.config import AQ_AGENT_DEFAULT_MODEL, AQ_AGENT_POLLUTANTS, DEEPSEEK_BASE_URL
from src.ui import DATASET_CHOICE_KEY, DATASET_OVERRIDE_KEY, dataset_path_from_env

st.set_page_config(page_title="Historical Data Agent", layout="wide")
dataset_path_from_env()

st.title("Historical Air Quality Collection Agent")
st.caption("Resolve a city, let the agent build a collection plan, then save a dashboard-ready parquet dataset.")

CURRENT_YEAR = pd.Timestamp.today().year
DEFAULT_YEARS = (max(2022, CURRENT_YEAR - 2), CURRENT_YEAR)
DEFAULT_POLLUTANTS = ["pm25", "pm10", "no2", "so2", "co", "o3"]


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
    years = st.session_state.get("aq_agent_years", DEFAULT_YEARS)
    country_code = str(st.session_state.get("aq_agent_country_code", "")).strip().upper() or None
    return CollectionRequest(
        city_query=str(st.session_state.get("aq_agent_city_query", "")).strip(),
        start_year=int(years[0]),
        end_year=int(years[1]),
        pollutants=list(st.session_state.get("aq_agent_pollutants", DEFAULT_POLLUTANTS)),
        include_weather=bool(st.session_state.get("aq_agent_include_weather", True)),
        country_code=country_code,
    )


def _selected_candidate() -> tuple[list, object | None]:
    raw_candidates = st.session_state.get("aq_agent_candidates", [])
    if not raw_candidates:
        return [], None

    candidates = [city_candidate_from_dict(item) for item in raw_candidates]
    idx = int(st.session_state.get("aq_agent_candidate_index", 0))
    idx = min(max(idx, 0), len(candidates) - 1)
    st.session_state["aq_agent_candidate_index"] = idx
    return candidates, candidates[idx]


def _planner_api_key() -> str | None:
    if not st.session_state.get("aq_agent_use_llm", True):
        return None
    return _safe_secret("deepseek_api_key")


def _planner_model() -> str:
    return str(st.session_state.get("aq_agent_model", AQ_AGENT_DEFAULT_MODEL)).strip() or AQ_AGENT_DEFAULT_MODEL


def _planner_base_url() -> str:
    return str(st.session_state.get("aq_agent_base_url", DEEPSEEK_BASE_URL)).strip() or DEEPSEEK_BASE_URL


def _render_plan(plan) -> None:
    st.subheader("Agent Plan")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("City", plan.city_label)
    col2.metric("Actual start", plan.actual_start_date)
    col3.metric("Actual end", plan.actual_end_date)
    col4.metric("Chunks", len(plan.chunks))

    st.info(plan.planner_notes)
    st.caption(
        f"Source: {plan.source_name} | Domain: {plan.source_domain} | Sampling: {plan.sampling_step} | Planner mode: {plan.planner_mode}"
    )

    if plan.warnings:
        for warning in plan.warnings:
            st.warning(warning)

    left, right = st.columns((1, 1))
    with left:
        st.write("Planned pollutants")
        st.write(", ".join(AQ_AGENT_POLLUTANTS[pollutant]["label"] for pollutant in plan.pollutants))
        if plan.quality_checks:
            st.write("Quality checks")
            for item in plan.quality_checks:
                st.write(f"- {item}")
    with right:
        if plan.risk_flags:
            st.write("Risk flags")
            for item in plan.risk_flags:
                st.write(f"- {item}")
        st.write("Chunk window preview")
        st.dataframe(pd.DataFrame(plan.chunks), use_container_width=True, hide_index=True)


with st.expander("DeepSeek Settings", expanded=False):
    st.checkbox(
        "Use DeepSeek for planning and summary when API key is configured",
        value=True,
        key="aq_agent_use_llm",
    )
    st.text_input("Model", value=_safe_secret("deepseek_model") or AQ_AGENT_DEFAULT_MODEL, key="aq_agent_model")
    st.text_input("Base URL", value=_safe_secret("deepseek_base_url") or DEEPSEEK_BASE_URL, key="aq_agent_base_url")
    if _safe_secret("deepseek_api_key"):
        st.success("Found `deepseek_api_key` in Streamlit secrets.")
    else:
        st.warning("No `deepseek_api_key` found. The page will fall back to deterministic planning and summaries.")

with st.form("aq_agent_request"):
    top_left, top_mid, top_right = st.columns((2, 1, 1))
    top_left.text_input("City query", value="Beijing", key="aq_agent_city_query")
    top_mid.text_input("Country code (optional)", value="CN", key="aq_agent_country_code", max_chars=2)
    top_right.slider("Year range", 2013, CURRENT_YEAR, value=DEFAULT_YEARS, key="aq_agent_years")

    st.multiselect(
        "Pollutants",
        options=list(AQ_AGENT_POLLUTANTS.keys()),
        default=DEFAULT_POLLUTANTS,
        format_func=lambda key: AQ_AGENT_POLLUTANTS[key]["label"],
        key="aq_agent_pollutants",
    )
    st.checkbox(
        "Include weather columns so the dataset works across all current dashboard pages",
        value=True,
        key="aq_agent_include_weather",
    )

    search_clicked = st.form_submit_button("1. Search City Candidates", use_container_width=True)

if search_clicked:
    request = _current_request()
    try:
        with st.spinner("Resolving city candidates..."):
            matches = search_city_candidates(
                request.city_query,
                country_code=request.country_code,
                count=5,
                language="en",
            )
    except Exception as exc:  # noqa: BLE001
        st.session_state["aq_agent_candidates"] = []
        st.error(f"City search failed: {exc}")
    else:
        st.session_state["aq_agent_candidates"] = [candidate.to_dict() for candidate in matches]
        st.session_state["aq_agent_plan"] = None
        st.session_state["aq_agent_last_result"] = None
        if matches:
            st.success(f"Found {len(matches)} candidate(s). Pick one below to continue.")
        else:
            st.warning("No city candidates were found. Try a broader city name or remove the country code.")

candidates, candidate = _selected_candidate()
if candidates:
    options = list(range(len(candidates)))
    st.selectbox(
        "Resolved city candidate",
        options=options,
        index=int(st.session_state.get("aq_agent_candidate_index", 0)),
        format_func=lambda idx: (
            f"{candidates[idx].display_name} | {candidates[idx].latitude:.2f}, {candidates[idx].longitude:.2f} | {candidates[idx].timezone}"
        ),
        key="aq_agent_candidate_index",
    )
    candidate = candidates[int(st.session_state.get("aq_agent_candidate_index", 0))]

    action_left, action_right = st.columns((1, 1))
    plan_clicked = action_left.button("2. Generate Agent Plan", use_container_width=True)
    run_clicked = action_right.button("3. Run Collection", type="primary", use_container_width=True)

    if plan_clicked:
        request = _current_request()
        try:
            with st.spinner("Generating collection plan..."):
                plan = build_collection_plan(
                    request,
                    candidate,
                    api_key=_planner_api_key(),
                    model=_planner_model(),
                    base_url=_planner_base_url(),
                )
        except Exception as exc:  # noqa: BLE001
            st.error(f"Plan generation failed: {exc}")
        else:
            st.session_state["aq_agent_plan"] = plan.to_dict()

    if run_clicked:
        request = _current_request()
        progress = st.progress(0)
        status = st.empty()

        def _progress(step: int, total: int, message: str) -> None:
            progress.progress(min(step / max(total, 1), 1.0))
            status.caption(message)

        try:
            result = run_collection_agent(
                request,
                candidate,
                api_key=_planner_api_key(),
                model=_planner_model(),
                base_url=_planner_base_url(),
                progress_callback=_progress,
            )
        except Exception as exc:  # noqa: BLE001
            progress.empty()
            status.empty()
            st.error(f"Collection run failed: {exc}")
        else:
            progress.progress(1.0)
            status.success(f"Collection completed. Saved to {result.output_path}")
            st.session_state["aq_agent_plan"] = result.plan.to_dict()
            st.session_state[DATASET_OVERRIDE_KEY] = result.output_path
            st.session_state[DATASET_CHOICE_KEY] = result.output_path
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
            st.success("This dataset is now the active dataset choice for the rest of the app.")

stored_plan = st.session_state.get("aq_agent_plan")
if stored_plan:
    _render_plan(collection_plan_from_dict(stored_plan))

last_result = st.session_state.get("aq_agent_last_result")
if last_result:
    st.subheader("Last Run")
    st.success(
        f"Saved {last_result['row_count']:,} rows to `{last_result['output_path']}` from {last_result['started_at']} to {last_result['ended_at']}."
    )
    st.write(last_result["summary_text"])
    st.caption(f"Summary mode: {last_result['summary_mode']}")

    if last_result["runtime_warnings"]:
        for item in last_result["runtime_warnings"]:
            st.warning(item)

    coverage_df = pd.DataFrame(last_result["coverage_rows"])
    if not coverage_df.empty:
        st.dataframe(coverage_df, use_container_width=True, hide_index=True)

    output_path = Path(last_result["output_path"])
    if output_path.exists():
        preview_df = pd.read_parquet(output_path)
        preview_pollutant = next(
            (
                pollutant
                for pollutant in st.session_state.get("aq_agent_pollutants", DEFAULT_POLLUTANTS)
                if pollutant in preview_df.columns and preview_df[pollutant].notna().any()
            ),
            "pm25",
        )
        if preview_pollutant in preview_df.columns:
            st.plotly_chart(
                trend_figure(preview_df, preview_pollutant),
                use_container_width=True,
                config={"displayModeBar": False},
            )
        st.dataframe(preview_df.tail(200), use_container_width=True)
        with output_path.open("rb") as handle:
            st.download_button(
                "Download parquet",
                data=handle.read(),
                file_name=output_path.name,
                mime="application/octet-stream",
            )
        st.download_button(
            "Download CSV",
            data=preview_df.to_csv(index=False).encode("utf-8"),
            file_name=output_path.with_suffix(".csv").name,
            mime="text/csv",
        )

    nav_left, nav_right = st.columns((1, 1))
    nav_left.page_link("pages/1_Overview.py", label="Open Overview with this dataset")
    nav_right.page_link("pages/2_Spatiotemporal_Playback.py", label="Open Playback with this dataset")
