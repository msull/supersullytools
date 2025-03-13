SuperSully Tools
================

**Latest Version:** 14.2.0

**SuperSullyTools** is a personal Python toolkit for prototyping and proof-of-concept development. It includes various utilities and helpers that I use when building projects, mostly in Python and Streamlit.  

This library isn’t necessarily designed for others to use directly, but there are plenty of useful pieces that might serve as inspiration—or be worth borrowing for your own projects.

## Some modules contained within...

### `supersullytools.gcalendar_access`
Provides a convenience wrapper for interacting with Google Calendar via the v3 API. Supports authentication, listing calendars, retrieving events, adding and updating events, and handling time zones seamlessly. Useful for automating calendar tasks and integrating with scheduling workflows.

### `supersullytools.utils.fuzzy_finder`
Implements fuzzy searching with Levenshtein distance to match and rank similar strings in a collection. Supports customizable scoring for insertions, deletions, and substitutions. Includes tools for ranking search results, handling structured objects, and efficiently retrieving the most relevant matches. Ideal for building intelligent search features and improving text-based lookups.

### `supersullytools.utils.media_manager`
Manages media files stored in Amazon S3 with metadata in DynamoDB. Supports uploading, retrieving, preview generation, and deletion of media files. Includes optional gzip compression and encryption for efficient and secure storage. Useful for handling images, audio, video, PDFs, and other file types in cloud-based applications.

### `supersullytools.utils.reminder_templates`
Provides a lightweight templating system for generating date-based reminders. Supports placeholders like `{current_year}`, `{age(YYYY-MM-DD)}`, `{years_since(YYYY-MM-DD)}`, and `{days_until(YYYY-MM-DD)}`. Useful for dynamically inserting calculated dates in reminder messages.

### `supersullytools.streamlit.paginator`
Implements a simple paginator for Streamlit applications, allowing users to navigate through lists of items efficiently. Supports both numeric and named items, optional keypress navigation, and customizable item actions. Useful for displaying and interacting with paginated content in Streamlit apps.

### `supersullytools.llm`
Contains tools for working with large language models (LLMs). Includes a generic completion interface compatible with AWS Bedrock, Ollama, and OpenAI, along with a custom agent for experimenting with AI-driven workflows. Designed for flexible AI integration and testing various agent-based interactions.

