from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from src.config import AQ_AGENT_OUTPUT_DIR, DEFAULT_DATA_PATH, POLLUTANT_COLUMNS
from src.data import filter_dataset, load_dataset

DATASET_OVERRIDE_KEY = "data_path_override"
DATASET_CHOICE_KEY = "dataset_path_choice"


def _configured_default_dataset_path() -> Path:
    raw = None
    try:
        raw = st.secrets.get("data_path")
    except Exception:  # noqa: BLE001
        raw = None

    if raw:
        return Path(raw)
    return DEFAULT_DATA_PATH


def discover_dataset_paths(root: Path | None = None) -> list[Path]:
    search_root = root or DEFAULT_DATA_PATH.parent
    candidates: list[Path] = []
    for path in sorted(search_root.rglob("*.parquet")):
        candidates.append(path)

    if AQ_AGENT_OUTPUT_DIR.exists():
        for path in sorted(AQ_AGENT_OUTPUT_DIR.rglob("*.parquet")):
            candidates.append(path)

    seen: set[str] = set()
    unique_paths: list[Path] = []
    for path in [DEFAULT_DATA_PATH, *candidates]:
        raw = str(path)
        if raw in seen:
            continue
        seen.add(raw)
        unique_paths.append(path)
    return unique_paths


def format_dataset_label(path: Path) -> str:
    try:
        relative = path.relative_to(Path.cwd())
        suffix = relative.as_posix()
    except ValueError:
        suffix = str(path)
    return f"{path.stem} ({suffix})"


def dataset_path_from_env(show_selector: bool = True) -> Path:
    configured_default = _configured_default_dataset_path()
    selected_default = Path(st.session_state.get(DATASET_OVERRIDE_KEY, configured_default))
    dataset_paths = discover_dataset_paths()

    if str(selected_default) not in {str(path) for path in dataset_paths}:
        dataset_paths.insert(0, selected_default)

    if not show_selector or len(dataset_paths) <= 1:
        st.session_state[DATASET_OVERRIDE_KEY] = str(selected_default)
        return selected_default

    options = [str(path) for path in dataset_paths]
    current_value = str(st.session_state.get(DATASET_CHOICE_KEY, selected_default))
    if current_value not in options:
        current_value = str(selected_default)

    selected = st.sidebar.selectbox(
        "Dataset",
        options=options,
        index=options.index(current_value),
        format_func=lambda raw: format_dataset_label(Path(raw)),
        key=DATASET_CHOICE_KEY,
    )
    st.session_state[DATASET_OVERRIDE_KEY] = selected
    st.sidebar.caption("Tip: agent-generated parquet files appear here automatically.")
    return Path(selected)


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
