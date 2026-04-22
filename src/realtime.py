from __future__ import annotations

from typing import Any

import pandas as pd
import requests

from src.config import REALTIME_MIN_COVERAGE, TIMEZONE

OPENAQ_BASE = "https://api.openaq.org/v3"


def _safe_get(url: str, params: dict[str, Any], timeout: int = 20) -> dict[str, Any]:
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _normalize_timestamp(raw: Any) -> pd.Timestamp | None:
    try:
        ts = pd.Timestamp(raw)
    except Exception:  # noqa: BLE001
        return None

    if ts.tz is None:
        return ts.tz_localize("UTC").tz_convert(TIMEZONE)
    return ts.tz_convert(TIMEZONE)


def fetch_openaq_latest(city: str = "Beijing", hours: int = 24) -> dict[str, Any]:
    """
    Fetch recent OpenAQ observations.

    The parser is defensive because OpenAQ response shapes can vary by endpoint revisions.
    """
    now = pd.Timestamp.now(tz=TIMEZONE)
    since = (now - pd.Timedelta(hours=hours)).isoformat()

    try:
        locations_payload = _safe_get(
            f"{OPENAQ_BASE}/locations",
            {"city": city, "limit": 200, "order_by": "lastUpdated", "sort_order": "desc"},
        )
        locations = locations_payload.get("results", [])
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "coverage": 0.0,
            "data": pd.DataFrame(),
            "message": f"OpenAQ location query failed: {exc}",
        }

    rows: list[dict[str, Any]] = []
    for location in locations:
        loc_id = location.get("id")
        station_name = location.get("name") or f"location_{loc_id}"
        coords = location.get("coordinates") or {}
        lat = coords.get("latitude")
        lon = coords.get("longitude")

        if not loc_id:
            continue

        try:
            latest_payload = _safe_get(
                f"{OPENAQ_BASE}/locations/{loc_id}/latest",
                {"date_from": since},
            )
            latest_rows = latest_payload.get("results", [])
        except Exception:
            latest_rows = []

        for item in latest_rows:
            parameter = (item.get("parameter") or "").lower()
            value = item.get("value")
            ts_raw = item.get("datetime") or item.get("date") or item.get("period")
            if isinstance(ts_raw, dict):
                ts_raw = ts_raw.get("utc") or ts_raw.get("local")
            if value is None or not parameter:
                continue

            timestamp = _normalize_timestamp(ts_raw)
            if timestamp is None:
                continue

            rows.append(
                {
                    "timestamp": timestamp,
                    "station_id": station_name,
                    "lat": lat,
                    "lon": lon,
                    "parameter": parameter,
                    "value": float(value),
                }
            )

    if not rows:
        return {
            "success": False,
            "coverage": 0.0,
            "data": pd.DataFrame(),
            "message": "OpenAQ returned no recent rows for this city.",
        }

    raw_df = pd.DataFrame(rows)
    pivot = (
        raw_df.pivot_table(
            index=["timestamp", "station_id", "lat", "lon"],
            columns="parameter",
            values="value",
            aggfunc="mean",
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )

    coverage = estimate_recent_coverage(pivot, hours=hours)
    success = coverage >= REALTIME_MIN_COVERAGE

    message = (
        f"Realtime coverage {coverage:.0%} is sufficient."
        if success
        else f"Realtime coverage {coverage:.0%} is below threshold {REALTIME_MIN_COVERAGE:.0%}."
    )

    return {
        "success": success,
        "coverage": coverage,
        "data": pivot,
        "message": message,
    }


def estimate_recent_coverage(df: pd.DataFrame, hours: int = 24) -> float:
    """Estimate station-hour coverage for recent data."""
    if df.empty or "timestamp" not in df.columns or "station_id" not in df.columns:
        return 0.0

    tmp = df[["station_id", "timestamp"]].dropna().copy()
    if tmp.empty:
        return 0.0

    tmp["hour"] = pd.to_datetime(tmp["timestamp"]).dt.floor("h")
    observed = tmp.drop_duplicates(["station_id", "hour"]).shape[0]
    station_count = max(tmp["station_id"].nunique(), 1)
    expected = station_count * max(hours, 1)
    if expected == 0:
        return 0.0

    return min(observed / expected, 1.0)
