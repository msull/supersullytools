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


# Simplified CSS for the fixed container
FIXED_CONTAINER_CSS = """
div[data-testid="stVerticalBlockBorderWrapper"]:has(div.fixed-container-simple_fixed_container):not(:has(div.not-fixed-container)){
    background-color: transparent;
    position: fixed;
    width: inherit;
    background-color: inherit;
    top: 100;
    z-index: 999;
}

div[data-testid="stVerticalBlockBorderWrapper"]:has(div.fixed-container-simple_fixed_container):not(:has(div.not-fixed-container)) div[data-testid="stVerticalBlock"]:has(div.fixed-container-simple_fixed_container):not(:has(div.not-fixed-container)) > div[data-testid="element-container"] {
    display: none;
}

div[data-testid="stVerticalBlockBorderWrapper"]:has(div.not-fixed-container):not(:has(div[class^='fixed-container-'])) {
    display: none;
}
""".strip()


def simple_fixed_container():
    key = "simple_fixed_container"
    fixed_container = st.container()
    non_fixed_container = st.container()

    css = FIXED_CONTAINER_CSS
    with fixed_container:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
        st.markdown(f"<div class='fixed-container-{key}'></div>", unsafe_allow_html=True)
    with non_fixed_container:
        st.markdown("<div class='not-fixed-container'></div>", unsafe_allow_html=True)

    with fixed_container:
        return st.container(border=False)
