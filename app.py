from __future__ import annotations

import streamlit as st

from src.i18n import get_language, render_language_selector, t
from src.ui import dataset_path_from_env

language = get_language()
st.set_page_config(page_title=t("app.page_title", language), layout="wide")

active_dataset_path = dataset_path_from_env()

header_left, header_right = st.columns((5, 1.4))
with header_right:
    language = render_language_selector()

header_left.title(t("app.title", language))
header_left.caption(t("app.caption", language))

st.markdown(t("app.body", language))
st.info(t("app.active_dataset", language, path=active_dataset_path))
st.caption(t("app.agent_hint", language))
