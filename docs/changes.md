# Changes

## 0.1.0

- Added `yhelpers.responses.streaming.jstream` for rich display of raw
  Responses API streams in Jupyter notebooks.
- Added optional `yhelpers.agents.streaming.jstream` support for OpenAI Agents
  SDK streaming runs.
- Added category and exact-name event filtering, completed-section Markdown
  rendering, language-aware code fences, diagnostic truncation, usage/error
  cards, and forward-compatible unknown-event rendering.
- Added offline and opt-in Yandex AI Studio live tests plus Responses and Agents
  example notebooks.
- Changed the default display to a concise coding-agent transcript and added
  opt-in `show_details=True` protocol names and JSON payloads.
- Added compact Web Search, File Search, Code Interpreter, and function-call
  summaries, plus raw/semantic Agents tool-call deduplication.
- Expanded credential-gated live coverage to direct hosted-tool streams and a
  combined Agents run using Web Search, File Search, and Code Interpreter.
- Expanded both example notebooks with explicit hosted-tool prompts and compact,
  filtered, silent, and diagnostic streaming modes.
