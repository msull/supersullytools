import time

import streamlit as st
from logzero import logger

from supersullytools.llm.agent import ChatAgent
from supersullytools.llm.agent_tools.duckduckgo import get_ddg_tools
from supersullytools.llm.trackers import SessionUsageTracking, TopicUsageTracking
from supersullytools.streamlit.chat_agent_utils import ChatAgentUtils
from supersullytools.utils.common_init import get_standard_completion_handler


@st.cache_resource
def get_session_usage_tracker() -> SessionUsageTracking:
    return SessionUsageTracking()


@st.cache_resource
def get_agent() -> ChatAgent:
    tool_profiles = {"all": [] + get_ddg_tools()}
    return ChatAgent(
        agent_description="You are a helpful assistant.",
        logger=logger,
        completion_handler=get_standard_completion_handler(
            include_session_tracker=False,
            extra_trackers=[get_session_usage_tracker()],
            store_source_tag="supersullytools",
            topics=["AIChat"],
        ),
        tool_profiles=tool_profiles,
    )


def main():
    with st.sidebar:
        model = ChatAgentUtils.select_llm(get_standard_completion_handler(), label="LLM to use")
    st.title("AI Chat Agent Testing")

    def _agent():
        agent = get_agent()
        agent.default_completion_model = model
        return agent

    agent = _agent()
    agent_utils = ChatAgentUtils(agent)

    agent.completion_handler.completion_tracker.fixup_trackers()

    if "image_key" not in st.session_state:
        st.session_state.image_key = 1
        st.session_state.upload_images = []

    image = st.sidebar.file_uploader("Image", type=["png", "jpg"], key=f"image-upload-{st.session_state.image_key}")
    if image and st.sidebar.button("Add image to msg"):
        st.session_state.image_key += 1
        st.session_state.upload_images.append(image)
        time.sleep(0.01)
        st.rerun()

    if st.session_state.upload_images:
        with st.sidebar.expander("Pending Images", expanded=True):
            for image in st.session_state.upload_images:
                st.image(image)

    chat_msg = st.chat_input()

    with st.sidebar.expander("Chat Config", expanded=True):
        include_function_calls = st.sidebar.toggle("Show function calls", True)

    agent_utils.display_chat_and_run_agent(include_function_calls)

    if chat_msg:
        if agent_utils.add_user_message(chat_msg, st.session_state.upload_images):
            if st.session_state.upload_images:
                # clearing out the upload_images immediately causes weird IO errors, so
                # just push to another key and overwrite it later
                st.session_state.uploaded_images = st.session_state.upload_images
                st.session_state.upload_images = []
            time.sleep(0.01)
            st.rerun()

    with st.sidebar.container(border=True):
        for tracker in _agent().completion_handler.completion_tracker.trackers:
            if isinstance(tracker, TopicUsageTracking):
                continue
            st.subheader(tracker.__class__.__name__)
            tracker.render_completion_cost_as_expander()


if __name__ == "__main__":
    main()
