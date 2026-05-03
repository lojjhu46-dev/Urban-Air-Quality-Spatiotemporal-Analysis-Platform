from __future__ import annotations

import time

import pandas as pd
from streamlit.testing.v1 import AppTest

import src.agent_task_store as agent_task_store
import src.collection_agent as collection_agent
from src.agent_task_store import AgentTaskStatus, InMemoryAgentTaskStore
from src.agent_interaction import (
    DEFAULT_CITY_PATH,
    build_agent_instruction,
    build_city_search_queries,
    candidate_matches_city_option,
    china_city_count,
    china_city_coverage_ratio,
    china_province_city_names,
    city_labels,
    city_option_from_path,
    continent_labels,
    country_labels,
    default_city_option,
    option_has_province_step,
    province_labels,
    resolve_china_catalog_province,
)
from src.collection_agent import (
    CityCandidate,
    CollectionPlan,
    CollectionResult,
    CustomCityValidationResult,
)


def _wait_for_task_status(
    store: InMemoryAgentTaskStore,
    task_id: str,
    expected_statuses: set[AgentTaskStatus],
    *,
    timeout: float = 2.0,
):
    deadline = time.monotonic() + timeout
    task = store.get_task(task_id)
    while time.monotonic() < deadline:
        task = store.get_task(task_id)
        if task is not None and task.status in expected_statuses:
            return task
        time.sleep(0.01)
    raise AssertionError(f"Task {task_id} did not reach {expected_statuses}; last={task}")


def test_default_city_path_resolves() -> None:
    option = default_city_option()

    assert DEFAULT_CITY_PATH == ("Asia", "China", "Beijing Municipality", "Beijing")
    assert option.country_code == "CN"
    assert option.path_label == "Asia - China - Beijing Municipality - Beijing"


def test_country_and_city_lists_are_sorted() -> None:
    assert country_labels("Europe")[:3] == ["France", "Germany", "Italy"]
    provinces = province_labels("Asia", "China")
    assert len(provinces) == 31
    assert provinces[:3] == ["Anhui", "Beijing Municipality", "Chongqing Municipality"]
    assert {"Guangdong", "Jiangsu", "Xinjiang", "Tibet", "Beijing Municipality"}.issubset(set(provinces))
    assert china_city_count() >= 150
    assert china_city_coverage_ratio() > 0.5

    guangdong = city_labels("Asia", "China", "Guangdong")
    assert len(guangdong) == 21
    assert guangdong == sorted(guangdong, key=lambda value: value.lower().replace(" ", ""))
    assert {"Guangzhou", "Shenzhen", "Foshan", "Zhuhai", "Zhanjiang", "Yangjiang"}.issubset(set(guangdong))
    assert set(china_province_city_names("Guangdong")) == set(guangdong)
    assert len(china_province_city_names("Jiangsu")) == 13
    assert resolve_china_catalog_province("Inner Mongolia Autonomous Region") == "Inner Mongolia"
    assert resolve_china_catalog_province("Beijing") == "Beijing Municipality"


def test_build_agent_instruction_mentions_location_and_tags() -> None:
    option = city_option_from_path("Europe", "Germany", "Berlin", "Berlin")

    instruction = build_agent_instruction(
        option,
        2023,
        2025,
        ["pm25", "o3"],
        ["temp", "wind_speed"],
        language="en",
    )

    assert "Europe - Germany - Berlin - Berlin" in instruction
    assert "pm25, o3" in instruction
    assert "temp, wind_speed" in instruction


def test_china_city_option_exposes_chinese_display_labels() -> None:
    option = city_option_from_path("Asia", "China", "Beijing Municipality", "Beijing")

    assert option.display_continent("zh-CN") == "\u4e9a\u6d32"
    assert option.display_country("zh-CN") == "\u4e2d\u56fd"
    assert option.display_province("zh-CN") == "\u5317\u4eac\u5e02"
    assert option.display_city("zh-CN") == "\u5317\u4eac"
    assert option.path_label_for_language("zh-CN") == "\u4e9a\u6d32 - \u4e2d\u56fd - \u5317\u4eac\u5e02 - \u5317\u4eac"
    assert option.city_query == "Beijing"


def test_non_china_city_option_exposes_localized_display_labels() -> None:
    option = city_option_from_path("North America", "United States", "California", "San Francisco")

    assert option.display_continent("zh-CN") == "\u5317\u7f8e\u6d32"
    assert option.display_country("zh-CN") == "\u7f8e\u56fd"
    assert option.display_province("zh-CN") == "\u52a0\u5229\u798f\u5c3c\u4e9a\u5dde"
    assert option.display_city("zh-CN") == "\u65e7\u91d1\u5c71"
    assert option.path_label_for_language("zh-CN") == "\u5317\u7f8e\u6d32 - \u7f8e\u56fd - \u52a0\u5229\u798f\u5c3c\u4e9a\u5dde - \u65e7\u91d1\u5c71"
    assert option.path_label_for_language("en") == "North America - United States - California - San Francisco"
    assert option.city_query == "San Francisco"


def test_build_city_search_queries_include_region_and_country() -> None:
    option = city_option_from_path("North America", "United States", "California", "San Francisco")

    assert build_city_search_queries(option) == [
        "San Francisco",
        "San Francisco California",
        "San Francisco United States",
        "San Francisco US",
    ]


def test_candidate_match_normalizes_suffixes_and_country_code() -> None:
    option = city_option_from_path("Asia", "China", "Beijing Municipality", "Beijing")

    assert candidate_matches_city_option(
        option,
        candidate_name="Beijing",
        candidate_admin1="Beijing Municipality",
        candidate_country_code="CN",
    )
    assert not candidate_matches_city_option(
        option,
        candidate_name="Beijing",
        candidate_admin1="Beijing Municipality",
        candidate_country_code="US",
    )


def test_catalog_marks_province_step_only_when_needed() -> None:
    assert option_has_province_step("Asia", "China")
    assert not option_has_province_step("Asia", "Singapore")


def test_agent_page_renders_structured_selectors() -> None:
    at = AppTest.from_file("pages/4_Historical_Data_Agent.py")
    at.run()

    labels = [widget.label for widget in at.selectbox]
    assert "Continent" in labels
    assert "Country / region" in labels
    assert "City" in labels
    assert len(at.multiselect) >= 2
    continent_widget = next(widget for widget in at.selectbox if widget.label == "Continent")
    assert continent_labels()[0] in continent_widget.options
    country_widget = next(widget for widget in at.selectbox if widget.label == "Country / region")
    assert "Custom search" in country_widget.options
    province_widget = next(widget for widget in at.selectbox if widget.label == "Province / state / region")
    assert "Custom search" in province_widget.options
    city_widget = next(widget for widget in at.selectbox if widget.label == "City")
    assert "Custom search" in city_widget.options


def test_custom_city_validated_location_uses_direct_collection_flow(monkeypatch) -> None:
    calls: dict[str, object] = {}

    def fake_validate(country_or_region: str, city_name: str, **kwargs):  # noqa: ANN001
        calls["validated"] = (country_or_region, city_name, kwargs["api_key"])
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

    def fail_run_agent(*args, **kwargs):  # noqa: ANN001
        del args, kwargs
        raise AssertionError("custom city flow should not wait on a second DeepSeek tool-calling turn")

    def fake_search(
        query: str,
        country_code: str | None = None,
        count: int = 5,
        language: str = "en",
    ) -> list[CityCandidate]:
        calls["search"] = (query, country_code, count, language)
        return [
            CityCandidate(
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
        ]

    def fake_build_plan(request, candidate, **kwargs):  # noqa: ANN001
        calls["plan"] = (request, candidate, kwargs["language"])
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
            planner_notes="Direct custom-city plan.",
            quality_checks=[],
            risk_flags=[],
        )

    monkeypatch.setattr(collection_agent, "validate_custom_city_with_deepseek", fake_validate)
    monkeypatch.setattr(collection_agent, "run_deepseek_tool_agent", fail_run_agent)
    monkeypatch.setattr(collection_agent, "search_city_candidates", fake_search)
    monkeypatch.setattr(collection_agent, "build_collection_plan", fake_build_plan)

    at = AppTest.from_file("pages/4_Historical_Data_Agent.py")
    at.secrets["deepseek_api_key"] = "sk-test"
    at.run()
    next(widget for widget in at.selectbox if widget.label == "City").select("Custom search").run()
    next(widget for widget in at.text_input if widget.label == "Country / region").set_value("Japan").run()
    next(widget for widget in at.text_input if widget.label == "City name").set_value("Tokyo").run()
    next(button for button in at.button if button.label == "Agent: Draft Plan").click().run()

    store = at.session_state["aq_agent_task_store"]
    task = _wait_for_task_status(store, at.session_state["aq_agent_current_task_id"], {AgentTaskStatus.PLANNED})

    assert calls["validated"] == ("Japan", "Tokyo", "sk-test")
    assert calls["search"] == ("Tokyo", "JP", 10, "en")
    assert calls["plan"][0].city_query == "Tokyo"
    assert task.result_payload["city_label"] == "Tokyo, Japan"


def test_custom_city_plan_writes_task_status_chain(monkeypatch) -> None:
    store = InMemoryAgentTaskStore()

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

    def fake_search(
        query: str,
        country_code: str | None = None,
        count: int = 5,
        language: str = "en",
    ) -> list[CityCandidate]:
        del query, country_code, count, language
        return [
            CityCandidate(
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
        ]

    def fake_build_plan(request, candidate, **kwargs):  # noqa: ANN001
        del kwargs
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
            planner_notes="Direct custom-city plan.",
            quality_checks=[],
            risk_flags=[],
        )

    monkeypatch.setattr(agent_task_store, "task_store_from_config", lambda database_url: store)
    monkeypatch.setattr(collection_agent, "validate_custom_city_with_deepseek", fake_validate)
    monkeypatch.setattr(collection_agent, "search_city_candidates", fake_search)
    monkeypatch.setattr(collection_agent, "build_collection_plan", fake_build_plan)

    at = AppTest.from_file("pages/4_Historical_Data_Agent.py")
    at.secrets["deepseek_api_key"] = "sk-test"
    at.run()
    next(widget for widget in at.selectbox if widget.label == "City").select("Custom search").run()
    next(widget for widget in at.text_input if widget.label == "Country / region").set_value("Japan").run()
    next(widget for widget in at.text_input if widget.label == "City name").set_value("Tokyo").run()
    next(button for button in at.button if button.label == "Agent: Draft Plan").click().run()

    task_id = at.session_state["aq_agent_current_task_id"]
    task = _wait_for_task_status(store, task_id, {AgentTaskStatus.PLANNED})
    logs = store.list_logs(task_id)

    assert task is not None
    assert task.status == AgentTaskStatus.PLANNED
    assert task.phase == "PLANNING"
    assert task.progress == 1.0
    assert task.result_payload["city_label"] == "Tokyo, Japan"
    assert [log.phase for log in logs] == ["VALIDATING", "RESOLVING", "PLANNING"]
    rendered_text = "\n".join(
        [item.value for item in at.markdown]
        + [item.value for item in at.caption]
        + [item.value for item in at.subheader]
    )
    assert "Current Agent Task" in rendered_text
    assert "PLANNED" in rendered_text
    assert "Collection plan is ready." in rendered_text


def test_custom_city_collection_writes_saved_task_status(monkeypatch) -> None:
    store = InMemoryAgentTaskStore()

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

    def fake_search(
        query: str,
        country_code: str | None = None,
        count: int = 5,
        language: str = "en",
    ) -> list[CityCandidate]:
        del query, country_code, count, language
        return [
            CityCandidate(
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
        ]

    def fake_run_collection(request, candidate, **kwargs):  # noqa: ANN001
        kwargs["progress_callback"](1, 2, "Collecting Tokyo PM2.5")
        plan = CollectionPlan(
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

    monkeypatch.setattr(agent_task_store, "task_store_from_config", lambda database_url: store)
    monkeypatch.setattr(collection_agent, "validate_custom_city_with_deepseek", fake_validate)
    monkeypatch.setattr(collection_agent, "search_city_candidates", fake_search)
    monkeypatch.setattr(collection_agent, "run_collection_agent", fake_run_collection)

    at = AppTest.from_file("pages/4_Historical_Data_Agent.py")
    at.secrets["deepseek_api_key"] = "sk-test"
    at.run()
    next(widget for widget in at.selectbox if widget.label == "City").select("Custom search").run()
    next(widget for widget in at.text_input if widget.label == "Country / region").set_value("Japan").run()
    next(widget for widget in at.text_input if widget.label == "City name").set_value("Tokyo").run()
    next(button for button in at.button if button.label == "Agent: Plan and Collect").click().run()

    task_id = at.session_state["aq_agent_current_task_id"]
    task = _wait_for_task_status(store, task_id, {AgentTaskStatus.SAVED})
    at.run()
    logs = store.list_logs(task_id)

    assert task is not None
    assert task.status == AgentTaskStatus.SAVED
    assert task.phase == "SAVED"
    assert task.output_path == "data/processed/agent_runs/tokyo_2024_2026_aq.parquet"
    assert task.result_payload["row_count"] == 1
    assert [log.phase for log in logs] == ["VALIDATING", "RESOLVING", "PLANNING", "COLLECTING", "SAVED"]
    rendered_text = "\n".join(
        [item.value for item in at.markdown]
        + [item.value for item in at.caption]
        + [item.value for item in at.subheader]
        + [item.value for item in at.success]
    )
    assert "Current Agent Task" in rendered_text
    assert "SAVED" in rendered_text
    assert "data/processed/agent_runs/tokyo_2024_2026_aq.parquet" in rendered_text
    log_expander = next(expander for expander in at.expander if expander.label == "Recent logs")
    assert log_expander.proto.expanded is False


def test_custom_city_collection_accepts_chinese_valid_deepseek_status(monkeypatch) -> None:
    store = InMemoryAgentTaskStore()

    def fake_json_completion(*args, **kwargs):  # noqa: ANN001
        del args, kwargs
        return {
            "status": "\u4f4d\u7f6e\u6709\u6548",
            "corrected_country": "\u4e2d\u56fd",
            "corrected_city": "\u6d4e\u5b81",
            "country_code": "CN",
            "matching_countries": ["\u4e2d\u56fd"],
            "message": "\u4f4d\u7f6e\u6709\u6548\uff0c\u6d4e\u5b81\u662f\u4e2d\u56fd\u5c71\u4e1c\u7701\u7684\u4e00\u4e2a\u5730\u7ea7\u5e02\u3002",
        }

    def fake_search(
        query: str,
        country_code: str | None = None,
        count: int = 5,
        language: str = "en",
    ) -> list[CityCandidate]:
        assert (query, country_code, count) == ("\u6d4e\u5b81", "CN", 10)
        del language
        return [
            CityCandidate(
                name="\u6d4e\u5b81",
                country="\u4e2d\u56fd",
                country_code="CN",
                latitude=35.4146,
                longitude=116.5872,
                timezone="Asia/Shanghai",
                admin1="\u5c71\u4e1c",
                population=8000000,
                open_meteo_id=1805518,
            )
        ]

    def fake_run_collection(request, candidate, **kwargs):  # noqa: ANN001
        kwargs["progress_callback"](1, 2, "Collecting Jining PM2.5")
        plan = CollectionPlan(
            city_label="\u6d4e\u5b81, \u4e2d\u56fd",
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
            output_path="data/processed/agent_runs/jining_2024_2026_aq.parquet",
            warnings=[],
            planner_mode="deterministic",
            planner_model=None,
            planner_notes="Direct custom-city collection.",
            quality_checks=[],
            risk_flags=[],
        )
        return CollectionResult(
            plan=plan,
            dataset=pd.DataFrame({"timestamp": ["2024-01-01 00:00:00"], "pm25": [12.0]}),
            output_path=plan.output_path,
            row_count=1,
            started_at="2024-01-01 00:00:00",
            ended_at="2024-01-01 00:00:00",
            coverage_rows=[{"pollutant": "pm25", "non_null_ratio": 1.0}],
            runtime_warnings=[],
            summary_text="Saved Jining dataset.",
            summary_mode="deterministic",
        )

    monkeypatch.setattr(agent_task_store, "task_store_from_config", lambda database_url: store)
    monkeypatch.setattr(collection_agent, "_deepseek_json_completion", fake_json_completion)
    monkeypatch.setattr(collection_agent, "search_city_candidates", fake_search)
    monkeypatch.setattr(collection_agent, "run_collection_agent", fake_run_collection)

    at = AppTest.from_file("pages/4_Historical_Data_Agent.py")
    at.secrets["deepseek_api_key"] = "sk-test"
    at.run()
    next(widget for widget in at.selectbox if widget.label == "City").select("Custom search").run()
    next(widget for widget in at.text_input if widget.label == "Country / region").set_value("\u4e2d\u56fd").run()
    next(widget for widget in at.text_input if widget.label == "City name").set_value("\u6d4e\u5b81").run()
    next(button for button in at.button if button.label == "Agent: Plan and Collect").click().run()

    task = _wait_for_task_status(store, at.session_state["aq_agent_current_task_id"], {AgentTaskStatus.SAVED})

    assert task is not None
    assert task.status == AgentTaskStatus.SAVED
    assert task.phase == "SAVED"
    assert task.output_path == "data/processed/agent_runs/jining_2024_2026_aq.parquet"


def test_custom_city_collection_continues_when_deepseek_success_lacks_country_code(monkeypatch) -> None:
    store = InMemoryAgentTaskStore()

    def fake_json_completion(*args, **kwargs):  # noqa: ANN001
        del args, kwargs
        return {
            "status": "\u4f4d\u7f6e\u9a8c\u8bc1\u6210\u529f\u3002",
            "message": "\u4f4d\u7f6e\u9a8c\u8bc1\u6210\u529f\u3002",
        }

    def fake_search(
        query: str,
        country_code: str | None = None,
        count: int = 5,
        language: str = "en",
    ) -> list[CityCandidate]:
        assert (query, country_code, count) == ("\u6d4e\u5b81", None, 10)
        del language
        return [
            CityCandidate(
                name="\u6d4e\u5b81",
                country="\u4e2d\u56fd",
                country_code="CN",
                latitude=35.4146,
                longitude=116.5872,
                timezone="Asia/Shanghai",
                admin1="\u5c71\u4e1c",
                population=8000000,
                open_meteo_id=1805518,
            )
        ]

    def fake_run_collection(request, candidate, **kwargs):  # noqa: ANN001
        kwargs["progress_callback"](1, 2, "Collecting Jining PM2.5")
        assert request.country_code is None
        plan = CollectionPlan(
            city_label="\u6d4e\u5b81, \u4e2d\u56fd",
            city_query=request.city_query,
            country_code=candidate.country_code,
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
            output_path="data/processed/agent_runs/jining_2024_2026_aq.parquet",
            warnings=[],
            planner_mode="deterministic",
            planner_model=None,
            planner_notes="Direct custom-city collection.",
            quality_checks=[],
            risk_flags=[],
        )
        return CollectionResult(
            plan=plan,
            dataset=pd.DataFrame({"timestamp": ["2024-01-01 00:00:00"], "pm25": [12.0]}),
            output_path=plan.output_path,
            row_count=1,
            started_at="2024-01-01 00:00:00",
            ended_at="2024-01-01 00:00:00",
            coverage_rows=[{"pollutant": "pm25", "non_null_ratio": 1.0}],
            runtime_warnings=[],
            summary_text="Saved Jining dataset.",
            summary_mode="deterministic",
        )

    monkeypatch.setattr(agent_task_store, "task_store_from_config", lambda database_url: store)
    monkeypatch.setattr(collection_agent, "_deepseek_json_completion", fake_json_completion)
    monkeypatch.setattr(collection_agent, "search_city_candidates", fake_search)
    monkeypatch.setattr(collection_agent, "run_collection_agent", fake_run_collection)

    at = AppTest.from_file("pages/4_Historical_Data_Agent.py")
    at.secrets["deepseek_api_key"] = "sk-test"
    at.run()
    next(widget for widget in at.selectbox if widget.label == "City").select("Custom search").run()
    next(widget for widget in at.text_input if widget.label == "Country / region").set_value("\u4e2d\u56fd").run()
    next(widget for widget in at.text_input if widget.label == "City name").set_value("\u6d4e\u5b81").run()
    next(button for button in at.button if button.label == "Agent: Plan and Collect").click().run()

    task = _wait_for_task_status(store, at.session_state["aq_agent_current_task_id"], {AgentTaskStatus.SAVED})

    assert task is not None
    assert task.status == AgentTaskStatus.SAVED
    assert task.phase == "SAVED"


def test_custom_city_validation_failure_shows_task_status_panel(monkeypatch) -> None:
    store = InMemoryAgentTaskStore()

    def fake_validate(country_or_region: str, city_name: str, **kwargs):  # noqa: ANN001
        del country_or_region, city_name, kwargs
        raise RuntimeError("DeepSeek timeout")

    monkeypatch.setattr(agent_task_store, "task_store_from_config", lambda database_url: store)
    monkeypatch.setattr(collection_agent, "validate_custom_city_with_deepseek", fake_validate)

    at = AppTest.from_file("pages/4_Historical_Data_Agent.py")
    at.secrets["deepseek_api_key"] = "sk-test"
    at.run()
    next(widget for widget in at.selectbox if widget.label == "City").select("Custom search").run()
    next(widget for widget in at.text_input if widget.label == "Country / region").set_value("Japan").run()
    next(widget for widget in at.text_input if widget.label == "City name").set_value("Tokyo").run()
    next(button for button in at.button if button.label == "Agent: Draft Plan").click().run()

    task_id = at.session_state["aq_agent_current_task_id"]
    task = _wait_for_task_status(store, task_id, {AgentTaskStatus.FAILED})
    logs = store.list_logs(task_id)

    assert task is not None
    assert task.status == AgentTaskStatus.FAILED
    assert task.phase == "FAILED"
    assert task.error == "DeepSeek timeout"
    assert [log.phase for log in logs] == ["VALIDATING", "FAILED"]
    rendered_text = "\n".join(
        [item.value for item in at.markdown]
        + [item.value for item in at.caption]
        + [item.value for item in at.subheader]
        + [item.value for item in at.error]
    )
    assert "Current Agent Task" in rendered_text
    assert "FAILED" in rendered_text
    assert "DeepSeek timeout" in rendered_text


def test_custom_city_keeps_progress_when_candidate_resolution_fails(monkeypatch) -> None:
    store = InMemoryAgentTaskStore()

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

    def fake_search(*args, **kwargs):  # noqa: ANN001
        del args, kwargs
        return []

    monkeypatch.setattr(agent_task_store, "task_store_from_config", lambda database_url: store)
    monkeypatch.setattr(collection_agent, "validate_custom_city_with_deepseek", fake_validate)
    monkeypatch.setattr(collection_agent, "search_city_candidates", fake_search)

    at = AppTest.from_file("pages/4_Historical_Data_Agent.py")
    at.secrets["deepseek_api_key"] = "sk-test"
    at.run()
    next(widget for widget in at.selectbox if widget.label == "City").select("Custom search").run()
    next(widget for widget in at.text_input if widget.label == "Country / region").set_value("Japan").run()
    next(widget for widget in at.text_input if widget.label == "City name").set_value("Tokyo").run()
    next(button for button in at.button if button.label == "Agent: Draft Plan").click().run()

    assert len(at.get("progress")) >= 1
    assert any("Could not resolve a stable city candidate" in error.value for error in at.error)
    assert "aq_agent_plan" not in at.session_state
    task_id = at.session_state["aq_agent_current_task_id"]
    task = _wait_for_task_status(store, task_id, {AgentTaskStatus.FAILED})
    logs = store.list_logs(task_id)

    assert task is not None
    assert task.status == AgentTaskStatus.FAILED
    assert task.phase == "FAILED"
    assert task.error is not None
    assert logs[-1].phase == "FAILED"


def test_custom_city_confirmation_yes_resumes_pending_agent_action(monkeypatch) -> None:
    calls: dict[str, object] = {"validate_count": 0}

    def fake_validate(country_or_region: str, city_name: str, **kwargs):  # noqa: ANN001
        del kwargs
        calls["validate_count"] = int(calls["validate_count"]) + 1
        return CustomCityValidationResult(
            input_country=country_or_region,
            input_city=city_name,
            status="needs_confirmation",
            corrected_country="Japan",
            corrected_city="Tokyo",
            country_code="JP",
            matching_countries=["Japan"],
            message="Did you mean Tokyo, Japan?",
        )

    def fake_search(
        query: str,
        country_code: str | None = None,
        count: int = 5,
        language: str = "en",
    ) -> list[CityCandidate]:
        calls["search"] = (query, country_code, count, language)
        return [
            CityCandidate(
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
        ]

    def fake_build_plan(request, candidate, **kwargs):  # noqa: ANN001
        calls["plan"] = (request, candidate, kwargs["language"])
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
            planner_notes="Direct custom-city plan.",
            quality_checks=[],
            risk_flags=[],
        )

    monkeypatch.setattr(collection_agent, "validate_custom_city_with_deepseek", fake_validate)
    monkeypatch.setattr(collection_agent, "search_city_candidates", fake_search)
    monkeypatch.setattr(collection_agent, "build_collection_plan", fake_build_plan)

    at = AppTest.from_file("pages/4_Historical_Data_Agent.py")
    at.secrets["deepseek_api_key"] = "sk-test"
    at.run()
    next(widget for widget in at.selectbox if widget.label == "City").select("Custom search").run()
    next(widget for widget in at.text_input if widget.label == "Country / region").set_value("Japen").run()
    next(widget for widget in at.text_input if widget.label == "City name").set_value("Tokio").run()
    next(button for button in at.button if button.label == "Agent: Draft Plan").click().run()

    store = at.session_state["aq_agent_task_store"]
    _wait_for_task_status(store, at.session_state["aq_agent_current_task_id"], {AgentTaskStatus.PENDING})
    at.run()

    assert "Yes, continue" in [button.label for button in at.button]

    next(button for button in at.button if button.label == "Yes, continue").click().run()
    task = _wait_for_task_status(store, at.session_state["aq_agent_current_task_id"], {AgentTaskStatus.PLANNED})

    assert calls["validate_count"] == 1
    assert calls["search"] == ("Tokyo", "JP", 10, "en")
    assert calls["plan"][0].city_query == "Tokyo"
    assert task.result_payload["city_label"] == "Tokyo, Japan"
