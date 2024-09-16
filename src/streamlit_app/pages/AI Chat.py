import os
import time
from base64 import b64decode, b64encode

import streamlit as st
from logzero import logger
from simplesingletable import DynamoDbMemory

from supersullytools.llm.agent import ChatAgent
from supersullytools.llm.agent_tools.duckduckgo import get_ddg_tools
from supersullytools.llm.completions import CompletionHandler, ImagePromptMessage
from supersullytools.llm.trackers import CompletionTracker, DailyUsageTracking, GlobalUsageTracker
from supersullytools.streamlit.chat_agent_utils import ChatAgentUtils


@st.cache_resource
def get_memory() -> DynamoDbMemory:
    return DynamoDbMemory(logger=logger, table_name=os.environ.get("DYNAMODB_TABLE"))


@st.cache_resource
def get_completion_handler() -> CompletionHandler:
    memory = get_memory()
    trackers = get_trackers()
    completion_tracker = CompletionTracker(memory=memory, trackers=list(trackers))
    return CompletionHandler(
        logger=logger, debug_output_prompt_and_response=False, completion_tracker=completion_tracker
    )


def get_trackers() -> tuple[GlobalUsageTracker, DailyUsageTracking]:
    memory = get_memory()
    global_tracker = GlobalUsageTracker.ensure_exists(memory)
    todays_tracker = DailyUsageTracking.get_for_today(memory)
    return (global_tracker, todays_tracker)


@st.cache_resource
def get_agent() -> ChatAgent:
    tool_profiles = {"all": [] + get_ddg_tools()}
    return ChatAgent(
        agent_description="You are a helpful assistant.",
        logger=logger,
        completion_handler=get_completion_handler(),
        tool_profiles=tool_profiles,
    )


def main():
    with st.sidebar:
        model = ChatAgentUtils.select_llm(get_completion_handler(), label="LLM to use")
    st.title("AI Chat Agent Testing")

    def _agent():
        agent = get_agent()
        agent.default_completion_model = model
        return agent

    agent = _agent()
    agent_utils = ChatAgentUtils(agent)
    _ = agent_utils

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
        include_function_calls = st.sidebar.toggle("Show function calls")

    num_chat_before = len(agent.get_chat_history(include_function_calls=include_function_calls))

    for msg in agent.get_chat_history(include_function_calls=include_function_calls):
        with st.chat_message(msg.role):
            if msg.role == "system":
                with st.popover("__system msg__"):
                    st.write(msg.content)
            else:
                if isinstance(msg, ImagePromptMessage):
                    main, images = st.columns((90, 10))
                    main.write(msg.content)
                    for x in msg.images:
                        images.image(b64decode(x.encode()))
                else:
                    st.write(msg.content)

    if agent.working:
        with st.spinner("Agent working..."):
            while agent.working:
                agent.run_agent()
                time.sleep(0.05)

    # output any new messages
    for msg in agent.get_chat_history(include_function_calls=include_function_calls)[num_chat_before:]:
        with st.chat_message(msg.role):
            st.write(msg.content)

    if chat_msg:
        if st.session_state.upload_images:
            prompt = ImagePromptMessage(
                content=chat_msg,
                images=[b64encode(image.getvalue()).decode() for image in st.session_state.upload_images],
                image_formats=[
                    "png" if image.name.endswith("png") else "jpeg" for image in st.session_state.upload_images
                ],
            )
        else:
            prompt = chat_msg
        agent.message_from_user(prompt)
        st.session_state.uploaded_images = st.session_state.upload_images
        st.session_state.upload_images = []

        time.sleep(0.01)
        st.rerun()

    global_tracker, daily_tracker = get_trackers()
    with st.sidebar.container():
        st.subheader("Total Usage")
        global_tracker.render_completion_cost_as_expander()
        st.subheader("Daily Usage")
        daily_tracker.render_completion_cost_as_expander()


if __name__ == "__main__":
    main()
