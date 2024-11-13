from typing import Optional

import streamlit as st
from logzero import logger
from simplesingletable import PaginatedList

from supersullytools.llm.agent import ChatAgent
from supersullytools.llm.agent_tools.duckduckgo import get_ddg_tools
from supersullytools.llm.trackers import SessionUsageTracking, StoredPromptAndResponse
from supersullytools.streamlit.chat_agent_utils import display_completion
from supersullytools.streamlit.paginator import item_paginator
from supersullytools.utils.common_init import (
    get_standard_completion_dynamodb_memory,
    get_standard_completion_handler,
    get_standard_completion_media_manager,
)
from supersullytools.utils.misc import now_with_dt

st.set_page_config(layout="wide", initial_sidebar_state="collapsed")


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
            include_session_tracker=False, extra_trackers=[get_session_usage_tracker()]
        ),
        tool_profiles=tool_profiles,
    )


@st.cache_data(persist=True)
def get_completions(
    pagination_key: Optional[str] = None, num_result: int = 25
) -> PaginatedList[StoredPromptAndResponse]:
    return get_standard_completion_dynamodb_memory().list_type_by_updated_at(
        StoredPromptAndResponse, results_limit=num_result, pagination_key=pagination_key
    )


def get_most_recent():
    return get_standard_completion_dynamodb_memory().list_type_by_updated_at(StoredPromptAndResponse, results_limit=1)


def main():
    get_standard_completion_dynamodb_memory()
    agent = get_agent()
    now = now_with_dt()

    completions = get_completions()

    if st.button("Check for new"):
        if get_most_recent()[0].resource_id != completions[0].resource_id:
            st.info("Newer completions available; reloading data")
            get_completions.clear()
            completions = get_completions()
        else:
            st.info("No new completions available")

    def _display(idx):
        this_completion = completions[idx]
        st.write(this_completion.resource_id)
        st.write(this_completion.source_tag)
        display_completion(this_completion, now, media_manager=get_standard_completion_media_manager())

    item_paginator(
        "Completion",
        [(f"{x.source_tag}: " if x.source_tag else "") + x.prompt[-1].content[:25] for x in completions],
        item_handler_fn=_display,
        enable_keypress_nav=True,
        display_item_names=True,
    )

    with st.sidebar.container(border=True):
        for tracker in agent.completion_handler.completion_tracker.trackers:
            st.subheader(tracker.__class__.__name__)
            tracker.render_completion_cost_as_expander()


if __name__ == "__main__":
    main()
