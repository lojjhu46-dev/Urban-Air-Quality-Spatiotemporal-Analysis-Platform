from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from src.config import DEFAULT_DATA_PATH, POLLUTANT_COLUMNS
from src.data import filter_dataset, load_dataset


def dataset_path_from_env() -> Path:
    raw = None
    try:
        raw = st.secrets.get("data_path")
    except Exception:  # noqa: BLE001
        raw = None

    if raw:
        return Path(raw)
    return DEFAULT_DATA_PATH


@st.cache_data(show_spinner=False)
def cached_load_dataset(path: str) -> pd.DataFrame:
    return load_dataset(path)


def render_filters(
    df: pd.DataFrame,
    default_pollutant: str = "pm25",
    default_days: int = 180,
) -> tuple[pd.DataFrame, str, list[str]]:
    st.sidebar.header("Global filters")

    min_date = df["timestamp"].min().date()
    max_date = df["timestamp"].max().date()

    default_start = max(min_date, max_date - timedelta(days=max(default_days - 1, 0)))

    selected_dates = st.sidebar.date_input(
        "Date range",
        (default_start, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if len(selected_dates) != 2:
        selected_dates = (default_start, max_date)

    stations = sorted(df["station_id"].dropna().unique().tolist())
    selected_stations = st.sidebar.multiselect("Stations", stations, default=stations)

    pollutants = [col for col in POLLUTANT_COLUMNS if col in df.columns]
    default_idx = pollutants.index(default_pollutant) if default_pollutant in pollutants else 0
    selected_pollutant = st.sidebar.selectbox("Primary pollutant", pollutants, index=default_idx)

    filtered = filter_dataset(
        df,
        date_range=(selected_dates[0], selected_dates[1]),
        stations=selected_stations,
        pollutants=pollutants,
    )

    st.sidebar.caption("Performance tip: keep date range focused (e.g., 30-180 days) for smoother interaction.")

    return filtered, selected_pollutant, pollutants
