from __future__ import annotations

from threading import Event

import pandas as pd

import src.agent_task_runner as agent_task_runner
import src.collection_agent as collection_agent
from src.agent_task_runner import AgentTaskRunConfig, run_custom_city_task, start_background_custom_city_task
from src.agent_task_store import AgentTaskStatus, InMemoryAgentTaskStore
from src.collection_agent import CityCandidate, CollectionPlan, CollectionResult, CustomCityValidationResult


def _custom_payload(action: str = "collect") -> dict[str, object]:
    return {
        "kind": "custom_city_collection",
        "action": action,
        "input_country": "Japan",
        "input_city": "Tokyo",
        "city_query": "Tokyo",
        "country_code": "",
        "start_year": 2024,
        "end_year": 2026,
        "pollutants": ["pm25"],
        "include_weather": False,
        "weather_fields": [],
    }


def _tokyo_candidate() -> CityCandidate:
    return CityCandidate(
        name="Tokyo",
        country="Japan",
        country_code="JP",
        latitude=35.6762,
        longitude=139.6503,
        timezone="Asia/Tokyo",
        admin1="Tokyo",
        population=14000000,
        open_meteo_id=1850147,
    )


def _tokyo_plan(request, candidate) -> CollectionPlan:  # noqa: ANN001
    return CollectionPlan(
        city_label="Tokyo, Japan",
        city_query=request.city_query,
        country_code=request.country_code or candidate.country_code,
        latitude=candidate.latitude,
        longitude=candidate.longitude,
        timezone=candidate.timezone,
        source_name="Open-Meteo Air Quality Archive",
        source_domain="auto",
        sampling_step="3-hourly",
        requested_start_date="2024-01-01",
        requested_end_date="2026-12-31",
        actual_start_date="2024-01-01",
        actual_end_date="2026-05-03",
        pollutants=["pm25"],
        pollutant_variables=["pm2_5"],
        weather_variables=[],
        chunks=[{"start_date": "2024-01-01", "end_date": "2024-01-31"}],
        output_path="data/processed/agent_runs/tokyo_2024_2026_aq.parquet",
        warnings=[],
        planner_mode="deterministic",
        planner_model=None,
        planner_notes="Direct custom-city collection.",
        quality_checks=[],
        risk_flags=[],
    )


def _kyoto_candidate() -> CityCandidate:
    return CityCandidate(
        name="Kyoto",
        country="Japan",
        country_code="JP",
        latitude=35.0116,
        longitude=135.7681,
        timezone="Asia/Tokyo",
        admin1="Kyoto",
        population=1460000,
        open_meteo_id=1857910,
    )


def _kyoto_plan(request, candidate) -> CollectionPlan:  # noqa: ANN001
    return CollectionPlan(
        city_label="Kyoto, Kyoto, Japan",
        city_query=request.city_query,
        country_code=request.country_code or candidate.country_code,
        latitude=candidate.latitude,
        longitude=candidate.longitude,
        timezone=candidate.timezone,
        source_name="Open-Meteo Air Quality Archive",
        source_domain="auto",
        sampling_step="3-hourly",
        requested_start_date="2024-01-01",
        requested_end_date="2026-12-31",
        actual_start_date="2024-01-01",
        actual_end_date="2026-05-03",
        pollutants=["pm25"],
        pollutant_variables=["pm2_5"],
        weather_variables=[],
        chunks=[{"start_date": "2024-01-01", "end_date": "2024-01-31"}],
        output_path="data/processed/agent_runs/kyoto_2024_2026_aq.parquet",
        warnings=[],
        planner_mode="deterministic",
        planner_model=None,
        planner_notes="Stable catalog alias plan.",
        quality_checks=[],
        risk_flags=[],
    )


def test_run_custom_city_task_collects_and_writes_status_chain(monkeypatch) -> None:
    store = InMemoryAgentTaskStore()
    task = store.create_task(kind="custom_city_collection", request_payload=_custom_payload("collect"))

    def fake_validate(country_or_region: str, city_name: str, **kwargs):  # noqa: ANN001
        del kwargs
        return CustomCityValidationResult(
            input_country=country_or_region,
            input_city=city_name,
            status="valid",
            corrected_country="Japan",
            corrected_city="Tokyo",
            country_code="JP",
            matching_countries=["Japan"],
            message="Tokyo, Japan is valid.",
        )

    def fake_search(query: str, country_code: str | None = None, count: int = 5, language: str = "en") -> list[CityCandidate]:
        assert (query, country_code, count, language) == ("Tokyo", "JP", 10, "en")
        return [_tokyo_candidate()]

    def fake_run_collection(request, candidate, **kwargs):  # noqa: ANN001
        kwargs["progress_callback"](1, 2, "Collecting Tokyo PM2.5")
        plan = _tokyo_plan(request, candidate)
        return CollectionResult(
            plan=plan,
            dataset=pd.DataFrame({"timestamp": ["2024-01-01 00:00:00"], "pm25": [12.0]}),
            output_path=plan.output_path,
            row_count=1,
            started_at="2024-01-01 00:00:00",
            ended_at="2024-01-01 00:00:00",
            coverage_rows=[{"pollutant": "pm25", "non_null_ratio": 1.0}],
            runtime_warnings=[],
            summary_text="Saved Tokyo dataset.",
            summary_mode="deterministic",
        )

    monkeypatch.setattr(collection_agent, "validate_custom_city_with_deepseek", fake_validate)
    monkeypatch.setattr(collection_agent, "search_city_candidates", fake_search)
    monkeypatch.setattr(collection_agent, "run_collection_agent", fake_run_collection)

    run_custom_city_task(
        store,
        task.task_id,
        AgentTaskRunConfig(api_key="sk-test", model="deepseek-chat", base_url="https://api.deepseek.com", language="en"),
    )

    updated = store.get_task(task.task_id)
    logs = store.list_logs(task.task_id)

    assert updated is not None
    assert updated.status == AgentTaskStatus.SAVED
    assert updated.phase == "SAVED"
    assert updated.progress == 1.0
    assert updated.output_path == "data/processed/agent_runs/tokyo_2024_2026_aq.parquet"
    assert updated.result_payload["row_count"] == 1
    assert [log.phase for log in logs] == ["VALIDATING", "RESOLVING", "PLANNING", "COLLECTING", "SAVED"]


def test_run_custom_city_task_uses_confirmed_validation_without_revalidating(monkeypatch) -> None:
    store = InMemoryAgentTaskStore()
    payload = _custom_payload("plan")
    payload["confirmed_validation"] = {
        "input_country": "Japan",
        "input_city": "Tokyo",
        "status": "needs_confirmation",
        "corrected_country": "Japan",
        "corrected_city": "Tokyo",
        "country_code": "JP",
        "matching_countries": ["Japan"],
        "message": "Did you mean Tokyo, Japan?",
    }
    task = store.create_task(kind="custom_city_collection", request_payload=payload)

    def fail_validate(*args, **kwargs):  # noqa: ANN001
        del args, kwargs
        raise AssertionError("confirmed validation should not call DeepSeek validation again")

    def fake_search(query: str, country_code: str | None = None, count: int = 5, language: str = "en") -> list[CityCandidate]:
        assert (query, country_code, count, language) == ("Tokyo", "JP", 10, "en")
        return [_tokyo_candidate()]

    def fake_build_plan(request, candidate, **kwargs):  # noqa: ANN001
        del kwargs
        return _tokyo_plan(request, candidate)

    monkeypatch.setattr(collection_agent, "validate_custom_city_with_deepseek", fail_validate)
    monkeypatch.setattr(collection_agent, "search_city_candidates", fake_search)
    monkeypatch.setattr(collection_agent, "build_collection_plan", fake_build_plan)

    run_custom_city_task(
        store,
        task.task_id,
        AgentTaskRunConfig(api_key="sk-test", model="deepseek-chat", base_url="https://api.deepseek.com", language="en"),
    )

    updated = store.get_task(task.task_id)
    logs = store.list_logs(task.task_id)

    assert updated is not None
    assert updated.status == AgentTaskStatus.PLANNED
    assert updated.result_payload["city_label"] == "Tokyo, Japan"
    assert [log.phase for log in logs] == ["VALIDATING", "RESOLVING", "PLANNING"]


def test_run_custom_city_task_uses_stable_catalog_alias_when_validated_name_has_no_candidates(monkeypatch) -> None:
    store = InMemoryAgentTaskStore()
    payload = _custom_payload("plan")
    payload["input_city"] = "\u4eac\u90fd"
    payload["city_query"] = "\u4eac\u90fd"
    task = store.create_task(kind="custom_city_collection", request_payload=payload)
    search_calls: list[tuple[str, str | None, int, str]] = []

    def fake_validate(country_or_region: str, city_name: str, **kwargs):  # noqa: ANN001
        del kwargs
        return CustomCityValidationResult(
            input_country=country_or_region,
            input_city=city_name,
            status="valid",
            corrected_country="Japan",
            corrected_city="\u4eac\u90fd",
            country_code="JP",
            matching_countries=["Japan"],
            message="\u4f4d\u7f6e\u6709\u6548\uff0c\u4eac\u90fd\u4f4d\u4e8e\u65e5\u672c\u3002",
        )

    def fake_search(query: str, country_code: str | None = None, count: int = 5, language: str = "en") -> list[CityCandidate]:
        search_calls.append((query, country_code, count, language))
        if query == "Kyoto":
            return [_kyoto_candidate()]
        return []

    def fake_build_plan(request, candidate, **kwargs):  # noqa: ANN001
        del kwargs
        return _kyoto_plan(request, candidate)

    monkeypatch.setattr(collection_agent, "validate_custom_city_with_deepseek", fake_validate)
    monkeypatch.setattr(collection_agent, "search_city_candidates", fake_search)
    monkeypatch.setattr(collection_agent, "build_collection_plan", fake_build_plan)

    run_custom_city_task(
        store,
        task.task_id,
        AgentTaskRunConfig(api_key="sk-test", model="deepseek-chat", base_url="https://api.deepseek.com", language="zh-CN"),
    )

    updated = store.get_task(task.task_id)

    assert updated is not None
    assert updated.status == AgentTaskStatus.PLANNED
    assert updated.result_payload["city_query"] == "Kyoto"
    assert search_calls[0] == ("\u4eac\u90fd", "JP", 10, "zh")
    assert ("Kyoto", "JP", 10, "zh") in search_calls


def test_start_background_custom_city_task_returns_before_runner_finishes(monkeypatch) -> None:
    store = InMemoryAgentTaskStore()
    task = store.create_task(kind="custom_city_collection", request_payload=_custom_payload("collect"))
    started = Event()
    release = Event()

    def fake_runner(store_arg, task_id_arg: str, config_arg) -> None:  # noqa: ANN001
        assert store_arg is store
        assert task_id_arg == task.task_id
        assert config_arg.api_key == "sk-test"
        started.set()
        release.wait(timeout=2)
        store.update_task(task.task_id, status=AgentTaskStatus.SAVED, phase="SAVED", progress=1.0, message="done")

    monkeypatch.setattr(agent_task_runner, "run_custom_city_task", fake_runner)

    thread = start_background_custom_city_task(
        store,
        task.task_id,
        AgentTaskRunConfig(api_key="sk-test", model="deepseek-chat", base_url="https://api.deepseek.com", language="en"),
    )

    assert started.wait(timeout=1)
    assert thread.is_alive()
    assert store.get_task(task.task_id).status == AgentTaskStatus.PENDING
    release.set()
    thread.join(timeout=2)
    assert store.get_task(task.task_id).status == AgentTaskStatus.SAVED


def test_runner_does_not_overwrite_watchdog_timeout(monkeypatch) -> None:
    store = InMemoryAgentTaskStore()
    task = store.create_task(kind="custom_city_collection", request_payload=_custom_payload("plan"))
    store.update_task(
        task.task_id,
        status=AgentTaskStatus.TIMEOUT,
        phase="TIMEOUT",
        progress=1.0,
        message="Timed out by watchdog",
        error="Timed out by watchdog",
    )

    agent_task_runner._record_step(
        store,
        task.task_id,
        status=AgentTaskStatus.PLANNED,
        phase="PLANNING",
        progress=1.0,
        message="Late plan",
        result_payload={"city_label": "Tokyo, Japan"},
    )

    updated = store.get_task(task.task_id)
    assert updated is not None
    assert updated.status == AgentTaskStatus.TIMEOUT
    assert updated.result_payload == {}
