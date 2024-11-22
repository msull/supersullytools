# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [10.2.1] 2024-11-22

### Added

* Added new utils/misc.py function to strip markdown backticks and content type code block markers from a str.

## [10.2.0] 2024-11-15

### Changed

- Removed the use of `requests` for submitting images to OpenAI's vision-capable models, streamlining the image
  submission process.
- Simplified the `CompletionHandler` logic by eliminating the conditional handling for image prompts, ensuring a unified
  approach for generating OpenAI ChatCompletions.
- Enhanced the `display_completion` function in `chat_agent_utils.py` to display the database item size for stored
  prompts and responses, providing better insight into stored data.

## [10.1.0]

## Changed

* Standard completion handler tweaks.

## [10.0.4] 2024-11-12

### Changed

* Daily tracker uses timezone-aware object for default date.

## [10.0.3] 2024-11-12

### Changed

* Deferred / made optional more dependencies in MediaManager

## [10.0.2] 2024-11-12

### Added

* Support kwargs on standard completion handler

## [10.0.1] 2024-11-12

### Fixed

* Moved matplotlib import into optional section

## [10.0.0] 2024-11-12

### Added

* Add optional storage for complete prompt and response using dynamodb and media manager.

### Removed

* Eliminated old openai code

### Fixed

* Removed 2 second debugging sleep in agent utils.

## [9.1.0] 2024-11-07

### Added

* Added support for status callback FNs on agent.

## [9.0.0] 2024-11-07

### Added

* Added support for new models (Claude 3.5 Haiku, 3.5 Sonnet V2)

### Changed

* Added a new global list DEFAULT_USE_MODELS to separate out the common models I still want to use.

## [8.3.0] 2024-10-24

### Changed

* Moved streamlit import in trackers.py to a local import within the render function.

## [8.2.0] 2024-10-23

### Added

* Introduced a new `require_reason` parameter in the `ChatAgent` class to control whether a reason is mandatory for tool
  calls.
* Enhanced tool call handling to provide a default reason ("Tool usage") when `require_reason` is set to `False`.

## [8.1.0] 2024-10-23

### Added

* Introduced support for `extra_trackers` in the `CompletionHandler` to allow additional tracking of completions.
* Enhanced `CompletionTracker` to accept `override_trackers`, enabling more flexible tracking configurations.

## [8.0.0] 2024-10-18

### Added

* Added MANIFEST.in to exclude test / streamlit app files from the final package.

### Changed

* Handle errors with bad generated JSON when displaying tool calls

## [7.2.0] 2024-10-17

### Added

- Handle exceptions during tool call extraction

## [7.1.0] 2024-10-11

### Added

- Add `max_consecutive_tool_calls` parameter to ChatAgent to control how many turns the agent may take in a row.

## [7.0.0] 2024-10-10

### Changed

- Image bytes are no longer logged in CompletionHandler debug output

## [6.2.2] 2024-10-10

### Fixed

- Ensure cached / reasoning token values are integers on CompletionResponse.

## [6.2.1]

### Fixed

- Fixed property cost computation when cached_input_tokens are present.

## [6.2.0]

### Changed

- Continued tweaking initial agent prompt.
- Added support for cached input tokens in cost calculations, as well as reporting of reasoning tokens in
  CompletionResponse.

## [6.1.0] 2024-10-04

### Changed

- Tweaked agent prompt with a startup example.

## [6.0.0] 2024-10-03

### Changed

- Attempting better handling for Invalid tool usage.

## [5.7.1] 2024-10-03

### Changed

- Automatically switch system => user for role when using the new o1 models.

## [5.7.0] 2024-10-03

### Added

- Introduced `OpenAIO1Preview` and `OpenAIO1Mini` models with pricing details.
- Added `get_simple_completion` method in `ChatAgent` for simplified message handling.
- Enhanced `CompletionResponse` with `stop_reason` and `response_metadata`.

### Changed

- Updated `Gpt4Omni` pricing.
- Adjusted OpenAI API payload to use `max_completion_tokens` for compatibility with new models.

## [5.6.0] 2024-09-30

### Added

* Added `default_max_response_tokens` attribute to CompletionHandler.

## [5.5.0] 2024-09-27

### Added

* Added `TopicUsageTracking` and `SessionTracking` tracker classes.

## [5.4.0] 2024-09-25

### Added

* Added system slash command to manually invoke tools.

## [5.3.0] 2024-09-24

### Added

* New ChatAgent parameter default_max_response_tokens.

## [5.2.2] 2024-09-19

* Improvement and bugfixes to chat_agent_utils.

## [5.2.1] 2024-09-17

* Improvement and bugfixes to chat_agent_utils.

## [5.2.0] 2024-09-16

* Add Streamlit helper module chat_agent_utils.

## [5.1.0] 2024-09-16

* Added completion tracking, streamlit msg flashing, various other things. Sorry for the lazy update.

## [5.0.0] 2024-09-06

### Changed

* Switched to Bedrock Converse API; some cleanup still TBD. Added Llama 3.1 Instruct models along with Claude 3.5
  Sonnet.

## [4.2.0] 2024-08-06

### Changed

* Switched `np.NAN` to `np.nan` for new Numpy version compatibility.

## [4.1.0] 2024-07-18

### Changed

* Added support for Gpt4OmniMini in llm.completions.

## [4.0.0] 2024-06-28

### Changed

* Swap out Fernet for AESGCM.

## [3.2.1] 2024-06-27

### Added

* Add a tweak to AudioSegment loading when generating waveforms.

## [3.2.0] 2024-06-27

### Added

* Added encryption support to MediaManager for both the original file contents and the generated preview images.

## [3.1.1] 2024-06-19

### Added

* Expanded features of MediaManager to include automatic gzip-compression on uploads; enhanced streamlit demo app.

## [3.1.0] 2024-06-18

### Added

* Added `MediaManager` (`supersullytools.utils.media_manager`) for managing S3 uploads and metadata.

## [3.0.0] 2024-05-16

### Added

* Added model support for (OpenAI) Gpt4 Omni and replaced the preview versions of GPT4-Turbo / GPT4-Turbo-Vision with
  GPT-4 Turbo
* Added model support for (AWS Bedrock) Claude 3 Opus
* Add basic tool using agent.

## [2.5.4] 2024-05-08

### Fixed

* Make flag to enable debug logging of all prompt and responses work properly with Bedrock in CompletionHandler.

## [2.5.3] 2024-05-08

### Added

* Add flags to enable/disable OpenAI and Bedrock in CompletionHandler.

## [2.5.2] 2024-05-07

### Fixed

* Consistent use of Decimal with expires_at in streamlit sessions.

## [2.5.1] 2024-05-07

### Added

* SessionManagerInterface.init_session now includes `auto_extend_session_expiration` flag.

## [2.5.0] 2024-05-07

### Changed

* SessionManagerInterface now automatically clears expired sessions when calling init_session.

## [2.4.0] 2024-05-06

* Added new `fuzzy_search.py` module under utils/ with some use tools for searching for similar strings in a list of
  items or otherwise scoring strings with `levenshtein`.

## [2.3.0] 2024-05-06

* Added a new LLM completion helper tool, which more or less replaces the openai.chat_session functionality.

## [2.2.0] 2024-03-21

### Added

* Added `resettable_tabs` function to `streamlit/misc.py`; this provides a replacement for streamlit tabs that support
  resetting to the default tab (via the `reset_tab_group` fn).

## [2.1.0] 2024-02-15

### Added

* Started expanding the basic functionality offered in the ChatSession, including some basic pydantic-based function
  calling support.

## [2.0.0] 2024-02-14

### Changed

* All dependencies moved to optional dev section; user must handle installing packages they want for the features they
  would like to use.

## [1.0.0] 2023-11-30

### Added

* Bumping to an initial 1.0.0 release.
* Added supersullytools.streamlit.paginator.item_paginator which is a general purpose mechanism for iterating over a
  list of items one at a time in a streamlit app, with support for keyboard navigation.
* Created a demo streamlit app to begin showcasing some features of the repo.
