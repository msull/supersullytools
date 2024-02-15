from dataclasses import dataclass, field
from logging import Logger
from typing import Optional

import openai
from openai.types import ModerationCreateResponse
from openai.types.chat import ChatCompletion


@dataclass
class ChatSession:
    initial_system_message: Optional[str] = None
    reinforcement_system_msg: Optional[str] = None
    history: list = field(default_factory=list)
    model: str = "gpt-3.5-turbo-0613"
    log: Logger = None

    def __post_init__(self):
        if self.log is None:
            from logzero import logger

            self.log = logger

    @classmethod
    def list_gpt_models(cls):
        return sorted([x.id for x in openai.models.list() if "gpt" in x.id and "instruct" not in x.id])

    def user_says(self, message):
        self.history.append({"role": "user", "content": message})

    def system_says(self, message):
        self.history.append({"role": "system", "content": message})

    def assistant_says(self, message):
        self.history.append({"role": "assistant", "content": message})

    def get_ai_response(
        self,
        initial_system_msg_override: str = None,
        reinforcement_system_msg_override: str = None,
    ) -> ChatCompletion:
        initial_system_msg = initial_system_msg_override or self.initial_system_message
        reinforcement_system_msg = reinforcement_system_msg_override or self.reinforcement_system_msg

        chat_history = self.history[:]
        # add the initial system message describing the AI's role
        if initial_system_msg:
            chat_history.insert(0, {"role": "system", "content": initial_system_msg})

        if reinforcement_system_msg:
            chat_history.append({"role": "system", "content": reinforcement_system_msg})
        self.log.info("Generating AI ChatCompletion")
        self.log.debug(chat_history)
        response = openai.chat.completions.create(model=self.model, messages=chat_history)
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
