from __future__ import annotations

from dataclasses import dataclass

import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

from src.i18n import t

_SIDEBAR_NAV_ITEMS = (
    ("app.py", "nav.home"),
    ("pages/1_Overview.py", "overview.page_title"),
    ("pages/2_Spatiotemporal_Playback.py", "playback.page_title"),
    ("pages/3_Correlation_Analysis.py", "correlation.page_title"),
    ("pages/4_Historical_Data_Agent.py", "agent.page_title"),
)


@dataclass(frozen=True, slots=True)
class SidebarNavItem:
    path: str
    label: str


def sidebar_navigation_items(language: str) -> list[SidebarNavItem]:
    return [SidebarNavItem(path=path, label=t(key, language)) for path, key in _SIDEBAR_NAV_ITEMS]


def _can_render_page_links() -> bool:
    ctx = get_script_run_ctx()
    if ctx is None:
        return True

    pages = ctx.pages_manager.get_pages()
    if not pages:
        return False

    return all("url_pathname" in page_data for page_data in pages.values())


def render_sidebar_navigation(language: str) -> None:
    if not _can_render_page_links():
        return

    for item in sidebar_navigation_items(language):
        st.page_link(item.path, label=item.label)
