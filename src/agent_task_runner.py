from __future__ import annotations

from dataclasses import dataclass
from threading import Thread
from time import monotonic
from typing import Protocol
import unicodedata

import src.collection_agent as collection_agent
from src.agent_interaction import all_city_options, build_city_search_queries
from src.agent_task_store import AgentTaskStatus
from src.collection_agent import CollectionRequest, custom_city_validation_from_dict
from src.config import AQ_AGENT_DEFAULT_MODEL, AQ_AGENT_TASK_TIMEOUT_SECONDS, DEEPSEEK_BASE_URL
from src.i18n import api_language, t


class AgentTaskStore(Protocol):
    def get_task(self, task_id: str): ...

    def update_task(
        self,
        task_id: str,
        *,
        status: AgentTaskStatus | str | None = None,
        phase: str | None = None,
        progress: float | None = None,
        message: str | None = None,
        result_payload: dict[str, object] | None = None,
        error: str | None = None,
        output_path: str | None = None,
    ): ...

    def append_log(self, task_id: str, *, level: str, phase: str, message: str): ...


@dataclass(frozen=True, slots=True)
class AgentTaskRunConfig:
    api_key: str | None
    model: str = AQ_AGENT_DEFAULT_MODEL
    base_url: str = DEEPSEEK_BASE_URL
    language: str = "en"
    timeout_seconds: int = AQ_AGENT_TASK_TIMEOUT_SECONDS


_ACTIVE_THREADS: dict[str, Thread] = {}


def start_background_custom_city_task(store: AgentTaskStore, task_id: str, config: AgentTaskRunConfig) -> Thread:
    existing = _ACTIVE_THREADS.get(task_id)
    if existing is not None and existing.is_alive():
        return existing

    thread = Thread(
        target=run_custom_city_task,
        args=(store, task_id, config),
        name=f"agent-task-{task_id[:8]}",
        daemon=True,
    )
    _ACTIVE_THREADS[task_id] = thread
    thread.start()
    return thread


def run_custom_city_task(store: AgentTaskStore, task_id: str, config: AgentTaskRunConfig) -> None:
    started = monotonic()

    def check_timeout() -> None:
        if monotonic() - started > config.timeout_seconds:
            raise TimeoutError(t("agent.task_timeout", config.language, seconds=config.timeout_seconds))

    try:
        task = store.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        payload = dict(task.request_payload)
        action = str(payload.get("action") or "plan")
        input_country = str(payload.get("input_country") or "").strip()
        input_city = str(payload.get("input_city") or "").strip()
        if not input_country or not input_city:
            raise ValueError(t("agent.custom_city_inputs_required", config.language))
        if not config.api_key:
            raise ValueError(t("agent.custom_city_requires_key", config.language))

        confirmed_validation = payload.get("confirmed_validation")
        is_confirmed_validation = isinstance(confirmed_validation, dict) and bool(confirmed_validation)
        if is_confirmed_validation:
            validation = custom_city_validation_from_dict(confirmed_validation)
            _record_step(
                store,
                task_id,
                status=AgentTaskStatus.RUNNING,
                phase="VALIDATING",
                progress=0.12,
                message=t(
                    "agent.custom_city_confirmed",
                    config.language,
                    city=validation.corrected_city or validation.input_city,
                    country=validation.corrected_country or validation.input_country,
                ),
            )
        else:
            _record_step(
                store,
                task_id,
                status=AgentTaskStatus.RUNNING,
                phase="VALIDATING",
                progress=0.08,
                message=t("agent.validating_custom_city", config.language),
            )
            validation = collection_agent.validate_custom_city_with_deepseek(
                input_country,
                input_city,
                api_key=config.api_key,
                model=config.model,
                base_url=config.base_url,
                language=config.language,
            )
        if validation.status == "low_confidence":
            message = validation.message or t("agent.custom_city_low_confidence", config.language)
            _record_step(store, task_id, status=AgentTaskStatus.FAILED, phase="FAILED", progress=1.0, message=message, error=message)
            return
        if validation.status == "needs_confirmation" and not is_confirmed_validation:
            message = validation.message or t(
                "agent.custom_city_confirmation",
                config.language,
                city=validation.corrected_city or validation.input_city,
                country=validation.corrected_country or validation.input_country,
            )
            _record_step(
                store,
                task_id,
                status=AgentTaskStatus.PENDING,
                phase="AWAITING_CONFIRMATION",
                progress=0.12,
                message=message,
                result_payload={"validation": validation.to_dict(), "action": action},
            )
            return

        check_timeout()
        request = _collection_request_from_payload(payload, validation)
        _record_step(
            store,
            task_id,
            status=AgentTaskStatus.RUNNING,
            phase="RESOLVING",
            progress=0.24,
            message=t("agent.resolving_city", config.language),
        )
        candidate, resolved_query = _resolve_city_candidate(
            request,
            payload,
            validation,
            language=api_language(config.language),
        )
        if candidate is None:
            raise ValueError(
                t(
                    "agent.city_not_found",
                    config.language,
                    city=f"{request.city_query}, {request.country_code or t('agent.custom_city_country', config.language)}",
                )
            )
        request.city_query = resolved_query

        check_timeout()
        _record_step(
            store,
            task_id,
            status=AgentTaskStatus.RUNNING,
            phase="PLANNING",
            progress=0.28,
            message=t("agent.building_plan", config.language),
        )
        if action == "collect":
            result = collection_agent.run_collection_agent(
                request,
                candidate,
                api_key=config.api_key,
                model=config.model,
                base_url=config.base_url,
                progress_callback=lambda step, total, message: _record_step(
                    store,
                    task_id,
                    status=AgentTaskStatus.RUNNING,
                    phase="COLLECTING",
                    progress=min(step / max(total, 1), 1.0),
                    message=message,
                ),
                language=config.language,
            )
            _record_step(
                store,
                task_id,
                status=AgentTaskStatus.SAVED,
                phase="SAVED",
                progress=1.0,
                message=t("collection.progress_saved", config.language, path=result.output_path),
                result_payload={
                    "row_count": result.row_count,
                    "started_at": result.started_at,
                    "ended_at": result.ended_at,
                    "summary_text": result.summary_text,
                    "summary_mode": result.summary_mode,
                    "runtime_warnings": result.runtime_warnings,
                    "coverage_rows": result.coverage_rows,
                    "plan": result.plan.to_dict(),
                },
                output_path=result.output_path,
            )
        else:
            plan = collection_agent.build_collection_plan(
                request,
                candidate,
                api_key=config.api_key,
                model=config.model,
                base_url=config.base_url,
                language=config.language,
            )
            _record_step(
                store,
                task_id,
                status=AgentTaskStatus.PLANNED,
                phase="PLANNING",
                progress=1.0,
                message=t("agent.task_plan_ready", config.language),
                result_payload=plan.to_dict(),
                log=False,
            )
    except TimeoutError as exc:
        _record_step(store, task_id, status=AgentTaskStatus.TIMEOUT, phase="TIMEOUT", progress=1.0, message=str(exc), error=str(exc))
    except Exception as exc:  # noqa: BLE001
        _record_step(store, task_id, status=AgentTaskStatus.FAILED, phase="FAILED", progress=1.0, message=str(exc), error=str(exc))


def _collection_request_from_payload(payload: dict[str, object], validation) -> CollectionRequest:
    weather_fields = [str(item) for item in list(payload.get("weather_fields") or []) if str(item).strip()]
    return CollectionRequest(
        city_query=validation.corrected_city or str(payload.get("input_city") or payload.get("city_query") or "").strip(),
        start_year=int(payload.get("start_year") or 2024),
        end_year=int(payload.get("end_year") or 2024),
        pollutants=[str(item) for item in list(payload.get("pollutants") or ["pm25"])],
        include_weather=bool(payload.get("include_weather")),
        country_code=validation.country_code,
        weather_fields=weather_fields,
    )


def _resolve_city_candidate(
    request: CollectionRequest,
    payload: dict[str, object],
    validation,
    *,
    language: str,
):
    for query in _city_candidate_queries(request, payload, validation):
        candidates = collection_agent.search_city_candidates(
            query,
            country_code=request.country_code,
            count=10,
            language=language,
        )
        if candidates:
            return candidates[0], query
    return None, request.city_query


def _city_candidate_queries(request: CollectionRequest, payload: dict[str, object], validation) -> list[str]:
    base_queries = [
        request.city_query,
        getattr(validation, "corrected_city", None),
        getattr(validation, "input_city", None),
        payload.get("input_city"),
        payload.get("city_query"),
    ]
    catalog_queries: list[str] = []
    for option in _matching_catalog_city_options(payload, validation):
        catalog_queries.extend(build_city_search_queries(option))
    return _unique_strings([*base_queries, *catalog_queries])


def _matching_catalog_city_options(payload: dict[str, object], validation):
    city_keys = {
        _normalize_match_value(value)
        for value in [
            getattr(validation, "corrected_city", None),
            getattr(validation, "input_city", None),
            payload.get("input_city"),
            payload.get("city_query"),
        ]
        if _normalize_match_value(value)
    }
    country_keys = {
        _normalize_match_value(value)
        for value in [
            getattr(validation, "corrected_country", None),
            getattr(validation, "input_country", None),
            getattr(validation, "country_code", None),
            payload.get("input_country"),
            payload.get("country_code"),
        ]
        if _normalize_match_value(value)
    }
    if not city_keys or not country_keys:
        return []

    matches = []
    for option in _all_catalog_city_options():
        option_country_keys = {
            _normalize_match_value(option.country_code),
            _normalize_match_value(option.country),
            _normalize_match_value(option.display_country("en")),
            _normalize_match_value(option.display_country("zh-CN")),
        }
        if country_keys.isdisjoint(option_country_keys):
            continue

        option_city_keys = {
            _normalize_match_value(option.city),
            _normalize_match_value(option.city_query),
            _normalize_match_value(option.display_city("en")),
            _normalize_match_value(option.display_city("zh-CN")),
        }
        if not city_keys.isdisjoint(option_city_keys):
            matches.append(option)
    return matches


def _all_catalog_city_options():
    return all_city_options()


def _normalize_match_value(value) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(char for char in text if char.isalnum())


def _unique_strings(values) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        output.append(text)
        seen.add(text)
    return output


def _record_step(
    store: AgentTaskStore,
    task_id: str,
    *,
    status: AgentTaskStatus,
    phase: str,
    progress: float,
    message: str,
    result_payload: dict[str, object] | None = None,
    error: str | None = None,
    output_path: str | None = None,
    log: bool = True,
) -> None:
    existing = store.get_task(task_id)
    if existing is not None and existing.status in {
        AgentTaskStatus.PLANNED,
        AgentTaskStatus.SAVED,
        AgentTaskStatus.FAILED,
        AgentTaskStatus.TIMEOUT,
    }:
        return
    store.update_task(
        task_id,
        status=status,
        phase=phase,
        progress=progress,
        message=message,
        result_payload=result_payload,
        error=error,
        output_path=output_path,
    )
    if log:
        store.append_log(task_id, level="error" if status in {AgentTaskStatus.FAILED, AgentTaskStatus.TIMEOUT} else "info", phase=phase, message=message)
