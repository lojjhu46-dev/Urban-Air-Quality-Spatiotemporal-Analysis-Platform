from __future__ import annotations

import plotly.express as px
import streamlit as st

from src.charts import correlation_heatmap, scatter_with_regression
from src.i18n import get_language, render_language_selector, t, weather_label
from src.metrics import compute_correlations
from src.navigation import render_sidebar_navigation
from src.ui import cached_load_dataset, dataset_path_from_env, render_filters

language = get_language()
st.set_page_config(page_title=t("correlation.page_title", language), layout="wide")

with st.sidebar:
    language = render_language_selector(key="language_selector_correlation")
    render_sidebar_navigation(language)

st.title(t("correlation.title", language))

try:
    df = cached_load_dataset(str(dataset_path_from_env()))
except Exception as exc:  # noqa: BLE001
    st.error(t("common.failed_to_load_dataset", language, error=exc))
    st.stop()

filtered, pollutant, pollutants = render_filters(df)
if filtered.empty:
    st.warning(t("common.no_data_after_filters", language))
    st.stop()

weather_options = ["temp", "humidity", "wind_speed"]
weather_col = st.selectbox(
    t("correlation.weather_variable", language),
    weather_options,
    index=0,
    format_func=lambda key: weather_label(key, language),
)
left, right = st.columns((1, 1))
with left:
    st.plotly_chart(
        scatter_with_regression(filtered, weather_col, pollutant, max_points=7000, language=language),
        use_container_width=True,
        config={"displayModeBar": False},
    )
with right:
    corr = compute_correlations(filtered, pollutants=pollutants, weather=weather_options)
    st.plotly_chart(
        correlation_heatmap(corr, language=language),
        use_container_width=True,
        config={"displayModeBar": False},
    )

station_compare = (
    filtered.set_index("timestamp")
    .groupby("station_id", observed=True)[pollutant]
    .resample("D")
    .mean()
    .reset_index()
)
fig = px.line(
    station_compare,
    x="timestamp",
    y=pollutant,
    color="station_id",
    render_mode="svg",
    title=t("correlation.station_daily_comparison", language),
)
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
