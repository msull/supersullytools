"""
Module for Tracking and Displaying Usage Statistics of LLM Completions and Transcriptions.

This module provides classes and methods to track usage statistics for language model completions
and transcriptions, compute associated costs, and display the information using Streamlit expanders.
It integrates with DynamoDB for persistent storage of daily usage data.

The cost calucation done here is an estimate at best, and misleading at worst. It doesn't currently
have any way to represent a change in model cost, as the only thing tracked is the actual usage itself.
If it is necessary to be able to compute the changing cost of a model over time, that information will
need to be tracked separately.

Classes:
    UsageStats:
        - Tracks input/output tokens, completions, and transcription data by model.
        - Computes costs per model based on usage and model pricing.
        - Provides methods to render usage statistics as Streamlit expanders.

    GlobalUsageTracker (UsageStats, SingletonResource):
        - A singleton resource that globally tracks usage statistics across sessions.

    DailyUsageTracking (UsageStats, DynamoDbResource):
        - Manages daily usage statistics with DynamoDB integration.
        - Provides methods to retrieve or create daily tracking records.
        - Supports querying usage data over a date range.

Usage:
    - Instantiate `UsageStats` to track and compute costs for LLM usage.
    - Use `GlobalUsageTracker` for application-wide usage tracking.
    - Use `DailyUsageTracking` to store and retrieve daily usage statistics from DynamoDB.

Examples:
    # Compute and display completion costs
    usage_stats = UsageStats(...)
    usage_stats.render_completion_cost_as_expander()

    # Get today's usage tracking record from DynamoDB
    memory = DynamoDbMemory(...)
    daily_usage = DailyUsageTracking.get_for_today(memory)

"""

import datetime
from base64 import b64decode
from io import BytesIO
from typing import ClassVar, Optional, Union

import pandas as pd
from boto3.dynamodb.conditions import Key
from pydantic import BaseModel, Field
from simplesingletable import DynamoDbMemory, DynamoDbResource
from simplesingletable.extras.singleton import SingletonResource
from simplesingletable.models import ResourceConfig

from supersullytools.llm.completions import (
    CompletionModel,
    CompletionResponse,
    ImagePromptMessage,
    PromptAndResponse,
    PromptMessage,
)
from supersullytools.utils.media_manager import MediaManager, MediaType


class UsageStats(BaseModel):
    # SECTION 1: llm completion tracking / helpers
    input_tokens_by_model: dict[str, int] = Field(default_factory=dict)
    cached_input_tokens_by_model: dict[str, int] = Field(default_factory=dict)
    reasoning_tokens_by_model: dict[str, int] = Field(default_factory=dict)
    output_tokens_by_model: dict[str, int] = Field(default_factory=dict)
    completions_by_model: dict[str, int] = Field(default_factory=dict)

    def compute_cost_per_model(self, model_classes: Optional[list[CompletionModel]] = None):
        if model_classes is None:
            from supersullytools.llm.completions import ALL_MODELS

            model_classes = ALL_MODELS

        # Build a mapping from model identifiers to model classes
        model_class_by_id = {mc.llm_id: mc for mc in model_classes}
        model_class_by_name = {mc.llm: mc for mc in model_classes}
        model_class_lookup = {**model_class_by_id, **model_class_by_name}

        results = {}
        for model in self.completions_by_model:
            model_class: CompletionModel = model_class_lookup.get(model)
            if not model_class:
                continue  # Skip if model_class is not found

            input_tokens = self.input_tokens_by_model.get(model, 0)
            if model_class.cached_input_price_per_1k:
                cached_input_tokens = self.cached_input_tokens_by_model.get(model, 0)
                regular_cost = ((input_tokens - cached_input_tokens) / 1000) * model_class.input_price_per_1k
                cached_cost = (cached_input_tokens / 1000) * model_class.cached_input_price_per_1k
                input_cost = regular_cost + cached_cost
            else:
                input_cost = input_tokens / 1000 * model_class.input_price_per_1k

            output_tokens = self.output_tokens_by_model.get(model, 0)
            output_cost = output_tokens / 1000 * model_class.output_price_per_1k
            results[model] = input_cost + output_cost
        return results

    def render_completion_cost_as_expander(
        self, header="Total Completions: ", model_classes: Optional[list[CompletionModel]] = None, total_in_header=True
    ):
        import streamlit as st

        stats_df = pd.DataFrame(
            {
                "count": self.completions_by_model,
                "input_tokens": self.input_tokens_by_model,
                "cached_input_tokens": self.cached_input_tokens_by_model,
                "output_tokens": self.output_tokens_by_model,
                "cost": self.compute_cost_per_model(model_classes),
            }
        )
        if not stats_df["count"].count():
            completions_label = "No Completions"
            total_cost = 0.0
        else:
            total_count = int(stats_df["count"].sum())
            total_cost = round(stats_df["cost"].sum(), 4)
            completions_label = f"{header}{total_count}"
            if total_in_header:
                completions_label += f"\n\nApprox Cost: ${total_cost}"

        with st.expander(completions_label):
            if not total_in_header and total_cost > 0:
                st.info(f"Approx Completions Cost: ${total_cost}")
            st.dataframe(stats_df.fillna(0))

    # SECTION 2: transcription tracking / helpers
    transcripts_by_model: dict[str, int] = Field(default_factory=dict)
    seconds_transcribed_by_model: dict[str, int] = Field(default_factory=dict)

    def get_minutes_transcribed_by_model(self) -> dict[str, float]:
        return {k: v / 60 for k, v in self.seconds_transcribed_by_model.items()}

    def compute_transcript_cost_per_model(self, model_cost_by_minute: dict[str, float]):
        minutes_transcribed = self.get_minutes_transcribed_by_model()
        results = {}
        for model in self.transcripts_by_model:
            minutes = minutes_transcribed.get(model, 0.0)
            price_per_minute = model_cost_by_minute.get(model, 0.0)
            results[model] = minutes * price_per_minute
        return results

    def render_transcript_cost_as_expander(self, model_cost_by_minute: dict[str, float]):
        import streamlit as st

        cost_per_model = self.compute_transcript_cost_per_model(model_cost_by_minute)
        stats_df = pd.DataFrame(
            {
                "count": self.transcripts_by_model,
                "minutes": self.get_minutes_transcribed_by_model(),
                "cost": cost_per_model,
            }
        )
        if not stats_df["count"].count():
            completions_label = "No Transcripts"
        else:
            total_count = int(stats_df["count"].sum())
            total_minutes = round(stats_df["minutes"].sum(), 2)
            total_cost = round(stats_df["cost"].sum(), 4)
            completions_label = f"Total Transcripts: {total_count} ({total_minutes} min)\n\nApprox Cost: ${total_cost}"

        with st.expander(completions_label):
            st.dataframe(stats_df.fillna(0))


class GlobalUsageTracker(SingletonResource, UsageStats):
    pass


class DailyUsageTracking(DynamoDbResource, UsageStats):
    day: str

    @classmethod
    def get_for_today(cls, memory: DynamoDbMemory, today: Optional[datetime.date] = None, consistent_read: bool = True):
        today = today or datetime.date.today()
        key = today.strftime("%Y%m%d")
        if not (existing := memory.get_existing(key, data_class=cls, consistent_read=consistent_read)):
            return memory.create_new(cls, {"day": today.isoformat()}, override_id=key)
        return existing

    @classmethod
    def get_by_date_range(
        cls, memory: DynamoDbMemory, first_date: datetime.date, last_date: datetime.date
    ) -> list["DailyUsageTracking"]:
        first_day = first_date.isoformat()
        last_day = (last_date + datetime.timedelta(days=1)).isoformat()
        return memory.paginated_dynamodb_query(
            key_condition=(Key("gsitype").eq(cls.__name__) & Key("gsitypesk").between(first_day, last_day)),
            index_name="gsitype",
            resource_class=cls,
        )

    def db_get_gsitypesk(self) -> str:
        # override the base method; use created_at instead of updated_at for the type sort key,
        # to enable easy queries for a range of dates off this index (see the classmethod `get_by_date_range`)
        return self.created_at.isoformat()


class TopicUsageTracking(DynamoDbResource, UsageStats):
    topic: str

    @classmethod
    def get_for_topic(cls, memory: DynamoDbMemory, topic: str, consistent_read: bool = True) -> "TopicUsageTracking":
        if not (existing := memory.get_existing(topic, data_class=cls, consistent_read=consistent_read)):
            return memory.create_new(cls, {"topic": topic}, override_id=topic)
        return existing


class SessionUsageTracking(UsageStats):
    completions: list[PromptAndResponse] = Field(default_factory=list)

    def reset(self):
        self.completions = []
        self.input_tokens_by_model = {}
        self.output_tokens_by_model = {}
        self.completions_by_model = {}


TrackerTypes = Union[UsageStats, GlobalUsageTracker, DailyUsageTracking, TopicUsageTracking]


class StoredPromptAndResponse(DynamoDbResource):
    prompt: list[PromptMessage]
    prompt_image_media_ids: dict[int, list[str]] = Field(default_factory=dict)
    response: CompletionResponse
    resource_config: ClassVar[ResourceConfig] = ResourceConfig(compress_data=True)
    source_tag: Optional[str] = None

    @classmethod
    def create_from_prompt_and_response(
        cls,
        par: PromptAndResponse,
        memory: DynamoDbMemory,
        media_manager: Optional[MediaManager],
        source_tag: Optional[str] = None,
    ) -> "StoredPromptAndResponse":
        """Convert image prompt messages into prompt messages; if an optional media manager is supplied, the images will be preserved and IDs attached."""
        prompt_image_media_ids = {}
        new_prompt: list[PromptMessage] = []
        for idx, message in enumerate(par.prompt):
            if isinstance(message, ImagePromptMessage):
                prompt_image_media_ids[idx] = []
                new_prompt.append(PromptMessage(role=message.role, content=message.content))
                if media_manager:
                    for image, format in zip(message.images, message.image_formats):
                        stored_media_obj = media_manager.upload_new_media(
                            source_file_name=f"image_from_completion:{format}",
                            media_type=MediaType.image,
                            file_obj=BytesIO(b64decode(image.encode())),
                            use_gzip=False,
                        )
                        prompt_image_media_ids[idx].append(stored_media_obj.resource_id)

            else:
                new_prompt.append(message)
        return memory.create_new(
            StoredPromptAndResponse,
            {
                "prompt": new_prompt,
                "response": par.response,
                "prompt_image_media_ids": prompt_image_media_ids,
                "source_tag": source_tag,
            },
        )


class CompletionTracker(object):
    def __init__(
        self,
        memory: DynamoDbMemory,
        trackers: list[TrackerTypes],
        store_prompt_and_response: bool = False,
        store_source_tag: Optional[str] = None,
        store_prompt_images_media_manager: Optional[MediaManager] = None,
    ):
        self.memory = memory
        self.trackers = trackers
        self.store_prompt_and_response = store_prompt_and_response
        self.store_prompt_images_media_manager = store_prompt_images_media_manager
        self.store_source_tag = store_source_tag

    def fixup_trackers(self):
        for tracker in self.trackers:
            if not tracker.cached_input_tokens_by_model and isinstance(tracker, DynamoDbResource):
                self.memory.update_existing(tracker, {"cached_input_tokens_by_model": {}})

    def track_completion(
        self,
        model: CompletionModel,
        prompt: list[PromptMessage | ImagePromptMessage],
        completion: CompletionResponse,
        override_trackers: Optional[list[TrackerTypes]] = None,
        store_prompt_and_response: Optional[bool] = None,
    ):
        if store_prompt_and_response is None:
            store_prompt_and_response = self.store_prompt_and_response
        par = PromptAndResponse(prompt=prompt, response=completion)
        llm_to_track = model.llm
        trackers = override_trackers or self.trackers
        for tracker in trackers:
            if isinstance(tracker, SessionUsageTracking):
                if llm_to_track in tracker.input_tokens_by_model:
                    tracker.completions_by_model[llm_to_track] += 1
                    tracker.input_tokens_by_model[llm_to_track] += completion.input_tokens
                    tracker.output_tokens_by_model[llm_to_track] += completion.output_tokens
                else:
                    tracker.completions_by_model[llm_to_track] = 1
                    tracker.input_tokens_by_model[llm_to_track] = completion.input_tokens
                    tracker.output_tokens_by_model[llm_to_track] = completion.output_tokens

                if completion.cached_input_tokens:
                    if llm_to_track in tracker.cached_input_tokens_by_model:
                        tracker.cached_input_tokens_by_model[llm_to_track] += completion.cached_input_tokens
                    else:
                        tracker.cached_input_tokens_by_model[llm_to_track] = completion.cached_input_tokens
                tracker.completions.append(par)

            if isinstance(tracker, DynamoDbResource):
                self.memory.increment_counter(tracker, f"completions_by_model.{llm_to_track}")
                self.memory.increment_counter(tracker, f"input_tokens_by_model.{llm_to_track}", completion.input_tokens)
                self.memory.increment_counter(
                    tracker, f"output_tokens_by_model.{llm_to_track}", completion.output_tokens
                )
                if completion.cached_input_tokens:
                    self.memory.increment_counter(
                        tracker, f"cached_input_tokens_by_model.{llm_to_track}", completion.cached_input_tokens
                    )

        if store_prompt_and_response:
            StoredPromptAndResponse.create_from_prompt_and_response(
                par,
                memory=self.memory,
                media_manager=self.store_prompt_images_media_manager,
                source_tag=self.store_source_tag,
            )
