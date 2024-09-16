# streamlit helpers for ChatAgent
from typing import Optional

import streamlit as st

from supersullytools.llm.agent import ChatAgent
from supersullytools.llm.completions import CompletionHandler, CompletionModel


class ChatAgentUtils(object):
    def __init__(self, chat_agent: ChatAgent):
        self.chat_agent = chat_agent

    def get_completion_model(self, model: Optional[str | CompletionModel] = None) -> CompletionModel:
        if isinstance(model, CompletionModel):
            return model
        return self.chat_agent.completion_handler.get_model_by_name_or_id(model)

    @staticmethod
    def select_llm(
        completion_handler: CompletionHandler,
        label,
        default: str = "GPT 4 Omni Mini",
        key=None,
    ) -> CompletionModel:
        completion_handler = completion_handler
        default_model = completion_handler.get_model_by_name_or_id(default)
        return st.selectbox(
            label,
            completion_handler.available_models,
            completion_handler.available_models.index(default_model),
            format_func=lambda x: x.llm,
            key=key,
            label_visibility="collapsed",
        )
