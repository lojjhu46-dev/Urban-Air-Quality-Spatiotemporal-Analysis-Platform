from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from src.collection_agent_summary import (
    default_planner_notes,
    default_run_summary,
    generate_planner_guidance,
    generate_run_summary,
    merge_run_summary,
)


@dataclass(slots=True)
class FakeCandidate:
    display_name: str = "Tokyo, Japan"


@dataclass(slots=True)
class FakePlan:
    city_label: str = "Tokyo, Japan"
    actual_start_date: str = "2024-01-01"
    actual_end_date: str = "2024-12-31"
    sampling_step: str = "3-hourly"
    output_path: str = "data/processed/tokyo_2024_aq.parquet"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def test_default_planner_notes_mentions_weather_fields() -> None:
    text = default_planner_notes(
        FakeCandidate(),
        pollutants=["pm25", "o3"],
        chunks=[{"start_date": "2024-01-01", "end_date": "2024-01-31"}],
        weather_fields=["temp", "humidity"],
        language="en",
    )

    assert "Tokyo, Japan" in text
    assert "PM25, O3" in text
    assert "weather fields temp, humidity" in text


def test_default_run_summary_includes_warnings() -> None:
    df = pd.DataFrame({"timestamp": ["2024-01-01T00:00"], "pm25": [12.0]})
    text = default_run_summary(
        df,
        FakePlan(),
        [{"pollutant": "pm25", "non_null_ratio": 1.0}],
        ["clipped start"],
        language="en",
    )

    assert "Collected 1 rows for Tokyo, Japan" in text
    assert "PM25 100%" in text
    assert "Warnings: clipped start" in text


def test_generate_planner_guidance_builds_json_only_prompt() -> None:
    captured: dict[str, object] = {}

    def fake_json_completion(messages, api_key, model, base_url, timeout):  # noqa: ANN001
        captured["messages"] = messages
        captured["args"] = (api_key, model, base_url, timeout)
        return {"planner_notes": "Use archive.", "quality_checks": ["coverage"], "risk_flags": []}

    payload = generate_planner_guidance(
        FakePlan(),
        "sk-test",
        "deepseek-chat",
        "https://api.deepseek.com",
        json_completion=fake_json_completion,
        language="en",
    )

    messages = captured["messages"]
    assert payload["planner_notes"] == "Use archive."
    assert captured["args"] == ("sk-test", "deepseek-chat", "https://api.deepseek.com", 90)
    assert "Return JSON only" in messages[0]["content"]
    assert "Tokyo, Japan" in messages[1]["content"]


def test_generate_run_summary_builds_preview_payload() -> None:
    captured: dict[str, object] = {}

    def fake_json_completion(messages, api_key, model, base_url, timeout):  # noqa: ANN001
        del api_key, model, base_url, timeout
        captured["messages"] = messages
        return {"summary": "Saved Tokyo data.", "caveat": "Coverage varies."}

    payload = generate_run_summary(
        pd.DataFrame({"timestamp": ["2024-01-01T00:00"], "pm25": [12.0]}),
        FakePlan(),
        [{"pollutant": "pm25", "non_null_ratio": 1.0}],
        ["clipped end"],
        "sk-test",
        "deepseek-chat",
        "https://api.deepseek.com",
        json_completion=fake_json_completion,
        language="en",
    )

    messages = captured["messages"]
    assert payload["summary"] == "Saved Tokyo data."
    assert "Summarize this run" in messages[1]["content"]
    assert "clipped end" in messages[1]["content"]


def test_merge_run_summary_falls_back_or_appends_caveat() -> None:
    assert merge_run_summary("fallback", None, "deepseek-chat") == ("fallback", "deterministic")
    assert merge_run_summary("fallback", {"summary": "", "caveat": ""}, "deepseek-chat") == ("fallback", "deepseek-chat")
    assert merge_run_summary("fallback", {"summary": "Saved.", "caveat": "Partial."}, "deepseek-chat") == (
        "Saved. Partial.",
        "deepseek-chat",
    )
