from __future__ import annotations

from streamlit.testing.v1 import AppTest

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

    assert option.display_province("zh-CN") == "北京市"
    assert option.display_city("zh-CN") == "北京"
    assert option.path_label_for_language("zh-CN") == "Asia - China - 北京市 - 北京"
    assert option.city_query == "Beijing"


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
