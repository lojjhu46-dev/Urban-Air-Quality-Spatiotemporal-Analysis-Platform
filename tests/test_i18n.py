from __future__ import annotations

from src.i18n import DEFAULT_LANGUAGE, LANGUAGE_OPTIONS, api_language, language_label, normalize_language, t, weather_label


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


def test_custom_city_agent_labels_are_bilingual() -> None:
    assert t("agent.custom_city_option", "zh-CN") == "\u81ea\u5b9a\u4e49\u67e5\u8be2"
    assert t("agent.custom_city_option", "en") == "Custom search"
    assert t("agent.custom_city_country", "zh-CN") == "\u56fd\u5bb6 / \u5730\u533a"
    assert t("agent.custom_city_name", "en") == "City name"
    assert "\u6b63\u5728\u542f\u52a8 Agent" in t("agent.custom_city_validated_starting_agent", "zh-CN")
    assert "did not continue with planning or collection tools" in t("agent.tool_no_progress_after_validation", "en")
    assert "Task status storage" in t("agent.task_store_backend", "en", backend="Supabase Postgres")
    assert "\u672c\u5730\u5185\u5b58" in t("agent.task_store_memory", "zh-CN")
    assert "Collection plan is ready" in t("agent.task_plan_ready", "en")


def test_weather_label_uses_translation_keys() -> None:
    assert weather_label("temp", "en") == "Temperature"
    assert weather_label("humidity", "zh-CN")
