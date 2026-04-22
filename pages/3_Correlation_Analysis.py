from __future__ import annotations

import plotly.express as px
import streamlit as st

from src.charts import correlation_heatmap, scatter_with_regression
from src.metrics import compute_correlations
from src.ui import cached_load_dataset, dataset_path_from_env, render_filters

st.set_page_config(page_title="Correlation Analysis", layout="wide")
st.title("Correlation Analysis")

try:
    df = cached_load_dataset(str(dataset_path_from_env()))
except Exception as exc:  # noqa: BLE001
    st.error(f"Failed to load dataset: {exc}")
    st.stop()

filtered, pollutant, pollutants = render_filters(df)
if filtered.empty:
    st.warning("No data after filters. Adjust the sidebar filters.")
    st.stop()

weather_col = st.selectbox("Weather variable", ["temp", "humidity", "wind_speed"], index=0)
left, right = st.columns((1, 1))
with left:
    st.plotly_chart(
        scatter_with_regression(filtered, weather_col, pollutant, max_points=7000),
        use_container_width=True,
        config={"displayModeBar": False},
    )
with right:
    corr = compute_correlations(filtered, pollutants=pollutants, weather=["temp", "humidity", "wind_speed"])
    st.plotly_chart(correlation_heatmap(corr), use_container_width=True, config={"displayModeBar": False})

station_compare = (
    filtered.set_index("timestamp")
    .groupby("station_id", observed=True)[pollutant]
    .resample("D")
    .mean()
    .reset_index()
)
fig = px.line(station_compare, x="timestamp", y=pollutant, color="station_id", title="Station daily comparison")
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
