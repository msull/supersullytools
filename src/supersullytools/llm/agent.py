import datetime
import json
from contextlib import suppress
from enum import Enum, auto
from logging import Logger
from typing import Any, Callable, Literal, Optional, Type, TypeVar

import jsonref
import pytz
from pydantic import BaseModel, computed_field

from supersullytools.llm.completions import (
    CompletionHandler,
    CompletionModel,
    CompletionResponse,
    ImagePromptMessage,
    PromptMessage,
)

PydanticModel = TypeVar("PydanticModel", bound=BaseModel)


class NoParams(BaseModel):
    pass


class AgentTool(BaseModel):
    name: str
    description: Optional[str] = None
    params_model: Type[PydanticModel]
    mechanism: Callable[[PydanticModel], dict | list | str | PydanticModel]
    safe_tool: bool = False

    def invoke_tool(self, params_dict: dict) -> str:
        params = self.params_model.model_validate(params_dict)
        result = self.mechanism(params)
        match result:
            case BaseModel():
                return result.model_dump_json()
            case str():
                return result
            case _:
                return json.dumps(result, default=str)


class StrEnum(str, Enum):
    @staticmethod
    def _generate_next_value_(name: str, start: int, count: int, last_values: list[Any]) -> Any:
        return name


class AgentStates(StrEnum):
    initializing = auto()
    ready_for_message = auto()
    received_message = auto()
    pending_tool_use = auto()
    awaiting_tool_approval = auto()
    using_tools = auto()
    error = auto()


class ToolUseModes(StrEnum):
    manual = auto()  # all tools require manual approval
    automatic_safe_only = auto()  # tools marked "safe" will be automatically called, others require approval
    automatic_unsafe = auto()  # all tools will be automatically called


_CT = TypeVar("_CT", bound=AgentTool)


class ToolAndParams(BaseModel):
    label: str
    tool: _CT
    params: dict

    @computed_field
    @property
    def tool_name(self) -> str:
        return self.tool.name

    def invoke_tool(self) -> str:
        return self.tool.invoke_tool(self.params)

    def validate_params(self) -> PydanticModel:
        return self.tool.params_model.model_validate(self.params)


class MsgVerificationError(RuntimeError):
    def __init__(self, error_msgs: list[str]):
        self.error_msgs = error_msgs


class ChatAgent(object):
    def __init__(
        self,
        agent_description: str,
        logger: Logger,
        completion_handler: CompletionHandler,
        default_completion_model: CompletionModel | str = "GPT 4 Omni Mini",
        tool_profiles: dict[str, list[_CT]] = None,
        initial_tool_profile: Optional[str] = None,
        tool_use_mode: ToolUseModes = ToolUseModes.automatic_safe_only,
        local_timezone_str="America/Los_Angeles",
        user_preferences: Optional[list[str]] = None,
        initial_llm_context: Optional[
            dict
        ] = None,  # copy initial context from here; modify with add_to_context/remove_from_context
        # names of tools to run during the init process; must work with all default parameters
        init_tools_to_use: Optional[list[str]] = None,
        default_max_response_tokens: int = 1000,
    ):
        self.agent_description = agent_description
        self.logger = logger
        self.completion_handler = completion_handler
        self._tool_profiles = (tool_profiles or {}).copy()
        self.tool_use_mode = tool_use_mode
        if initial_tool_profile:
            self.active_tool_profile = initial_tool_profile
        else:
            if self._tool_profiles:
                self.active_tool_profile = next(iter(self._tool_profiles.keys()))
            else:
                self.active_tool_profile = None

        # default completion model
        if isinstance(default_completion_model, CompletionModel):
            self.default_completion_model = default_completion_model
        else:
            self.default_completion_model = self.completion_handler.get_model_by_name_or_id(default_completion_model)

        self.pending_tool_calls = None
        self.approved_tool_calls = None
        self.applied_tool_calls = None
        self.applied_tool_call_results = None
        self.chat_history: list[PromptMessage | ImagePromptMessage] = []
        self.reset_history()
        self.current_state = AgentStates.ready_for_message
        self.local_timezone = pytz.timezone(local_timezone_str)

        self._status_msg = "Initialization Complete"
        self._user_preferences = [x for x in user_preferences] if user_preferences else []
        self._llm_context = {**initial_llm_context} if initial_llm_context else {}
        self.default_max_response_tokens = default_max_response_tokens

        for tool_name in init_tools_to_use or []:
            self.manually_invoke_tool(tool_name, {}, force_pass=True)
            self.run_agent()
            self._add_chat_msg("PASS", role="assistant")
            self.current_state = AgentStates.ready_for_message

        self._chat_start_idx = len(self.chat_history)

    def add_tool_to_active_profile(self, tool: AgentTool):
        try:
            self.get_current_tool_by_name(tool.name)
        except ValueError:
            self._tool_profiles[self.active_tool_profile].append(tool)

    def replace_user_preferences(self, new_preferences: list[str]):
        self._user_preferences = [x for x in new_preferences] if new_preferences else []

    def add_to_context(self, key, value):
        self._llm_context[key] = value

    def remove_from_context(self, key):
        with suppress(KeyError):
            self._llm_context.pop(key)

    def get_current_status_msg(self):
        return self._status_msg

    def get_chat_history(
        self, include_system_messages: bool = False, include_function_calls: bool = False
    ) -> list[PromptMessage | ImagePromptMessage]:
        messages = [x.copy() for x in self.chat_history[self._chat_start_idx :]]

        def ai_system_msg(x: PromptMessage):
            if not x.role == "assistant":
                return False
            return x.content in ["CONTINUE", "PASS"]

        if not include_system_messages:
            if include_function_calls:
                # leave tool call results in place
                messages = [
                    x
                    for x in messages
                    if (not x.role == "system" and not ai_system_msg(x)) or "<tool_result>" in x.content
                ]
            else:
                messages = [x for x in messages if not x.role == "system" and not ai_system_msg(x)]
        if not include_function_calls:
            for idx, msg in enumerate(messages):
                msg.content = msg.content.split("<tool>", maxsplit=1)[0]
                messages[idx] = msg
        return messages

    @property
    def working(self) -> bool:
        match self.current_state:
            case AgentStates.ready_for_message:
                return False
            case AgentStates.awaiting_tool_approval:
                return False
            case AgentStates.error:
                return False
            case _:
                return True

    def reset_history(self):
        self.pending_tool_calls = []
        self.approved_tool_calls = []
        self.applied_tool_calls = []
        self.applied_tool_call_results = []
        self.chat_history: list[PromptMessage | ImagePromptMessage] = []

    def run_agent(
        self, max_response_tokens: Optional[int] = None, override_model: Optional[CompletionModel | str] = None
    ):
        # run this in a loop
        max_response_tokens = max_response_tokens or self.default_max_response_tokens

        current_state = self.current_state
        self.logger.debug(f"Running agent {current_state=}")
        match self.current_state:
            case AgentStates.ready_for_message:
                self._status_msg = "Waiting for user message"
            case AgentStates.received_message:
                if self.chat_history[-1].role != "assistant":
                    self._status_msg = "Agent is generating a message"
                    response = self._generate_response(
                        max_response_tokens=max_response_tokens, override_model=override_model
                    )
                    if response:
                        if "<tool>" in response:
                            self._status_msg = "Preparing for tool use"
                            self.current_state = AgentStates.pending_tool_use
                        else:
                            self.current_state = AgentStates.ready_for_message
                        self._add_chat_msg(msg=response, role="assistant")
                else:
                    self.current_state = AgentStates.error
                    self._status_msg = "Invalid state -- received_message but last msg in chat_history is from ai!"
            case AgentStates.pending_tool_use:
                self.logger.info("Tool use pending, checking if tool approval is required ")
                pending_tools = self.get_pending_tool_calls()
                if not pending_tools:
                    self.logger.info("No tool use pending, returning ready_for_message state")
                    self.current_state = AgentStates.ready_for_message
                    return self.run_agent()
                match self.tool_use_mode:
                    case ToolUseModes.manual:
                        self.logger.info("Manual mode, approval required for all tools")
                        self.current_state = AgentStates.awaiting_tool_approval
                    case ToolUseModes.automatic_safe_only:
                        self.logger.info('Automatic "safe" tool usage mode, checking for unsafe tools')
                        any_unsafe_tools = False
                        for pending_tool in pending_tools:
                            if not pending_tool.tool.safe_tool:
                                any_unsafe_tools = True
                        if any_unsafe_tools:
                            self.logger.info("Tools include unsafe tool, approval required")
                            self.current_state = AgentStates.awaiting_tool_approval
                        else:
                            self.logger.info("Tools do not include unsafe tool usage, no approval required")
                            self.current_state = AgentStates.using_tools
                    case ToolUseModes.automatic_unsafe:
                        self.logger.info("Operating in automatic_unsafe mode; all tool usage approved")
                        self.current_state = AgentStates.using_tools
                    case _:
                        raise ValueError(self.tool_use_mode)
            case AgentStates.awaiting_tool_approval:
                self._status_msg = "Waiting for tool approval"
            case AgentStates.using_tools:
                self.logger.info("Using tools!")
                self._status_msg = "Beginning tool use"
                tools_and_results = []
                for idx, pending_tool in enumerate(self.get_pending_tool_calls()):
                    self._status_msg = f'Using Tool "{pending_tool.tool.name}"'
                    result = self._handle_tool_usage(pending_tool)
                    self.applied_tool_calls.append(pending_tool)
                    self.applied_tool_call_results.append(result)
                    tools_and_results.append((pending_tool, result))

                msg = "Tool use complete\n"
                for tool, result in tools_and_results:
                    msg += f"<tool_used>{tool.tool_name}</tool_used>\n<tool_result>\n{result}\n</tool_result>\n"

                msg += (
                    "You may now use more tools or respond to the user. "
                    "Do not send the tool_result directly; provide relevant information."
                )
                self._add_chat_msg(msg, role="system")

                self.logger.info("Tool use completed, sending results to Agent")
                self.current_state = AgentStates.received_message
                self._status_msg = "Ready to handle tool results"
            case AgentStates.initializing:
                pass
            case _:
                raise ValueError(self.current_state)

    def _handle_tool_usage(self, tool_to_use: ToolAndParams) -> str:
        try:
            return tool_to_use.invoke_tool()
        except Exception as e:
            self.logger.warning("Caught exception using tool, providing error to Agent", exc_info=True)
            return "TOOL FAILED!\n" + str(e)

    def get_current_tool_by_name(self, tool_name: str) -> _CT:
        try:
            return next(x for x in self.get_current_tools() if x.name == tool_name)
        except StopIteration:
            raise ValueError(tool_name)

    def message_from_user(self, msg: str | PromptMessage | ImagePromptMessage):
        if not self.current_state == AgentStates.ready_for_message:
            raise RuntimeError("Cannot accept messages at this time")

        is_prompt_message = False
        if isinstance(msg, (PromptMessage, ImagePromptMessage)):
            is_prompt_message = True
            if not msg.role == "user":
                raise RuntimeError("Role must be user")

        self.logger.info("Agent received message")
        self.current_state = AgentStates.received_message
        if is_prompt_message:
            self._append_chat(msg)
        else:
            self._add_chat_msg(msg, role="user")

    def _append_chat(self, msg: PromptMessage | ImagePromptMessage):
        self.chat_history.append(msg)

    def _add_chat_msg(self, msg: str, role: Literal["system", "user", "assistant"] = "user"):
        self._append_chat(PromptMessage(role=role, content=msg))

    def force_add_chat_msg(self, msg: str, role: Literal["system", "user", "assistant"]):
        self._add_chat_msg(msg, role)

    def get_current_tools(self) -> list[_CT]:
        if not self.tool_use_mode:
            return []
        return self._tool_profiles.get(self.active_tool_profile) or []

    def get_simple_completion(
        self,
        msg: str | PromptMessage | ImagePromptMessage | list[str | PromptMessage | ImagePromptMessage],
        model: Optional[CompletionModel] = None,
    ) -> CompletionResponse:
        if not isinstance(msg, list):
            msg = [msg]
        messages = msg
        final_messages = []
        for this_msg in messages:
            if isinstance(this_msg, str):
                final_messages.append(PromptMessage(content=this_msg, role="user"))
            else:
                final_messages.append(this_msg)

        return self.completion_handler.get_completion(
            model=model or self.default_completion_model, prompt=final_messages
        )

    def manually_invoke_tool(self, tool_name, params: dict, force_pass=False):
        if not self.current_state == AgentStates.ready_for_message:
            raise RuntimeError("Cannot use tools at this time")
        tool = self.get_current_tool_by_name(tool_name)

        msg = f"User triggered tool: {tool.name} / {params}"
        if force_pass:
            msg += "; respond PASS and use data later"

        self._add_chat_msg(
            msg=f"<system>{msg}</system>",
            role="system",
        )
        tool_call_str = json.dumps({"name": tool.name, "label": f"Manually called: {tool.name}", "parameters": params})
        self._add_chat_msg(f"<tool>{tool_call_str}</tool>", role="assistant")
        self.current_state = AgentStates.using_tools

    def get_pending_tool_calls(self) -> list[ToolAndParams]:
        return_data = []
        for pending_tool_call in self.get_pending_tool_calls_data():
            tool_obj = self.get_current_tool_by_name(pending_tool_call["name"])
            return_data.append(
                ToolAndParams(
                    label=pending_tool_call["label"], tool=tool_obj, params=pending_tool_call.get("parameters", {})
                )
            )

        return return_data

    def get_pending_tool_calls_data(self) -> list[dict]:
        if not self.chat_history:
            return []
        if not (self.chat_history[-1].role == "assistant" and "<tool>" in self.chat_history[-1].content):
            return []
        completion = self.chat_history[-1]

        tool_calls = self.extract_tool_calls_from_msg(completion.content)
        return tool_calls

    def extract_tool_calls_from_msg(self, msg: str) -> list[dict]:
        ai_msg, fn_call_str = msg.split("<tool>", maxsplit=1)
        tool_call_strs = [
            this_call_str.split("</tool>", maxsplit=1)[0] for this_call_str in fn_call_str.split("<tool>")
        ]
        tool_calls = [json.loads(x) for x in tool_call_strs]
        return tool_calls

    def approve_pending_tool_usage(self):
        if not self.current_state == AgentStates.awaiting_tool_approval:
            raise RuntimeError("Not currently awaiting approval for tool usage")
        self.logger.info("Pending tool usage approved, moving into using_tools state")
        self.current_state = AgentStates.using_tools

    def reject_pending_tool_usage(self, why: str):
        if not self.current_state == AgentStates.awaiting_tool_approval:
            raise RuntimeError("Not currently awaiting approval for tool usage")
        self.logger.info("Pending tool usage rejected")
        why = why.strip() or "No reason provided..."
        msg = f"The user rejected your tool calls and supplied the following reason:\n\n{why}"
        self._add_chat_msg(msg, role="system")
        self.current_state = AgentStates.received_message

    def retry_last_response(
        self,
        override_last_prompt_msg: PromptMessage | ImagePromptMessage = None,
        override_model: Callable = None,
    ):
        if not self.current_state == AgentStates.ready_for_message:
            raise RuntimeError("Must be in state ready_for_message to retry a response!")
        final_prompt_msg = override_last_prompt_msg or self.chat_history[-2]
        self.chat_history = self.chat_history[:-2] + [final_prompt_msg]
        self.current_state = AgentStates.received_message
        return self.run_agent(override_model)

    def _generate_response(
        self, max_response_tokens: int, max_attempts=3, override_model: Optional[CompletionModel | str] = None
    ) -> str:
        # allow specific code to override the default completion_fn
        if override_model:
            if isinstance(override_model, CompletionModel):
                this_model = override_model
            else:
                this_model = self.completion_handler.get_model_by_name_or_id(override_model)
        else:
            this_model = self.default_completion_model
        now = datetime.datetime.now(tz=self.local_timezone)
        now_fmt = now.strftime("%A, %b %d %Y %I:%M %p")

        prompt = self.build_tool_usage_prompt(
            prompt=self.agent_description, available_functions=self.get_current_tools()
        )

        prompt += (
            "\n\n---\n\n"
            "To begin, simply use the `BeginChatOperation` tool"
            ' with the startup phrase "OrangeCreamsicle" to enable your tools and '
            "indicate you are ready to process user messages."
        )
        response = """
I am ready for user messages.
<tool>
{
  "name": "BeginChatOperation",
  "label": "Performing startup task"
  "parameters": {
    "startup_phrase": "OrangeCreamsicle"
  }
}
</tool>
""".strip()

        chat_prefix = [
            PromptMessage(role="user", content=prompt),
            PromptMessage(role="assistant", content=response),
        ]

        final_message: PromptMessage | ImagePromptMessage = self.chat_history[-1].model_copy()
        msg_content = final_message.content

        ephemeral_context = {
            "current_local_time": now_fmt,
            "user_preference_notes": self._user_preferences,
        }
        system_context = {**self._llm_context, **ephemeral_context}
        system_context_str = json.dumps(system_context, default=str, indent=2)
        msg_content += (
            f"\n\n<system_context>This section provides data injected automatically by the system at runtime."
            f"\n{system_context_str}"
            f"\n</system_context>"
        )
        final_message.content = msg_content

        chat_prompt = chat_prefix + self.chat_history[:-1] + [final_message]

        attempt_num = 1
        bad_responses = []
        while attempt_num <= max_attempts:
            self.logger.info(f"Generating completion, attempt {attempt_num} of {max_attempts}")
            response = self.completion_handler.get_completion(
                model=this_model, prompt=chat_prompt, max_response_tokens=max_response_tokens
            )
            try:
                self._verify(response.content)
            except MsgVerificationError as e:
                self.logger.warning("Generated response failed verification", exc_info=True)
                self.logger.debug(response)
                bad_responses.append(response)
                attempt_num += 1

                if attempt_num <= max_attempts:
                    error_fmt = ", ".join(e.error_msgs)
                    error_msg = f"<system>Error with tool calls: {error_fmt}</system>"
                    chat_prompt += [
                        PromptMessage(role="assistant", content=response.content),
                        PromptMessage(role="system", content=error_msg),
                    ]
                    self._add_chat_msg(response.content, "assistant")
                    self._add_chat_msg(error_msg, "system")
            else:
                # verified with no error, so break out
                break
        else:  # if we didn't hit a break before running out of attempts
            self.logger.error("Failed to get a valid response within max_attempts value!")
            raise ValueError("Bad AI Response")
        return response.content

    def _verify(self, msg: str):
        error_msgs = []
        if "<tool>" in msg:
            required_keys = {"name", "label"}

            for idx, tool_call in enumerate(self.extract_tool_calls_from_msg(msg)):
                for key in required_keys:
                    if key not in tool_call:
                        error_msgs.append(f"tool call {idx+1} missing required field `{key}`")

                    try:
                        self.get_current_tool_by_name(tool_call["name"])
                    except ValueError:
                        all_tool_names = [x.name for x in self.get_current_tools()]
                        error_msgs.append(
                            f"Invalid tool specified {tool_call['name']}; Valid options are: "
                            + ", ".join(all_tool_names)
                        )
        if error_msgs:
            raise MsgVerificationError(error_msgs=error_msgs)
        return True

    @classmethod
    def build_tool_usage_prompt(
        cls, prompt: str, available_functions: list[_CT], preamble_prompt: Optional[str] = None
    ) -> str:
        if available_functions:
            functions_block = json.dumps([cls.tool_description_to_dict(x) for x in available_functions], indent=2)
        else:
            functions_block = "No tools currently available."
        usage_prompt = TOOL_USAGE_PROMPT.replace("TOOLS_BLOCK_HERE", functions_block)
        output_prompt = f"{usage_prompt}\n\n---\n\n{prompt}"
        if preamble_prompt:
            return f"{preamble_prompt}\n\n{output_prompt}"
        return output_prompt

    @staticmethod
    def tool_description_to_dict(tool: _CT) -> dict:
        parameters = jsonref.loads(tool.params_model.schema_json())["properties"]
        with suppress(KeyError):
            for param, details in parameters.items():
                del details["title"]
        output = {"name": tool.name, "parameters": parameters}
        descr = tool.params_model.__doc__ or tool.description or ""
        if descr:
            output["description"] = descr

        return output


TOOL_USAGE_PROMPT = """
In this environment, you have access to tools to achieve your goal.

Use a tool by embedding the appropriate tag and JSON:

<tool>
{
  "name": "$TOOL_NAME",
  "label": "Brief description (e.g., 'Getting upcoming events', 'Hiding date columns')",
  "parameters": {
    "$PARAMETER_NAME": "$PARAMETER_VALUE"
  }
}
</tool>

- **Must** include the wrapper tag around the JSON.
- **May** include a short message before tool usage but **may not** add content after.
- You can call multiple tools in parallel by including multiple `<tool>` blocks.
- You can use additional tools after receiving results (e.g., look up an ID before another operation).
- Use your first response to plan how you will accomplish the task (including any branching logic and multiple steps), then proceed.

Available tools:

<available_tools>
TOOLS_BLOCK_HERE
</available_tools>

<important>Do not forget to add the "label" when using a tool!</important>
""".strip()
