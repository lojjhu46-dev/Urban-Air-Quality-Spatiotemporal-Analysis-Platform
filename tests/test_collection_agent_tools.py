from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from src.collection_agent_tools import (
    candidate_payload,
    collection_request_from_tool_arguments,
    collection_result_payload,
    default_request_context,
    default_request_tool_arguments,
    execute_collection_agent_tool,
    execute_default_request_tool_flow,
    fallback_agent_reply,
    get_collection_agent_tool_schemas,
    resolve_candidate_for_tool,
    sanitize_assistant_message,
    should_execute_default_request_flow,
    tool_calling_system_prompt,
)


@dataclass(slots=True)
class FakeRequest:
    city_query: str
    start_year: int
    end_year: int
    pollutants: list[str]
    include_weather: bool = True
    country_code: str | None = None
    weather_fields: list[str] | None = None

    def normalized_pollutants(self) -> list[str]:
        return [item.lower() for item in self.pollutants]

    def normalized_weather_fields(self) -> list[str]:
        return self.weather_fields or []


@dataclass(slots=True)
class FakeCandidate:
    name: str = "Tokyo"
    country: str = "Japan"

    @property
    def display_name(self) -> str:
        return f"{self.name}, {self.country}"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "country": self.country}


@dataclass
class FakeResult:
    plan: Any = None
    output_path: str = "data/tokyo.parquet"
    row_count: int = 3
    started_at: str = "2024-01-01 00:00:00"
    ended_at: str = "2024-01-01 00:01:00"
    coverage_rows: list[dict[str, Any]] | None = None
    runtime_warnings: list[str] | None = None
    summary_text: str = "Saved Tokyo data."
    summary_mode: str = "deterministic"

    def __post_init__(self) -> None:
        if self.plan is None:
            self.plan = FakePlan("dummy")
        if self.coverage_rows is None:
            self.coverage_rows = [{"pollutant": "pm25", "non_null_ratio": 1.0}]
        if self.runtime_warnings is None:
            self.runtime_warnings = []


@dataclass
class FakePlan:
    city_label: str = "Tokyo, Japan"

    def to_dict(self) -> dict[str, Any]:
        return {"city_label": self.city_label}


@dataclass(slots=True)
class FakeState:
    last_plan: FakePlan | None = None
    last_result: FakeResult | None = None


@dataclass(slots=True)
class FakeMutableState:
    last_candidates: list[FakeCandidate] | None = None
    last_search_query: str | None = None
    last_country_code: str | None = None
    selected_candidate: FakeCandidate | None = None
    last_plan: FakePlan | None = None
    last_result: FakeResult | None = None


def test_tool_schemas_can_exclude_run_collection() -> None:
    tools = get_collection_agent_tool_schemas(
        pollutant_keys=["o3", "pm25"],
        weather_keys=["temp"],
        include_run_collection=False,
    )

    assert [tool["function"]["name"] for tool in tools] == ["search_city_candidates", "build_collection_plan"]
    plan_schema = tools[1]["function"]["parameters"]["properties"]
    assert plan_schema["pollutants"]["items"]["enum"] == ["o3", "pm25"]
    assert plan_schema["weather_fields"]["items"]["enum"] == ["temp"]


def test_tool_schemas_include_run_collection_by_default() -> None:
    tools = get_collection_agent_tool_schemas(pollutant_keys=["pm25"], weather_keys=["temp"])

    assert [tool["function"]["name"] for tool in tools] == [
        "search_city_candidates",
        "build_collection_plan",
        "run_collection",
    ]


def test_collection_request_from_tool_arguments_validates_arrays() -> None:
    with pytest.raises(ValueError, match="pollutants must be an array"):
        collection_request_from_tool_arguments(
            {"city_query": "Tokyo", "start_year": 2024, "end_year": 2024, "pollutants": "pm25"},
            request_factory=FakeRequest,
            normalize_country_code=lambda value: str(value).upper() if value else None,
        )

    with pytest.raises(ValueError, match="city_query"):
        collection_request_from_tool_arguments(
            {"start_year": 2024, "end_year": 2024, "pollutants": ["pm25"]},
            request_factory=FakeRequest,
            normalize_country_code=lambda value: str(value).upper() if value else None,
        )


def test_collection_request_from_tool_arguments_normalizes_payload() -> None:
    request = collection_request_from_tool_arguments(
        {
            "city_query": " Tokyo ",
            "country_code": " jp ",
            "start_year": "2024",
            "end_year": "2025",
            "pollutants": ["pm25", "O3"],
            "include_weather": False,
            "weather_fields": ["temp"],
        },
        request_factory=FakeRequest,
        normalize_country_code=lambda value: str(value).strip().upper() if value else None,
    )

    assert request.city_query == "Tokyo"
    assert request.country_code == "JP"
    assert request.start_year == 2024
    assert request.end_year == 2025
    assert request.pollutants == ["pm25", "O3"]
    assert request.include_weather is False
    assert request.weather_fields == ["temp"]


def test_default_request_tool_arguments_and_payload_helpers() -> None:
    request = FakeRequest("Tokyo", 2024, 2024, ["PM25"], country_code="JP", weather_fields=["temp"])
    result_payload = collection_result_payload(FakeResult())

    assert default_request_tool_arguments(request) == {
        "city_query": "Tokyo",
        "country_code": "JP",
        "start_year": 2024,
        "end_year": 2024,
        "pollutants": ["pm25"],
        "include_weather": True,
        "weather_fields": ["temp"],
        "candidate_index": 0,
    }
    assert candidate_payload(FakeCandidate(), 2) == {"name": "Tokyo", "country": "Japan", "display_name": "Tokyo, Japan", "index": 2}
    assert result_payload["summary_text"] == "Saved Tokyo data."
    assert result_payload["coverage_rows"] == [{"pollutant": "pm25", "non_null_ratio": 1.0}]


def test_tool_calling_prompt_and_default_request_context() -> None:
    prompt = tool_calling_system_prompt(allow_run_collection=False, pollutant_keys=["pm25", "o3"], language="zh-CN")
    request = FakeRequest("Tokyo", 2024, 2025, ["PM25"], country_code="JP", weather_fields=["temp"])
    context = default_request_context(request)

    assert "Do not run data collection" in prompt
    assert "pm25" in prompt
    assert "Simplified Chinese" in prompt
    assert "city_query='Tokyo'" in context
    assert "weather_fields=['temp']" in context


def test_fallback_agent_reply_prefers_result_then_plan() -> None:
    def fake_translate(key: str, language: str, **kwargs: object) -> str:
        return f"{language}:{key}:{kwargs.get('city', '')}"

    assert fallback_agent_reply(FakeState(last_result=FakeResult()), allow_run_collection=True, translate=fake_translate) == "Saved Tokyo data."
    assert (
        fallback_agent_reply(FakeState(last_plan=FakePlan()), allow_run_collection=False, translate=fake_translate, language="en")
        == "en:collection.agent_planned:Tokyo, Japan"
    )
    assert fallback_agent_reply(FakeState(), allow_run_collection=True, translate=fake_translate, language="en") == "en:collection.agent_no_message:"


def test_should_execute_default_request_flow_checks_missing_terminal_state() -> None:
    request = FakeRequest("Tokyo", 2024, 2024, ["pm25"])

    assert should_execute_default_request_flow(default_request=request, allow_run_collection=True, state=FakeState()) is True
    assert should_execute_default_request_flow(default_request=request, allow_run_collection=True, state=FakeState(last_result=FakeResult())) is False
    assert should_execute_default_request_flow(default_request=request, allow_run_collection=False, state=FakeState()) is True
    assert should_execute_default_request_flow(default_request=request, allow_run_collection=False, state=FakeState(last_plan=FakePlan())) is False
    assert should_execute_default_request_flow(default_request=None, allow_run_collection=True, state=FakeState()) is False


def test_execute_default_request_tool_flow_appends_search_then_terminal_tool() -> None:
    request = FakeRequest("Tokyo", 2024, 2024, ["PM25"], country_code="JP")
    state = FakeState()
    tool_trace: list[dict[str, object]] = []
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_execute_tool(name: str, arguments: dict[str, object], **kwargs: object) -> dict[str, object]:
        del kwargs
        calls.append((name, arguments))
        return {"ok": name}

    execute_default_request_tool_flow(
        request,
        allow_run_collection=True,
        state=state,
        tool_trace=tool_trace,
        execute_tool=fake_execute_tool,
        progress_callback=None,
        output_dir=Path("data"),
        search_language="en",
        language="en",
    )

    assert [name for name, _arguments in calls] == ["search_city_candidates", "run_collection"]
    assert tool_trace[0]["arguments"] == {"query": "Tokyo", "country_code": "JP", "count": 5}
    assert tool_trace[1]["arguments"]["candidate_index"] == 0


def test_sanitize_assistant_message_preserves_tool_calls_only_when_present() -> None:
    assert sanitize_assistant_message({"role": "assistant", "content": "done"}) == {"role": "assistant", "content": "done"}

    message = {"content": "", "tool_calls": [{"id": "call_1"}]}

    assert sanitize_assistant_message(message) == {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1"}]}


def test_resolve_candidate_for_tool_searches_when_no_prior_result() -> None:
    search_calls: list[tuple[str, str | None, int, str]] = []
    tokyo = FakeCandidate("Tokyo", "Japan")

    def fake_search(query: str, country_code: str | None = None, count: int = 5, language: str = "en") -> list[FakeCandidate]:
        search_calls.append((query, country_code, count, language))
        return [tokyo]

    state = FakeMutableState()
    request = FakeRequest("Tokyo", 2024, 2024, ["pm25"], country_code="JP")
    candidate, candidates = resolve_candidate_for_tool(
        request,
        candidate_index=0,
        state=state,
        search_language="en",
        search_fn=fake_search,
        normalize_country_code=lambda v: str(v).upper() if v else None,
    )

    assert candidate is tokyo
    assert len(candidates) == 1
    assert search_calls == [("Tokyo", "JP", 5, "en")]
    assert state.last_candidates == [tokyo]
    assert state.selected_candidate is tokyo


def test_resolve_candidate_for_tool_reuses_prior_search() -> None:
    search_calls: list[tuple] = []
    tokyo = FakeCandidate("Tokyo", "Japan")

    def fake_search(query: str, country_code: str | None = None, count: int = 5, language: str = "en") -> list[FakeCandidate]:
        search_calls.append((query, country_code))
        return [tokyo]

    state = FakeMutableState(last_candidates=[tokyo], last_search_query="Tokyo", last_country_code="JP")
    request = FakeRequest("Tokyo", 2024, 2024, ["pm25"], country_code="JP")
    candidate, candidates = resolve_candidate_for_tool(
        request,
        candidate_index=0,
        state=state,
        search_language="en",
        search_fn=fake_search,
        normalize_country_code=lambda v: str(v).upper() if v else None,
    )

    assert candidate is tokyo
    assert search_calls == []  # reused cache


def test_resolve_candidate_for_tool_raises_on_index_out_of_range() -> None:
    tokyo = FakeCandidate("Tokyo", "Japan")
    state = FakeMutableState(last_candidates=[tokyo], last_search_query="Tokyo", last_country_code="JP")
    request = FakeRequest("Tokyo", 2024, 2024, ["pm25"], country_code="JP")

    with pytest.raises(ValueError, match="candidate_index"):
        resolve_candidate_for_tool(
            request,
            candidate_index=5,
            state=state,
            search_language="en",
            search_fn=lambda *a, **kw: [tokyo],
            normalize_country_code=lambda v: str(v).upper() if v else None,
        )


def test_execute_collection_agent_tool_search_updates_state() -> None:
    tokyo = FakeCandidate("Tokyo", "Japan")
    state = FakeMutableState()

    result = execute_collection_agent_tool(
        "search_city_candidates",
        {"query": "Tokyo", "country_code": "JP", "count": 3},
        state=state,
        output_dir=Path("data"),
        coerce_tool_arguments=lambda v: v if isinstance(v, dict) else {},
        normalize_country_code=lambda v: str(v).upper() if v else None,
        request_factory=FakeRequest,
        search_fn=lambda query, country_code=None, count=5, language="en": [tokyo],
        build_plan_fn=lambda *a, **kw: None,
        run_collection_fn=lambda *a, **kw: None,
    )

    assert result["query"] == "Tokyo"
    assert result["country_code"] == "JP"
    assert result["candidate_count"] == 1
    assert result["candidates"][0]["display_name"] == "Tokyo, Japan"
    assert state.last_candidates == [tokyo]
    assert state.last_search_query == "Tokyo"


def test_execute_collection_agent_tool_build_plan_dispatches_to_builder() -> None:
    tokyo = FakeCandidate("Tokyo", "Japan")
    state = FakeMutableState(last_candidates=[tokyo], last_search_query="Tokyo", last_country_code="JP")

    build_calls: list[tuple] = []

    def fake_build_plan(request, candidate, *, api_key=None, output_dir=None, language="en"):
        build_calls.append((request.city_query, candidate.name))
        return FakePlan(f"{candidate.name}, Japan")

    result = execute_collection_agent_tool(
        "build_collection_plan",
        {"city_query": "Tokyo", "start_year": 2024, "end_year": 2024, "pollutants": ["pm25"], "candidate_index": 0},
        state=state,
        output_dir=Path("data"),
        coerce_tool_arguments=lambda v: v if isinstance(v, dict) else {},
        normalize_country_code=lambda v: str(v).upper() if v else None,
        request_factory=FakeRequest,
        search_fn=lambda *a, **kw: [tokyo],
        build_plan_fn=fake_build_plan,
        run_collection_fn=lambda *a, **kw: None,
    )

    assert build_calls == [("Tokyo", "Tokyo")]
    assert result["plan"]["city_label"] == "Tokyo, Japan"
    assert result["selected_candidate"]["index"] == 0


def test_execute_collection_agent_tool_run_collection_dispatches_to_runner() -> None:
    tokyo = FakeCandidate("Tokyo", "Japan")
    state = FakeMutableState(last_candidates=[tokyo], last_search_query="Tokyo", last_country_code="JP")

    run_calls: list[tuple] = []

    def fake_run(request, candidate, *, api_key=None, output_dir=None, progress_callback=None, language="en"):
        run_calls.append((request.city_query, candidate.name))
        result = FakeResult(plan=FakePlan("Tokyo, Japan"))
        return result

    result = execute_collection_agent_tool(
        "run_collection",
        {"city_query": "Tokyo", "start_year": 2024, "end_year": 2024, "pollutants": ["pm25"], "candidate_index": 0},
        state=state,
        output_dir=Path("data"),
        coerce_tool_arguments=lambda v: v if isinstance(v, dict) else {},
        normalize_country_code=lambda v: str(v).upper() if v else None,
        request_factory=FakeRequest,
        search_fn=lambda *a, **kw: [tokyo],
        build_plan_fn=lambda *a, **kw: None,
        run_collection_fn=fake_run,
    )

    assert run_calls == [("Tokyo", "Tokyo")]
    assert result["plan"]["city_label"] == "Tokyo, Japan"
    assert result["collection_result"]["summary_text"] == "Saved Tokyo data."
    assert state.last_result is not None


def test_execute_collection_agent_tool_raises_on_unknown_tool() -> None:
    with pytest.raises(ValueError, match="Unsupported agent tool"):
        execute_collection_agent_tool(
            "unknown_tool",
            {},
            state=FakeMutableState(),
            output_dir=Path("data"),
            coerce_tool_arguments=lambda v: v if isinstance(v, dict) else {},
            normalize_country_code=lambda v: str(v).upper() if v else None,
            request_factory=FakeRequest,
            search_fn=lambda *a, **kw: [],
            build_plan_fn=lambda *a, **kw: None,
            run_collection_fn=lambda *a, **kw: None,
        )
