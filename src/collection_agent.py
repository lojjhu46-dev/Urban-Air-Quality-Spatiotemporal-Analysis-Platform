from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from time import sleep
from typing import Any, Callable

import pandas as pd
import requests

import src.collection_data_pipeline as collection_data_pipeline
import src.collection_agent_summary as collection_agent_summary
import src.collection_agent_tools as collection_agent_tools
import src.collection_proxy_fallback as collection_proxy_fallback
import src.custom_city_validation as custom_city_validation
import src.deepseek_client as deepseek_client
from src.config import (
    AQ_AGENT_CHUNK_DAYS,
    AQ_AGENT_DEFAULT_MODEL,
    AQ_AGENT_OUTPUT_DIR,
    AQ_AGENT_POLLUTANTS,
    DEEPSEEK_BASE_URL,
    EUROPE_COUNTRY_CODES,
    OPEN_METEO_GEOCODING_URL,
)
from src.agent_interaction import china_province_city_names, resolve_china_catalog_province
from src.i18n import t
from src.collection_data_pipeline import (
    WEATHER_API_FIELDS,
    _concat_unique_frames,
    _normalize_local_times,
    _normalize_numeric_values,
    _open_meteo_unavailable_message,
    build_output_path,
    chunk_date_range,
    finalize_collected_dataset,
    resolve_supported_window,
    save_dataset,
    slugify,
    summarize_dataset_coverage,
    weather_archive_available_end,
    weather_archive_chunk_window,
)
from src.custom_city_validation import CustomCityValidationResult

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
    weather_fields: list[str] | None = None

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

    def normalized_weather_fields(self) -> list[str]:
        if not self.include_weather:
            return []

        raw_values = self.weather_fields if self.weather_fields is not None else list(WEATHER_API_FIELDS.keys())
        seen: set[str] = set()
        normalized: list[str] = []
        for item in raw_values:
            key = str(item).strip().lower()
            if key in WEATHER_API_FIELDS and key not in seen:
                normalized.append(key)
                seen.add(key)
        if not normalized:
            normalized = list(WEATHER_API_FIELDS.keys())
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


def custom_city_validation_from_dict(data: dict[str, Any]) -> CustomCityValidationResult:
    return custom_city_validation.custom_city_validation_from_dict(data)


def validate_custom_city_with_deepseek(
    country_or_region: str,
    city_name: str,
    *,
    api_key: str,
    model: str = AQ_AGENT_DEFAULT_MODEL,
    base_url: str = DEEPSEEK_BASE_URL,
    language: str = "en",
) -> CustomCityValidationResult:
    clean_country = country_or_region.strip()
    clean_city = city_name.strip()
    if not clean_country or not clean_city:
        raise ValueError(t("agent.custom_city_inputs_required", language))
    if not str(api_key).strip():
        raise ValueError(t("agent.custom_city_requires_key", language))

    reply_language = "Simplified Chinese" if language == "zh-CN" else "English"
    messages = [
        {
            "role": "system",
            "content": (
                "You validate user-entered global city searches for an air-quality collection agent. "
                "Return JSON only with keys status, corrected_country, corrected_city, country_code, "
                "matching_countries, message. "
                "status must be one of valid, needs_confirmation, low_confidence. "
                "Use ISO-3166 alpha-2 country_code when one country/region is likely. "
                "If the city name exists in multiple countries, list all plausible countries in matching_countries "
                "and set status to needs_confirmation. "
                "If spelling is close, fill corrected_country/corrected_city and set status to needs_confirmation. "
                "If confidence is low, set status to low_confidence and leave country_code empty. "
                f"Write message in {reply_language}."
            ),
        },
        {
            "role": "user",
            "content": (
                "Validate this requested location before data collection.\n"
                f"Country/region input: {clean_country}\n"
                f"City input: {clean_city}\n"
                "Do not collect data. Only validate the location and return the JSON object."
            ),
        },
    ]
    data = _deepseek_json_completion(messages, api_key=api_key, model=model, base_url=base_url, timeout=90)
    if not data:
        raise ValueError(t("agent.custom_city_validation_unavailable", language))

    return custom_city_validation.custom_city_validation_from_model_response(clean_country, clean_city, data, language=language)


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
    return collection_agent_tools.get_collection_agent_tool_schemas(
        pollutant_keys=list(AQ_AGENT_POLLUTANTS),
        weather_keys=list(WEATHER_API_FIELDS),
        include_run_collection=include_run_collection,
    )


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
    return collection_agent_tools.execute_collection_agent_tool(
        name,
        raw_arguments,
        state=state,
        progress_callback=progress_callback,
        output_dir=output_dir,
        search_language=search_language,
        language=language,
        coerce_tool_arguments=_coerce_tool_arguments,
        normalize_country_code=_normalize_country_code,
        request_factory=CollectionRequest,
        search_fn=search_city_candidates,
        build_plan_fn=build_collection_plan,
        run_collection_fn=run_collection_agent,
    )


def _default_request_tool_arguments(default_request: CollectionRequest) -> dict[str, Any]:
    return collection_agent_tools.default_request_tool_arguments(default_request)


def _execute_default_request_tool_flow(
    default_request: CollectionRequest,
    *,
    allow_run_collection: bool,
    state: ToolCallingAgentState,
    tool_trace: list[dict[str, Any]],
    progress_callback: ProgressCallback | None,
    output_dir: Path,
    search_language: str,
    language: str,
) -> None:
    collection_agent_tools.execute_default_request_tool_flow(
        default_request,
        allow_run_collection=allow_run_collection,
        state=state,
        tool_trace=tool_trace,
        execute_tool=execute_collection_agent_tool,
        progress_callback=progress_callback,
        output_dir=output_dir,
        search_language=search_language,
        language=language,
    )


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
            if collection_agent_tools.should_execute_default_request_flow(
                default_request=default_request,
                allow_run_collection=allow_run_collection,
                state=state,
            ):
                _execute_default_request_tool_flow(
                    default_request,
                    allow_run_collection=allow_run_collection,
                    state=state,
                    tool_trace=tool_trace,
                    progress_callback=progress_callback,
                    output_dir=output_dir,
                    search_language=search_language,
                    language=language,
                )
            final_message = _fallback_agent_reply(state, allow_run_collection, language=language) or last_assistant_content
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

    if collection_agent_tools.should_execute_default_request_flow(
        default_request=default_request,
        allow_run_collection=allow_run_collection,
        state=state,
    ):
        _execute_default_request_tool_flow(
            default_request,
            allow_run_collection=allow_run_collection,
            state=state,
            tool_trace=tool_trace,
            progress_callback=progress_callback,
            output_dir=output_dir,
            search_language=search_language,
            language=language,
        )
    final_message = _fallback_agent_reply(state, allow_run_collection, language=language) or last_assistant_content
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
    weather_fields = request.normalized_weather_fields()
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
        weather_variables=[WEATHER_API_FIELDS[key] for key in weather_fields],
        chunks=chunks,
        output_path=str(output_path),
        warnings=warnings,
        planner_mode="deterministic",
        planner_model=None,
        planner_notes=_default_planner_notes(candidate, pollutants, chunks, weather_fields, language=language),
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
    final_df, runtime_warnings = _collect_candidate_dataset(
        plan,
        candidate,
        progress_callback=progress_callback,
        language=language,
    )
    coverage_rows = summarize_dataset_coverage(final_df, plan.pollutants)

    if not _has_usable_coverage_rows(coverage_rows):
        fallback = _maybe_collect_with_deepseek_proxy(
            request,
            candidate,
            initial_warnings=runtime_warnings,
            api_key=api_key,
            model=model,
            base_url=base_url,
            output_dir=output_dir,
            language=language,
            progress_callback=progress_callback,
        )
        if fallback is not None:
            plan, final_df, runtime_warnings, coverage_rows = fallback
        elif final_df.empty:
            raise ValueError(t("collection.no_rows", language))
        else:
            raise ValueError(t("collection.no_usable_rows", language))

    actual_output_path = save_dataset(final_df, Path(plan.output_path))
    plan.output_path = str(actual_output_path)
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
    _notify(progress_callback, 1, 1, t("collection.progress_saved", language, path=plan.output_path))

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


def _collect_candidate_dataset(
    plan: CollectionPlan,
    candidate: CityCandidate,
    *,
    progress_callback: ProgressCallback | None = None,
    language: str = "en",
) -> tuple[pd.DataFrame, list[str]]:
    aq_frames: list[pd.DataFrame] = []
    weather_frames: list[pd.DataFrame] = []
    runtime_warnings: list[str] = []

    total_steps = len(plan.chunks) + (len(plan.chunks) if plan.weather_variables else 0) + 1
    step = 0

    for chunk in plan.chunks:
        step += 1
        _notify(
            progress_callback,
            step,
            total_steps,
            t("collection.progress_air_quality", language, start=chunk["start_date"], end=chunk["end_date"]),
        )
        aq_frame = fetch_air_quality_chunk(plan, chunk)
        if not aq_frame.empty:
            aq_frames.append(aq_frame)

        if plan.weather_variables:
            step += 1
            _notify(
                progress_callback,
                step,
                total_steps,
                t("collection.progress_weather", language, start=chunk["start_date"], end=chunk["end_date"]),
            )
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

    _notify(progress_callback, total_steps, total_steps, t("collection.progress_merge", language))
    air_quality_df = _concat_unique_frames(aq_frames)
    if air_quality_df.empty:
        return pd.DataFrame(columns=["timestamp", *plan.pollutants]), runtime_warnings

    weather_df = _concat_unique_frames(weather_frames)
    final_df = finalize_collected_dataset(
        air_quality_df,
        weather_df,
        station_name=candidate.name,
        latitude=candidate.latitude,
        longitude=candidate.longitude,
    )
    return final_df, runtime_warnings


def _maybe_collect_with_deepseek_proxy(
    request: CollectionRequest,
    candidate: CityCandidate,
    *,
    initial_warnings: list[str],
    api_key: str | None,
    model: str,
    base_url: str,
    output_dir: Path,
    language: str,
    progress_callback: ProgressCallback | None,
) -> tuple[CollectionPlan, pd.DataFrame, list[str], list[dict[str, Any]]] | None:
    return collection_proxy_fallback.maybe_collect_with_deepseek_proxy(
        request,
        candidate,
        initial_warnings=initial_warnings,
        api_key=api_key,
        model=model,
        base_url=base_url,
        output_dir=output_dir,
        language=language,
        progress_callback=progress_callback,
        province_city_names=china_province_city_names,
        candidate_catalog_province_fn=_candidate_catalog_province,
        same_candidate_fn=_same_candidate,
        generate_proxy_plan=_generate_proxy_city_plan,
        search_city_candidates=search_city_candidates,
        collect_proxy=_collect_proxy_candidate,
        unique_strings=_unique_strings,
        translate=t,
        notify=_notify,
    )


def _collect_proxy_candidate(
    request: CollectionRequest,
    candidate: CityCandidate,
    *,
    output_dir: Path,
    language: str,
) -> tuple[CollectionPlan, pd.DataFrame, list[str], list[dict[str, Any]]] | None:
    return collection_proxy_fallback.collect_proxy_candidate(
        request,
        candidate,
        output_dir=output_dir,
        language=language,
        build_plan=build_collection_plan,
        collect_dataset=_collect_candidate_dataset,
        summarize_coverage=summarize_dataset_coverage,
        has_usable_coverage_rows=_has_usable_coverage_rows,
    )


def fetch_air_quality_chunk(plan: CollectionPlan, chunk: dict[str, str]) -> pd.DataFrame:
    return collection_data_pipeline.fetch_air_quality_chunk(plan, chunk, get_json=_safe_get_json)


def fetch_weather_chunk(plan: CollectionPlan, chunk: dict[str, str]) -> pd.DataFrame:
    return collection_data_pipeline.fetch_weather_chunk(plan, chunk, get_json=_safe_get_json, today=date.today())


def _safe_get_json(url: str, params: dict[str, Any], timeout: int = 45, retries: int = 2) -> dict[str, Any]:
    original_requests = collection_data_pipeline.requests
    original_sleep = collection_data_pipeline.sleep
    collection_data_pipeline.requests = requests
    collection_data_pipeline.sleep = sleep
    try:
        return collection_data_pipeline._safe_get_json(url, params, timeout=timeout, retries=retries)
    finally:
        collection_data_pipeline.requests = original_requests
        collection_data_pipeline.sleep = original_sleep


def _has_usable_coverage_rows(rows: list[dict[str, Any]]) -> bool:
    return any(float(row.get("non_null_ratio") or 0.0) > 0.0 for row in rows)


def _candidate_catalog_province(candidate: CityCandidate) -> str | None:
    return collection_proxy_fallback.candidate_catalog_province(
        candidate,
        resolve_province=resolve_china_catalog_province,
    )


def _same_candidate(left: CityCandidate, right: CityCandidate) -> bool:
    return collection_proxy_fallback.same_candidate(
        left,
        right,
        normalize_location_key=_normalize_location_key,
    )


def _generate_proxy_city_plan(
    request: CollectionRequest,
    candidate: CityCandidate,
    *,
    province: str,
    api_key: str,
    model: str,
    base_url: str,
    language: str = "en",
) -> dict[str, Any] | None:
    return collection_proxy_fallback.generate_proxy_city_plan(
        request,
        candidate,
        province=province,
        api_key=api_key,
        model=model,
        base_url=base_url,
        json_completion=_json_completion_for_proxy,
        province_city_names=china_province_city_names,
        normalize_location_key=_normalize_location_key,
        unique_strings=_unique_strings,
        language=language,
    )


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
    return collection_agent_summary.merge_run_summary(deterministic_summary, summary_data, model)


def _default_planner_notes(
    candidate: CityCandidate,
    pollutants: list[str],
    chunks: list[dict[str, str]],
    weather_fields: list[str],
    language: str = "en",
) -> str:
    return collection_agent_summary.default_planner_notes(candidate, pollutants, chunks, weather_fields, language=language)


def _default_run_summary(
    df: pd.DataFrame,
    plan: CollectionPlan,
    coverage_rows: list[dict[str, Any]],
    runtime_warnings: list[str],
    language: str = "en",
) -> str:
    return collection_agent_summary.default_run_summary(df, plan, coverage_rows, runtime_warnings, language=language)


def _tool_calling_system_prompt(allow_run_collection: bool, language: str = "en") -> str:
    return collection_agent_tools.tool_calling_system_prompt(
        allow_run_collection=allow_run_collection,
        pollutant_keys=list(AQ_AGENT_POLLUTANTS),
        language=language,
    )


def _default_request_context(default_request: CollectionRequest) -> str:
    return collection_agent_tools.default_request_context(default_request)


def _collection_request_from_tool_arguments(arguments: dict[str, Any]) -> CollectionRequest:
    return collection_agent_tools.collection_request_from_tool_arguments(
        arguments,
        request_factory=CollectionRequest,
        normalize_country_code=_normalize_country_code,
    )


def _resolve_candidate_for_tool(
    request: CollectionRequest,
    *,
    candidate_index: int,
    state: ToolCallingAgentState,
    search_language: str,
) -> tuple[CityCandidate, list[CityCandidate]]:
    return collection_agent_tools.resolve_candidate_for_tool(
        request,
        candidate_index=candidate_index,
        state=state,
        search_language=search_language,
        search_fn=search_city_candidates,
        normalize_country_code=_normalize_country_code,
    )


def _candidate_payload(candidate: CityCandidate, index: int | None = None) -> dict[str, Any]:
    return collection_agent_tools.candidate_payload(candidate, index)


def _collection_result_payload(result: CollectionResult) -> dict[str, Any]:
    return collection_agent_tools.collection_result_payload(result)


def _fallback_agent_reply(state: ToolCallingAgentState, allow_run_collection: bool, language: str = "en") -> str:
    return collection_agent_tools.fallback_agent_reply(
        state,
        allow_run_collection=allow_run_collection,
        translate=t,
        language=language,
    )


def _sanitize_assistant_message(message: dict[str, Any]) -> dict[str, Any]:
    return collection_agent_tools.sanitize_assistant_message(message)


def _generate_planner_guidance(
    plan: CollectionPlan,
    api_key: str,
    model: str,
    base_url: str,
    language: str = "en",
) -> dict[str, Any] | None:
    return collection_agent_summary.generate_planner_guidance(
        plan,
        api_key,
        model,
        base_url,
        json_completion=_json_completion_for_summary,
        language=language,
    )


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
    return collection_agent_summary.generate_run_summary(
        df,
        plan,
        coverage_rows,
        runtime_warnings,
        api_key,
        model,
        base_url,
        json_completion=_json_completion_for_summary,
        language=language,
    )


def _json_completion_for_summary(
    messages: list[dict[str, Any]],
    api_key: str,
    model: str,
    base_url: str,
    timeout: int,
) -> dict[str, Any] | None:
    return _deepseek_json_completion(messages, api_key=api_key, model=model, base_url=base_url, timeout=timeout)


def _json_completion_for_proxy(
    messages: list[dict[str, Any]],
    api_key: str,
    model: str,
    base_url: str,
    timeout: int,
) -> dict[str, Any] | None:
    return _deepseek_json_completion(messages, api_key=api_key, model=model, base_url=base_url, timeout=timeout)


def _deepseek_json_completion(
    messages: list[dict[str, Any]],
    api_key: str,
    model: str,
    base_url: str,
    timeout: int = 90,
) -> dict[str, Any] | None:
    return deepseek_client.deepseek_json_completion(
        messages,
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout=timeout,
        chat_completion=_deepseek_chat_completion,
    )


def _deepseek_model_candidates(model: str) -> list[str]:
    return deepseek_client.deepseek_model_candidates(model)


def _deepseek_http_error(response: requests.Response, exc: requests.HTTPError, model: str) -> requests.HTTPError:
    return deepseek_client.deepseek_http_error(response, exc, model)


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
    return deepseek_client.deepseek_chat_completion(
        messages,
        api_key=api_key,
        model=model,
        base_url=base_url,
        tools=tools,
        tool_choice=tool_choice,
        temperature=temperature,
        timeout=timeout,
        thinking_type=thinking_type,
        post=requests.post,
        model_candidates=_deepseek_model_candidates,
        http_error_factory=_deepseek_http_error,
    )


def _coerce_tool_arguments(raw_arguments: str | dict[str, Any]) -> dict[str, Any]:
    return deepseek_client.coerce_tool_arguments(raw_arguments)


def _extract_json_object(content: str) -> dict[str, Any]:
    return deepseek_client.extract_json_object(content)


def _notify(callback: ProgressCallback | None, step: int, total_steps: int, message: str) -> None:
    if callback is not None:
        callback(step, total_steps, message)


def _unique_strings(values: list[str]) -> list[str]:
    return custom_city_validation.unique_strings(values)


def _normalize_custom_city_status(raw_status: Any, message: Any = None) -> str:
    return custom_city_validation.normalize_custom_city_status(raw_status, message)


def _normalize_country_code(value: Any) -> str | None:
    return custom_city_validation.normalize_country_code(value)


def _normalize_location_key(value: Any) -> str:
    return custom_city_validation.normalize_location_key(value)
