import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from logging import Logger
from typing import TYPE_CHECKING, Literal, Optional, TypeVar, Union

import boto3
import openai
import requests
from openai.types.chat import ChatCompletion as OpenAiChatCompletion
from pydantic import AwareDatetime, BaseModel, computed_field

if TYPE_CHECKING:
    from mypy_boto3_bedrock_runtime import BedrockRuntimeClient
    from openai import Client


class PromptMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ImagePromptMessage(BaseModel):
    role: Literal["user"] = "user"
    content: str
    images: list[str]  # images in base64 encoded format
    image_formats: list[Literal["jpeg", "png"]]


class CompletionModel(BaseModel, ABC):
    provider: str
    make: str
    llm: str
    llm_id: str
    input_price_per_1k: float
    output_price_per_1k: float
    supports_images: bool


class CompletionResponse(BaseModel):
    content: str
    input_tokens: int
    output_tokens: int
    llm_metadata: CompletionModel
    generated_at: AwareDatetime
    completion_time_ms: int

    @computed_field
    @property
    def completion_cost(self) -> float:
        input_cost = self.input_tokens / 1000 * self.llm_metadata.input_price_per_1k
        output_cost = self.output_tokens / 1000 * self.llm_metadata.output_price_per_1k
        return round(input_cost + output_cost, 4)


class OpenAiModel(CompletionModel):
    provider: Literal["OpenAI"] = "OpenAI"


class BedrockCompletionResponse(BaseModel):
    """A helper class to use with parsing bedrock responses from AWS"""

    content: str
    input_tokens: int
    output_tokens: int


class BedrockModel(CompletionModel):
    provider: Literal["AWS Bedrock"] = "AWS Bedrock"

    @abstractmethod
    def prepare_bedrock_body(
        self, prompt: str | list[PromptMessage | ImagePromptMessage], max_response_tokens: int
    ) -> dict:
        pass

    @abstractmethod
    def parse_bedrock_response(self, response: dict) -> BedrockCompletionResponse:
        pass


CompletionModelType = TypeVar("CompletionModelType", bound=CompletionModel)


class CompletionHandler:
    def __init__(
        self,
        logger: Logger,
        openai_client: Optional["Client"] = None,
        bedrock_runtime_client: Optional["BedrockRuntimeClient"] = None,
        available_models: Optional[list["CompletionModel"]] = None,
        debug_output_prompt_and_response=False,
        enable_openai=True,
        enable_bedrock=True,
    ):
        self.logger = logger
        self.enable_openai = enable_openai
        self.enable_bedrock = enable_bedrock

        self.openai_client = None
        if self.enable_openai:
            self.openai_client = openai_client or openai.Client()

        self.bedrock_runtime_client = None
        if self.enable_bedrock:
            self.bedrock_runtime_client = bedrock_runtime_client or boto3.client("bedrock-runtime")

        self.debug_output_prompt_and_response = debug_output_prompt_and_response
        if available_models:
            self.available_models = available_models
        else:
            if enable_bedrock and enable_openai:
                self.available_models = ALL_MODELS
            elif enable_bedrock:
                self.available_models = [x for x in ALL_MODELS if isinstance(x, BedrockModel)]
            elif enable_openai:
                self.available_models = [x for x in ALL_MODELS if isinstance(x, OpenAiModel)]
            else:
                # what do?
                raise ValueError("No models specified")

    def get_model_by_name_or_id(self, model_name_or_id: str) -> "CompletionModelType":
        try:
            return next(x for x in self.available_models if x.llm == model_name_or_id)
        except StopIteration:
            try:
                return next(x for x in self.available_models if x.llm_id == model_name_or_id)
            except StopIteration:
                raise ValueError(f"No model found {model_name_or_id=}") from None

    def get_completion(
        self,
        model: Union[str, "CompletionModel"],
        prompt: str | list[PromptMessage | ImagePromptMessage],
        max_response_tokens: int = 1000,
    ) -> "CompletionResponse":
        if isinstance(model, str):
            model = self.get_model_by_name_or_id(model)

        match model:
            case OpenAiModel():
                return self._get_openai_completion(model, prompt, max_response_tokens)
            case BedrockModel():
                return self._get_bedrock_completion(model, prompt, max_response_tokens)
            case _:
                raise ValueError(model)

    def _get_bedrock_completion(
        self, llm: BedrockModel, prompt: str | list[PromptMessage | ImagePromptMessage], max_response_tokens: int
    ) -> "CompletionResponse":
        if not self.enable_bedrock:
            raise RuntimeError("Bedrock completions disabled!")
        boto_input = llm.prepare_bedrock_body(prompt, max_response_tokens)
        body = json.dumps(boto_input)

        accept = "application/json"
        content_type = "application/json"

        self.logger.info(f"Generating Bedrock Completion {llm.llm_id}")
        if self.debug_output_prompt_and_response:
            self.logger.debug(f"LLM input:\n{boto_input}")

        # Invoke Bedrock API
        started_at = datetime.now(timezone.utc)
        response = self.bedrock_runtime_client.invoke_model(
            body=body, modelId=llm.llm_id, accept=accept, contentType=content_type
        )
        finished_at = datetime.now(timezone.utc)
        self.logger.info("Generation complete")
        if self.debug_output_prompt_and_response:
            self.logger.debug(f"LLM Response:\n{response}")

        parsed_response = llm.parse_bedrock_response(response)

        return CompletionResponse(
            content=parsed_response.content,
            input_tokens=parsed_response.input_tokens,
            output_tokens=parsed_response.output_tokens,
            llm_metadata=CompletionModel.model_validate(llm, from_attributes=True),
            generated_at=finished_at,
            completion_time_ms=int((finished_at - started_at).total_seconds() * 1000),
        )

    def _get_openai_completion(
        self, llm: OpenAiModel, prompt: str | list[PromptMessage | ImagePromptMessage], max_response_tokens: int
    ) -> "CompletionResponse":
        if not self.enable_openai:
            raise RuntimeError("OpenAI completions disabled!")
        is_image_prompt = False
        if isinstance(prompt, str):
            chat_history = [{"role": "user", "content": prompt}]
        else:
            chat_history = []
            for msg in prompt:
                match msg:
                    case PromptMessage():
                        chat_history.append({"role": msg.role, "content": msg.content})
                    case ImagePromptMessage():
                        is_image_prompt = True
                        content = [{"type": "text", "text": msg.content}]
                        for image, image_fmt in zip(msg.images, msg.image_formats):
                            content.append(
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/{image_fmt};base64,{image}",
                                        "detail": "high",
                                    },
                                }
                            )
                        chat_history.append(
                            {
                                "role": msg.role,
                                "content": content,
                            }
                        )
                    case _:
                        raise ValueError("Base prompt type")

        started_at = datetime.now(timezone.utc)
        if is_image_prompt:
            if not llm.supports_images:
                raise ValueError("Specified model does not have image prompt support")
            self.logger.info("Generating Open AI ChatCompletion with Images")
            if self.debug_output_prompt_and_response:
                self.logger.debug(f"LLM input:\n{chat_history}")
            # have to use requests for this one
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.openai_client.api_key}"}

            payload = {"model": llm.llm_id, "messages": chat_history, "max_tokens": max_response_tokens}
            raw_response = requests.post(
                "https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=300
            )
            raw_response.raise_for_status()
            data = raw_response.json()
            if self.debug_output_prompt_and_response:
                self.logger.debug(f"LLM response:\n{data}")
            openai_response = OpenAiChatCompletion.model_validate(data)
        else:
            self.logger.info("Generating Open AI ChatCompletion")
            if self.debug_output_prompt_and_response:
                self.logger.debug(f"LLM input:\n{chat_history}")
            openai_response = self.openai_client.chat.completions.create(
                model=llm.llm_id, messages=chat_history, max_tokens=max_response_tokens
            )
            if self.debug_output_prompt_and_response:
                self.logger.debug(f"LLM response:\n{openai_response}")
        finished_at = datetime.now(timezone.utc)

        return CompletionResponse(
            content=openai_response.choices[0].message.content,
            input_tokens=openai_response.usage.prompt_tokens,
            output_tokens=openai_response.usage.completion_tokens,
            llm_metadata=CompletionModel.model_validate(llm, from_attributes=True),
            generated_at=finished_at,
            completion_time_ms=int((finished_at - started_at).total_seconds() * 1000),
        )


class Gpt3p5Turbo0125(OpenAiModel):
    make: str = "OpenAI"
    llm: str = "GPT 3.5 Turbo"
    llm_id: str = "gpt-3.5-turbo-0125"
    input_price_per_1k: float = 0.000500
    output_price_per_1k: float = 0.001500
    supports_images: bool = False


class Gpt4Turbo0125Preview(Gpt3p5Turbo0125):
    make: str = "OpenAI"
    llm: str = "GPT 4 Turbo"
    llm_id: str = "gpt-4-0125-preview"
    input_price_per_1k: float = 0.010000
    output_price_per_1k: float = 0.030000
    supports_images: bool = False


class Gpt4VisionPreview(Gpt3p5Turbo0125):
    make: str = "OpenAI"
    llm: str = "GPT 4 Vision Preview"
    llm_id: str = "gpt-4-vision-preview"
    input_price_per_1k: float = 0.010000
    output_price_per_1k: float = 0.030000
    supports_images: bool = True


class Llama2Chat13B(BedrockModel):
    make: str = "Meta"
    llm: str = "Llama 2 Chat 13B"
    llm_id: str = "meta.llama2-13b-chat-v1"
    input_price_per_1k: float = 0.000750
    output_price_per_1k: float = 0.001000
    supports_images: bool = False

    def prepare_bedrock_body(
        self, prompt: str | list[PromptMessage | ImagePromptMessage], max_response_tokens: int
    ) -> dict:
        if not isinstance(prompt, str):
            raise ValueError("Only support str type prompt for this model currently")

        return {
            "prompt": prompt,
            "max_gen_len": max_response_tokens,
            # "stop": [string],
            # "temperature": float,
            # "top_p": float,
            # "top_k": int,
        }

    def parse_bedrock_response(self, response: dict) -> BedrockCompletionResponse:
        response_body = json.loads(response.get("body").read())
        return BedrockCompletionResponse(
            content=response_body["generation"],
            input_tokens=response_body["prompt_token_count"],
            output_tokens=response_body["generation_token_count"],
        )


class Llama2Chat70B(Llama2Chat13B):
    make: str = "Meta"
    llm: str = "Llama 2 Chat 70B"
    llm_id: str = "meta.llama2-70b-chat-v1"
    input_price_per_1k: float = 0.001950
    output_price_per_1k: float = 0.002560
    supports_images: bool = False


class Claude3Sonnet(BedrockModel):
    make: str = "Anthropic"
    llm: str = "Claude 3 Sonnet"
    llm_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    input_price_per_1k: float = 0.003
    output_price_per_1k: float = 0.015
    supports_images: bool = True

    def prepare_bedrock_body(
        self, prompt: str | list[PromptMessage | ImagePromptMessage], max_response_tokens: int
    ) -> dict:
        chat_history = []
        if isinstance(prompt, str):
            chat_history = [{"role": "user", "content": prompt}]
        else:
            for msg in prompt:
                match msg:
                    case PromptMessage():
                        chat_history.append({"role": msg.role, "content": msg.content})
                    case ImagePromptMessage():
                        if not self.supports_images:
                            raise ValueError("Specified model does not have image prompt support")
                        content = [{"type": "text", "text": msg.content}]
                        for image, image_fmt in zip(msg.images, msg.image_formats):
                            content.append(
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": f"image/{image_fmt}",
                                        "data": image,
                                    },
                                }
                            )
                        chat_history.append(
                            {
                                "role": msg.role,
                                "content": content,
                            }
                        )
                    case _:
                        raise ValueError("Bad prompt type")

        return {
            "messages": chat_history,
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_response_tokens,
        }

    def parse_bedrock_response(self, response: dict) -> BedrockCompletionResponse:
        response_body = json.loads(response.get("body").read())
        content = response_body["content"][0]["text"].strip()
        response_headers = response["ResponseMetadata"]["HTTPHeaders"]
        return BedrockCompletionResponse(
            content=content,
            input_tokens=int(response_headers["x-amzn-bedrock-input-token-count"]),
            output_tokens=int(response_headers["x-amzn-bedrock-output-token-count"]),
        )


class Claude3Haiku(Claude3Sonnet):
    make: str = "Anthropic"
    llm: str = "Claude 3 Haiku"
    llm_id: str = "anthropic.claude-3-haiku-20240307-v1:0"
    input_price_per_1k: float = 0.00025
    output_price_per_1k: float = 0.00125
    supports_images: bool = True


class Mistral7B(BedrockModel):
    make: str = "Mistral AI"
    llm: str = "Mistral 7B Instruct"
    llm_id: str = "mistral.mistral-7b-instruct-v0:2"
    input_price_per_1k: float = 0.000150
    output_price_per_1k: float = 0.000200
    supports_images: bool = False

    def prepare_bedrock_body(
        self, prompt: str | list[PromptMessage | ImagePromptMessage], max_response_tokens: int
    ) -> dict:
        if not isinstance(prompt, str):
            raise ValueError("Only support str type prompt for this model currently")

        return {
            "prompt": f"<s>[INST]{prompt}[/INST]",
            "max_tokens": max_response_tokens,
        }

    def parse_bedrock_response(self, response: dict) -> BedrockCompletionResponse:
        response_body = json.loads(response.get("body").read())
        content = response_body["outputs"][0]["text"].strip()
        response_headers = response["ResponseMetadata"]["HTTPHeaders"]
        return BedrockCompletionResponse(
            content=content,
            input_tokens=int(response_headers["x-amzn-bedrock-input-token-count"]),
            output_tokens=int(response_headers["x-amzn-bedrock-output-token-count"]),
        )


class Mixtral8x7B(Mistral7B):
    make: str = "Mistral AI"
    llm: str = "Mixtral 8x7B Instruct"
    llm_id: str = "mistral.mixtral-8x7b-instruct-v0:1"
    input_price_per_1k: float = 0.000450
    output_price_per_1k: float = 0.000700
    supports_images: bool = False


ALL_MODELS = [
    Gpt3p5Turbo0125(),
    Gpt4Turbo0125Preview(),
    Gpt4VisionPreview(),
    Llama2Chat13B(),
    Llama2Chat70B(),
    Mistral7B(),
    Mixtral8x7B(),
    Claude3Haiku(),
    Claude3Sonnet(),
]
