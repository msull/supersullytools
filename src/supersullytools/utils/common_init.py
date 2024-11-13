import os
from typing import Optional

from simplesingletable import DynamoDbMemory

from supersullytools.llm.completions import CompletionHandler
from supersullytools.llm.trackers import (
    CompletionTracker,
    DailyUsageTracking,
    GlobalUsageTracker,
    SessionUsageTracking,
    TopicUsageTracking,
)
from supersullytools.utils.media_manager import MediaManager


def get_standard_completion_dynamodb_memory(logger=None) -> DynamoDbMemory:
    if logger is None:
        from logzero import logger
    memory = DynamoDbMemory(logger=logger, table_name=os.environ["COMPLETION_TRACKING_DYNAMODB_TABLE"])
    return memory


def get_standard_completion_media_manager(logger=None) -> MediaManager:
    if logger is None:
        from logzero import logger
    return MediaManager(
        bucket_name=os.environ["COMPLETION_TRACKING_BUCKET_NAME"],
        logger=logger,
        dynamodb_memory=get_standard_completion_dynamodb_memory(logger),
        global_prefix="completion_tracking",
    )


def get_standard_completion_handler(
    extra_trackers: Optional[list] = None,
    topics: Optional[list[str]] = None,
    logger=None,
    include_session_tracker: bool = False,
    store_source_tag: Optional[str] = None,
) -> CompletionHandler:
    if logger is None:
        from logzero import logger
    memory = get_standard_completion_dynamodb_memory(logger=logger)
    media_manager = get_standard_completion_media_manager(logger)

    trackers = [
        GlobalUsageTracker.ensure_exists(memory),
        DailyUsageTracking.get_for_today(memory),
    ]
    trackers.extend(TopicUsageTracking.get_for_topic(memory, x) for x in (topics or []))
    trackers.extend(extra_trackers or [])
    if include_session_tracker:
        trackers.append(SessionUsageTracking())

    return CompletionHandler(
        logger=logger,
        completion_tracker=CompletionTracker(
            memory=memory,
            trackers=trackers,
            store_prompt_and_response=True,
            store_prompt_images_media_manager=media_manager,
            store_source_tag=store_source_tag,
        ),
    )
