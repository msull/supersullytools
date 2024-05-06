from dataclasses import dataclass, field
from logging import Logger
from typing import Optional, Type, TypeVar

import openai
from openai import Client
from openai.types import ModerationCreateResponse
from openai.types.chat import ChatCompletion
from openai.types.chat.completion_create_params import Function
from pydantic import BaseModel


class ChatTool(BaseModel):
    pass

    @classmethod
    def to_chat_function(cls) -> Function:
        return Function(name=cls.__name__, description=cls.__doc__, parameters=cls.model_json_schema())


_T = TypeVar("_T", bound=ChatTool)


# NOTE: this is now "legacy" and I'm using the supersullytools.llm.completions CompletionHandler class now


@dataclass
class ChatSession:
    initial_system_message: Optional[str] = None
    reinforcement_system_msg: Optional[str] = None
    default_tools: list[Type[_T]] = None
    history: list = field(default_factory=list)
    log: Logger = None
    model: str = "gpt-3.5-turbo-0125"
    openai: Client = None

    def __post_init__(self):
        if self.log is None:
            from logzero import logger

            self.log = logger

    def user_says(self, message):
        self.history.append({"role": "user", "content": message})

    def system_says(self, message):
        self.history.append({"role": "system", "content": message})

    def assistant_says(self, message):
        self.history.append({"role": "assistant", "content": message})

    def openai_client(self) -> Client:
        return self.openai or openai

    @classmethod
    def list_gpt_models(cls):
        return sorted([x.id for x in openai.models.list() if "gpt" in x.id and "instruct" not in x.id])

    def get_ai_response(
        self,
        initial_system_msg_override: str = None,
        reinforcement_system_msg_override: str = None,
        tools_override: list[type[_T]] = None,
        force_tool: Optional[str | bool] = None,
    ) -> ChatCompletion:
        initial_system_msg = initial_system_msg_override or self.initial_system_message
        reinforcement_system_msg = reinforcement_system_msg_override or self.reinforcement_system_msg
        tools = tools_override or self.default_tools

        chat_history = self.history[:]
        # add the initial system message describing the AI's role
        if initial_system_msg:
            chat_history.insert(0, {"role": "system", "content": initial_system_msg})

        if reinforcement_system_msg:
            chat_history.append({"role": "system", "content": reinforcement_system_msg})
        self.log.info("Generating AI ChatCompletion")
        self.log.debug(chat_history)
        if tools:
            functions: list[Function] = [x.to_chat_function() for x in tools]
            if force_tool:
                match force_tool:
                    case str():
                        # force the usage of the specified tool
                        if force_tool not in {x["name"] for x in functions}:
                            raise ValueError("Supplied force_tool value is not a valid function name")
                        function_call = {"name": force_tool}
                    case bool():
                        # use the name of the single supplied tool automatically
                        if len(tools) > 1:
                            raise ValueError("Cannot use force_tool=True shortcut when supplying more than one tool!")
                        function_call = {"name": functions[0]["name"]}
                    case _:
                        raise ValueError("Bad force_tool value")

            else:
                function_call = "auto"

            response = self.openai_client().chat.completions.create(
                model=self.model, messages=chat_history, functions=functions, function_call=function_call
            )
        else:
            response = self.openai_client().chat.completions.create(model=self.model, messages=chat_history)
        self.log.debug(response)
        return response


class FlaggedInputError(RuntimeError):
    def __init__(self, response: ModerationCreateResponse):
        super().__init__()
        self.response = response


def check_for_flagged_content(msg: str):
    response = openai.moderations.create(input=msg)

    if response.results[0].flagged:
        raise FlaggedInputError(response=response)
