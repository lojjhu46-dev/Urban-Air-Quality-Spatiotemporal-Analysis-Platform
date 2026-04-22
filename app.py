from __future__ import annotations

import streamlit as st

from src.config import DEFAULT_DATA_PATH

st.set_page_config(page_title="Beijing AQ Dashboard", layout="wide")

st.title("Beijing Air Quality Spatiotemporal Dashboard")
st.caption("Python 3.14 | Streamlit + Plotly")

st.markdown(
    """
This project delivers:
- Multi-filter linked analysis across pages
- Spatiotemporal map playback at station level
- Pollutant-weather correlation views
- Optional realtime panel with safe fallback

If processed data is missing, run one of these commands:
- `python scripts/generate_demo_data.py --out data/processed/beijing_aq.parquet`
- `python scripts/build_dataset.py --raw data/raw --out data/processed/beijing_aq.parquet`
"""
)

st.info(f"Default dataset path: `{DEFAULT_DATA_PATH}`")
