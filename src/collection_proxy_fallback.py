from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol


JsonCompletion = Callable[[list[dict[str, Any]], str, str, str, int], dict[str, Any] | None]
LocationKeyNormalizer = Callable[[Any], str]
UniqueStrings = Callable[[list[str]], list[str]]
ProvinceResolver = Callable[[str], str | None]
ProvinceCityNames = Callable[[str], list[str]]
Translator = Callable[..., str]
Notifier = Callable[[Any | None, int, int, str], None]
PlanBuilder = Callable[..., Any]
DatasetCollector = Callable[..., tuple[Any, list[str]]]
CoverageSummarizer = Callable[[Any, list[str]], list[dict[str, Any]]]
CoverageChecker = Callable[[list[dict[str, Any]]], bool]
CitySearcher = Callable[..., list[Any]]
ProxyPlanGenerator = Callable[..., dict[str, Any] | None]
ProxyCollector = Callable[..., tuple[Any, Any, list[str], list[dict[str, Any]]] | None]


class ProxyRequestLike(Protocol):
    city_query: str


class ProxyCandidateLike(Protocol):
    name: str
    country_code: str
    admin1: str | None
    open_meteo_id: int | None
    display_name: str


class ProxyPlanLike(Protocol):
    pollutants: list[str]
    warnings: list[str]
    risk_flags: list[str] | None


def candidate_catalog_province(
    candidate: ProxyCandidateLike,
    *,
    resolve_province: ProvinceResolver,
) -> str | None:
    if candidate.country_code.upper() != "CN":
        return None
    return resolve_province(candidate.admin1 or "")


def same_candidate(
    left: ProxyCandidateLike,
    right: ProxyCandidateLike,
    *,
    normalize_location_key: LocationKeyNormalizer,
) -> bool:
    if left.open_meteo_id is not None and right.open_meteo_id is not None:
        return left.open_meteo_id == right.open_meteo_id
    return (
        normalize_location_key(left.name) == normalize_location_key(right.name)
        and normalize_location_key(left.admin1 or "") == normalize_location_key(right.admin1 or "")
        and left.country_code.upper() == right.country_code.upper()
    )


def parse_proxy_city_plan_response(
    data: dict[str, Any],
    *,
    allowed_city_names: list[str],
    normalize_location_key: LocationKeyNormalizer,
    unique_strings: UniqueStrings,
) -> dict[str, Any] | None:
    allowed_keys = {normalize_location_key(city) for city in allowed_city_names}
    proxy_names = [
        str(item).strip()
        for item in list(data.get("proxy_city_names") or [])
        if normalize_location_key(item) in allowed_keys
    ]
    query_variants = [str(item).strip() for item in list(data.get("query_variants") or []) if str(item).strip()]
    note = str(data.get("note") or "").strip()
    if not proxy_names and not query_variants:
        return None
    return {
        "proxy_city_names": unique_strings(proxy_names),
        "query_variants": unique_strings(query_variants),
        "note": note,
    }


def generate_proxy_city_plan(
    request: ProxyRequestLike,
    candidate: ProxyCandidateLike,
    *,
    province: str,
    api_key: str,
    model: str,
    base_url: str,
    json_completion: JsonCompletion,
    province_city_names: ProvinceCityNames,
    normalize_location_key: LocationKeyNormalizer,
    unique_strings: UniqueStrings,
    language: str = "en",
) -> dict[str, Any] | None:
    reply_language = "Simplified Chinese" if language == "zh-CN" else "English"
    allowed_city_names = province_city_names(province)
    allowed_cities = ", ".join(allowed_city_names)
    messages = [
        {
            "role": "system",
            "content": (
                "You help recover sparse air-quality coverage for curated mainland China cities. "
                "Return JSON only with keys query_variants, proxy_city_names, note. "
                "Do not invent measurements. Only suggest curated same-province municipalities or prefecture-level cities. "
                f"Write note in {reply_language}."
            ),
        },
        {
            "role": "user",
            "content": (
                "The requested city returned no usable air-quality coverage from the current source. "
                "Suggest query aliases and nearby same-province proxy cities that are likely to have stable coverage.\n"
                f"Requested city: {candidate.display_name}\n"
                f"Province: {province}\n"
                f"Original query: {request.city_query}\n"
                f"Allowed same-province cities: {allowed_cities}\n"
                "Return at most 4 query_variants and at most 3 proxy_city_names."
            ),
        },
    ]
    data = json_completion(messages, api_key, model, base_url, 90)
    if not data:
        return None
    return parse_proxy_city_plan_response(
        data,
        allowed_city_names=allowed_city_names,
        normalize_location_key=normalize_location_key,
        unique_strings=unique_strings,
    )


def proxy_query_values(proxy_plan: dict[str, Any], *, unique_strings: UniqueStrings) -> list[str]:
    return unique_strings(
        [
            *list(proxy_plan.get("query_variants") or []),
            *list(proxy_plan.get("proxy_city_names") or []),
        ]
    )


def collect_proxy_candidate(
    request: ProxyRequestLike,
    candidate: ProxyCandidateLike,
    *,
    output_dir: Path,
    language: str,
    build_plan: PlanBuilder,
    collect_dataset: DatasetCollector,
    summarize_coverage: CoverageSummarizer,
    has_usable_coverage_rows: CoverageChecker,
) -> tuple[Any, Any, list[str], list[dict[str, Any]]] | None:
    proxy_plan = build_plan(
        request,
        candidate,
        api_key=None,
        output_dir=output_dir,
        language=language,
    )
    proxy_df, proxy_warnings = collect_dataset(proxy_plan, candidate, progress_callback=None, language=language)
    proxy_coverage = summarize_coverage(proxy_df, proxy_plan.pollutants)
    if not has_usable_coverage_rows(proxy_coverage):
        return None
    return proxy_plan, proxy_df, proxy_warnings, proxy_coverage


def maybe_collect_with_deepseek_proxy(
    request: ProxyRequestLike,
    candidate: ProxyCandidateLike,
    *,
    initial_warnings: list[str],
    api_key: str | None,
    model: str,
    base_url: str,
    output_dir: Path,
    language: str,
    progress_callback: Any | None,
    province_city_names: ProvinceCityNames,
    candidate_catalog_province_fn: Callable[[Any], str | None],
    same_candidate_fn: Callable[[Any, Any], bool],
    generate_proxy_plan: ProxyPlanGenerator,
    search_city_candidates: CitySearcher,
    collect_proxy: ProxyCollector,
    unique_strings: UniqueStrings,
    translate: Translator,
    notify: Notifier,
) -> tuple[Any, Any, list[str], list[dict[str, Any]]] | None:
    source_province = candidate_catalog_province_fn(candidate)
    if not api_key or not source_province or len(province_city_names(source_province)) < 2:
        return None

    warning_prefix = translate(
        "collection.deepseek_proxy_attempt",
        language,
        requested=candidate.display_name,
        province=source_province,
    )
    notify(progress_callback, 0, 1, warning_prefix)

    proxy_plan = generate_proxy_plan(
        request,
        candidate,
        province=source_province,
        api_key=api_key,
        model=model,
        base_url=base_url,
        language=language,
    )
    if not proxy_plan:
        return None

    combined_warnings = unique_strings([*initial_warnings, warning_prefix])
    note = str(proxy_plan.get("note") or "").strip()
    if note:
        combined_warnings.append(note)

    for query in proxy_query_values(proxy_plan, unique_strings=unique_strings):
        try:
            candidates = search_city_candidates(
                query,
                country_code=getattr(request, "country_code", None) or candidate.country_code,
                count=5,
                language="en",
            )
        except Exception:  # noqa: BLE001
            continue

        for proxy_candidate in candidates:
            if candidate_catalog_province_fn(proxy_candidate) != source_province:
                continue
            if same_candidate_fn(candidate, proxy_candidate):
                continue

            proxy_run = collect_proxy(
                request,
                proxy_candidate,
                output_dir=output_dir,
                language=language,
            )
            if proxy_run is None:
                continue

            proxy_plan_result, proxy_df, proxy_warnings, proxy_coverage = proxy_run
            proxy_warning = translate(
                "collection.deepseek_proxy_used",
                language,
                requested=candidate.display_name,
                actual=proxy_candidate.display_name,
            )
            proxy_plan_result.warnings = unique_strings([*proxy_plan_result.warnings, proxy_warning])
            proxy_plan_result.risk_flags = unique_strings([*(proxy_plan_result.risk_flags or []), proxy_warning])
            proxy_warnings = unique_strings([*combined_warnings, *proxy_warnings, proxy_warning])
            return proxy_plan_result, proxy_df, proxy_warnings, proxy_coverage

    combined_warnings.append(translate("collection.deepseek_proxy_failed", language))
    return None
