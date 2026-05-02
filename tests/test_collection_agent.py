from __future__ import annotations

from datetime import date

import pandas as pd

import src.collection_agent as collection_agent
from src.collection_agent import (
    CityCandidate,
    CollectionRequest,
    ToolCallingAgentState,
    _normalize_local_times,
    build_collection_plan,
    chunk_date_range,
    execute_collection_agent_tool,
    finalize_collected_dataset,
    get_collection_agent_tool_schemas,
    resolve_supported_window,
    run_deepseek_tool_agent,
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


def yangjiang_candidate() -> CityCandidate:
    return CityCandidate(
        name="Yangjiang",
        country="China",
        country_code="CN",
        latitude=21.857958,
        longitude=111.982232,
        timezone="Asia/Shanghai",
        admin1="Guangdong",
        population=2480000,
        open_meteo_id=1787452,
    )


def foshan_candidate() -> CityCandidate:
    return CityCandidate(
        name="Foshan",
        country="China",
        country_code="CN",
        latitude=23.021478,
        longitude=113.121435,
        timezone="Asia/Shanghai",
        admin1="Guangdong",
        population=7194311,
        open_meteo_id=1811104,
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
        weather_fields=["temp", "wind_speed"],
    )

    plan = build_collection_plan(request, berlin_candidate(), api_key=None)

    assert plan.source_domain == "cams_europe"
    assert plan.actual_start_date == "2013-01-01"
    assert plan.actual_end_date == "2014-12-31"
    assert plan.pollutants == ["pm25", "o3"]
    assert plan.weather_variables == ["temperature_2m", "wind_speed_10m"]
    assert len(plan.chunks) >= 1


def test_chunk_date_range_is_inclusive() -> None:
    chunks = chunk_date_range(date(2024, 1, 1), date(2024, 4, 5), chunk_days=30)

    assert chunks[0] == {"start_date": "2024-01-01", "end_date": "2024-01-30"}
    assert chunks[-1] == {"start_date": "2024-03-31", "end_date": "2024-04-05"}


def test_normalize_local_times_drops_nonexistent_dst_hour() -> None:
    out = _normalize_local_times(
        ["2023-03-26 01:00:00", "2023-03-26 02:00:00", "2023-03-26 03:00:00"],
        "Europe/Berlin",
    )

    assert str(out.iloc[0]) == "2023-03-26 01:00:00+01:00"
    assert pd.isna(out.iloc[1])
    assert str(out.iloc[2]) == "2023-03-26 03:00:00+02:00"


def test_normalize_local_times_drops_ambiguous_dst_hour() -> None:
    out = _normalize_local_times(
        ["2023-10-29 01:00:00", "2023-10-29 02:00:00", "2023-10-29 03:00:00"],
        "Europe/Berlin",
    )

    assert str(out.iloc[0]) == "2023-10-29 01:00:00+02:00"
    assert pd.isna(out.iloc[1])
    assert str(out.iloc[2]) == "2023-10-29 03:00:00+01:00"


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


def test_tool_schemas_toggle_run_collection() -> None:
    names_without_run = [tool["function"]["name"] for tool in get_collection_agent_tool_schemas(include_run_collection=False)]
    names_with_run = [tool["function"]["name"] for tool in get_collection_agent_tool_schemas(include_run_collection=True)]

    assert names_without_run == ["search_city_candidates", "build_collection_plan"]
    assert names_with_run == ["search_city_candidates", "build_collection_plan", "run_collection"]
    weather_fields_schema = get_collection_agent_tool_schemas(include_run_collection=True)[1]["function"]["parameters"]["properties"]["weather_fields"]
    assert weather_fields_schema["items"]["enum"] == ["humidity", "temp", "wind_speed"]


def test_execute_collection_agent_tool_build_plan_updates_state(monkeypatch) -> None:
    state = ToolCallingAgentState()

    def fake_search(query: str, country_code: str | None = None, count: int = 5, language: str = "en") -> list[CityCandidate]:
        assert query == "Berlin"
        assert country_code == "DE"
        return [berlin_candidate()]

    monkeypatch.setattr(collection_agent, "search_city_candidates", fake_search)

    payload = execute_collection_agent_tool(
        "build_collection_plan",
        {
            "city_query": "Berlin",
            "country_code": "DE",
            "start_year": 2013,
            "end_year": 2014,
            "pollutants": ["pm25", "o3"],
            "include_weather": True,
            "weather_fields": ["temp"],
            "candidate_index": 0,
        },
        state=state,
    )

    assert payload["plan"]["city_label"] == "Berlin, Germany"
    assert payload["plan"]["source_domain"] == "cams_europe"
    assert payload["plan"]["weather_variables"] == ["temperature_2m"]
    assert state.selected_candidate is not None
    assert state.selected_candidate.name == "Berlin"
    assert state.last_plan is not None
    assert state.last_plan.actual_start_date == "2013-01-01"


def test_run_deepseek_tool_agent_completes_tool_loop(monkeypatch) -> None:
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "build_collection_plan",
                                    "arguments": "{\"city_query\": \"Berlin\", \"country_code\": \"DE\", \"start_year\": 2013, \"end_year\": 2014, \"pollutants\": [\"pm25\", \"o3\"], \"include_weather\": true, \"candidate_index\": 0}",
                                },
                            }
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "I selected Berlin and drafted a historical air-quality collection plan.",
                    }
                }
            ]
        },
    ]

    def fake_chat_completion(*args, **kwargs):
        return responses.pop(0)

    def fake_search(query: str, country_code: str | None = None, count: int = 5, language: str = "en") -> list[CityCandidate]:
        assert query == "Berlin"
        return [berlin_candidate()]

    monkeypatch.setattr(collection_agent, "_deepseek_chat_completion", fake_chat_completion)
    monkeypatch.setattr(collection_agent, "search_city_candidates", fake_search)

    result = run_deepseek_tool_agent(
        "Collect Berlin PM2.5 and O3 data from 2013 to 2014.",
        api_key="sk-test",
        allow_run_collection=False,
    )

    assert "Berlin" in result.assistant_message
    assert result.state.last_plan is not None
    assert result.tool_trace[0]["tool"] == "build_collection_plan"


def test_run_collection_agent_uses_deepseek_proxy_for_sparse_same_province_city(monkeypatch) -> None:
    request = CollectionRequest(
        city_query="Yangjiang",
        start_year=2023,
        end_year=2023,
        pollutants=["pm25"],
        include_weather=False,
        country_code="CN",
    )

    def fake_fetch_air_quality_chunk(plan, chunk):  # noqa: ANN001
        del chunk
        timestamps = pd.date_range("2023-01-01", periods=3, freq="3h", tz="Asia/Shanghai")
        if plan.city_label.startswith("Yangjiang"):
            return pd.DataFrame({"timestamp": timestamps, "pm25": [pd.NA, pd.NA, pd.NA]})
        return pd.DataFrame({"timestamp": timestamps, "pm25": [11.0, 14.0, 18.0]})

    def fake_generate_proxy_city_plan(*args, **kwargs):  # noqa: ANN001
        del args, kwargs
        return {
            "query_variants": [],
            "proxy_city_names": ["Foshan"],
            "note": "Using a nearby same-province proxy city.",
        }

    def fake_search(query: str, country_code: str | None = None, count: int = 5, language: str = "en") -> list[CityCandidate]:
        assert query == "Foshan"
        assert country_code == "CN"
        assert count == 5
        assert language == "en"
        return [foshan_candidate()]

    monkeypatch.setattr(collection_agent, "fetch_air_quality_chunk", fake_fetch_air_quality_chunk)
    monkeypatch.setattr(collection_agent, "fetch_weather_chunk", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(collection_agent, "_generate_proxy_city_plan", fake_generate_proxy_city_plan)
    monkeypatch.setattr(collection_agent, "search_city_candidates", fake_search)
    monkeypatch.setattr(collection_agent, "save_dataset", lambda df, output_path: output_path)
    monkeypatch.setattr(collection_agent, "generate_collection_summary", lambda *args, **kwargs: ("proxy summary", "deterministic"))
    monkeypatch.setattr(collection_agent, "_generate_planner_guidance", lambda *args, **kwargs: None)

    result = collection_agent.run_collection_agent(
        request,
        yangjiang_candidate(),
        api_key="sk-test",
        language="en",
    )

    assert result.plan.city_label == "Foshan, Guangdong, China"
    assert result.row_count == 3
    assert result.coverage_rows[0]["non_null_ratio"] == 1.0
    assert any("proxy dataset" in item for item in result.runtime_warnings)
    assert result.summary_text == "proxy summary"



def test_deepseek_chat_completion_retries_with_compat_model(monkeypatch) -> None:
    attempted_models: list[str] = []

    class FakeResponse:
        def __init__(self, status_code: int, body: dict[str, object] | str) -> None:
            self.status_code = status_code
            self._body = body
            self.text = body if isinstance(body, str) else ""

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise collection_agent.requests.HTTPError(f"{self.status_code} Client Error")

        def json(self) -> dict[str, object]:
            if isinstance(self._body, dict):
                return self._body
            raise ValueError("non-json body")

    def fake_post(url: str, headers: dict[str, str], json: dict[str, object], timeout: int):
        del url, headers, timeout
        attempted_models.append(str(json["model"]))
        assert json.get("thinking") == {"type": "disabled"}
        if json["model"] == "deepseek-v4-flash":
            return FakeResponse(400, {"error": {"message": "tool calls not enabled for this model alias"}})
        return FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(collection_agent.requests, "post", fake_post)

    payload = collection_agent._deepseek_chat_completion(
        [{"role": "user", "content": "test"}],
        api_key="sk-test",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        tools=[{"type": "function", "function": {"name": "noop", "parameters": {"type": "object", "properties": {}}}}],
        tool_choice="auto",
        thinking_type="disabled",
    )

    assert attempted_models == ["deepseek-v4-flash", "deepseek-chat"]
    assert payload["choices"][0]["message"]["content"] == "ok"
