from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from src.i18n import t


@dataclass(slots=True)
class CustomCityValidationResult:
    input_country: str
    input_city: str
    status: str
    corrected_country: str | None
    corrected_city: str | None
    country_code: str | None
    matching_countries: list[str]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def custom_city_validation_from_dict(data: dict[str, Any]) -> CustomCityValidationResult:
    return CustomCityValidationResult(
        input_country=str(data.get("input_country") or ""),
        input_city=str(data.get("input_city") or ""),
        status=normalize_custom_city_status(data.get("status"), data.get("message")),
        corrected_country=str(data.get("corrected_country") or "") or None,
        corrected_city=str(data.get("corrected_city") or "") or None,
        country_code=normalize_country_code(data.get("country_code")),
        matching_countries=[str(item) for item in list(data.get("matching_countries") or []) if str(item).strip()],
        message=str(data.get("message") or ""),
    )


def custom_city_validation_from_model_response(
    clean_country: str,
    clean_city: str,
    data: dict[str, Any],
    *,
    language: str = "en",
) -> CustomCityValidationResult:
    corrected_country = str(data.get("corrected_country") or "").strip() or None
    corrected_city = str(data.get("corrected_city") or "").strip() or None
    country_code = normalize_country_code(data.get("country_code"))
    matching_countries = unique_strings(
        [str(item).strip() for item in list(data.get("matching_countries") or []) if str(item).strip()]
    )
    message = str(data.get("message") or "").strip()
    if not message:
        message = t("agent.custom_city_validated", language, city=corrected_city or clean_city, country=corrected_country or clean_country)
    status = normalize_custom_city_status(data.get("status"), message)

    if status == "valid":
        corrected_country = corrected_country or clean_country
        corrected_city = corrected_city or clean_city

    if status == "valid" and (not corrected_city or not corrected_country):
        status = "needs_confirmation" if matching_countries else "low_confidence"
    if status == "valid":
        country_changed = corrected_country and normalize_location_key(corrected_country) != normalize_location_key(clean_country)
        city_changed = corrected_city and normalize_location_key(corrected_city) != normalize_location_key(clean_city)
        if country_changed or city_changed or len(matching_countries) > 1:
            status = "needs_confirmation"

    return CustomCityValidationResult(
        input_country=clean_country,
        input_city=clean_city,
        status=status,
        corrected_country=corrected_country,
        corrected_city=corrected_city,
        country_code=country_code,
        matching_countries=matching_countries,
        message=message,
    )


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        output.append(text)
        seen.add(text)
    return output


def normalize_custom_city_status(raw_status: Any, message: Any = None) -> str:
    text = f"{raw_status or ''} {message or ''}".strip().lower()
    compact = re.sub(r"[\s_\-]+", "", text)
    if not compact:
        return "low_confidence"
    if compact in {"valid", "needsconfirmation", "lowconfidence"}:
        return {"valid": "valid", "needsconfirmation": "needs_confirmation", "lowconfidence": "low_confidence"}[compact]
    if any(token in text for token in ("low confidence", "invalid", "not valid")) or any(
        token in compact for token in ("\u4f4e\u7f6e\u4fe1", "\u7f6e\u4fe1\u5ea6\u4f4e", "\u65e0\u6548", "\u4e0d\u786e\u5b9a", "\u4e0d\u5339\u914d")
    ):
        return "low_confidence"
    if any(
        token in compact
        for token in (
            "needsconfirmation",
            "requiresconfirmation",
            "confirmationrequired",
            "pleaseconfirm",
            "confirmcountry",
            "ambiguous",
            "\u9700\u786e\u8ba4",
            "\u9700\u8981\u786e\u8ba4",
            "\u91cd\u540d",
            "\u591a\u4e2a",
        )
    ):
        return "needs_confirmation"
    if any(token in compact for token in ("valid", "correct", "\u6709\u6548", "\u6b63\u786e", "\u9a8c\u8bc1\u6210\u529f")):
        return "valid"
    return "low_confidence"


def normalize_country_code(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


def normalize_location_key(value: Any) -> str:
    lowered = str(value or "").strip().lower()
    collapsed = re.sub(r"[^a-z0-9]+", "", lowered)
    return collapsed.replace("province", "").replace("city", "")
