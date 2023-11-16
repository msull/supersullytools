# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.1] 2023-11-06

### Fixed

* Pinned `pydantic` to a minimum working version.

## [1.5.0] 2023-11-06

### Added

* Implemented optional automated stats tracking by object data_class

### Changed

* Atomic counter increments on non-versioned resources now modifies the `updated_at` attribute and can be utilized with
  dictionary-based counters.

## [1.4.0] 2023-11-06

### Added

* Added support for a non-versioned resource, including methods for atomic counters and set manipulation.
* Added example streamlit_app.py as the start of some documentation.

### Changed

* Refactored codebase a bit, started `models.py`

## [1.3.0] 2023-10-26

### Added

* Added Change Log

### Changed

* Now uses a consistent read after updating a versioned item.

### Deprecated

### Removed

### Fixed

### Security

## [1.2.0] - 2023-10-26

### Added

* Added docstring for paginated query fn

### Fixed

* Pagination key is now properly returned when max_api_calls is reached during a query.

## [1.1.0] - 2023-10-16

### Changed

* Eliminated `pydantic<2` restriction from requirements.

## [1.0.0] - 2023-10-16

### Added

* Initial Release of library
