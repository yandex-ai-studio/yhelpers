# Changes

## 0.1.0

- Renamed the repository and Python distribution from `ai-studio-helpers` to
  `yhelpers`; the import namespace remains `yhelpers`.
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
- Improved transcript readability with larger black model output, smaller
  auxiliary blocks, light-gray reasoning, and distinct colors for tool calls,
  search, Code Interpreter, and shell activity.
- Added a partial `colormap` override and a `show_reasoning` switch to both
  streaming helpers.
- Suppressed label-only cards and whitespace-only streamed blocks.
- Suppressed compact reasoning-part boundary cards and intermediate Web/File
  Search `searching` status cards.
- Added Code Interpreter execution-log rendering alongside streamed Python
  source, with offline and live coverage of both displays.
- Suppressed Code Interpreter starting, interpreting, and completed lifecycle
  cards from the compact view while retaining them in diagnostic mode.
