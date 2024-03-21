from typing import Sequence

import streamlit as st


def check_or_x(value: bool) -> str:
    return "✅" if value else "❌"


def resettable_tabs(name: str, tabs=Sequence[str], session_key_prefix: str = "resettable_tabs_") -> str:
    key = f"{session_key_prefix}{name}"
    for x in range(st.session_state.get(key, 0)):
        st.empty()
    return st.tabs(tabs)


def reset_tab_group(name: str, session_key_prefix: str = "resettable_tabs_"):
    key = f"{session_key_prefix}{name}"
    current = st.session_state.get(key, 0)
    st.session_state[key] = current + 1
