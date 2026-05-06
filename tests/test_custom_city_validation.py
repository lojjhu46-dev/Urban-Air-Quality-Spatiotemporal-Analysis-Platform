from __future__ import annotations

from src.custom_city_validation import (
    custom_city_validation_from_dict,
    custom_city_validation_from_model_response,
    normalize_country_code,
    normalize_custom_city_status,
    normalize_location_key,
    unique_strings,
)


def test_custom_city_validation_from_model_response_accepts_valid_location() -> None:
    result = custom_city_validation_from_model_response(
        "Japan",
        "Tokyo",
        {
            "status": "valid",
            "corrected_country": "Japan",
            "corrected_city": "Tokyo",
            "country_code": "jp",
            "matching_countries": ["Japan", "Japan"],
            "message": "Tokyo, Japan is valid.",
        },
    )

    assert result.status == "valid"
    assert result.corrected_country == "Japan"
    assert result.corrected_city == "Tokyo"
    assert result.country_code == "JP"
    assert result.matching_countries == ["Japan"]


def test_custom_city_validation_from_model_response_prompts_for_corrected_spelling() -> None:
    result = custom_city_validation_from_model_response(
        "Japen",
        "Tokio",
        {
            "status": "valid",
            "corrected_country": "Japan",
            "corrected_city": "Tokyo",
            "country_code": "JP",
            "matching_countries": ["Japan"],
            "message": "Did you mean Tokyo, Japan?",
        },
    )

    assert result.status == "needs_confirmation"
    assert result.corrected_country == "Japan"
    assert result.corrected_city == "Tokyo"


def test_custom_city_validation_from_model_response_defaults_valid_fields_and_message() -> None:
    result = custom_city_validation_from_model_response(
        "China",
        "Jining",
        {
            "status": "\u4f4d\u7f6e\u9a8c\u8bc1\u6210\u529f\u3002",
            "message": "",
        },
        language="zh-CN",
    )

    assert result.status == "valid"
    assert result.corrected_country == "China"
    assert result.corrected_city == "Jining"
    assert result.message


def test_custom_city_validation_from_dict_normalizes_stored_payload() -> None:
    result = custom_city_validation_from_dict(
        {
            "input_country": "United States",
            "input_city": "Springfield",
            "status": "ambiguous",
            "corrected_country": "",
            "corrected_city": "Springfield",
            "country_code": "",
            "matching_countries": ["United States", "", "Canada"],
            "message": "Confirm country.",
        }
    )

    assert result.status == "needs_confirmation"
    assert result.country_code is None
    assert result.matching_countries == ["United States", "Canada"]


def test_custom_city_validation_normalizers() -> None:
    assert unique_strings([" A ", "A", "", "B"]) == ["A", "B"]
    assert normalize_custom_city_status("\u4f4d\u7f6e\u6709\u6548") == "valid"
    assert normalize_custom_city_status("not valid") == "low_confidence"
    assert normalize_country_code(" cn ") == "CN"
    assert normalize_country_code("") is None
    assert normalize_location_key("Guangdong Province") == "guangdong"
