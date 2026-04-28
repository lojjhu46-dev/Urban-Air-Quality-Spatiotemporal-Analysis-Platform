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
from src.data import output_dataset_path, write_dataset as write_tabular_dataset
from src.i18n import t

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


@dataclass(slots=True)
class ToolCallingAgentState:
    last_candidates: list[CityCandidate] | None = None
    last_search_query: str | None = None
    last_country_code: str | None = None
    selected_candidate: CityCandidate | None = None
    last_plan: CollectionPlan | None = None
    last_result: CollectionResult | None = None


@dataclass(slots=True)
class ToolCallingAgentResult:
    assistant_message: str
    tool_trace: list[dict[str, Any]]
    state: ToolCallingAgentState


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


def get_collection_agent_tool_schemas(include_run_collection: bool = True) -> list[dict[str, Any]]:
    pollutant_keys = sorted(AQ_AGENT_POLLUTANTS)

    search_tool = {
        "type": "function",
        "function": {
            "name": "search_city_candidates",
            "description": "Search matching city candidates before planning or collecting data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "City name or city phrase to resolve, such as Beijing or Los Angeles.",
                    },
                    "country_code": {
                        "type": "string",
                        "description": "Optional ISO-3166 alpha-2 country code such as CN, US, or DE.",
                    },
                    "count": {
                        "type": "integer",
                        "description": "How many candidate matches to return.",
                        "minimum": 1,
                        "maximum": 10,
                    },
                },
                "required": ["query"],
            },
        },
    }

    plan_tool = {
        "type": "function",
        "function": {
            "name": "build_collection_plan",
            "description": "Create a deterministic historical air-quality collection plan for a city candidate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city_query": {"type": "string", "description": "City name to collect."},
                    "country_code": {"type": "string", "description": "Optional ISO-3166 alpha-2 country code."},
                    "start_year": {"type": "integer", "minimum": 2013},
                    "end_year": {"type": "integer", "minimum": 2013},
                    "pollutants": {
                        "type": "array",
                        "items": {"type": "string", "enum": pollutant_keys},
                        "minItems": 1,
                    },
                    "include_weather": {"type": "boolean", "description": "Whether to enrich with weather columns."},
                    "candidate_index": {
                        "type": "integer",
                        "description": "Index from the last city search result to use as the resolved city candidate.",
                        "minimum": 0,
                    },
                },
                "required": ["city_query", "start_year", "end_year", "pollutants"],
            },
        },
    }

    tools = [search_tool, plan_tool]
    if include_run_collection:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "run_collection",
                    "description": "Execute the planned data collection and save a parquet dataset.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city_query": {"type": "string", "description": "City name to collect."},
                            "country_code": {"type": "string", "description": "Optional ISO-3166 alpha-2 country code."},
                            "start_year": {"type": "integer", "minimum": 2013},
                            "end_year": {"type": "integer", "minimum": 2013},
                            "pollutants": {
                                "type": "array",
                                "items": {"type": "string", "enum": pollutant_keys},
                                "minItems": 1,
                            },
                            "include_weather": {"type": "boolean", "description": "Whether to enrich with weather columns."},
                            "candidate_index": {
                                "type": "integer",
                                "description": "Index from the last city search result to use as the resolved city candidate.",
                                "minimum": 0,
                            },
                        },
                        "required": ["city_query", "start_year", "end_year", "pollutants"],
                    },
                },
            }
        )
    return tools


def execute_collection_agent_tool(
    name: str,
    raw_arguments: str | dict[str, Any],
    *,
    state: ToolCallingAgentState,
    progress_callback: ProgressCallback | None = None,
    output_dir: Path = AQ_AGENT_OUTPUT_DIR,
    search_language: str = "en",
    language: str = "en",
) -> dict[str, Any]:
    arguments = _coerce_tool_arguments(raw_arguments)

    if name == "search_city_candidates":
        query = str(arguments.get("query") or "").strip()
        country_code = _normalize_country_code(arguments.get("country_code"))
        count = int(arguments.get("count", 5))
        candidates = search_city_candidates(query, country_code=country_code, count=count, language=search_language)
        state.last_candidates = candidates
        state.last_search_query = query
        state.last_country_code = country_code
        return {
            "query": query,
            "country_code": country_code,
            "candidate_count": len(candidates),
            "candidates": [_candidate_payload(candidate, index) for index, candidate in enumerate(candidates)],
        }

    if name == "build_collection_plan":
        request = _collection_request_from_tool_arguments(arguments)
        candidate_index = int(arguments.get("candidate_index", 0))
        candidate, candidates = _resolve_candidate_for_tool(
            request,
            candidate_index=candidate_index,
            state=state,
            search_language=search_language,
        )
        plan = build_collection_plan(request, candidate, api_key=None, output_dir=output_dir, language=language)
        state.last_plan = plan
        return {
            "selected_candidate": _candidate_payload(candidate, candidate_index),
            "candidate_count": len(candidates),
            "plan": plan.to_dict(),
        }

    if name == "run_collection":
        request = _collection_request_from_tool_arguments(arguments)
        candidate_index = int(arguments.get("candidate_index", 0))
        candidate, candidates = _resolve_candidate_for_tool(
            request,
            candidate_index=candidate_index,
            state=state,
            search_language=search_language,
        )
        result = run_collection_agent(
            request,
            candidate,
            api_key=None,
            output_dir=output_dir,
            progress_callback=progress_callback,
            language=language,
        )
        state.last_plan = result.plan
        state.last_result = result
        return {
            "selected_candidate": _candidate_payload(candidate, candidate_index),
            "candidate_count": len(candidates),
            "plan": result.plan.to_dict(),
            "collection_result": _collection_result_payload(result),
        }

    raise ValueError(f"Unsupported agent tool: {name}")


def run_deepseek_tool_agent(
    user_prompt: str,
    *,
    api_key: str,
    model: str = AQ_AGENT_DEFAULT_MODEL,
    base_url: str = DEEPSEEK_BASE_URL,
    default_request: CollectionRequest | None = None,
    allow_run_collection: bool = False,
    progress_callback: ProgressCallback | None = None,
    output_dir: Path = AQ_AGENT_OUTPUT_DIR,
    search_language: str = "en",
    language: str = "en",
    max_turns: int = 8,
) -> ToolCallingAgentResult:
    if not str(api_key).strip():
        raise ValueError("DeepSeek API key is required for tool-calling agent mode.")

    clean_prompt = user_prompt.strip()
    if not clean_prompt:
        raise ValueError("Agent instruction cannot be empty.")

    state = ToolCallingAgentState()
    tool_trace: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = [{"role": "system", "content": _tool_calling_system_prompt(allow_run_collection, language=language)}]
    if default_request is not None:
        messages.append({"role": "system", "content": _default_request_context(default_request)})
    messages.append({"role": "user", "content": clean_prompt})

    tools = get_collection_agent_tool_schemas(include_run_collection=allow_run_collection)
    last_assistant_content = ""

    for _turn in range(max_turns):
        response = _deepseek_chat_completion(
            messages,
            api_key=api_key,
            model=model,
            base_url=base_url,
            tools=tools,
            tool_choice="auto",
            temperature=0.1,
            timeout=90,
            thinking_type="disabled",
        )
        choices = response.get("choices") or []
        if not choices:
            raise ValueError("DeepSeek returned no choices.")

        raw_message = choices[0].get("message") or {}
        assistant_message = _sanitize_assistant_message(raw_message)
        messages.append(assistant_message)
        last_assistant_content = str(assistant_message.get("content") or "").strip()

        tool_calls = assistant_message.get("tool_calls") or []
        if not tool_calls:
            final_message = last_assistant_content or _fallback_agent_reply(state, allow_run_collection, language=language)
            return ToolCallingAgentResult(assistant_message=final_message, tool_trace=tool_trace, state=state)

        for tool_call in tool_calls:
            function = tool_call.get("function") or {}
            tool_name = str(function.get("name") or "").strip()
            raw_arguments = function.get("arguments") or "{}"
            tool_call_id = str(tool_call.get("id") or tool_name or f"call_{len(tool_trace) + 1}")
            try:
                tool_output = execute_collection_agent_tool(
                    tool_name,
                    raw_arguments,
                    state=state,
                    progress_callback=progress_callback,
                    output_dir=output_dir,
                    search_language=search_language,
                    language=language,
                )
            except Exception as exc:  # noqa: BLE001
                tool_output = {"error": str(exc), "tool": tool_name}

            tool_trace.append({"tool": tool_name, "arguments": _coerce_tool_arguments(raw_arguments), "result": tool_output})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(tool_output, ensure_ascii=False),
                }
            )

    final_message = last_assistant_content or _fallback_agent_reply(state, allow_run_collection, language=language)
    return ToolCallingAgentResult(assistant_message=final_message, tool_trace=tool_trace, state=state)


def build_collection_plan(
    request: CollectionRequest,
    candidate: CityCandidate,
    api_key: str | None = None,
    model: str = AQ_AGENT_DEFAULT_MODEL,
    base_url: str = DEEPSEEK_BASE_URL,
    output_dir: Path = AQ_AGENT_OUTPUT_DIR,
    language: str = "en",
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
        language=language,
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
        planner_notes=_default_planner_notes(candidate, pollutants, chunks, request.include_weather, language=language),
        quality_checks=[
            t("collection.quality_window", language),
            t("collection.quality_non_null", language),
            t("collection.quality_parquet", language),
        ],
        risk_flags=[
            t("collection.risk_coverage", language),
            t("collection.risk_sampling", language),
        ],
    )

    if api_key:
        planner_data = _generate_planner_guidance(plan, api_key=api_key, model=model, base_url=base_url, language=language)
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
    language: str = "en",
) -> CollectionResult:
    plan = build_collection_plan(
        request,
        candidate,
        api_key=api_key,
        model=model,
        base_url=base_url,
        output_dir=output_dir,
        language=language,
    )

    aq_frames: list[pd.DataFrame] = []
    weather_frames: list[pd.DataFrame] = []
    runtime_warnings: list[str] = []

    total_steps = len(plan.chunks) + (len(plan.chunks) if plan.weather_variables else 0) + 2
    step = 0

    for chunk in plan.chunks:
        step += 1
        _notify(progress_callback, step, total_steps, t("collection.progress_air_quality", language, start=chunk["start_date"], end=chunk["end_date"]))
        aq_frame = fetch_air_quality_chunk(plan, chunk)
        if not aq_frame.empty:
            aq_frames.append(aq_frame)

        if plan.weather_variables:
            step += 1
            _notify(progress_callback, step, total_steps, t("collection.progress_weather", language, start=chunk["start_date"], end=chunk["end_date"]))
            try:
                weather_frame = fetch_weather_chunk(plan, chunk)
            except Exception as exc:  # noqa: BLE001
                runtime_warnings.append(
                    t(
                        "collection.weather_skipped",
                        language,
                        start=chunk["start_date"],
                        end=chunk["end_date"],
                        error=exc,
                    )
                )
            else:
                if not weather_frame.empty:
                    weather_frames.append(weather_frame)

    step += 1
    _notify(progress_callback, step, total_steps, t("collection.progress_merge", language))
    air_quality_df = _concat_unique_frames(aq_frames)
    if air_quality_df.empty:
        raise ValueError(t("collection.no_rows", language))

    weather_df = _concat_unique_frames(weather_frames)
    final_df = finalize_collected_dataset(
        air_quality_df,
        weather_df,
        station_name=candidate.name,
        latitude=candidate.latitude,
        longitude=candidate.longitude,
    )

    actual_output_path = save_dataset(final_df, Path(plan.output_path))
    plan.output_path = str(actual_output_path)

    coverage_rows = summarize_dataset_coverage(final_df, plan.pollutants)
    summary_text, summary_mode = generate_collection_summary(
        final_df,
        plan,
        coverage_rows,
        runtime_warnings=runtime_warnings,
        api_key=api_key,
        model=model,
        base_url=base_url,
        language=language,
    )

    step += 1
    _notify(progress_callback, step, total_steps, t("collection.progress_saved", language, path=plan.output_path))

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
    return output_dataset_path(output_dir / filename)


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


def generate_collection_summary(
    df: pd.DataFrame,
    plan: CollectionPlan,
    coverage_rows: list[dict[str, Any]],
    runtime_warnings: list[str] | None = None,
    api_key: str | None = None,
    model: str = AQ_AGENT_DEFAULT_MODEL,
    base_url: str = DEEPSEEK_BASE_URL,
    language: str = "en",
) -> tuple[str, str]:
    deterministic_summary = _default_run_summary(df, plan, coverage_rows, runtime_warnings or [], language=language)
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
        language=language,
    )
    if not summary_data:
        return deterministic_summary, "deterministic"

    llm_summary = str(summary_data.get("summary") or "").strip()
    caveat = str(summary_data.get("caveat") or "").strip()
    if caveat:
        llm_summary = " ".join(part for part in [llm_summary, caveat] if part).strip()
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
    language: str = "en",
) -> str:
    weather_note = t("collection.weather_with", language) if include_weather else t("collection.weather_without", language)
    pollutants_text = ", ".join(pollutant.upper() for pollutant in pollutants)
    return t(
        "collection.default_planner_notes",
        language,
        city=candidate.display_name,
        chunks=len(chunks),
        pollutants=pollutants_text,
        weather_clause=weather_note,
    )


def _default_run_summary(
    df: pd.DataFrame,
    plan: CollectionPlan,
    coverage_rows: list[dict[str, Any]],
    runtime_warnings: list[str],
    language: str = "en",
) -> str:
    coverage_text = ", ".join(
        f"{row['pollutant'].upper()} {row['non_null_ratio']:.0%}" for row in coverage_rows
    )
    warning_text = t("collection.summary_warnings", language, warnings='; '.join(runtime_warnings)) if runtime_warnings else ""
    return t(
        "collection.default_summary",
        language,
        city=plan.city_label,
        rows=len(df),
        start=plan.actual_start_date,
        end=plan.actual_end_date,
        sampling=plan.sampling_step,
        coverage=coverage_text,
        path=plan.output_path,
        warnings=warning_text,
    )


def _tool_calling_system_prompt(allow_run_collection: bool, language: str = "en") -> str:
    run_rule = (
        "You may execute the collection once the request is specific and a city candidate is resolved."
        if allow_run_collection
        else "Do not run data collection; stop after building the plan and explaining it."
    )
    reply_language = "Simplified Chinese" if language == "zh-CN" else "English"
    pollutant_keys = ", ".join(sorted(AQ_AGENT_POLLUTANTS))
    return (
        "You are an air-quality data collection agent embedded in a Streamlit app. "
        "Use tool calls to search cities, build a deterministic collection plan, and optionally run collection. "
        f"Allowed pollutant keys are: {pollutant_keys}. "
        "Search for city candidates first when the target city may be ambiguous. "
        "When multiple candidates exist, prefer the most likely major-city match unless the user specifies otherwise. "
        "Never claim historical coverage outside the dates returned by the planning tool. "
        f"{run_rule} After finishing tool use, reply with a concise user-facing summary in {reply_language}."
    )


def _default_request_context(default_request: CollectionRequest) -> str:
    return (
        "Current UI defaults are available as optional hints, but the user's latest free-text instruction takes priority. "
        f"Defaults: city_query={default_request.city_query!r}, country_code={default_request.country_code!r}, "
        f"start_year={default_request.start_year}, end_year={default_request.end_year}, "
        f"pollutants={default_request.normalized_pollutants()}, include_weather={default_request.include_weather}."
    )


def _collection_request_from_tool_arguments(arguments: dict[str, Any]) -> CollectionRequest:
    city_query = str(arguments.get("city_query") or "").strip()
    if not city_query:
        raise ValueError("Tool arguments must include city_query.")

    pollutants_raw = arguments.get("pollutants") or []
    if not isinstance(pollutants_raw, list):
        raise ValueError("Tool arguments field pollutants must be an array.")

    return CollectionRequest(
        city_query=city_query,
        start_year=int(arguments.get("start_year")),
        end_year=int(arguments.get("end_year")),
        pollutants=[str(item) for item in pollutants_raw],
        include_weather=bool(arguments.get("include_weather", True)),
        country_code=_normalize_country_code(arguments.get("country_code")),
    )


def _resolve_candidate_for_tool(
    request: CollectionRequest,
    *,
    candidate_index: int,
    state: ToolCallingAgentState,
    search_language: str,
) -> tuple[CityCandidate, list[CityCandidate]]:
    normalized_country = _normalize_country_code(request.country_code)
    can_reuse_last_search = (
        state.last_candidates is not None
        and state.last_search_query == request.city_query.strip()
        and state.last_country_code == normalized_country
    )

    if can_reuse_last_search:
        candidates = state.last_candidates or []
    else:
        candidates = search_city_candidates(
            request.city_query,
            country_code=normalized_country,
            count=max(candidate_index + 1, 5),
            language=search_language,
        )
        state.last_candidates = candidates
        state.last_search_query = request.city_query.strip()
        state.last_country_code = normalized_country

    if not candidates:
        raise ValueError(f"No matching city candidates were found for {request.city_query!r}.")
    if candidate_index < 0 or candidate_index >= len(candidates):
        raise ValueError(f"candidate_index {candidate_index} is outside the available range 0..{len(candidates) - 1}.")

    candidate = candidates[candidate_index]
    state.selected_candidate = candidate
    return candidate, candidates


def _candidate_payload(candidate: CityCandidate, index: int | None = None) -> dict[str, Any]:
    payload = candidate.to_dict()
    payload["display_name"] = candidate.display_name
    if index is not None:
        payload["index"] = index
    return payload


def _collection_result_payload(result: CollectionResult) -> dict[str, Any]:
    return {
        "output_path": result.output_path,
        "row_count": result.row_count,
        "started_at": result.started_at,
        "ended_at": result.ended_at,
        "coverage_rows": result.coverage_rows,
        "runtime_warnings": result.runtime_warnings,
        "summary_text": result.summary_text,
        "summary_mode": result.summary_mode,
    }


def _fallback_agent_reply(state: ToolCallingAgentState, allow_run_collection: bool, language: str = "en") -> str:
    if state.last_result is not None:
        return state.last_result.summary_text
    if state.last_plan is not None:
        key = "collection.agent_planned" if not allow_run_collection else "collection.agent_prepared"
        return t(key, language, city=state.last_plan.city_label)
    return t("collection.agent_no_message", language)


def _sanitize_assistant_message(message: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {
        "role": "assistant",
        "content": message.get("content"),
    }
    if message.get("tool_calls"):
        sanitized["tool_calls"] = message["tool_calls"]
    return sanitized


def _generate_planner_guidance(
    plan: CollectionPlan,
    api_key: str,
    model: str,
    base_url: str,
    language: str = "en",
) -> dict[str, Any] | None:
    reply_language = "Simplified Chinese" if language == "zh-CN" else "English"
    messages = [
        {
            "role": "system",
            "content": (
                "You are a data collection planner for an air-quality dashboard. "
                "Return JSON only and never claim data exists outside the provided source window. "
                f"Write planner_notes, quality_checks, and risk_flags in {reply_language}."
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
    language: str = "en",
) -> dict[str, Any] | None:
    reply_language = "Simplified Chinese" if language == "zh-CN" else "English"
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
                "Return JSON only with keys summary and caveat. "
                f"Write both fields in {reply_language}."
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
    payload = _deepseek_chat_completion(
        messages,
        api_key=api_key,
        model=model,
        base_url=base_url,
        temperature=0.1,
        timeout=timeout,
        thinking_type="disabled",
    )
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


def _deepseek_model_candidates(model: str) -> list[str]:
    candidates = [model]
    if model == "deepseek-v4-flash":
        candidates.append("deepseek-chat")
    return candidates


def _deepseek_http_error(response: requests.Response, exc: requests.HTTPError, model: str) -> requests.HTTPError:
    detail = ""
    try:
        body = response.json()
    except Exception:  # noqa: BLE001
        body = response.text.strip()
    if isinstance(body, dict):
        raw_error = body.get("error") or body.get("message") or body.get("reason") or body
        detail = raw_error if isinstance(raw_error, str) else json.dumps(raw_error, ensure_ascii=False)
    else:
        detail = str(body).strip()

    message = f"{exc}. Model: {model}"
    if detail:
        message = f"{message}. Response: {detail}"
    return requests.HTTPError(message, response=response)


def _deepseek_chat_completion(
    messages: list[dict[str, Any]],
    *,
    api_key: str,
    model: str,
    base_url: str,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | None = None,
    temperature: float = 0.1,
    timeout: int = 90,
    thinking_type: str | None = None,
) -> dict[str, Any]:
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    candidates = _deepseek_model_candidates(model)
    last_error: requests.HTTPError | None = None

    for idx, candidate_model in enumerate(candidates):
        payload: dict[str, Any] = {
            "model": candidate_model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
        }
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if thinking_type is not None:
            payload["thinking"] = {"type": thinking_type}

        response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            wrapped = _deepseek_http_error(response, exc, candidate_model)
            last_error = wrapped
            is_last_candidate = idx == len(candidates) - 1
            if response.status_code == 400 and not is_last_candidate:
                continue
            raise wrapped from exc
        return response.json()

    if last_error is not None:
        raise last_error
    raise RuntimeError("DeepSeek request failed before a response was returned.")


def _coerce_tool_arguments(raw_arguments: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_arguments, dict):
        return raw_arguments

    text = str(raw_arguments or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _extract_json_object(text)


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


def _normalize_country_code(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


