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


def flash_message_after_reload(
    msg: str, toast=False, flash_msgs_session_key="flash_msgs", flash_toasts_session_session_key="flash_toast"
):
    key = flash_toasts_session_session_key if toast else flash_msgs_session_key
    if key not in st.session_state:
        st.session_state[key] = [msg]
    else:
        st.session_state[key].append(msg)


def display_flash_msgs(
    flash_msgs_session_key="flash_msgs", flash_toasts_session_session_key="flash_toast", container=None
):
    if flash_msgs := st.session_state.get(flash_msgs_session_key):
        for msg in flash_msgs:
            if container:
                with container:
                    st.write(msg)
            else:
                st.write(msg)
        st.session_state[flash_msgs_session_key] = []
    if toast_msgs := st.session_state.get(flash_toasts_session_session_key):
        for msg in toast_msgs:
            st.toast(msg)
        st.session_state[flash_toasts_session_session_key] = []
