from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from src.config import POLLUTANT_COLUMNS, POLLUTANT_THRESHOLDS, WEATHER_COLUMNS


def compute_metrics(
    df: pd.DataFrame,
    pollutant: str = "pm25",
    thresholds: dict[str, float] | None = None,
) -> dict[str, float]:
    """Compute top-level dashboard KPIs for selected pollutant."""
    if pollutant not in df.columns or df.empty:
        return {
            "latest_mean": float("nan"),
            "rolling_24h_mean": float("nan"),
            "exceed_hours": 0.0,
            "station_spread": float("nan"),
        }

    threshold_map = thresholds or POLLUTANT_THRESHOLDS
    threshold = threshold_map.get(pollutant, float("inf"))

    latest_ts = df["timestamp"].max()
    latest_frame = df[df["timestamp"] == latest_ts]

    latest_mean = float(latest_frame[pollutant].mean())
    rolling_start = latest_ts - pd.Timedelta(hours=24)
    rolling_24h_mean = float(df[df["timestamp"] >= rolling_start][pollutant].mean())
    exceed_hours = float((df[pollutant] > threshold).sum())
    station_spread = float(latest_frame[pollutant].max() - latest_frame[pollutant].min())

    return {
        "latest_mean": latest_mean,
        "rolling_24h_mean": rolling_24h_mean,
        "exceed_hours": exceed_hours,
        "station_spread": station_spread,
    }


def compute_station_ranking(
    df: pd.DataFrame,
    pollutant: str,
    latest_only: bool = True,
    top_n: int = 12,
) -> pd.DataFrame:
    """Compute station ranking for one pollutant."""
    if df.empty or pollutant not in df.columns:
        return pd.DataFrame(columns=["station_id", pollutant])

    ranked = df
    if latest_only:
        latest_ts = df["timestamp"].max()
        ranked = df[df["timestamp"] == latest_ts]

    result = (
        ranked.groupby("station_id", as_index=False, observed=True)[pollutant]
        .mean()
        .sort_values(pollutant, ascending=False)
        .head(top_n)
    )
    return result.reset_index(drop=True)


def compute_correlations(
    df: pd.DataFrame,
    pollutants: Iterable[str] | None = None,
    weather: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Correlation matrix between pollutant and weather fields."""
    poll_cols = [c for c in (pollutants or POLLUTANT_COLUMNS) if c in df.columns]
    weather_cols = [c for c in (weather or WEATHER_COLUMNS) if c in df.columns]
    cols = poll_cols + weather_cols
    if not cols:
        return pd.DataFrame()
    return df[cols].corr(method="pearson")


def detect_events(df: pd.DataFrame, pollutant: str = "pm25") -> pd.DataFrame:
    """Create coarse event labels from daily city averages."""
    if df.empty or pollutant not in df.columns:
        return pd.DataFrame(columns=["timestamp", "event", "description"])

    city_daily = (
        df.set_index("timestamp")
        .groupby("station_id", observed=True)
        .resample("D")[pollutant]
        .mean()
        .groupby("timestamp")
        .mean()
        .dropna()
        .reset_index()
    )
    if city_daily.empty:
        return pd.DataFrame(columns=["timestamp", "event", "description"])

    high_threshold = city_daily[pollutant].quantile(0.9)
    delta = city_daily[pollutant].diff().abs()
    delta_threshold = delta.quantile(0.95)

    event_rows: list[dict[str, object]] = []
    for idx, row in city_daily.iterrows():
        ts = row["timestamp"]
        val = row[pollutant]
        if val >= high_threshold:
            event_rows.append(
                {
                    "timestamp": ts,
                    "event": "heavy_pollution",
                    "description": f"{pollutant.upper()} high day ({val:.1f})",
                }
            )
        if idx > 0 and delta.iloc[idx] >= delta_threshold:
            event_rows.append(
                {
                    "timestamp": ts,
                    "event": "sharp_shift",
                    "description": f"Rapid day-over-day shift ({delta.iloc[idx]:.1f})",
                }
            )

    return pd.DataFrame(event_rows)
