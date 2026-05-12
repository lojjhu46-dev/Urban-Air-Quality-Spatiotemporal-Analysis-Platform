from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from src.config import AQ_AGENT_OUTPUT_DIR, DEFAULT_DATA_PATH, POLLUTANT_COLUMNS
from src.data import (
    filter_dataset,
    load_dataset,
    pyarrow_runtime_available,
    resolve_existing_dataset_path,
)
from src.dataset_registry import dataset_registry_from_config
from src.dataset_storage import is_remote_storage_uri
from src.i18n import t

DATASET_OVERRIDE_KEY = "data_path_override"
DATASET_CHOICE_KEY = "dataset_path_choice"
PENDING_DATASET_CHOICE_KEY = "pending_dataset_path_choice"
_REGISTRY_LABEL_CACHE: dict[str, str] = {}


def _configured_default_dataset_path() -> Path:
    raw = None
    try:
        raw = st.secrets.get("data_path")
    except Exception:  # noqa: BLE001
        raw = None

    if raw:
        return Path(raw)
    return DEFAULT_DATA_PATH


def discover_dataset_paths(root: Path | None = None) -> list[str]:
    search_root = root or DEFAULT_DATA_PATH.parent
    candidates: list[str] = []
    for pattern in ("*.parquet", "*.csv"):
        for path in sorted(search_root.rglob(pattern)):
            candidates.append(str(path))

    if AQ_AGENT_OUTPUT_DIR.exists():
        for pattern in ("*.parquet", "*.csv"):
            for path in sorted(AQ_AGENT_OUTPUT_DIR.rglob(pattern)):
                candidates.append(str(path))
    candidates.extend(_indexed_dataset_paths())

    seen: set[str] = set()
    unique_paths: list[str] = []
    default_path = resolve_existing_dataset_path(_configured_default_dataset_path())
    for raw in [str(default_path), *candidates]:
        if raw in seen:
            continue
        seen.add(raw)
        unique_paths.append(raw)
    return unique_paths


def _indexed_dataset_paths() -> list[str]:
    try:
        database_url = None
        try:
            database_url = st.secrets.get("database_url") or st.secrets.get("DATABASE_URL")
        except Exception:  # noqa: BLE001
            database_url = None
        entries = dataset_registry_from_config(database_url).list_entries()
    except Exception:  # noqa: BLE001
        return []

    paths: list[str] = []
    for entry in entries:
        if is_remote_storage_uri(entry.storage_uri):
            paths.append(entry.storage_uri)
            continue
        path = Path(entry.storage_uri)
        if path.exists() and path.suffix.lower() in {".parquet", ".csv"}:
            paths.append(str(path))
    return paths


def format_dataset_label(path: str | Path) -> str:
    raw = str(path)
    registry_label = _dataset_registry_label(raw)
    if registry_label:
        return registry_label
    if is_remote_storage_uri(raw):
        return raw
    path = Path(raw)
    try:
        relative = path.relative_to(Path.cwd())
        suffix = relative.as_posix()
    except ValueError:
        suffix = str(path)
    return f"{path.stem} [{path.suffix.lstrip('.').upper()}] ({suffix})"


def _dataset_registry_label(raw: str) -> str | None:
    if raw in _REGISTRY_LABEL_CACHE:
        return _REGISTRY_LABEL_CACHE[raw] or None

    try:
        database_url = None
        try:
            database_url = st.secrets.get("database_url") or st.secrets.get("DATABASE_URL")
        except Exception:  # noqa: BLE001
            database_url = None
        entry = dataset_registry_from_config(database_url).find_by_uri(raw)
    except Exception:  # noqa: BLE001
        entry = None

    if entry is None or not entry.city:
        _REGISTRY_LABEL_CACHE[raw] = ""
        return None

    date_range = ""
    if entry.start_date or entry.end_date:
        date_range = f" ({entry.start_date[:10]} ~ {entry.end_date[:10]})"
    label = f"{entry.city} [{entry.format.upper()}]{date_range}"
    _REGISTRY_LABEL_CACHE[raw] = label
    return label


def dataset_path_from_env(show_selector: bool = True) -> str:
    configured_default = resolve_existing_dataset_path(_configured_default_dataset_path())

    pending_choice = st.session_state.pop(PENDING_DATASET_CHOICE_KEY, None)
    if pending_choice is not None:
        resolved_pending = str(pending_choice) if is_remote_storage_uri(pending_choice) else str(resolve_existing_dataset_path(pending_choice))
        st.session_state[DATASET_OVERRIDE_KEY] = str(resolved_pending)
        st.session_state[DATASET_CHOICE_KEY] = str(resolved_pending)

    override_value = st.session_state.get(DATASET_OVERRIDE_KEY, configured_default)
    selected_default = str(override_value) if is_remote_storage_uri(override_value) else str(resolve_existing_dataset_path(Path(override_value)))
    dataset_paths = discover_dataset_paths()

    if selected_default not in set(dataset_paths):
        dataset_paths.insert(0, selected_default)

    if not show_selector or len(dataset_paths) <= 1:
        st.session_state[DATASET_OVERRIDE_KEY] = selected_default
        return selected_default

    options = list(dataset_paths)
    choice_value = st.session_state.get(DATASET_CHOICE_KEY, selected_default)
    current_value = str(choice_value) if is_remote_storage_uri(choice_value) else str(resolve_existing_dataset_path(choice_value))
    if current_value not in options:
        current_value = selected_default

    selected = st.sidebar.selectbox(
        t("ui.dataset"),
        options=options,
        index=options.index(current_value),
        format_func=format_dataset_label,
        key=DATASET_CHOICE_KEY,
    )
    resolved_selected = selected if is_remote_storage_uri(selected) else str(resolve_existing_dataset_path(selected))
    st.session_state[DATASET_OVERRIDE_KEY] = resolved_selected
    st.sidebar.caption(t("ui.dataset_hint"))
    return resolved_selected


@st.cache_data(show_spinner=False)
def cached_load_dataset(path: str) -> pd.DataFrame:
    return load_dataset(path)


def render_dataframe(
    df: pd.DataFrame,
    *,
    hide_index: bool = False,
    use_container_width: bool = True,
) -> None:
    if pyarrow_runtime_available():
        st.dataframe(df, hide_index=hide_index, use_container_width=use_container_width)
        return

    html = df.to_html(index=not hide_index, escape=True)
    wrapper = html
    if use_container_width:
        wrapper = f'<div style="width:100%; overflow-x:auto;">{html}</div>'
    st.markdown(wrapper, unsafe_allow_html=True)


def render_filters(
    df: pd.DataFrame,
    default_pollutant: str = "pm25",
    default_days: int = 180,
) -> tuple[pd.DataFrame, str, list[str]]:
    st.sidebar.header(t("ui.filters"))

    min_date = df["timestamp"].min().date()
    max_date = df["timestamp"].max().date()

    default_start = max(min_date, max_date - timedelta(days=max(default_days - 1, 0)))

    selected_dates = st.sidebar.date_input(
        t("ui.date_range"),
        (default_start, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if len(selected_dates) != 2:
        selected_dates = (default_start, max_date)

    stations = sorted(df["station_id"].dropna().unique().tolist())
    selected_stations = st.sidebar.multiselect(t("ui.stations"), stations, default=stations)

    pollutants = [col for col in POLLUTANT_COLUMNS if col in df.columns]
    default_idx = pollutants.index(default_pollutant) if default_pollutant in pollutants else 0
    selected_pollutant = st.sidebar.selectbox(t("ui.primary_pollutant"), pollutants, index=default_idx)

    filtered = filter_dataset(
        df,
        date_range=(selected_dates[0], selected_dates[1]),
        stations=selected_stations,
        pollutants=pollutants,
    )

    st.sidebar.caption(t("ui.performance_hint"))

    return filtered, selected_pollutant, pollutants
