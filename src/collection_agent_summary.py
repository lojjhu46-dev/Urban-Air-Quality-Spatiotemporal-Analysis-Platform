from __future__ import annotations

import json
from typing import Any, Callable, Protocol

import pandas as pd

from src.i18n import t

JsonCompletion = Callable[[list[dict[str, Any]], str, str, str, int], dict[str, Any] | None]


class PlannerCandidateLike(Protocol):
    display_name: str


class CollectionPlanLike(Protocol):
    city_label: str
    actual_start_date: str
    actual_end_date: str
    sampling_step: str
    output_path: str

    def to_dict(self) -> dict[str, Any]: ...


def default_planner_notes(
    candidate: PlannerCandidateLike,
    pollutants: list[str],
    chunks: list[dict[str, str]],
    weather_fields: list[str],
    language: str = "en",
) -> str:
    weather_note = (
        t("collection.weather_with_fields", language, fields=", ".join(field.lower() for field in weather_fields))
        if weather_fields
        else t("collection.weather_without", language)
    )
    pollutants_text = ", ".join(pollutant.upper() for pollutant in pollutants)
    return t(
        "collection.default_planner_notes",
        language,
        city=candidate.display_name,
        chunks=len(chunks),
        pollutants=pollutants_text,
        weather_clause=weather_note,
    )


def default_run_summary(
    df: pd.DataFrame,
    plan: CollectionPlanLike,
    coverage_rows: list[dict[str, Any]],
    runtime_warnings: list[str],
    language: str = "en",
) -> str:
    coverage_text = ", ".join(f"{row['pollutant'].upper()} {row['non_null_ratio']:.0%}" for row in coverage_rows)
    warning_text = t("collection.summary_warnings", language, warnings="; ".join(runtime_warnings)) if runtime_warnings else ""
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


def generate_planner_guidance(
    plan: CollectionPlanLike,
    api_key: str,
    model: str,
    base_url: str,
    *,
    json_completion: JsonCompletion,
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
    return json_completion(messages, api_key, model, base_url, 90)


def generate_run_summary(
    df: pd.DataFrame,
    plan: CollectionPlanLike,
    coverage_rows: list[dict[str, Any]],
    runtime_warnings: list[str],
    api_key: str,
    model: str,
    base_url: str,
    *,
    json_completion: JsonCompletion,
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
    return json_completion(messages, api_key, model, base_url, 90)


def merge_run_summary(
    deterministic_summary: str,
    summary_data: dict[str, Any] | None,
    model: str,
) -> tuple[str, str]:
    if not summary_data:
        return deterministic_summary, "deterministic"

    llm_summary = str(summary_data.get("summary") or "").strip()
    caveat = str(summary_data.get("caveat") or "").strip()
    if caveat:
        llm_summary = " ".join(part for part in [llm_summary, caveat] if part).strip()
    if not llm_summary:
        llm_summary = deterministic_summary
    return llm_summary, model
