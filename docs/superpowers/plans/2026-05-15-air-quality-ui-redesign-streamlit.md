# Air Quality UI Redesign Streamlit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Figma redesign as a lightweight Streamlit analytical workbench without rewriting business logic.

**Architecture:** Keep the existing multi-page Streamlit structure. Add reusable UI helpers in `src/ui.py`, centralize CSS/theme treatment in `.streamlit/config.toml` plus one injected stylesheet helper, and update each page layout while preserving current data loading, filtering, metrics, charts, and Agent execution flows.

**Tech Stack:** Python, Streamlit, Plotly, pandas, pytest.

---

## File Structure

- Modify: `.streamlit/config.toml` for final theme colors if needed.
- Modify: `src/ui.py` for shared shell helpers, cards, panels, status badges, dataset summary, and CSS injection.
- Modify: `src/charts.py` for a shared Plotly template and consistent chart margins/legend styling.
- Modify: `app.py` for the redesigned Home screen.
- Modify: `pages/1_Overview.py` for KPI row, chart panels, and event panel layout.
- Modify: `pages/2_Spatiotemporal_Playback.py` for time console and map insight layout.
- Modify: `pages/3_Correlation_Analysis.py` for compact variable controls and chart panels.
- Modify: `pages/4_Historical_Data_Agent.py` for workflow grouping around existing Agent logic.
- Modify: `tests/test_navigation.py` only if navigation labels change.
- Add: `tests/test_ui_helpers.py` for pure helper behavior that can be tested without Streamlit rendering.

## Task 1: Add Shared UI Helper Tests

**Files:**

- Create: `tests/test_ui_helpers.py`
- Modify: `src/ui.py`

- [ ] **Step 1: Write failing tests for pure helper output**

```python
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.ui import dataset_summary, format_dataset_label, pollutant_display_label


def test_pollutant_display_label_uppercases_known_values() -> None:
    assert pollutant_display_label("pm25") == "PM25"
    assert pollutant_display_label("o3") == "O3"


def test_dataset_summary_reports_basic_shape() -> None:
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-01 00:00", "2024-01-02 00:00"]),
            "station_id": ["A", "B"],
            "pm25": [10.0, 20.0],
            "pm10": [30.0, 40.0],
            "temp": [5.0, 6.0],
        }
    )

    summary = dataset_summary(df, Path("data/processed/demo.csv"))

    assert summary["name"] == "demo"
    assert summary["format"] == "CSV"
    assert summary["rows"] == "2"
    assert summary["stations"] == "2"
    assert summary["date_range"] == "2024-01-01 - 2024-01-02"
    assert summary["pollutants"] == "PM25, PM10"


def test_format_dataset_label_keeps_existing_behavior() -> None:
    label = format_dataset_label(Path("data/processed/demo.parquet"))
    assert "demo" in label
    assert "PARQUET" in label
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ui_helpers.py -v`

Expected: FAIL because `dataset_summary` and `pollutant_display_label` do not exist yet.

- [ ] **Step 3: Implement pure helpers**

Add to `src/ui.py`:

```python
def pollutant_display_label(value: str) -> str:
    return value.upper()


def dataset_summary(df: pd.DataFrame, path: str | Path) -> dict[str, str]:
    dataset_path = Path(path)
    pollutant_columns = [col for col in POLLUTANT_COLUMNS if col in df.columns]

    if "timestamp" in df.columns and not df.empty:
        timestamps = pd.to_datetime(df["timestamp"].dropna())
        if timestamps.empty:
            date_range = "-"
        else:
            date_range = f"{timestamps.min():%Y-%m-%d} - {timestamps.max():%Y-%m-%d}"
    else:
        date_range = "-"

    stations = df["station_id"].nunique() if "station_id" in df.columns else 0

    return {
        "name": dataset_path.stem,
        "format": dataset_path.suffix.lstrip(".").upper() or "-",
        "path": str(dataset_path),
        "rows": f"{len(df):,}",
        "stations": f"{stations:,}",
        "date_range": date_range,
        "pollutants": ", ".join(pollutant_display_label(col) for col in pollutant_columns) or "-",
    }
```

- [ ] **Step 4: Run helper tests**

Run: `pytest tests/test_ui_helpers.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ui.py tests/test_ui_helpers.py
git commit -m "test: cover dashboard ui summary helpers"
```

## Task 2: Add Workbench Styling Primitives

**Files:**

- Modify: `src/ui.py`
- Test: `tests/test_ui_helpers.py`

- [ ] **Step 1: Extend tests for stable class names**

Append to `tests/test_ui_helpers.py`:

```python
from src.ui import status_badge_html


def test_status_badge_html_escapes_text_and_uses_variant_class() -> None:
    html = status_badge_html("<Ready>", "success")
    assert "&lt;Ready&gt;" in html
    assert "aq-badge--success" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ui_helpers.py::test_status_badge_html_escapes_text_and_uses_variant_class -v`

Expected: FAIL because `status_badge_html` does not exist yet.

- [ ] **Step 3: Add CSS and badge helpers**

Add imports and helpers to `src/ui.py`:

```python
from html import escape


def status_badge_html(label: str, variant: str = "neutral") -> str:
    safe_variant = variant if variant in {"neutral", "success", "warning", "danger", "running"} else "neutral"
    return f'<span class="aq-badge aq-badge--{safe_variant}">{escape(label)}</span>'


def inject_workbench_css() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2.5rem;
        }
        section[data-testid="stSidebar"] {
            border-right: 1px solid #d9e2ea;
        }
        .aq-page-kicker {
            color: #52606d;
            font-size: 0.84rem;
            margin-bottom: 0.2rem;
        }
        .aq-panel {
            border: 1px solid #d9e2ea;
            border-radius: 8px;
            background: #ffffff;
            padding: 1rem;
            margin-bottom: 1rem;
        }
        .aq-panel-title {
            color: #102a43;
            font-size: 0.96rem;
            font-weight: 650;
            margin-bottom: 0.5rem;
        }
        .aq-badge {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 0.12rem 0.5rem;
            font-size: 0.76rem;
            font-weight: 650;
            border: 1px solid transparent;
        }
        .aq-badge--neutral { background: #eef3f6; color: #334e68; border-color: #d9e2ea; }
        .aq-badge--success { background: #e6f4ea; color: #2f855a; border-color: #b7dfc2; }
        .aq-badge--warning { background: #fff7e6; color: #b7791f; border-color: #f4d27a; }
        .aq-badge--danger { background: #fff1ed; color: #c2410c; border-color: #f3b39b; }
        .aq-badge--running { background: #e8f4ff; color: #2563eb; border-color: #b8d7ff; }
        </style>
        """,
        unsafe_allow_html=True,
    )
```

- [ ] **Step 4: Run helper tests**

Run: `pytest tests/test_ui_helpers.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ui.py tests/test_ui_helpers.py
git commit -m "feat: add dashboard workbench styling helpers"
```

## Task 3: Apply Unified Shell to Home

**Files:**

- Modify: `app.py`
- Modify: `src/ui.py`

- [ ] **Step 1: Add render helpers**

Add to `src/ui.py`:

```python
def render_page_header(title: str, caption: str | None = None, kicker: str | None = None) -> None:
    if kicker:
        st.markdown(f'<div class="aq-page-kicker">{escape(kicker)}</div>', unsafe_allow_html=True)
    st.title(title)
    if caption:
        st.caption(caption)


def render_panel_start(title: str | None = None) -> None:
    st.markdown('<div class="aq-panel">', unsafe_allow_html=True)
    if title:
        st.markdown(f'<div class="aq-panel-title">{escape(title)}</div>', unsafe_allow_html=True)


def render_panel_end() -> None:
    st.markdown("</div>", unsafe_allow_html=True)
```

- [ ] **Step 2: Update `app.py`**

Use `inject_workbench_css`, `render_page_header`, and `dataset_summary`. Keep existing language selector and navigation.

```python
from src.ui import cached_load_dataset, dataset_path_from_env, dataset_summary, inject_workbench_css, render_page_header

inject_workbench_css()
active_dataset_path = dataset_path_from_env()

header_left, header_right = st.columns((5, 1.4))
with header_right:
    language = render_language_selector()

with header_left:
    render_page_header(t("app.title", language), t("app.caption", language), kicker=t("nav.home", language))

try:
    active_df = cached_load_dataset(active_dataset_path)
    summary = dataset_summary(active_df, active_dataset_path)
except Exception as exc:  # noqa: BLE001
    st.error(t("common.failed_to_load_dataset", language, error=exc))
    st.stop()

summary_cols = st.columns(5)
summary_cols[0].metric(t("ui.dataset"), summary["name"])
summary_cols[1].metric("Format", summary["format"])
summary_cols[2].metric("Rows", summary["rows"])
summary_cols[3].metric(t("ui.stations"), summary["stations"])
summary_cols[4].metric(t("ui.primary_pollutant"), summary["pollutants"])

st.info(t("app.active_dataset", language, path=active_dataset_path))

nav_cols = st.columns(4)
nav_cols[0].page_link("pages/1_Overview.py", label=t("overview.page_title", language))
nav_cols[1].page_link("pages/2_Spatiotemporal_Playback.py", label=t("playback.page_title", language))
nav_cols[2].page_link("pages/3_Correlation_Analysis.py", label=t("correlation.page_title", language))
nav_cols[3].page_link("pages/4_Historical_Data_Agent.py", label=t("agent.page_title", language))
```

- [ ] **Step 3: Run targeted tests**

Run: `pytest tests/test_ui_helpers.py tests/test_navigation.py tests/test_i18n.py -v`

Expected: PASS.

- [ ] **Step 4: Launch Streamlit smoke check**

Run: `python -m streamlit run app.py`

Expected: Home loads, the sidebar navigation is still visible, language selector works, and no dataset summary field overflows.

- [ ] **Step 5: Commit**

```bash
git add app.py src/ui.py tests/test_ui_helpers.py
git commit -m "feat: redesign dashboard home shell"
```

## Task 4: Standardize Plotly Figure Theme

**Files:**

- Modify: `src/charts.py`
- Test: existing chart and metrics tests.

- [ ] **Step 1: Add a chart theme helper**

Add to `src/charts.py`:

```python
def apply_dashboard_chart_theme(fig: go.Figure) -> go.Figure:
    fig.update_layout(
        paper_bgcolor="white",
        plot_bgcolor="white",
        font={"color": "#102A43", "size": 12},
        title={"font": {"size": 15, "color": "#102A43"}},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        margin=dict(l=12, r=12, t=48, b=16),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#EEF3F6", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="#EEF3F6", zeroline=False)
    return fig
```

- [ ] **Step 2: Apply helper to existing chart functions**

At the end of `trend_figure`, `ranking_figure`, `map_figure`, `correlation_heatmap`, and `scatter_with_regression`, replace or follow existing `update_layout` calls with:

```python
return apply_dashboard_chart_theme(fig)
```

- [ ] **Step 3: Run chart-adjacent tests**

Run: `pytest tests/test_metrics.py tests/test_data.py -v`

Expected: PASS.

- [ ] **Step 4: Visual smoke check**

Run: `python -m streamlit run app.py`

Expected: Plotly charts keep their data and titles, with consistent margins and legends.

- [ ] **Step 5: Commit**

```bash
git add src/charts.py
git commit -m "feat: apply consistent dashboard chart theme"
```

## Task 5: Redesign Overview Page Layout

**Files:**

- Modify: `pages/1_Overview.py`
- Modify: `src/ui.py` only if a new helper is clearly reusable.

- [ ] **Step 1: Inject CSS and page header**

Add `inject_workbench_css` and `render_page_header` imports, call `inject_workbench_css()` after `st.set_page_config`, and replace `st.title(...)` with:

```python
render_page_header(t("overview.title", language), kicker=t("overview.page_title", language))
```

- [ ] **Step 2: Wrap charts in named sections**

Use `st.subheader` or `render_panel_start`/`render_panel_end` around trend, ranking, and events. Keep existing calls to `compute_metrics`, `compute_station_ranking`, `trend_figure`, `ranking_figure`, and `detect_events`.

- [ ] **Step 3: Keep event detection behavior intact**

The checkbox must still control expensive event calculation:

```python
if st.checkbox(t("overview.compute_events", language), value=False):
    events = detect_events(filtered, pollutant=pollutant, language=language)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_metrics.py tests/test_i18n.py -v`

Expected: PASS.

- [ ] **Step 5: Manual acceptance**

Run: `python -m streamlit run app.py`, open Overview, confirm KPI row, trend chart, ranking chart, empty-filter warning, and event expander work.

- [ ] **Step 6: Commit**

```bash
git add pages/1_Overview.py src/ui.py
git commit -m "feat: redesign overview analysis layout"
```

## Task 6: Redesign Playback Page Layout

**Files:**

- Modify: `pages/2_Spatiotemporal_Playback.py`

- [ ] **Step 1: Add shared shell helpers**

Import and call `inject_workbench_css()` and `render_page_header(...)`.

- [ ] **Step 2: Put time controls in a right-side console**

Create columns:

```python
map_col, control_col = st.columns((3, 1))
```

Move day, hour, playback span, play button, and hotspot spread into `control_col`. Keep `build_map_frame` and playback loop unchanged.

- [ ] **Step 3: Keep map dominant**

Render `map_figure(frame, pollutant, language=language)` inside `map_col` with `use_container_width=True`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_data.py tests/test_i18n.py -v`

Expected: PASS.

- [ ] **Step 5: Manual acceptance**

Run: `python -m streamlit run app.py`, open Playback, select day/hour, press play, and confirm animated frames still update.

- [ ] **Step 6: Commit**

```bash
git add pages/2_Spatiotemporal_Playback.py
git commit -m "feat: redesign spatiotemporal playback controls"
```

## Task 7: Redesign Correlation Page Layout

**Files:**

- Modify: `pages/3_Correlation_Analysis.py`

- [ ] **Step 1: Add shared shell helpers**

Import and call `inject_workbench_css()` and `render_page_header(...)`.

- [ ] **Step 2: Keep variable control compact**

Place weather variable selectbox above the two-chart grid, with a short caption showing selected pollutant and sample cap.

- [ ] **Step 3: Preserve chart logic**

Keep `scatter_with_regression(filtered, weather_col, pollutant, max_points=7000, language=language)` and `compute_correlations(filtered, pollutants=pollutants, weather=weather_options)` unchanged.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_metrics.py tests/test_i18n.py -v`

Expected: PASS.

- [ ] **Step 5: Manual acceptance**

Run: `python -m streamlit run app.py`, open Correlation Analysis, change weather variable, and confirm scatter, heatmap, and station daily comparison update.

- [ ] **Step 6: Commit**

```bash
git add pages/3_Correlation_Analysis.py
git commit -m "feat: redesign correlation analysis layout"
```

## Task 8: Redesign Historical Data Agent Workflow

**Files:**

- Modify: `pages/4_Historical_Data_Agent.py`
- Test: existing Agent tests.

- [ ] **Step 1: Add shared shell helpers**

Import and call `inject_workbench_css()` and `render_page_header(...)`. Keep all existing state keys unchanged.

- [ ] **Step 2: Group existing controls into workflow sections**

Use visible section headings:

```python
st.subheader("1. 城市与范围")
st.subheader("2. 采集参数")
st.subheader("3. 计划与采集")
st.subheader("4. 任务状态")
st.subheader("5. 结果预览")
```

Do not rename state keys such as `AQ_AGENT_YEAR_RANGE`, `CUSTOM_CITY_NAME_KEY`, `CURRENT_TASK_KEY`, or `SYNCED_TASK_RESULT_KEY`.

- [ ] **Step 3: Keep task start behavior unchanged**

The button logic must still call `_start_custom_task(action)` and `_submit_custom_city_task(...)` exactly once per click.

- [ ] **Step 4: Keep result preview behavior unchanged**

The output path preview, download buttons, trend chart, and links to Overview/Playback must remain available after a successful run.

- [ ] **Step 5: Run Agent tests**

Run: `pytest tests/test_agent_task_ui.py tests/test_agent_task_store.py tests/test_agent_task_runner.py tests/test_agent_task_executor.py tests/test_agent_interaction.py -v`

Expected: PASS.

- [ ] **Step 6: Manual acceptance**

Run: `python -m streamlit run app.py`, open Historical Data Agent, verify API-key-missing, validation, task status, and result preview states if local secrets/data allow.

- [ ] **Step 7: Commit**

```bash
git add pages/4_Historical_Data_Agent.py
git commit -m "feat: redesign historical data agent workflow"
```

## Task 9: Final Verification

**Files:**

- No planned edits.

- [ ] **Step 1: Run focused test suite**

Run:

```bash
pytest tests/test_navigation.py tests/test_i18n.py tests/test_metrics.py tests/test_data.py tests/test_ui_helpers.py -v
```

Expected: PASS.

- [ ] **Step 2: Run Agent regression tests**

Run:

```bash
pytest tests/test_agent_task_ui.py tests/test_agent_task_store.py tests/test_agent_task_runner.py tests/test_agent_task_executor.py tests/test_agent_interaction.py -v
```

Expected: PASS.

- [ ] **Step 3: Run full suite if local dependencies are available**

Run:

```bash
pytest -q
```

Expected: PASS. If it fails due to missing external secrets or environment-specific services, capture exact failures and confirm all local UI/layout tests pass.

- [ ] **Step 4: Manual UI review**

Run:

```bash
python -m streamlit run app.py
```

Review Home, Overview, Playback, Correlation Analysis, and Historical Data Agent at desktop width. Confirm no Chinese labels overflow, no chart legends cover chart data, and sidebar navigation remains stable.

- [ ] **Step 5: Commit final polish**

```bash
git status --short
git add .streamlit/config.toml app.py pages src tests
git commit -m "feat: polish air quality dashboard redesign"
```

## Risk Controls

- Do not touch data collection, task execution, storage backends, or dataset parsing unless a UI test proves a narrow helper is required.
- Do not rename existing Streamlit session-state keys.
- Do not introduce React, custom Streamlit components, or a new frontend build step.
- Do not revert unrelated dirty-worktree changes.
- Keep Plotly chart data and metric computations unchanged while visual styling is adjusted.
