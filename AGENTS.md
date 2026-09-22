## AI Studio Helpers

This directory contains a library with miscellaneous helper functions that can be used together with Yandex AI Studio, OpenAI Responses API and OpenAI Agents SDK.

The library should be installable by pip install directly from git, but later on we will put it on pypi as well.

Namespace for the library is yhelpers, and then some more namespaces inside it, eg.:
- yhelpers.responses.streaming - streaming functions for Responses API
- yhelpers.agents.streaming - streaming functions for OpenAI Agents library
- yhelpers.common.streaming - common functions such as markdown formatting, etc.

## Documentation

Whenever you make any changes to the code, also keep the following documentation updated:
- docs/reference.md - complete function reference
- docs/changes.md - list of all changes to the library
- docs/architecture.md - main architectural decisions
- README.md - overall documentation for the library, describing how to install it, and what categories of functions are available.

## Tests

Keep tests inside tests directory. You can live test against Yandex AI Studio: `folder_id` and `api_key` are expected to be set in environment variables.
