from __future__ import annotations

import streamlit as st

from src.charts import ranking_figure, trend_figure
from src.i18n import get_language, render_language_selector, t
from src.metrics import compute_metrics, compute_station_ranking, detect_events
from src.navigation import render_sidebar_navigation
from src.ui import cached_load_dataset, dataset_path_from_env, render_dataframe, render_filters

language = get_language()
st.set_page_config(page_title=t("overview.page_title", language), layout="wide")

with st.sidebar:
    language = render_language_selector(key="language_selector_overview")
    render_sidebar_navigation(language)

st.title(t("overview.title", language))

try:
    df = cached_load_dataset(str(dataset_path_from_env()))
except Exception as exc:  # noqa: BLE001
    st.error(t("common.failed_to_load_dataset", language, error=exc))
    st.stop()

filtered, pollutant, _pollutants = render_filters(df)

if filtered.empty:
    st.warning(t("common.no_data_after_filters", language))
    st.stop()

kpi = compute_metrics(filtered, pollutant=pollutant)
col1, col2, col3, col4 = st.columns(4)
col1.metric(t("overview.latest_mean", language), f"{kpi['latest_mean']:.1f}")
col2.metric(t("overview.last_24h_mean", language), f"{kpi['rolling_24h_mean']:.1f}")
col3.metric(t("overview.exceed_hours", language), f"{kpi['exceed_hours']:.0f}")
col4.metric(t("overview.station_spread", language), f"{kpi['station_spread']:.1f}")

left, right = st.columns((2, 1))
with left:
    st.plotly_chart(
        trend_figure(filtered, pollutant, language=language),
        use_container_width=True,
        config={"displayModeBar": False},
    )
with right:
    ranking = compute_station_ranking(filtered, pollutant=pollutant, latest_only=True)
    st.plotly_chart(
        ranking_figure(ranking, pollutant, language=language),
        use_container_width=True,
        config={"displayModeBar": False},
    )

if st.checkbox(t("overview.compute_events", language), value=False):
    events = detect_events(filtered, pollutant=pollutant, language=language)
    with st.expander(t("overview.detected_events", language), expanded=True):
        if events.empty:
            st.write(t("overview.no_events", language))
        else:
            render_dataframe(events.sort_values("timestamp", ascending=False), use_container_width=True)
