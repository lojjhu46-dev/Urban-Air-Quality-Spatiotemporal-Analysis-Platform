from __future__ import annotations

from src.i18n import DEFAULT_LANGUAGE, LANGUAGE_OPTIONS, api_language, language_label, normalize_language, weather_label


def test_normalize_language_falls_back_to_default() -> None:
    assert normalize_language("zh-CN") == "zh-CN"
    assert normalize_language("en") == "en"
    assert normalize_language("fr") == DEFAULT_LANGUAGE
    assert normalize_language(None) == DEFAULT_LANGUAGE


def test_language_label_matches_supported_options() -> None:
    for key, label in LANGUAGE_OPTIONS.items():
        assert language_label(key) == label


def test_api_language_matches_supported_options() -> None:
    assert api_language("zh-CN") == "zh"
    assert api_language("en") == "en"


def test_weather_label_uses_translation_keys() -> None:
    assert weather_label("temp", "en") == "Temperature"
    assert weather_label("humidity", "zh-CN")
