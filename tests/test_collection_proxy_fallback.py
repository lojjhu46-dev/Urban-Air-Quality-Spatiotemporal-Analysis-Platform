from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.collection_proxy_fallback import (
    candidate_catalog_province,
    collect_proxy_candidate,
    generate_proxy_city_plan,
    maybe_collect_with_deepseek_proxy,
    parse_proxy_city_plan_response,
    proxy_query_values,
    same_candidate,
)


@dataclass(slots=True)
class FakeRequest:
    city_query: str = "Yangjiang"


@dataclass(slots=True)
class FakeCandidate:
    name: str
    country_code: str = "CN"
    admin1: str | None = "Guangdong"
    open_meteo_id: int | None = None

    @property
    def display_name(self) -> str:
        return f"{self.name}, {self.admin1}, China"


@dataclass(slots=True)
class FakePlan:
    city_label: str
    pollutants: list[str]
    warnings: list[str]
    risk_flags: list[str] | None = None


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "").replace("province", "").replace("city", "")


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def test_candidate_catalog_province_only_accepts_china_candidates() -> None:
    assert candidate_catalog_province(FakeCandidate("Yangjiang"), resolve_province=lambda admin: admin) == "Guangdong"
    assert candidate_catalog_province(FakeCandidate("Tokyo", country_code="JP", admin1="Tokyo"), resolve_province=lambda admin: admin) is None


def test_same_candidate_prefers_open_meteo_id_when_available() -> None:
    assert same_candidate(
        FakeCandidate("Yangjiang", open_meteo_id=123),
        FakeCandidate("Other", open_meteo_id=123),
        normalize_location_key=_normalize,
    )
    assert not same_candidate(
        FakeCandidate("Yangjiang", open_meteo_id=123),
        FakeCandidate("Yangjiang", open_meteo_id=456),
        normalize_location_key=_normalize,
    )


def test_same_candidate_falls_back_to_normalized_location() -> None:
    assert same_candidate(
        FakeCandidate("Yangjiang City", admin1="Guangdong Province"),
        FakeCandidate("Yangjiang", admin1="Guangdong"),
        normalize_location_key=_normalize,
    )
    assert not same_candidate(
        FakeCandidate("Yangjiang", admin1="Guangdong"),
        FakeCandidate("Yangjiang", admin1="Guangxi"),
        normalize_location_key=_normalize,
    )


def test_parse_proxy_city_plan_response_filters_to_allowed_cities() -> None:
    plan = parse_proxy_city_plan_response(
        {
            "proxy_city_names": ["Foshan", "Shenzhen", "Tokyo", "Foshan"],
            "query_variants": ["Yangjiang Guangdong", "", "Foshan AQ"],
            "note": "Use a same-province proxy.",
        },
        allowed_city_names=["Foshan", "Shenzhen"],
        normalize_location_key=_normalize,
        unique_strings=_unique,
    )

    assert plan == {
        "proxy_city_names": ["Foshan", "Shenzhen"],
        "query_variants": ["Yangjiang Guangdong", "Foshan AQ"],
        "note": "Use a same-province proxy.",
    }


def test_parse_proxy_city_plan_response_returns_none_without_queries_or_allowed_proxies() -> None:
    assert (
        parse_proxy_city_plan_response(
            {"proxy_city_names": ["Tokyo"], "query_variants": [], "note": "No match."},
            allowed_city_names=["Foshan"],
            normalize_location_key=_normalize,
            unique_strings=_unique,
        )
        is None
    )


def test_generate_proxy_city_plan_builds_prompt_and_filters_response() -> None:
    captured: dict[str, object] = {}

    def fake_json_completion(messages, api_key, model, base_url, timeout):  # noqa: ANN001
        captured["messages"] = messages
        captured["args"] = (api_key, model, base_url, timeout)
        return {
            "proxy_city_names": ["Foshan", "Tokyo"],
            "query_variants": ["Foshan"],
            "note": "Use Foshan.",
        }

    plan = generate_proxy_city_plan(
        FakeRequest(),
        FakeCandidate("Yangjiang"),
        province="Guangdong",
        api_key="sk-test",
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        json_completion=fake_json_completion,
        province_city_names=lambda province: ["Foshan", "Shenzhen"] if province == "Guangdong" else [],
        normalize_location_key=_normalize,
        unique_strings=_unique,
        language="en",
    )

    messages = captured["messages"]
    assert captured["args"] == ("sk-test", "deepseek-chat", "https://api.deepseek.com", 90)
    assert "Return JSON only" in messages[0]["content"]
    assert "Allowed same-province cities: Foshan, Shenzhen" in messages[1]["content"]
    assert plan == {"proxy_city_names": ["Foshan"], "query_variants": ["Foshan"], "note": "Use Foshan."}


def test_proxy_query_values_combines_variants_before_proxy_names() -> None:
    assert proxy_query_values(
        {"query_variants": ["Yangjiang", "Foshan"], "proxy_city_names": ["Foshan", "Shenzhen"]},
        unique_strings=_unique,
    ) == ["Yangjiang", "Foshan", "Shenzhen"]


def test_collect_proxy_candidate_returns_none_without_usable_coverage() -> None:
    plan = FakePlan("Foshan, Guangdong, China", ["pm25"], [])

    result = collect_proxy_candidate(
        FakeRequest(),
        FakeCandidate("Foshan"),
        output_dir=Path("data"),
        language="en",
        build_plan=lambda *args, **kwargs: plan,
        collect_dataset=lambda *args, **kwargs: ("frame", ["warning"]),
        summarize_coverage=lambda frame, pollutants: [{"pollutant": pollutants[0], "non_null_ratio": 0.0}],
        has_usable_coverage_rows=lambda rows: False,
    )

    assert result is None


def test_collect_proxy_candidate_returns_plan_dataset_and_coverage() -> None:
    plan = FakePlan("Foshan, Guangdong, China", ["pm25"], [])

    result = collect_proxy_candidate(
        FakeRequest(),
        FakeCandidate("Foshan"),
        output_dir=Path("data"),
        language="en",
        build_plan=lambda *args, **kwargs: plan,
        collect_dataset=lambda *args, **kwargs: ("frame", ["warning"]),
        summarize_coverage=lambda frame, pollutants: [{"pollutant": pollutants[0], "non_null_ratio": 1.0}],
        has_usable_coverage_rows=lambda rows: True,
    )

    assert result == (plan, "frame", ["warning"], [{"pollutant": "pm25", "non_null_ratio": 1.0}])


def test_maybe_collect_with_deepseek_proxy_uses_first_valid_proxy_candidate() -> None:
    source = FakeCandidate("Yangjiang")
    same_city = FakeCandidate("Yangjiang")
    other_province = FakeCandidate("Guilin", admin1="Guangxi")
    proxy = FakeCandidate("Foshan")
    proxy_plan_result = FakePlan("Foshan, Guangdong, China", ["pm25"], ["proxy warning"])
    notifications: list[str] = []

    def fake_translate(key: str, language: str, **kwargs: object) -> str:
        del language
        if key == "collection.deepseek_proxy_attempt":
            return f"attempt {kwargs['requested']} in {kwargs['province']}"
        if key == "collection.deepseek_proxy_used":
            return f"used {kwargs['actual']}"
        return key

    result = maybe_collect_with_deepseek_proxy(
        FakeRequest(),
        source,
        initial_warnings=["initial"],
        api_key="sk-test",
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        output_dir=Path("data"),
        language="en",
        progress_callback=None,
        province_city_names=lambda province: ["Yangjiang", "Foshan"] if province == "Guangdong" else [],
        candidate_catalog_province_fn=lambda candidate: candidate.admin1 if candidate.country_code == "CN" else None,
        same_candidate_fn=lambda left, right: left.name == right.name and left.admin1 == right.admin1,
        generate_proxy_plan=lambda *args, **kwargs: {
            "query_variants": ["bad query"],
            "proxy_city_names": ["Foshan"],
            "note": "Use same-province proxy.",
        },
        search_city_candidates=lambda query, **kwargs: (_ for _ in ()).throw(RuntimeError("network")) if query == "bad query" else [same_city, other_province, proxy],
        collect_proxy=lambda *args, **kwargs: (proxy_plan_result, "frame", ["collect warning"], [{"pollutant": "pm25", "non_null_ratio": 1.0}]),
        unique_strings=_unique,
        translate=fake_translate,
        notify=lambda callback, step, total, message: notifications.append(message),
    )

    assert result == (
        proxy_plan_result,
        "frame",
        ["initial", "attempt Yangjiang, Guangdong, China in Guangdong", "Use same-province proxy.", "collect warning", "used Foshan, Guangdong, China"],
        [{"pollutant": "pm25", "non_null_ratio": 1.0}],
    )
    assert proxy_plan_result.warnings == ["proxy warning", "used Foshan, Guangdong, China"]
    assert proxy_plan_result.risk_flags == ["used Foshan, Guangdong, China"]
    assert notifications == ["attempt Yangjiang, Guangdong, China in Guangdong"]


def test_maybe_collect_with_deepseek_proxy_requires_key_and_multiple_same_province_cities() -> None:
    result = maybe_collect_with_deepseek_proxy(
        FakeRequest(),
        FakeCandidate("Yangjiang"),
        initial_warnings=[],
        api_key=None,
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        output_dir=Path("data"),
        language="en",
        progress_callback=None,
        province_city_names=lambda province: ["Yangjiang", "Foshan"],
        candidate_catalog_province_fn=lambda candidate: "Guangdong",
        same_candidate_fn=lambda left, right: False,
        generate_proxy_plan=lambda *args, **kwargs: {"proxy_city_names": ["Foshan"]},
        search_city_candidates=lambda *args, **kwargs: [],
        collect_proxy=lambda *args, **kwargs: None,
        unique_strings=_unique,
        translate=lambda key, language, **kwargs: key,
        notify=lambda *args: None,
    )

    assert result is None
