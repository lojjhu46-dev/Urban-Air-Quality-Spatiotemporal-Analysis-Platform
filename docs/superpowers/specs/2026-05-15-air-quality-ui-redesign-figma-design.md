# Air Quality Dashboard UI Redesign Figma Design

## Goal

将现有 Streamlit 空气质量分析系统重设计为中文优先的研究分析工作台。Figma 交付物应覆盖首页、总览、时空回放、相关性分析、历史数据 Agent 五个桌面高保真页面，并给后续 Streamlit 落地保留清晰组件边界。

## Product Direction

系统当前由 `app.py`、`pages/1_Overview.py`、`pages/2_Spatiotemporal_Playback.py`、`pages/3_Correlation_Analysis.py`、`pages/4_Historical_Data_Agent.py` 组成，导航和语言切换集中在 `src/navigation.py` 与 `src/i18n.py`，筛选与数据集选择集中在 `src/ui.py`，图表集中在 `src/charts.py`。

重设计不做营销型首页，也不把界面变成低密度展示页。目标用户是需要反复筛选、比较、回放、采集数据的研究者或分析人员，因此界面应该安静、密集、可扫描，优先服务图表阅读和任务推进。

## Visual System

### Layout

- 桌面画板尺寸：1440 x 1024。
- 左侧固定导航：宽 240，包含产品名、数据集状态、五个页面入口、当前语言。
- 顶部工作区标题栏：高 88，包含页面标题、页面说明、当前数据时间范围、主要操作。
- 主内容区：使用 12 列网格，左右内边距 32，列间距 16。
- 筛选控件：默认保留在左侧导航下半区或页面右侧控制栏，不散落在图表之间。
- 图表面板：8px 圆角，浅色边框，标题区和图表区分离。

### Palette

- Background: `#F6F8FB`
- Surface: `#FFFFFF`
- Surface muted: `#EEF3F6`
- Border: `#D9E2EA`
- Text primary: `#102A43`
- Text secondary: `#52606D`
- Accent teal: `#0B7285`
- Accent blue: `#2563EB`
- Warning: `#B7791F`
- Danger: `#C2410C`
- Success: `#2F855A`
- Pollutant scale should use a multi-stop analytic ramp, not a decorative single-hue gradient.

### Typography

- Chinese UI copy should use a CJK-safe sans-serif such as Microsoft YaHei, PingFang SC, Noto Sans CJK SC, or the closest available Figma font.
- Page title: 28/36, semibold.
- Section title: 18/26, semibold.
- Panel title: 15/22, semibold.
- Body: 14/22.
- Caption and meta labels: 12/18.
- Numeric KPI values: 28/34, semibold, tabular style when available.

### Components

Create or map these Figma components:

- App Shell: left navigation, top title bar, content canvas.
- Nav Item: default, active, disabled.
- Dataset Status: file name, format, date range, station count.
- Filter Group: date range, station multiselect, pollutant select.
- KPI Card: label, value, unit, delta/status.
- Chart Panel: title, description/meta, toolbar slot, chart placeholder.
- Status Badge: success, warning, danger, neutral, running.
- Empty State: compact inline state for no data and no result.
- Agent Step Card: input, validation, plan, running, completed, failed.
- Task Timeline: queued, running, stalled, completed, failed.
- Table Preview Panel: title, row count, download actions.

## Page Specs

### Home

Purpose: Replace the current text-heavy landing view with an operational overview.

Content:

- Header: `空气质量分析工作台` with short caption about monitoring, replay, correlation and collection.
- Dataset summary strip: active dataset path, data format, date range, station count, pollutant coverage.
- Quick entry grid: 总览, 时空回放, 相关性分析, 历史数据 Agent.
- Recent Agent block: latest task status, output path if available, next action.
- Data readiness block: pyarrow availability, API key state, missing dataset/error state.

States:

- No dataset found: show compact repair guidance and keep navigation visible.
- Dataset loaded: emphasize quick analysis entry.

### Overview

Purpose: First analytical stop for understanding the selected dataset.

Content:

- Filter summary: date range, station count, pollutant.
- KPI row: 最新均值, 近 24 小时均值, 超标小时数, 站点差异.
- Main trend panel: daily pollutant trend by station.
- Station ranking panel: latest station ranking.
- Event detection panel: collapsed by default in Streamlit today, but visible in Figma as a secondary panel with table rows and severity badges.

Layout:

- KPI cards span the full width.
- Trend panel takes 8 columns, ranking takes 4 columns.
- Event detection spans full width beneath charts.

### Spatiotemporal Playback

Purpose: Make time selection and playback state feel like a control console.

Content:

- Time console: day selector, hour slider, span selector, play button, current frame timestamp.
- Map panel: station distribution by pollutant with color legend.
- Frame insight strip: hotspot spread, max station, min station, selected pollutant.
- Playback state: idle, playing, completed.

Layout:

- Map takes 9 columns, time console takes 3 columns.
- Current timestamp is visually prominent.
- Playback controls use icons where possible: play, pause, step, reset.

### Correlation Analysis

Purpose: Support exploratory comparison between weather variables and pollutants.

Content:

- Variable controls: weather variable, pollutant, station/date filters.
- Scatter regression panel.
- Correlation heatmap panel.
- Station daily comparison panel.
- Small explanation meta labels for sample cap and regression fit.

Layout:

- Scatter and heatmap are equal width.
- Station daily comparison spans full width.
- Controls stay compact and do not push charts below the fold.

### Historical Data Agent

Purpose: Turn the current long form into a legible multi-step workflow.

Content:

- Step 1: City input and stable city selector.
- Step 2: Collection parameters: year range, pollutants, weather fields.
- Step 3: Planner configuration: model, base URL, API key state, task store backend.
- Step 4: Request preview and primary actions: draft plan, plan and collect.
- Step 5: Task status and confirmation panel.
- Step 6: Result preview: plan summary, warnings, coverage table, trend chart, downloads, links to analysis pages.

States:

- API key missing: keep form editable, disable collection action or show clear error.
- Validation needs confirmation: warning card with confirm action.
- Task running: progress/timeline card with last heartbeat.
- Task stalled/failed: error panel with retry action.
- Task complete: result preview with download controls.

## Figma Execution Notes

The current Codex session does not expose a callable `use_figma` tool. When Figma MCP is connected, execute with the `figma-use` and `figma-generate-design` workflow:

1. Inspect existing Figma file pages, components, variables, styles, and naming conventions.
2. Preserve the existing page if the user wants overwrite; otherwise create a new page named `AQ Dashboard Redesign`.
3. Create local variables only if the file has no usable design-system variables. Use explicit scopes for fills, text, gaps, and radii.
4. Build the App Shell wrapper frame first, then append each page screen inside it or as sibling frames.
5. Build one screen per Figma call and validate with screenshots after each screen.
6. Use component instances for repeated controls where possible; use manually drawn chart placeholders only for chart content that Streamlit/Plotly will render.
7. Return all created and mutated node IDs from every Figma call.
8. Final validation must check for clipped Chinese text, overlapping controls, unreadable chart legends, and placeholder text left in components.

## Acceptance Criteria

- Five desktop screens exist and are named Home, Overview, Spatiotemporal Playback, Correlation Analysis, Historical Data Agent.
- Chinese copy is the primary visible copy; English may appear only where it matches code identifiers or component names.
- Navigation, dataset status, filter behavior, chart hierarchy, and Agent workflow correspond to the current Streamlit implementation.
- The design is implementable with Streamlit plus light CSS and helper components; it does not require replacing Streamlit with React.
- Empty, no-result, API-key-missing, task-running, task-completed, and task-failed states are represented.
- No screen relies on decorative gradients, oversized marketing hero sections, or low-density card walls.

## Out of Scope

- Rewriting data loading, metrics, Agent execution, or dataset storage.
- Adding new analysis algorithms beyond the existing metrics, charts, and task states.
- Creating a mobile-first app design. The initial target is desktop analytical use.
