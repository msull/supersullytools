# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0] 2024-02-15

### Added

* Started expanding the basic functionality offered in the ChatSession, including some basic pydantic-based function
  calling support.

## [2.0.0] 2024-02-14

### Changed

* All depedencies moved to optional dev section; user must handle installing packages they want for the features they
  would like to use.

## [1.0.0] 2023-11-30

### Added

* Bumping to an initial 1.0.0 release.
* Added supersullytools.streamlit.paginator.item_paginator which is a general purpose mechanism for iterating over a
  list of items one at a time in a streamlit app, with support for keyboard navigation.
* Created a demo streamlit app to begin showcasing some features of the repo.
