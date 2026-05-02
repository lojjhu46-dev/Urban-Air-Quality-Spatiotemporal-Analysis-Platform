from __future__ import annotations

from src.navigation import sidebar_navigation_items


def test_sidebar_navigation_items_are_localized() -> None:
    zh_items = sidebar_navigation_items("zh-CN")
    en_items = sidebar_navigation_items("en")

    assert [item.label for item in zh_items] == [
        "\u9996\u9875",
        "\u603b\u89c8",
        "\u65f6\u7a7a\u56de\u653e",
        "\u76f8\u5173\u6027\u5206\u6790",
        "\u5386\u53f2\u6570\u636e Agent",
    ]
    assert [item.label for item in en_items] == [
        "Home",
        "Overview",
        "Spatiotemporal Playback",
        "Correlation Analysis",
        "Historical Data Agent",
    ]
