from __future__ import annotations

import re
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from time import sleep
from typing import Any, Callable, Protocol

import pandas as pd
import requests

from src.config import (
    AQ_AGENT_CHUNK_DAYS,
    CAMS_EUROPE_START_DATE,
    OPEN_METEO_AIR_QUALITY_URL,
    OPEN_METEO_GLOBAL_START_DATE,
    OPEN_METEO_WEATHER_ARCHIVE_URL,
    POLLUTANT_COLUMNS,
)
from src.data import output_dataset_path, write_dataset as write_tabular_dataset
from src.i18n import t

WEATHER_API_FIELDS = {
    "temp": "temperature_2m",
    "humidity": "relative_humidity_2m",
    "wind_speed": "wind_speed_10m",
}
OPEN_METEO_WEATHER_ARCHIVE_DELAY_DAYS = 5
JsonGetter = Callable[..., dict[str, Any]]


class CollectionCandidateLike(Protocol):
    name: str
    country_code: str
    open_meteo_id: int | None
    is_europe: bool


class CollectionPlanLike(Protocol):
    latitude: float
    longitude: float
    timezone: str
    pollutant_variables: list[str]
    pollutants: list[str]
    source_domain: str
    weather_variables: list[str]


def resolve_supported_window(
    candidate: CollectionCandidateLike,
    requested_start: date,
    requested_end: date,
    today: date | None = None,
    language: str = "en",
) -> tuple[date, date, str, str, list[str]]:
    current_day = today or date.today()
    warnings: list[str] = []

    if candidate.is_europe:
        supported_start = date.fromisoformat(CAMS_EUROPE_START_DATE)
        source_domain = "cams_europe"
        sampling_step = "hourly"
    else:
        supported_start = date.fromisoformat(OPEN_METEO_GLOBAL_START_DATE)
        source_domain = "auto"
        sampling_step = "3-hourly"

    actual_start = max(requested_start, supported_start)
    actual_end = min(requested_end, current_day)

    if requested_start < supported_start:
        warnings.append(t("collection.clipped_start", language, date=supported_start.isoformat()))
    if requested_end > current_day:
        warnings.append(t("collection.clipped_end", language, date=current_day.isoformat()))

    return actual_start, actual_end, source_domain, sampling_step, warnings


def chunk_date_range(start_date: date, end_date: date, chunk_days: int = AQ_AGENT_CHUNK_DAYS) -> list[dict[str, str]]:
    if start_date > end_date:
        return []

    chunks: list[dict[str, str]] = []
    current = start_date
    while current <= end_date:
        chunk_end = min(current + timedelta(days=max(chunk_days, 1) - 1), end_date)
        chunks.append(
            {
                "start_date": current.isoformat(),
                "end_date": chunk_end.isoformat(),
            }
        )
        current = chunk_end + timedelta(days=1)
    return chunks


def build_output_path(
    output_dir: Path,
    candidate: CollectionCandidateLike,
    start_date: date,
    end_date: date,
) -> Path:
    slug = slugify(candidate.name)
    if not slug:
        if candidate.open_meteo_id:
            slug = f"city-{candidate.open_meteo_id}"
        else:
            slug = f"city-{candidate.country_code.lower()}"
    filename = f"{slug}_{start_date.year}_{end_date.year}_aq.parquet"
    return output_dataset_path(output_dir / filename)


def fetch_air_quality_chunk(
    plan: CollectionPlanLike,
    chunk: dict[str, str],
    get_json: JsonGetter | None = None,
) -> pd.DataFrame:
    params = {
        "latitude": plan.latitude,
        "longitude": plan.longitude,
        "hourly": ",".join(plan.pollutant_variables),
        "start_date": chunk["start_date"],
        "end_date": chunk["end_date"],
        "timezone": plan.timezone,
        "domains": plan.source_domain,
    }
    request_json = get_json or _safe_get_json
    payload = request_json(OPEN_METEO_AIR_QUALITY_URL, params=params, timeout=60)
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return pd.DataFrame(columns=["timestamp", *plan.pollutants])

    length = len(times)
    frame = pd.DataFrame({"timestamp": _normalize_local_times(times, plan.timezone)})
    for pollutant, api_field in zip(plan.pollutants, plan.pollutant_variables, strict=False):
        frame[pollutant] = _normalize_numeric_values(hourly.get(api_field, []), length)
    return frame.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


def fetch_weather_chunk(
    plan: CollectionPlanLike,
    chunk: dict[str, str],
    get_json: JsonGetter | None = None,
    today: date | None = None,
) -> pd.DataFrame:
    weather_window = weather_archive_chunk_window(chunk, today=today)
    if weather_window is None:
        return pd.DataFrame(columns=["timestamp", *WEATHER_API_FIELDS.keys()])

    start_date, end_date = weather_window
    params = {
        "latitude": plan.latitude,
        "longitude": plan.longitude,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": ",".join(plan.weather_variables),
        "timezone": plan.timezone,
    }
    request_json = get_json or _safe_get_json
    payload = request_json(OPEN_METEO_WEATHER_ARCHIVE_URL, params=params, timeout=60)
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return pd.DataFrame(columns=["timestamp", *WEATHER_API_FIELDS.keys()])

    length = len(times)
    frame = pd.DataFrame({"timestamp": _normalize_local_times(times, plan.timezone)})
    for output_field, api_field in WEATHER_API_FIELDS.items():
        frame[output_field] = _normalize_numeric_values(hourly.get(api_field, []), length)
    return frame.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


def weather_archive_available_end(today: date | None = None) -> date:
    current_day = today or date.today()
    return current_day - timedelta(days=OPEN_METEO_WEATHER_ARCHIVE_DELAY_DAYS)


def weather_archive_chunk_window(chunk: dict[str, str], today: date | None = None) -> tuple[str, str] | None:
    start_date = date.fromisoformat(chunk["start_date"])
    end_date = date.fromisoformat(chunk["end_date"])
    archive_end = weather_archive_available_end(today)
    clipped_end = min(end_date, archive_end)
    if start_date > clipped_end:
        return None
    return start_date.isoformat(), clipped_end.isoformat()


def finalize_collected_dataset(
    air_quality_df: pd.DataFrame,
    weather_df: pd.DataFrame,
    station_name: str,
    latitude: float,
    longitude: float,
) -> pd.DataFrame:
    merged = air_quality_df.copy()
    if not weather_df.empty:
        merged = merged.merge(weather_df, on="timestamp", how="left")

    merged["station_id"] = station_name
    merged["lat"] = latitude
    merged["lon"] = longitude

    for pollutant in POLLUTANT_COLUMNS:
        if pollutant not in merged.columns:
            merged[pollutant] = pd.NA
        merged[pollutant] = pd.to_numeric(merged[pollutant], errors="coerce")

    for weather_col in WEATHER_API_FIELDS:
        if weather_col not in merged.columns:
            merged[weather_col] = pd.NA
        merged[weather_col] = pd.to_numeric(merged[weather_col], errors="coerce")

    for pollutant in POLLUTANT_COLUMNS:
        series = merged[pollutant]
        quantiles = series.dropna()
        if quantiles.empty:
            merged[f"{pollutant}_viz"] = series
        else:
            lower = quantiles.quantile(0.01)
            upper = quantiles.quantile(0.99)
            merged[f"{pollutant}_viz"] = series.clip(lower, upper)

    keep = [
        "timestamp",
        "station_id",
        "lat",
        "lon",
        *POLLUTANT_COLUMNS,
        *WEATHER_API_FIELDS.keys(),
        *[f"{pollutant}_viz" for pollutant in POLLUTANT_COLUMNS],
    ]
    out = (
        merged[keep]
        .drop_duplicates(subset=["timestamp", "station_id"], keep="last")
        .sort_values(["timestamp", "station_id"])
        .reset_index(drop=True)
    )
    return out


def save_dataset(df: pd.DataFrame, output_path: Path) -> Path:
    return write_tabular_dataset(df, output_path)


def summarize_dataset_coverage(df: pd.DataFrame, pollutants: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pollutant in pollutants:
        if pollutant not in df.columns:
            continue
        non_null_ratio = float(df[pollutant].notna().mean()) if len(df) else 0.0
        rows.append(
            {
                "pollutant": pollutant,
                "non_null_ratio": round(non_null_ratio, 4),
                "rows_with_values": int(df[pollutant].notna().sum()),
            }
        )
    return rows


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered)
    return slug.strip("-")


def _safe_get_json(url: str, params: dict[str, Any], timeout: int = 45, retries: int = 2) -> dict[str, Any]:
    last_error: requests.RequestException | None = None
    for attempt in range(max(1, retries + 1)):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            break
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= retries:
                raise RuntimeError(_open_meteo_unavailable_message()) from exc
            sleep(0.25 * (attempt + 1))
    else:
        raise RuntimeError(_open_meteo_unavailable_message()) from last_error

    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise ValueError(payload.get("reason") or "Unknown API error")
    return payload


def _open_meteo_unavailable_message() -> str:
    return "Open-Meteo 服务暂时不可用，请稍后重试。Open-Meteo is temporarily unavailable; try again shortly."


def _normalize_local_times(values: list[Any], timezone: str) -> pd.Series:
    ts = pd.to_datetime(pd.Series(values), errors="coerce")
    if ts.dt.tz is None:
        return ts.dt.tz_localize(timezone, ambiguous="NaT", nonexistent="NaT")
    return ts.dt.tz_convert(timezone)


def _normalize_numeric_values(values: list[Any], length: int) -> pd.Series:
    series = pd.Series(values, dtype="object")
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.reindex(range(length))


def _concat_unique_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames, ignore_index=True)
    if "timestamp" not in merged.columns:
        return merged
    return merged.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp").reset_index(drop=True)
