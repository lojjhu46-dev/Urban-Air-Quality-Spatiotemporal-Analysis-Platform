from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from src.charts import map_figure
from src.data import build_map_frame
from src.ui import cached_load_dataset, dataset_path_from_env, render_filters

st.set_page_config(page_title="Spatiotemporal Playback", layout="wide")
st.title("Spatiotemporal Playback")

try:
    df = cached_load_dataset(str(dataset_path_from_env()))
except Exception as exc:  # noqa: BLE001
    st.error(f"Failed to load dataset: {exc}")
    st.stop()

filtered, pollutant, _pollutants = render_filters(df, default_days=90)
if filtered.empty:
    st.warning("No data after filters. Adjust the sidebar filters.")
    st.stop()

available_ts = pd.to_datetime(filtered["timestamp"].dropna().sort_values().unique())
if len(available_ts) == 0:
    st.warning("No timestamp values after filtering.")
    st.stop()

available_days = sorted(pd.Series(available_ts).dt.date.unique().tolist())
selected_day = st.select_slider("Select day", options=available_days, value=available_days[-1])
selected_hour = st.slider("Select hour", min_value=0, max_value=23, value=12, step=1)
detailed_tiles = st.checkbox("Use detailed map tiles (slower)", value=False)

selected_ts = pd.Timestamp(f"{selected_day} {selected_hour:02d}:00:00", tz=available_ts[0].tz)

frame = build_map_frame(filtered, pollutant, selected_ts)
st.plotly_chart(
    map_figure(frame, pollutant, detailed_tiles=detailed_tiles),
    use_container_width=True,
    config={"displayModeBar": False},
)

playback_hours = st.slider("Playback span (hours)", min_value=6, max_value=24, value=12, step=6)
if st.button("Play hourly animation"):
    placeholder = st.empty()
    for offset in range(playback_hours):
        ts = selected_ts + pd.Timedelta(hours=offset)
        anim_frame = build_map_frame(filtered, pollutant, ts)
        fig = map_figure(anim_frame, pollutant, detailed_tiles=detailed_tiles)
        fig.update_layout(title=f"{pollutant.upper()} @ {ts:%Y-%m-%d %H:%M}")
        placeholder.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        time.sleep(0.16)

spread = (
    frame.groupby("timestamp", observed=True)[pollutant].agg(["min", "max"]).reset_index()
    if pollutant in frame.columns and not frame.empty
    else pd.DataFrame()
)
if not spread.empty:
    st.caption(f"Hotspot spread at selected hour: {float(spread['max'].iloc[0] - spread['min'].iloc[0]):.1f}")
