from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.config import DEFAULT_DATA_PATH, TIMEZONE


def _normalize_timestamp_series(ts: pd.Series) -> pd.Series:
    converted = pd.to_datetime(ts, utc=False)
    if converted.dt.tz is None:
        return converted.dt.tz_localize(TIMEZONE)
    return converted.dt.tz_convert(TIMEZONE)


def _maybe_generate_demo_dataset(dataset_path: Path) -> None:
    if dataset_path.exists():
        return

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "generate_demo_data.py"
    if not script_path.exists():
        return

    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(script_path),
        "--out",
        str(dataset_path),
        "--days",
        "90",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def load_dataset(path: str | Path | None = None) -> pd.DataFrame:
    """Load processed dataset with lightweight dtypes for faster interaction."""
    dataset_path = Path(path) if path else DEFAULT_DATA_PATH

    if not dataset_path.exists():
        try:
            _maybe_generate_demo_dataset(dataset_path)
        except Exception as exc:  # noqa: BLE001
            raise FileNotFoundError(
                f"Processed dataset not found at {dataset_path} and demo bootstrap failed: {exc}"
            ) from exc

    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Processed dataset not found: {dataset_path}. "
            "Build it with scripts/build_dataset.py or scripts/generate_demo_data.py"
        )

    df = pd.read_parquet(dataset_path)
    if "timestamp" not in df.columns:
        raise ValueError("Dataset must include `timestamp` column.")

    df["timestamp"] = _normalize_timestamp_series(df["timestamp"])

    if "station_id" in df.columns:
        df["station_id"] = df["station_id"].astype("category")

    # Downcast numeric columns to reduce memory pressure on reruns.
    for col in df.select_dtypes(include=["float64", "int64", "int32"]).columns:
        if col != "timestamp":
            df[col] = pd.to_numeric(df[col], downcast="float")

    return df.sort_values(["timestamp", "station_id"]).reset_index(drop=True)


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
