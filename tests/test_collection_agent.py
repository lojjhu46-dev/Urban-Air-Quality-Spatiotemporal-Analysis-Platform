from __future__ import annotations

from datetime import date

import pandas as pd

from src.collection_agent import (
    CityCandidate,
    CollectionRequest,
    build_collection_plan,
    chunk_date_range,
    finalize_collected_dataset,
    resolve_supported_window,
    summarize_dataset_coverage,
)


def shanghai_candidate() -> CityCandidate:
    return CityCandidate(
        name="Shanghai",
        country="China",
        country_code="CN",
        latitude=31.2304,
        longitude=121.4737,
        timezone="Asia/Shanghai",
        admin1="Shanghai",
        population=24870895,
        open_meteo_id=1796236,
    )


def berlin_candidate() -> CityCandidate:
    return CityCandidate(
        name="Berlin",
        country="Germany",
        country_code="DE",
        latitude=52.5244,
        longitude=13.4105,
        timezone="Europe/Berlin",
        admin1="Berlin",
        population=3426354,
        open_meteo_id=2950159,
    )


def test_resolve_supported_window_clips_non_europe_start() -> None:
    actual_start, actual_end, source_domain, sampling_step, warnings = resolve_supported_window(
        shanghai_candidate(),
        requested_start=date(2020, 1, 1),
        requested_end=date(2023, 12, 31),
        today=date(2024, 1, 31),
    )

    assert actual_start == date(2022, 8, 1)
    assert actual_end == date(2023, 12, 31)
    assert source_domain == "auto"
    assert sampling_step == "3-hourly"
    assert warnings


def test_build_collection_plan_for_europe_uses_cams_europe() -> None:
    request = CollectionRequest(
        city_query="Berlin",
        start_year=2012,
        end_year=2014,
        pollutants=["pm25", "o3"],
        include_weather=True,
        country_code="DE",
    )

    plan = build_collection_plan(request, berlin_candidate(), api_key=None)

    assert plan.source_domain == "cams_europe"
    assert plan.actual_start_date == "2013-01-01"
    assert plan.actual_end_date == "2014-12-31"
    assert plan.pollutants == ["pm25", "o3"]
    assert plan.weather_variables == ["temperature_2m", "relative_humidity_2m", "wind_speed_10m"]
    assert len(plan.chunks) >= 1


def test_chunk_date_range_is_inclusive() -> None:
    chunks = chunk_date_range(date(2024, 1, 1), date(2024, 4, 5), chunk_days=30)

    assert chunks[0] == {"start_date": "2024-01-01", "end_date": "2024-01-30"}
    assert chunks[-1] == {"start_date": "2024-03-31", "end_date": "2024-04-05"}


def test_finalize_collected_dataset_matches_dashboard_contract() -> None:
    timestamps = pd.date_range("2024-01-01", periods=3, freq="3h", tz="Asia/Shanghai")
    aq_df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "pm25": [10.0, 30.0, 25.0],
            "pm10": [20.0, 40.0, 35.0],
        }
    )
    weather_df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "temp": [1.0, 2.0, 3.0],
            "humidity": [50.0, 55.0, 60.0],
            "wind_speed": [1.2, 1.5, 1.1],
        }
    )

    out = finalize_collected_dataset(
        aq_df,
        weather_df,
        station_name="Shanghai",
        latitude=31.2304,
        longitude=121.4737,
    )
    coverage = summarize_dataset_coverage(out, ["pm25", "pm10"])

    assert {"timestamp", "station_id", "lat", "lon", "pm25", "pm10", "temp", "humidity", "wind_speed"}.issubset(
        out.columns
    )
    assert {"pm25_viz", "pm10_viz"}.issubset(out.columns)
    assert out["station_id"].nunique() == 1
    assert coverage[0]["non_null_ratio"] == 1.0
