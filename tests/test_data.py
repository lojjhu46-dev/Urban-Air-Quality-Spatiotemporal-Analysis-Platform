from __future__ import annotations

import pandas as pd

from src.data import build_map_frame, filter_dataset


def sample_df() -> pd.DataFrame:
    ts = pd.date_range("2025-01-01", periods=4, freq="h", tz="Asia/Shanghai")
    return pd.DataFrame(
        {
            "timestamp": [ts[0], ts[0], ts[1], ts[1]],
            "station_id": ["A", "B", "A", "B"],
            "lat": [39.9, 39.8, 39.9, 39.8],
            "lon": [116.4, 116.3, 116.4, 116.3],
            "pm25": [10.0, 20.0, 30.0, 40.0],
        }
    )


def test_filter_dataset_by_date_and_station() -> None:
    df = sample_df()
    out = filter_dataset(
        df,
        date_range=("2025-01-01", "2025-01-01"),
        stations=["A"],
        pollutants=["pm25"],
    )
    assert not out.empty
    assert out["station_id"].nunique() == 1
    assert out["station_id"].iloc[0] == "A"


def test_build_map_frame_nearest_timestamp_fallback() -> None:
    df = sample_df()
    missing_ts = pd.Timestamp("2025-01-01 00:30:00", tz="Asia/Shanghai")
    frame = build_map_frame(df, "pm25", missing_ts)
    assert not frame.empty
    assert "pm25" in frame.columns
    assert frame["station_id"].nunique() == 2
