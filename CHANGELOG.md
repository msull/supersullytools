# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] 2024-05-16

### Added

* Added model support for (OpenAI) Gpt4 Omni and replaced the preview versions of GPT4-Turbo / GPT4-Turbo-Vision with
  GPT-4 Turbo
* Added model support for (AWS Bedrock) Claude 3 Opus

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
