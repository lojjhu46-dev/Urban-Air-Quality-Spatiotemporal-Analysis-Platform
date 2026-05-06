from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from src.collection_data_pipeline import (
    _normalize_local_times,
    chunk_date_range,
    finalize_collected_dataset,
    summarize_dataset_coverage,
    weather_archive_chunk_window,
)


@dataclass(frozen=True, slots=True)
class FakeCandidate:
    name: str = "Shanghai"
    country_code: str = "CN"
    open_meteo_id: int | None = 1796236
    is_europe: bool = False


def test_data_pipeline_chunk_date_range_is_inclusive() -> None:
    chunks = chunk_date_range(date(2024, 1, 1), date(2024, 2, 5), chunk_days=30)

    assert chunks == [
        {"start_date": "2024-01-01", "end_date": "2024-01-30"},
        {"start_date": "2024-01-31", "end_date": "2024-02-05"},
    ]


def test_data_pipeline_weather_archive_chunk_window_clips_recent_days() -> None:
    chunk = {"start_date": "2026-03-21", "end_date": "2026-05-05"}

    assert weather_archive_chunk_window(chunk, today=date(2026, 5, 5)) == ("2026-03-21", "2026-04-30")
    assert weather_archive_chunk_window({"start_date": "2026-05-01", "end_date": "2026-05-05"}, today=date(2026, 5, 5)) is None


def test_data_pipeline_normalize_local_times_handles_dst_gaps() -> None:
    out = _normalize_local_times(
        ["2023-03-26 01:00:00", "2023-03-26 02:00:00", "2023-03-26 03:00:00"],
        "Europe/Berlin",
    )

    assert out.notna().tolist() == [True, False, True]


def test_data_pipeline_finalize_dataset_and_coverage_contract() -> None:
    timestamps = pd.date_range("2024-01-01", periods=2, freq="3h", tz="Asia/Shanghai")
    aq_df = pd.DataFrame({"timestamp": timestamps, "pm25": [10.0, 20.0]})
    weather_df = pd.DataFrame({"timestamp": timestamps, "temp": [2.0, 3.0]})

    out = finalize_collected_dataset(
        aq_df,
        weather_df,
        station_name="Shanghai",
        latitude=31.2304,
        longitude=121.4737,
    )
    coverage = summarize_dataset_coverage(out, ["pm25", "pm10"])

    assert list(out["station_id"].unique()) == ["Shanghai"]
    assert {"pm25", "pm25_viz", "temp", "humidity", "wind_speed"}.issubset(out.columns)
    assert coverage[0] == {"pollutant": "pm25", "non_null_ratio": 1.0, "rows_with_values": 2}
    assert coverage[1] == {"pollutant": "pm10", "non_null_ratio": 0.0, "rows_with_values": 0}
