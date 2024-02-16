"""Demo page for session manager, sessions, and ChatSession / basic pydantic tools."""

import json
from typing import Optional

import streamlit as st
from logzero import logger
from openai.types.chat import ChatCompletion
from pydantic import Field

from supersullytools.openai.chat_session import ChatSession, ChatTool
from supersullytools.streamlit.sessions import InMemorySessionManager, StreamlitSessionBase

st.set_page_config("AI Chat - respond with suggestions")


class AiChatAppSession(StreamlitSessionBase):
    chat_history: list[dict] = Field(default_factory=list)
    last_ai_response: Optional[ChatCompletion] = None


class RespondWithSuggestions(ChatTool):
    """Respond to the user, also providing 3 suggestions for them to continue the conversation with you"""

    response: str
    suggestions: list[str]


@st.cache_resource()
def setup_session_manager() -> InMemorySessionManager:
    return InMemorySessionManager(model_type=AiChatAppSession, logger=logger, memory={})


def main():
    session_manager = setup_session_manager()
    user_session: AiChatAppSession = session_manager.init_session()

    with st.form("load previous session"):
        load_session_id = st.selectbox(
            "Load Session", sorted(session_manager.session_store.keys(), reverse=True), index=None
        )
        if st.form_submit_button("Load"):
            if not load_session_id:
                st.error("Select session")
            else:
                session_manager.switch_session(load_session_id)
                st.rerun()
    if user_session.chat_history:
        st.subheader(f"Chat Session {user_session.session_id}")

        def _close():
            session_manager.clear_session_data()

        st.button("Close Session", use_container_width=True, on_click=_close)

    for msg in user_session.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    def user_says(msg: str):
        cs = ChatSession(history=user_session.chat_history)
        cs.user_says(msg)
        user_session.chat_history = cs.history

    def ai_responds():
        cs = ChatSession(history=user_session.chat_history, default_tools=[RespondWithSuggestions])
        response = cs.get_ai_response(force_tool=True)
        user_session.last_ai_response = response

        function_call_args = json.loads(response.choices[0].message.function_call.arguments)
        content = function_call_args["response"]
        st.write(content)
        cs.assistant_says(content)
        user_session.chat_history = cs.history
        session_manager.persist_session(user_session)

    if user_session.chat_history and user_session.chat_history[-1]["role"] != "assistant":
        with st.chat_message("ai"):
            with st.spinner("Generating response"):
                ai_responds()

    with st.chat_message("user"):
        selection = None
        if user_session.last_ai_response:
            fc_args = json.loads(user_session.last_ai_response.choices[0].message.function_call.arguments)
            suggestions = fc_args["suggestions"]
            selection = st.radio("Use Suggested Response", suggestions, index=None, label_visibility="collapsed")
            # st.write(last_ai_response.choices[0].message.function_call)

        new_input = selection or st.chat_input()

        if new_input:
            user_says(new_input)
            session_manager.persist_session(user_session)
            st.rerun()


if __name__ == "__main__":
    main()
