from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol


RequestFactory = Callable[..., Any]
CountryCodeNormalizer = Callable[[Any], str | None]
Translator = Callable[..., str]
ToolExecutor = Callable[..., dict[str, Any]]
SearchFn = Callable[..., list[Any]]
PlanBuilder = Callable[..., Any]
CollectFn = Callable[..., Any]
CoerceFn = Callable[[str | dict[str, Any]], dict[str, Any]]


class CollectionRequestLike(Protocol):
    city_query: str
    country_code: str | None
    start_year: int
    end_year: int
    include_weather: bool

    def normalized_pollutants(self) -> list[str]: ...

    def normalized_weather_fields(self) -> list[str]: ...


class CityCandidateLike(Protocol):
    name: str
    display_name: str

    def to_dict(self) -> dict[str, Any]: ...


class CollectionPlanLike(Protocol):
    city_label: str

    def to_dict(self) -> dict[str, Any]: ...


class CollectionResultLike(Protocol):
    plan: Any
    output_path: str
    row_count: int
    started_at: str
    ended_at: str
    coverage_rows: list[dict[str, Any]]
    runtime_warnings: list[str]
    summary_text: str
    summary_mode: str


class ToolCallingStateLike(Protocol):
    last_plan: Any | None
    last_result: Any | None


class ToolCallingMutableState(Protocol):
    last_candidates: list[Any] | None
    last_search_query: str | None
    last_country_code: str | None
    selected_candidate: Any | None
    last_plan: Any | None
    last_result: Any | None


def get_collection_agent_tool_schemas(
    *,
    pollutant_keys: list[str],
    weather_keys: list[str],
    include_run_collection: bool = True,
) -> list[dict[str, Any]]:
    sorted_pollutant_keys = sorted(pollutant_keys)
    sorted_weather_keys = sorted(weather_keys)
    request_properties = {
        "city_query": {"type": "string", "description": "City name to collect."},
        "country_code": {"type": "string", "description": "Optional ISO-3166 alpha-2 country code."},
        "start_year": {"type": "integer", "minimum": 2013},
        "end_year": {"type": "integer", "minimum": 2013},
        "pollutants": {
            "type": "array",
            "items": {"type": "string", "enum": sorted_pollutant_keys},
            "minItems": 1,
        },
        "include_weather": {"type": "boolean", "description": "Whether to enrich with weather columns."},
        "weather_fields": {
            "type": "array",
            "items": {"type": "string", "enum": sorted_weather_keys},
            "description": "Optional subset of weather fields to include when include_weather is true.",
        },
        "candidate_index": {
            "type": "integer",
            "description": "Index from the last city search result to use as the resolved city candidate.",
            "minimum": 0,
        },
    }

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
                "properties": request_properties,
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
                        "properties": request_properties,
                        "required": ["city_query", "start_year", "end_year", "pollutants"],
                    },
                },
            }
        )
    return tools


def collection_request_from_tool_arguments(
    arguments: dict[str, Any],
    *,
    request_factory: RequestFactory,
    normalize_country_code: CountryCodeNormalizer,
) -> Any:
    city_query = str(arguments.get("city_query") or "").strip()
    if not city_query:
        raise ValueError("Tool arguments must include city_query.")

    pollutants_raw = arguments.get("pollutants") or []
    if not isinstance(pollutants_raw, list):
        raise ValueError("Tool arguments field pollutants must be an array.")
    weather_fields_raw = arguments.get("weather_fields")
    if weather_fields_raw is not None and not isinstance(weather_fields_raw, list):
        raise ValueError("Tool arguments field weather_fields must be an array when provided.")

    return request_factory(
        city_query=city_query,
        start_year=int(arguments.get("start_year")),
        end_year=int(arguments.get("end_year")),
        pollutants=[str(item) for item in pollutants_raw],
        include_weather=bool(arguments.get("include_weather", True)),
        country_code=normalize_country_code(arguments.get("country_code")),
        weather_fields=[str(item) for item in weather_fields_raw] if isinstance(weather_fields_raw, list) else None,
    )


def default_request_tool_arguments(default_request: CollectionRequestLike) -> dict[str, Any]:
    return {
        "city_query": default_request.city_query,
        "country_code": default_request.country_code,
        "start_year": default_request.start_year,
        "end_year": default_request.end_year,
        "pollutants": default_request.normalized_pollutants(),
        "include_weather": default_request.include_weather,
        "weather_fields": default_request.normalized_weather_fields(),
        "candidate_index": 0,
    }


def tool_calling_system_prompt(
    *,
    allow_run_collection: bool,
    pollutant_keys: list[str],
    language: str = "en",
) -> str:
    run_rule = (
        "You may execute the collection once the request is specific and a city candidate is resolved."
        if allow_run_collection
        else "Do not run data collection; stop after building the plan and explaining it."
    )
    reply_language = "Simplified Chinese" if language == "zh-CN" else "English"
    sorted_pollutant_keys = ", ".join(sorted(pollutant_keys))
    return (
        "You are an air-quality data collection agent embedded in a Streamlit app. "
        "Use tool calls to search cities, build a deterministic collection plan, and optionally run collection. "
        f"Allowed pollutant keys are: {sorted_pollutant_keys}. "
        "Search for city candidates first when the target city may be ambiguous. "
        "When multiple candidates exist, prefer the most likely major-city match unless the user specifies otherwise. "
        "Never claim historical coverage outside the dates returned by the planning tool. "
        f"{run_rule} After finishing tool use, reply with a concise user-facing summary in {reply_language}."
    )


def default_request_context(default_request: CollectionRequestLike) -> str:
    return (
        "Current UI defaults are available as optional hints, but the user's latest free-text instruction takes priority. "
        f"Defaults: city_query={default_request.city_query!r}, country_code={default_request.country_code!r}, "
        f"start_year={default_request.start_year}, end_year={default_request.end_year}, "
        f"pollutants={default_request.normalized_pollutants()}, include_weather={default_request.include_weather}, "
        f"weather_fields={default_request.normalized_weather_fields()}."
    )


def execute_default_request_tool_flow(
    default_request: CollectionRequestLike,
    *,
    allow_run_collection: bool,
    state: ToolCallingStateLike,
    tool_trace: list[dict[str, Any]],
    execute_tool: ToolExecutor,
    progress_callback: Any | None,
    output_dir: Path,
    search_language: str,
    language: str,
) -> None:
    search_arguments = {
        "query": default_request.city_query,
        "country_code": default_request.country_code,
        "count": 5,
    }
    search_output = execute_tool(
        "search_city_candidates",
        search_arguments,
        state=state,
        progress_callback=progress_callback,
        output_dir=output_dir,
        search_language=search_language,
        language=language,
    )
    tool_trace.append({"tool": "search_city_candidates", "arguments": search_arguments, "result": search_output})

    tool_name = "run_collection" if allow_run_collection else "build_collection_plan"
    tool_arguments = default_request_tool_arguments(default_request)
    tool_output = execute_tool(
        tool_name,
        tool_arguments,
        state=state,
        progress_callback=progress_callback,
        output_dir=output_dir,
        search_language=search_language,
        language=language,
    )
    tool_trace.append({"tool": tool_name, "arguments": tool_arguments, "result": tool_output})


def should_execute_default_request_flow(
    *,
    default_request: CollectionRequestLike | None,
    allow_run_collection: bool,
    state: ToolCallingStateLike,
) -> bool:
    return default_request is not None and (
        (allow_run_collection and state.last_result is None)
        or (not allow_run_collection and state.last_plan is None)
    )


def fallback_agent_reply(
    state: ToolCallingStateLike,
    *,
    allow_run_collection: bool,
    translate: Translator,
    language: str = "en",
) -> str:
    if state.last_result is not None:
        return state.last_result.summary_text
    if state.last_plan is not None:
        key = "collection.agent_planned" if not allow_run_collection else "collection.agent_prepared"
        return translate(key, language, city=state.last_plan.city_label)
    return translate("collection.agent_no_message", language)


def candidate_payload(candidate: CityCandidateLike, index: int | None = None) -> dict[str, Any]:
    payload = candidate.to_dict()
    payload["display_name"] = candidate.display_name
    if index is not None:
        payload["index"] = index
    return payload


def collection_result_payload(result: CollectionResultLike) -> dict[str, Any]:
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


def sanitize_assistant_message(message: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {
        "role": "assistant",
        "content": message.get("content"),
    }
    if message.get("tool_calls"):
        sanitized["tool_calls"] = message["tool_calls"]
    return sanitized


def resolve_candidate_for_tool(
    request: CollectionRequestLike,
    *,
    candidate_index: int,
    state: ToolCallingMutableState,
    search_language: str,
    search_fn: SearchFn,
    normalize_country_code: CountryCodeNormalizer,
) -> tuple[Any, list[Any]]:
    normalized_country = normalize_country_code(request.country_code)
    can_reuse_last_search = (
        state.last_candidates is not None
        and state.last_search_query == request.city_query.strip()
        and state.last_country_code == normalized_country
    )

    if can_reuse_last_search:
        candidates = state.last_candidates or []
    else:
        candidates = search_fn(
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

    state.selected_candidate = candidates[candidate_index]
    return candidates[candidate_index], candidates


def execute_collection_agent_tool(
    name: str,
    raw_arguments: str | dict[str, Any],
    *,
    state: ToolCallingMutableState,
    progress_callback: Any | None = None,
    output_dir: Path,
    search_language: str = "en",
    language: str = "en",
    coerce_tool_arguments: CoerceFn,
    normalize_country_code: CountryCodeNormalizer,
    request_factory: RequestFactory,
    search_fn: SearchFn,
    build_plan_fn: PlanBuilder,
    run_collection_fn: CollectFn,
) -> dict[str, Any]:
    arguments = coerce_tool_arguments(raw_arguments)

    if name == "search_city_candidates":
        query = str(arguments.get("query") or "").strip()
        country_code = normalize_country_code(arguments.get("country_code"))
        count = int(arguments.get("count", 5))
        candidates = search_fn(query, country_code=country_code, count=count, language=search_language)
        state.last_candidates = candidates
        state.last_search_query = query
        state.last_country_code = country_code
        return {
            "query": query,
            "country_code": country_code,
            "candidate_count": len(candidates),
            "candidates": [candidate_payload(candidate, index) for index, candidate in enumerate(candidates)],
        }

    if name == "build_collection_plan":
        request = collection_request_from_tool_arguments(
            arguments,
            request_factory=request_factory,
            normalize_country_code=normalize_country_code,
        )
        candidate_index = int(arguments.get("candidate_index", 0))
        candidate, candidates = resolve_candidate_for_tool(
            request,
            candidate_index=candidate_index,
            state=state,
            search_language=search_language,
            search_fn=search_fn,
            normalize_country_code=normalize_country_code,
        )
        plan = build_plan_fn(request, candidate, api_key=None, output_dir=output_dir, language=language)
        state.last_plan = plan
        return {
            "selected_candidate": candidate_payload(candidate, candidate_index),
            "candidate_count": len(candidates),
            "plan": plan.to_dict(),
        }

    if name == "run_collection":
        request = collection_request_from_tool_arguments(
            arguments,
            request_factory=request_factory,
            normalize_country_code=normalize_country_code,
        )
        candidate_index = int(arguments.get("candidate_index", 0))
        candidate, candidates = resolve_candidate_for_tool(
            request,
            candidate_index=candidate_index,
            state=state,
            search_language=search_language,
            search_fn=search_fn,
            normalize_country_code=normalize_country_code,
        )
        result = run_collection_fn(
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
            "selected_candidate": candidate_payload(candidate, candidate_index),
            "candidate_count": len(candidates),
            "plan": result.plan.to_dict(),
            "collection_result": collection_result_payload(result),
        }

    raise ValueError(f"Unsupported agent tool: {name}")
