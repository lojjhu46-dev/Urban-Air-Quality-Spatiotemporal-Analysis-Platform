from __future__ import annotations

import importlib
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.config import DEFAULT_DATA_PATH, TIMEZONE

TABULAR_SUFFIXES = (".parquet", ".csv")


@lru_cache(maxsize=1)
def pyarrow_runtime_available() -> bool:
    try:
        importlib.import_module("pyarrow")
    except Exception:  # noqa: BLE001
        return False
    return True


@lru_cache(maxsize=1)
def parquet_engine_available() -> bool:
    for module_name in ("pyarrow", "fastparquet"):
        try:
            importlib.import_module(module_name)
        except Exception:  # noqa: BLE001
            continue
        return True
    return False


def output_dataset_path(path: str | Path) -> Path:
    dataset_path = Path(path)
    suffix = dataset_path.suffix.lower()
    if suffix == ".parquet" and not parquet_engine_available():
        return dataset_path.with_suffix(".csv")
    if suffix in TABULAR_SUFFIXES:
        return dataset_path
    return dataset_path.with_suffix(".parquet" if parquet_engine_available() else ".csv")


def resolve_existing_dataset_path(path: str | Path) -> Path:
    dataset_path = Path(path)
    suffix = dataset_path.suffix.lower()

    if suffix == ".parquet" and not parquet_engine_available():
        csv_path = dataset_path.with_suffix(".csv")
        if csv_path.exists():
            return csv_path
    if dataset_path.exists():
        return dataset_path

    if suffix == ".parquet":
        csv_path = dataset_path.with_suffix(".csv")
        if csv_path.exists():
            return csv_path
    elif suffix == ".csv":
        parquet_path = dataset_path.with_suffix(".parquet")
        if parquet_path.exists() and parquet_engine_available():
            return parquet_path
    else:
        parquet_path = dataset_path.with_suffix(".parquet")
        csv_path = dataset_path.with_suffix(".csv")
        if parquet_path.exists() and parquet_engine_available():
            return parquet_path
        if csv_path.exists():
            return csv_path

    return output_dataset_path(dataset_path)


def write_dataset(df: pd.DataFrame, path: str | Path) -> Path:
    output_path = output_dataset_path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.suffix.lower() == ".parquet":
        df.to_parquet(output_path, index=False)
    elif output_path.suffix.lower() == ".csv":
        df.to_csv(output_path, index=False)
    else:
        raise ValueError(f"Unsupported dataset suffix: {output_path.suffix}")

    return output_path


def _normalize_timestamp_series(ts: pd.Series) -> pd.Series:
    converted = pd.to_datetime(ts, utc=False)
    if converted.dt.tz is None:
        return converted.dt.tz_localize(TIMEZONE)
    return converted.dt.tz_convert(TIMEZONE)


def _maybe_generate_demo_dataset(dataset_path: Path) -> None:
    target_path = output_dataset_path(dataset_path)
    if target_path.exists():
        return

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "generate_demo_data.py"
    if not script_path.exists():
        return

    target_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(script_path),
        "--out",
        str(target_path),
        "--days",
        "90",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _should_bootstrap_default_csv(requested_path: Path, resolved_path: Path) -> bool:
    return (
        requested_path == DEFAULT_DATA_PATH
        and requested_path.suffix.lower() == ".parquet"
        and not parquet_engine_available()
        and resolved_path.suffix.lower() == ".parquet"
        and not resolved_path.with_suffix(".csv").exists()
    )


def _read_dataset_frame(dataset_path: Path) -> pd.DataFrame:
    suffix = dataset_path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(dataset_path)
    if suffix == ".csv":
        return pd.read_csv(dataset_path)
    raise ValueError(f"Unsupported dataset suffix: {dataset_path.suffix}")


def load_dataset(path: str | Path | None = None) -> pd.DataFrame:
    """Load processed dataset with lightweight dtypes for faster interaction."""
    requested_path = Path(path) if path else DEFAULT_DATA_PATH
    dataset_path = resolve_existing_dataset_path(requested_path)

    if not dataset_path.exists() or _should_bootstrap_default_csv(requested_path, dataset_path):
        try:
            _maybe_generate_demo_dataset(requested_path)
        except Exception as exc:  # noqa: BLE001
            raise FileNotFoundError(
                f"Processed dataset not found at {requested_path} and demo bootstrap failed: {exc}"
            ) from exc
        dataset_path = resolve_existing_dataset_path(requested_path)

    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Processed dataset not found: {requested_path}. "
            "Build it with scripts/build_dataset.py or scripts/generate_demo_data.py"
        )

    df = _read_dataset_frame(dataset_path)
    if "timestamp" not in df.columns:
        raise ValueError("Dataset must include `timestamp` column.")

    df["timestamp"] = _normalize_timestamp_series(df["timestamp"])

    if "station_id" in df.columns:
        df["station_id"] = df["station_id"].astype("category")

    for col in df.select_dtypes(include=["float64", "int64", "int32"]).columns:
        if col != "timestamp":
            df[col] = pd.to_numeric(df[col], downcast="float")

    sort_columns = [col for col in ["timestamp", "station_id"] if col in df.columns]
    if sort_columns:
        df = df.sort_values(sort_columns)
    return df.reset_index(drop=True)


def filter_dataset(
    df: pd.DataFrame,
    date_range: tuple | list | None = None,
    stations: Iterable[str] | None = None,
    pollutants: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Filter dataframe by date range, stations, and pollutant availability."""
    if df.empty:
        return df.copy()

    mask = pd.Series(True, index=df.index)

    if date_range and len(date_range) == 2:
        start = pd.Timestamp(date_range[0])
        end = pd.Timestamp(date_range[1])
        start = start.tz_localize(TIMEZONE) if start.tz is None else start.tz_convert(TIMEZONE)
        end = end.tz_localize(TIMEZONE) if end.tz is None else end.tz_convert(TIMEZONE)
        end = end + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        mask &= (df["timestamp"] >= start) & (df["timestamp"] <= end)

    if stations:
        station_set = set(stations)
        mask &= df["station_id"].isin(station_set)

    out = df.loc[mask]

    if pollutants:
        available = [col for col in pollutants if col in out.columns]
        if available:
            out = out.dropna(subset=available, how="all")

    return out.reset_index(drop=True)


def build_map_frame(df: pd.DataFrame, pollutant: str, ts: pd.Timestamp) -> pd.DataFrame:
    """Build a station-level frame for one timestamp. Uses nearest hour fallback."""
    if df.empty:
        return df.copy()

    target = pd.Timestamp(ts)
    target = target.tz_localize(TIMEZONE) if target.tz is None else target.tz_convert(TIMEZONE)

    frame = df[df["timestamp"] == target]
    if frame.empty:
        all_ts = df["timestamp"].dropna().sort_values().unique()
        if len(all_ts) == 0:
            return frame
        nearest = min(all_ts, key=lambda item: abs(item - target))
        frame = df[df["timestamp"] == nearest]

    cols = ["timestamp", "station_id", "lat", "lon"]
    if pollutant in frame.columns:
        cols.append(pollutant)
    return frame[cols].reset_index(drop=True)
