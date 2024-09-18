# streamlit helpers for ChatAgent
import time
from base64 import b64decode, b64encode
from typing import Callable, Optional

import streamlit as st
from pydantic import BaseModel
from streamlit.runtime.uploaded_file_manager import UploadedFile

from supersullytools.llm.agent import ChatAgent
from supersullytools.llm.completions import CompletionHandler, CompletionModel, ImagePromptMessage


class SlashCmd(BaseModel):
    name: str
    description: str
    mechanism: Callable
    refresh_after: bool = False


class ChatAgentUtils(object):
    def __init__(
        self,
        chat_agent: ChatAgent,
        use_system_slash_cmds: bool = True,
        extra_slash_cmds: Optional[dict[str, SlashCmd]] = None,
    ):
        self.chat_agent = chat_agent
        self.use_system_slash_cmds = use_system_slash_cmds
        self._system_slash_cmds = {}
        if self.use_system_slash_cmds:
            self._system_slash_cmds = {
                "/help": SlashCmd(
                    name="Help",
                    description="Display available commands",
                    mechanism=self._display_slash_help,
                    refresh_after=False,
                ),
                "/clear": SlashCmd(
                    name="Clear Chat",
                    description="Clear current chat history",
                    mechanism=self.chat_agent.reset_history,
                    refresh_after=True,
                ),
            }
        self.extra_slash_cmds = extra_slash_cmds

    def _display_slash_help(self):
        output = "### Available Commands\n\n"
        for slash_cmd, obj in self._system_slash_cmds.items():
            obj: SlashCmd
            output += f"* **{obj.name}** (`{slash_cmd}`): {obj.description}\n"
        return output

    def get_completion_model(self, model: Optional[str | CompletionModel] = None) -> CompletionModel:
        if isinstance(model, CompletionModel):
            return model
        return self.chat_agent.completion_handler.get_model_by_name_or_id(model)

    @staticmethod
    def select_llm(
        completion_handler: CompletionHandler, label, default: str = "GPT 4 Omni Mini", key=None, **kwargs
    ) -> CompletionModel:
        completion_handler = completion_handler
        default_model = completion_handler.get_model_by_name_or_id(default)
        return st.selectbox(
            label,
            completion_handler.available_models,
            completion_handler.available_models.index(default_model),
            format_func=lambda x: x.llm,
            key=key,
            **kwargs,
        )

    def select_llm_from_agent(
        self, label, default_override: Optional[str] = None, key=None, **kwargs
    ) -> CompletionModel:
        default_model = (
            self.chat_agent.completion_handler.get_model_by_name_or_id(default_override)
            if default_override
            else self.chat_agent.default_completion_model
        )
        return self.select_llm(
            completion_handler=self.chat_agent.completion_handler,
            label=label,
            default=default_model.llm,
            key=key,
            **kwargs,
        )

    def display_chat_msg(self, msg: str):
        if "<tool>" in msg:
            content, _ = msg.split("<tool>", maxsplit=1)
            content = content.strip()
            tool_calls = self.chat_agent.extract_tool_calls_from_msg(msg)
            if content:
                st.write(content)
            for tc in tool_calls:
                if params := tc.get("parameters"):
                    with st.popover(tc["name"]):
                        st.write(params)
                else:
                    st.caption(f"used `{tc['name']}`")
        elif "<tool_result>" in msg:
            _, result_str = msg.split("<tool_result>", maxsplit=1)
            tool_result_str = [
                this_result_str.split("</tool_result>", maxsplit=1)[0]
                for this_result_str in result_str.split("<tool_result>")
            ]
            tool_results = [x.strip() for x in tool_result_str]
            st.json(tool_results, expanded=0)

        else:
            st.write(msg)

    def _try_handle_system_slash_command(self, command_str: str) -> Optional[tuple[SlashCmd, str]]:
        if command_str in self._system_slash_cmds:
            command: SlashCmd = self._system_slash_cmds[command_str]
            output = command.mechanism()
            if output:
                with st.chat_message("system").container(border=True):
                    st.write(output)
            return command, output

    def _try_handle_extra_slash_cmd(self, command_str: str) -> Optional[tuple[SlashCmd, str]]:
        if command_str in self.extra_slash_cmds:
            command: SlashCmd = self.extra_slash_cmds[command_str]
            output = command.mechanism()
            if output:
                with st.chat_message("system").container(border=True):
                    st.write(output)
            return command, output

    def add_user_message(self, msg: str, images: Optional[list[UploadedFile]] = None) -> bool:
        """Returns true if the streamlit app should reload."""
        if msg.startswith("/"):
            if not self.use_system_slash_cmds or self.extra_slash_cmds:
                raise RuntimeError("No slash commands available!")
            executed_command = None
            if self.use_system_slash_cmds:
                result = self._try_handle_system_slash_command(msg)
                if result:
                    executed_command, _ = result
            if not executed_command and self.extra_slash_cmds:
                result = self._try_handle_extra_slash_cmd(msg)
                if result:
                    executed_command, _ = result
            if not executed_command:
                executed_command, _ = self._try_handle_system_slash_command("/help")
            return executed_command.refresh_after
        else:
            if images:
                prompt = ImagePromptMessage(
                    content=msg,
                    images=[b64encode(image.getvalue()).decode() for image in images],
                    image_formats=["png" if image.name.endswith("png") else "jpeg" for image in images],  # noqa
                )
            else:
                prompt = msg
            self.chat_agent.message_from_user(prompt)
            return True

    def display_chat_and_run_agent(self, include_function_calls):
        num_chat_before = len(self.chat_agent.get_chat_history(include_function_calls=include_function_calls))

        for msg in self.chat_agent.get_chat_history(include_function_calls=include_function_calls):
            with st.chat_message(msg.role):
                if isinstance(msg, ImagePromptMessage):
                    main, images = st.columns((90, 10))
                    with main:
                        self.display_chat_msg(msg.content)
                    for x in msg.images:
                        images.image(b64decode(x.encode()))
                else:
                    self.display_chat_msg(msg.content)

        if self.chat_agent.working:
            with st.spinner("Agent working..."):
                while self.chat_agent.working:
                    self.chat_agent.run_agent()
                    time.sleep(0.05)

        # output any new messages
        for msg in self.chat_agent.get_chat_history(include_function_calls=include_function_calls)[num_chat_before:]:
            with st.chat_message(msg.role):
                self.display_chat_msg(msg.content)
