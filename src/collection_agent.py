from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import requests

from src.config import (
    AQ_AGENT_CHUNK_DAYS,
    AQ_AGENT_DEFAULT_MODEL,
    AQ_AGENT_OUTPUT_DIR,
    AQ_AGENT_POLLUTANTS,
    CAMS_EUROPE_START_DATE,
    DEEPSEEK_BASE_URL,
    EUROPE_COUNTRY_CODES,
    OPEN_METEO_AIR_QUALITY_URL,
    OPEN_METEO_GEOCODING_URL,
    OPEN_METEO_GLOBAL_START_DATE,
    OPEN_METEO_WEATHER_ARCHIVE_URL,
    POLLUTANT_COLUMNS,
)

WEATHER_API_FIELDS = {
    "temp": "temperature_2m",
    "humidity": "relative_humidity_2m",
    "wind_speed": "wind_speed_10m",
}

ProgressCallback = Callable[[int, int, str], None]


@dataclass(slots=True)
class CityCandidate:
    name: str
    country: str
    country_code: str
    latitude: float
    longitude: float
    timezone: str
    admin1: str | None = None
    population: int | None = None
    open_meteo_id: int | None = None

    @property
    def display_name(self) -> str:
        parts = [self.name]
        if self.admin1 and self.admin1 != self.name:
            parts.append(self.admin1)
        if self.country:
            parts.append(self.country)
        return ", ".join(parts)

    @property
    def is_europe(self) -> bool:
        return self.country_code.upper() in EUROPE_COUNTRY_CODES

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CollectionRequest:
    city_query: str
    start_year: int
    end_year: int
    pollutants: list[str]
    include_weather: bool = True
    country_code: str | None = None

    def normalized_pollutants(self) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for item in self.pollutants:
            key = str(item).strip().lower()
            if key in AQ_AGENT_POLLUTANTS and key not in seen:
                normalized.append(key)
                seen.add(key)
        if not normalized:
            normalized = ["pm25"]
        return normalized


@dataclass(slots=True)
class CollectionPlan:
    city_label: str
    city_query: str
    country_code: str
    latitude: float
    longitude: float
    timezone: str
    source_name: str
    source_domain: str
    sampling_step: str
    requested_start_date: str
    requested_end_date: str
    actual_start_date: str
    actual_end_date: str
    pollutants: list[str]
    pollutant_variables: list[str]
    weather_variables: list[str]
    chunks: list[dict[str, str]]
    output_path: str
    warnings: list[str]
    planner_mode: str
    planner_model: str | None = None
    planner_notes: str = ""
    quality_checks: list[str] | None = None
    risk_flags: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["quality_checks"] = self.quality_checks or []
        payload["risk_flags"] = self.risk_flags or []
        return payload


@dataclass(slots=True)
class CollectionResult:
    plan: CollectionPlan
    dataset: pd.DataFrame
    output_path: str
    row_count: int
    started_at: str
    ended_at: str
    coverage_rows: list[dict[str, Any]]
    runtime_warnings: list[str]
    summary_text: str
    summary_mode: str

    def coverage_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.coverage_rows)


def city_candidate_from_dict(data: dict[str, Any]) -> CityCandidate:
    return CityCandidate(**data)


def collection_plan_from_dict(data: dict[str, Any]) -> CollectionPlan:
    return CollectionPlan(**data)


def search_city_candidates(
    query: str,
    country_code: str | None = None,
    count: int = 5,
    language: str = "en",
) -> list[CityCandidate]:
    clean_query = query.strip()
    if len(clean_query) < 2:
        raise ValueError("City query must include at least 2 characters.")

    params = {
        "name": clean_query,
        "count": max(1, min(int(count), 10)),
        "language": language,
        "format": "json",
    }
    if country_code:
        params["countryCode"] = country_code.strip().upper()

    payload = _safe_get_json(OPEN_METEO_GEOCODING_URL, params=params, timeout=20)
    results = payload.get("results") or []
    candidates: list[CityCandidate] = []
    for item in results:
        latitude = item.get("latitude")
        longitude = item.get("longitude")
        timezone = item.get("timezone")
        name = item.get("name")
        country = item.get("country") or ""
        cc = item.get("country_code") or country_code or ""
        if latitude is None or longitude is None or not timezone or not name:
            continue

        population = item.get("population")
        try:
            population_value = int(population) if population is not None else None
        except (TypeError, ValueError):
            population_value = None

        candidates.append(
            CityCandidate(
                name=str(name),
                country=str(country),
                country_code=str(cc).upper(),
                latitude=float(latitude),
                longitude=float(longitude),
                timezone=str(timezone),
                admin1=item.get("admin1") or None,
                population=population_value,
                open_meteo_id=item.get("id"),
            )
        )

    candidates.sort(key=lambda row: (row.population or 0, row.name), reverse=True)
    return candidates


def build_collection_plan(
    request: CollectionRequest,
    candidate: CityCandidate,
    api_key: str | None = None,
    model: str = AQ_AGENT_DEFAULT_MODEL,
    base_url: str = DEEPSEEK_BASE_URL,
    output_dir: Path = AQ_AGENT_OUTPUT_DIR,
) -> CollectionPlan:
    pollutants = request.normalized_pollutants()
    start_year = int(request.start_year)
    end_year = int(request.end_year)
    if start_year > end_year:
        raise ValueError("Start year must be less than or equal to end year.")

    requested_start = date(start_year, 1, 1)
    requested_end = date(end_year, 12, 31)
    actual_start, actual_end, source_domain, sampling_step, warnings = resolve_supported_window(
        candidate,
        requested_start,
        requested_end,
    )
    if actual_start > actual_end:
        raise ValueError("The requested year range is outside the available archive window for this city.")

    chunks = chunk_date_range(actual_start, actual_end, chunk_days=AQ_AGENT_CHUNK_DAYS)
    output_path = build_output_path(output_dir, candidate, actual_start, actual_end)

    plan = CollectionPlan(
        city_label=candidate.display_name,
        city_query=request.city_query.strip(),
        country_code=candidate.country_code,
        latitude=candidate.latitude,
        longitude=candidate.longitude,
        timezone=candidate.timezone,
        source_name="Open-Meteo Air Quality Archive",
        source_domain=source_domain,
        sampling_step=sampling_step,
        requested_start_date=requested_start.isoformat(),
        requested_end_date=requested_end.isoformat(),
        actual_start_date=actual_start.isoformat(),
        actual_end_date=actual_end.isoformat(),
        pollutants=pollutants,
        pollutant_variables=[AQ_AGENT_POLLUTANTS[key]["api_field"] for key in pollutants],
        weather_variables=list(WEATHER_API_FIELDS.values()) if request.include_weather else [],
        chunks=chunks,
        output_path=str(output_path),
        warnings=warnings,
        planner_mode="deterministic",
        planner_model=None,
        planner_notes=_default_planner_notes(candidate, pollutants, chunks, request.include_weather),
        quality_checks=[
            "Confirm the first and last timestamps match the planned collection window.",
            "Inspect non-null ratios for the selected pollutants after all chunks are merged.",
            "Keep the dataset in parquet format so the existing dashboard pages can load it directly.",
        ],
        risk_flags=[
            "Historical coverage depends on the selected city and Open-Meteo domain availability.",
            "Global CAMS data is 3-hourly rather than hourly, so time density can differ by region.",
        ],
    )

    if api_key:
        planner_data = _generate_planner_guidance(plan, api_key=api_key, model=model, base_url=base_url)
        if planner_data:
            plan.planner_mode = "deepseek-assisted"
            plan.planner_model = model
            plan.planner_notes = str(planner_data.get("planner_notes") or plan.planner_notes)
            plan.quality_checks = _unique_strings(
                [*(plan.quality_checks or []), *list(planner_data.get("quality_checks") or [])]
            )
            plan.risk_flags = _unique_strings(
                [*(plan.risk_flags or []), *list(planner_data.get("risk_flags") or []), *plan.warnings]
            )

    plan.risk_flags = _unique_strings([*(plan.risk_flags or []), *plan.warnings])
    return plan


def run_collection_agent(
    request: CollectionRequest,
    candidate: CityCandidate,
    api_key: str | None = None,
    model: str = AQ_AGENT_DEFAULT_MODEL,
    base_url: str = DEEPSEEK_BASE_URL,
    output_dir: Path = AQ_AGENT_OUTPUT_DIR,
    progress_callback: ProgressCallback | None = None,
) -> CollectionResult:
    plan = build_collection_plan(
        request,
        candidate,
        api_key=api_key,
        model=model,
        base_url=base_url,
        output_dir=output_dir,
    )

    aq_frames: list[pd.DataFrame] = []
    weather_frames: list[pd.DataFrame] = []
    runtime_warnings: list[str] = []

    total_steps = len(plan.chunks) + (len(plan.chunks) if plan.weather_variables else 0) + 2
    step = 0

    for chunk in plan.chunks:
        step += 1
        _notify(progress_callback, step, total_steps, f"Fetching air quality {chunk['start_date']} -> {chunk['end_date']}")
        aq_frame = fetch_air_quality_chunk(plan, chunk)
        if not aq_frame.empty:
            aq_frames.append(aq_frame)

        if plan.weather_variables:
            step += 1
            _notify(progress_callback, step, total_steps, f"Fetching weather {chunk['start_date']} -> {chunk['end_date']}")
            try:
                weather_frame = fetch_weather_chunk(plan, chunk)
            except Exception as exc:  # noqa: BLE001
                runtime_warnings.append(
                    f"Weather supplement skipped for {chunk['start_date']} to {chunk['end_date']}: {exc}"
                )
            else:
                if not weather_frame.empty:
                    weather_frames.append(weather_frame)

    step += 1
    _notify(progress_callback, step, total_steps, "Merging chunk outputs and building dashboard-ready dataset")
    air_quality_df = _concat_unique_frames(aq_frames)
    if air_quality_df.empty:
        raise ValueError("The collection run completed, but no air-quality rows were returned for the planned range.")

    weather_df = _concat_unique_frames(weather_frames)
    final_df = finalize_collected_dataset(
        air_quality_df,
        weather_df,
        station_name=candidate.name,
        latitude=candidate.latitude,
        longitude=candidate.longitude,
    )

    save_dataset(final_df, Path(plan.output_path))

    coverage_rows = summarize_dataset_coverage(final_df, plan.pollutants)
    summary_text, summary_mode = generate_collection_summary(
        final_df,
        plan,
        coverage_rows,
        runtime_warnings=runtime_warnings,
        api_key=api_key,
        model=model,
        base_url=base_url,
    )

    step += 1
    _notify(progress_callback, step, total_steps, f"Saved dataset to {plan.output_path}")

    return CollectionResult(
        plan=plan,
        dataset=final_df,
        output_path=plan.output_path,
        row_count=len(final_df),
        started_at=str(final_df["timestamp"].min()),
        ended_at=str(final_df["timestamp"].max()),
        coverage_rows=coverage_rows,
        runtime_warnings=runtime_warnings,
        summary_text=summary_text,
        summary_mode=summary_mode,
    )


def resolve_supported_window(
    candidate: CityCandidate,
    requested_start: date,
    requested_end: date,
    today: date | None = None,
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
        warnings.append(
            f"Requested start year was clipped to {supported_start.isoformat()} because this city's source window starts there."
        )
    if requested_end > current_day:
        warnings.append(f"Requested end date was clipped to {current_day.isoformat()} because future history is unavailable.")

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
    candidate: CityCandidate,
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
    return output_dir / filename


def fetch_air_quality_chunk(plan: CollectionPlan, chunk: dict[str, str]) -> pd.DataFrame:
    params = {
        "latitude": plan.latitude,
        "longitude": plan.longitude,
        "hourly": ",".join(plan.pollutant_variables),
        "start_date": chunk["start_date"],
        "end_date": chunk["end_date"],
        "timezone": plan.timezone,
        "domains": plan.source_domain,
    }
    payload = _safe_get_json(OPEN_METEO_AIR_QUALITY_URL, params=params, timeout=60)
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return pd.DataFrame(columns=["timestamp", *plan.pollutants])

    length = len(times)
    frame = pd.DataFrame({"timestamp": _normalize_local_times(times, plan.timezone)})
    for pollutant, api_field in zip(plan.pollutants, plan.pollutant_variables, strict=False):
        frame[pollutant] = _normalize_numeric_values(hourly.get(api_field, []), length)
    return frame.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


def fetch_weather_chunk(plan: CollectionPlan, chunk: dict[str, str]) -> pd.DataFrame:
    params = {
        "latitude": plan.latitude,
        "longitude": plan.longitude,
        "start_date": chunk["start_date"],
        "end_date": chunk["end_date"],
        "hourly": ",".join(plan.weather_variables),
        "timezone": plan.timezone,
    }
    payload = _safe_get_json(OPEN_METEO_WEATHER_ARCHIVE_URL, params=params, timeout=60)
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return pd.DataFrame(columns=["timestamp", *WEATHER_API_FIELDS.keys()])

    length = len(times)
    frame = pd.DataFrame({"timestamp": _normalize_local_times(times, plan.timezone)})
    for output_field, api_field in WEATHER_API_FIELDS.items():
        frame[output_field] = _normalize_numeric_values(hourly.get(api_field, []), length)
    return frame.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


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


def save_dataset(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)


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


def generate_collection_summary(
    df: pd.DataFrame,
    plan: CollectionPlan,
    coverage_rows: list[dict[str, Any]],
    runtime_warnings: list[str] | None = None,
    api_key: str | None = None,
    model: str = AQ_AGENT_DEFAULT_MODEL,
    base_url: str = DEEPSEEK_BASE_URL,
) -> tuple[str, str]:
    deterministic_summary = _default_run_summary(df, plan, coverage_rows, runtime_warnings or [])
    if not api_key:
        return deterministic_summary, "deterministic"

    summary_data = _generate_run_summary(
        df,
        plan,
        coverage_rows,
        runtime_warnings=runtime_warnings or [],
        api_key=api_key,
        model=model,
        base_url=base_url,
    )
    if not summary_data:
        return deterministic_summary, "deterministic"

    llm_summary = str(summary_data.get("summary") or "").strip()
    caveat = str(summary_data.get("caveat") or "").strip()
    if caveat:
        llm_summary = f"{llm_summary} Caveat: {caveat}".strip()
    if not llm_summary:
        llm_summary = deterministic_summary
    return llm_summary, model


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered)
    return slug.strip("-")


def _default_planner_notes(
    candidate: CityCandidate,
    pollutants: list[str],
    chunks: list[dict[str, str]],
    include_weather: bool,
) -> str:
    weather_note = "with weather enrichment" if include_weather else "without weather enrichment"
    pollutants_text = ", ".join(pollutant.upper() for pollutant in pollutants)
    return (
        f"Collect {pollutants_text} for {candidate.display_name} in {len(chunks)} chunk(s) {weather_note}, "
        "then save a parquet dataset that can be loaded by the existing dashboard pages."
    )


def _default_run_summary(
    df: pd.DataFrame,
    plan: CollectionPlan,
    coverage_rows: list[dict[str, Any]],
    runtime_warnings: list[str],
) -> str:
    coverage_text = ", ".join(
        f"{row['pollutant'].upper()} {row['non_null_ratio']:.0%}" for row in coverage_rows
    )
    warning_text = f" Warnings: {'; '.join(runtime_warnings)}" if runtime_warnings else ""
    return (
        f"Collected {len(df):,} rows for {plan.city_label} from {plan.actual_start_date} to {plan.actual_end_date}. "
        f"Sampling is {plan.sampling_step}; selected pollutant coverage is {coverage_text}."
        f" Saved to {plan.output_path}.{warning_text}"
    )


def _generate_planner_guidance(
    plan: CollectionPlan,
    api_key: str,
    model: str,
    base_url: str,
) -> dict[str, Any] | None:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a data collection planner for an air-quality dashboard. "
                "Return JSON only and never claim data exists outside the provided source window."
            ),
        },
        {
            "role": "user",
            "content": (
                "Create a concise execution brief for this collection plan. "
                "Return a JSON object with keys planner_notes, quality_checks, risk_flags.\n"
                f"Plan: {json.dumps(plan.to_dict(), ensure_ascii=False)}"
            ),
        },
    ]
    return _deepseek_json_completion(messages, api_key=api_key, model=model, base_url=base_url, timeout=90)


def _generate_run_summary(
    df: pd.DataFrame,
    plan: CollectionPlan,
    coverage_rows: list[dict[str, Any]],
    runtime_warnings: list[str],
    api_key: str,
    model: str,
    base_url: str,
) -> dict[str, Any] | None:
    preview = {
        "city": plan.city_label,
        "range": [plan.actual_start_date, plan.actual_end_date],
        "rows": len(df),
        "sampling_step": plan.sampling_step,
        "coverage_rows": coverage_rows,
        "warnings": runtime_warnings,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You summarize completed air-quality data collection runs. "
                "Return JSON only with keys summary and caveat."
            ),
        },
        {
            "role": "user",
            "content": f"Summarize this run in 2 sentences max: {json.dumps(preview, ensure_ascii=False)}",
        },
    ]
    return _deepseek_json_completion(messages, api_key=api_key, model=model, base_url=base_url, timeout=90)


def _deepseek_json_completion(
    messages: list[dict[str, Any]],
    api_key: str,
    model: str,
    base_url: str,
    timeout: int = 90,
) -> dict[str, Any] | None:
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": 0.1,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    choices = payload.get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if not content:
        return None
    try:
        return _extract_json_object(str(content))
    except Exception:  # noqa: BLE001
        return None


def _extract_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = stripped.replace("json", "", 1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("JSON object not found in model response.")
    return json.loads(stripped[start : end + 1])


def _safe_get_json(url: str, params: dict[str, Any], timeout: int = 45) -> dict[str, Any]:
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise ValueError(payload.get("reason") or "Unknown API error")
    return payload


def _normalize_local_times(values: list[Any], timezone: str) -> pd.Series:
    ts = pd.to_datetime(pd.Series(values), errors="coerce")
    if ts.dt.tz is None:
        return ts.dt.tz_localize(timezone)
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


def _notify(callback: ProgressCallback | None, step: int, total_steps: int, message: str) -> None:
    if callback is not None:
        callback(step, total_steps, message)


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        output.append(text)
        seen.add(text)
    return output
