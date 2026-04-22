from __future__ import annotations

import streamlit as st

from src.charts import ranking_figure, trend_figure
from src.metrics import compute_metrics, compute_station_ranking, detect_events
from src.ui import cached_load_dataset, dataset_path_from_env, render_filters

st.set_page_config(page_title="Overview", layout="wide")
st.title("Overview")

try:
    df = cached_load_dataset(str(dataset_path_from_env()))
except Exception as exc:  # noqa: BLE001
    st.error(f"Failed to load dataset: {exc}")
    st.stop()

filtered, pollutant, _pollutants = render_filters(df)

if filtered.empty:
    st.warning("No data after filters. Adjust the sidebar filters.")
    st.stop()

kpi = compute_metrics(filtered, pollutant=pollutant)
col1, col2, col3, col4 = st.columns(4)
col1.metric("Latest mean", f"{kpi['latest_mean']:.1f}")
col2.metric("Last 24h mean", f"{kpi['rolling_24h_mean']:.1f}")
col3.metric("Exceed hours", f"{kpi['exceed_hours']:.0f}")
col4.metric("Station spread", f"{kpi['station_spread']:.1f}")

left, right = st.columns((2, 1))
with left:
    st.plotly_chart(trend_figure(filtered, pollutant), use_container_width=True, config={"displayModeBar": False})
with right:
    ranking = compute_station_ranking(filtered, pollutant=pollutant, latest_only=True)
    st.plotly_chart(ranking_figure(ranking, pollutant), use_container_width=True, config={"displayModeBar": False})

if st.checkbox("Compute event annotations (slower)", value=False):
    events = detect_events(filtered, pollutant=pollutant)
    with st.expander("Detected event annotations", expanded=True):
        if events.empty:
            st.write("No events detected for current filter range.")
        else:
            st.dataframe(events.sort_values("timestamp", ascending=False), use_container_width=True)
