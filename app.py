from __future__ import annotations

import streamlit as st

from src.ui import dataset_path_from_env

st.set_page_config(page_title="Air Quality Dashboard", layout="wide")

active_dataset_path = dataset_path_from_env()

st.title("City Air Quality Spatiotemporal Dashboard")
st.caption("Python 3.14 | Streamlit + Plotly | Historical Collection Agent")

st.markdown(
    """
This project delivers:
- Multi-filter linked analysis across pages
- Spatiotemporal map playback at station level
- Pollutant-weather correlation views
- Optional realtime panel with safe fallback
- A DeepSeek-assisted agent for collecting historical AQ data for a selected city

If processed data is missing, run one of these commands:
- `python scripts/generate_demo_data.py --out data/processed/beijing_aq.parquet`
- `python scripts/build_dataset.py --raw data/raw --out data/processed/beijing_aq.parquet`
"""
)

st.info(f"Active dataset path: `{active_dataset_path}`")
st.caption("Open the Historical Data Agent page to collect another city's archive and switch this app to the new parquet file.")
