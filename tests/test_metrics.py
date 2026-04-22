from __future__ import annotations

import pandas as pd

from src.metrics import compute_correlations, compute_metrics


def metric_df() -> pd.DataFrame:
    ts = pd.date_range("2025-01-01", periods=6, freq="h", tz="Asia/Shanghai")
    return pd.DataFrame(
        {
            "timestamp": [ts[0], ts[0], ts[1], ts[1], ts[2], ts[2]],
            "station_id": ["A", "B", "A", "B", "A", "B"],
            "pm25": [10, 20, 30, 40, 50, 60],
            "pm10": [20, 40, 60, 80, 100, 120],
            "temp": [1, 2, 3, 4, 5, 6],
            "humidity": [60, 58, 56, 54, 52, 50],
            "wind_speed": [1, 1.2, 1.4, 1.5, 1.7, 2.0],
        }
    )


def test_compute_metrics_basic() -> None:
    df = metric_df()
    out = compute_metrics(df, pollutant="pm25", thresholds={"pm25": 25.0})
    assert out["latest_mean"] == 55.0
    assert out["exceed_hours"] == 4.0


def test_compute_correlations_returns_matrix() -> None:
    df = metric_df()
    corr = compute_correlations(df, pollutants=["pm25", "pm10"], weather=["temp"])
    assert set(corr.columns) == {"pm25", "pm10", "temp"}
    assert corr.shape == (3, 3)
