from __future__ import annotations

import streamlit as st

from src.realtime import fetch_openaq_latest
from src.ui import cached_load_dataset, dataset_path_from_env

st.set_page_config(page_title="Realtime Monitor", layout="wide")
st.title("Realtime Monitor (Optional)")

dataset_path_from_env()
city = st.text_input("Realtime city", value=st.session_state.get("realtime_city", "Beijing"))
st.session_state["realtime_city"] = city

with st.spinner("Querying OpenAQ..."):
    realtime = fetch_openaq_latest(city=city, hours=24)

st.info(realtime["message"])

if realtime["success"] and not realtime["data"].empty:
    st.success(f"Realtime mode enabled for {city}. Coverage: {realtime['coverage']:.0%}")
    st.dataframe(realtime["data"].sort_values("timestamp", ascending=False), use_container_width=True)
else:
    st.warning("Realtime coverage too low. Falling back to latest historical snapshot.")
    try:
        historical = cached_load_dataset(str(dataset_path_from_env(show_selector=False)))
        latest_ts = historical["timestamp"].max()
        fallback = historical[historical["timestamp"] == latest_ts]
        st.dataframe(fallback, use_container_width=True)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Fallback failed: {exc}")
