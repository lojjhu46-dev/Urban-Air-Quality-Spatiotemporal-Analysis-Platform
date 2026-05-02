from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from src.charts import map_figure
from src.data import build_map_frame
from src.i18n import get_language, render_language_selector, t
from src.navigation import render_sidebar_navigation
from src.ui import cached_load_dataset, dataset_path_from_env, render_filters

language = get_language()
st.set_page_config(page_title=t("playback.page_title", language), layout="wide")

with st.sidebar:
    language = render_language_selector(key="language_selector_playback")
    render_sidebar_navigation(language)

st.title(t("playback.title", language))

try:
    df = cached_load_dataset(str(dataset_path_from_env()))
except Exception as exc:  # noqa: BLE001
    st.error(t("common.failed_to_load_dataset", language, error=exc))
    st.stop()

filtered, pollutant, _pollutants = render_filters(df, default_days=90)
if filtered.empty:
    st.warning(t("common.no_data_after_filters", language))
    st.stop()

available_ts = pd.to_datetime(filtered["timestamp"].dropna().sort_values().unique())
if len(available_ts) == 0:
    st.warning(t("playback.no_timestamp", language))
    st.stop()

available_days = sorted(pd.Series(available_ts).dt.date.unique().tolist())
selected_day = st.select_slider(t("playback.select_day", language), options=available_days, value=available_days[-1])
selected_hour = st.slider(t("playback.select_hour", language), min_value=0, max_value=23, value=12, step=1)

selected_ts = pd.Timestamp(f"{selected_day} {selected_hour:02d}:00:00", tz=available_ts[0].tz)

frame = build_map_frame(filtered, pollutant, selected_ts)
st.plotly_chart(
    map_figure(frame, pollutant, language=language),
    use_container_width=True,
    config={"displayModeBar": False},
)

playback_hours = st.slider(t("playback.span", language), min_value=6, max_value=24, value=12, step=6)
if st.button(t("playback.play_button", language)):
    placeholder = st.empty()
    for offset in range(playback_hours):
        ts = selected_ts + pd.Timedelta(hours=offset)
        anim_frame = build_map_frame(filtered, pollutant, ts)
        fig = map_figure(anim_frame, pollutant, language=language)
        fig.update_layout(title=t("playback.frame_title", language, pollutant=pollutant.upper(), timestamp=f"{ts:%Y-%m-%d %H:%M}"))
        placeholder.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        time.sleep(0.16)

spread = (
    frame.groupby("timestamp", observed=True)[pollutant].agg(["min", "max"]).reset_index()
    if pollutant in frame.columns and not frame.empty
    else pd.DataFrame()
)
if not spread.empty:
    st.caption(t("playback.hotspot_spread", language, value=float(spread["max"].iloc[0] - spread["min"].iloc[0])))
