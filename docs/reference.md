# Function reference

## `yhelpers.responses.streaming.jstream`

```python
def jstream(
    stream: Iterable[ResponseStreamEvent],
    *,
    events: str | Collection[str] | None = None,
    max_chars: int | None = 2000,
    show_details: bool = False,
) -> Response
```

Consumes the synchronous raw event iterator returned by
`client.responses.create(..., stream=True)`, renders selected events in the
current Jupyter output cell, and returns the `Response` attached to the final
`response.completed`, `response.failed`, or `response.incomplete` event.

The function raises `RuntimeError` if the iterator finishes without a terminal
response. Exceptions raised by the iterator are displayed and re-raised.

## `yhelpers.agents.streaming.jstream`

```python
async def jstream(
    result: RunResultStreaming,
    *,
    events: str | Collection[str] | None = None,
    max_chars: int | None = 2000,
    show_details: bool = False,
) -> RunResultStreaming
```

Consumes `result.stream_events()` until it settles and returns the same result
object. Pending approval interruptions are displayed after streaming. A
non-null `run_loop_exception` is displayed and raised.

Install the optional dependency with `pip install "yhelpers[agents]"`.

## Parameters

### `events`

- `None`: use the concise coding-agent preset: text, reasoning, tools, search,
  code, media, handoffs, approvals, and errors.
- `"all"`: display every category, including lifecycle, usage, and unknown
  events.
- Empty collection: consume without displaying.
- Category names: select groups of related events.
- Exact event names: select an individual Responses event type, Agents run-item
  name, or Agents wrapper event type.

| Category | Content |
| --- | --- |
| `text` | Output text, annotations, and structured final output |
| `reasoning` | Reasoning text, summaries, and reasoning run items |
| `tools` | Function, custom, MCP, and generic tool activity |
| `search` | Web, file, and dynamic tool search activity |
| `code` | Code Interpreter, shell, computer, and patch activity |
| `media` | Image-generation and audio status/transcript activity |
| `handoffs` | Agent changes and handoff requests/completions |
| `approvals` | MCP approvals and paused-run interruptions |
| `lifecycle` | Response and output-item state transitions |
| `usage` | Token usage from terminal Responses events |
| `errors` | Failures, incomplete responses, refusals, and exceptions |
| `unknown` | Forward-compatible fallback for unrecognized events |

For Agents streams, selecting `raw_response_event` enables all wrapped raw
Responses events; selecting `run_item_stream_event` enables all run-item events.
Filtering changes presentation only. All events are still consumed and
processed so the returned object is complete.

### `max_chars`

Maximum size of diagnostic cards and tool-output previews. It must be a positive
integer or `None`. Model output text and streamed source code are never
truncated. Binary and encoded media payloads are represented by their sizes.

### `show_details`

`False` by default. Event cards show a short human-readable status or preview,
without SDK event names or JSON blocks. Set `show_details=True` to add the exact
event name and a serialized diagnostic payload. The payload observes
`max_chars`, HTML escaping, and binary/base64 suppression.

`show_details` does not affect model text or streamed Code Interpreter/shell
source. Those remain complete. Function, custom-tool, and MCP argument deltas
are summarized as compact calls by default and are rendered as fenced `json`
only when details are enabled.

## Rendering behavior

- Output text starts in an escaped `<pre>` display and updates in place.
- A matching `done` event replaces that display with rendered Markdown.
- Content/item boundaries, terminal events, and stream exhaustion finalize any
  open display as a compatibility fallback.
- Code Interpreter source uses a `python` fence and shell commands use `bash`.
  With `show_details=True`, function/MCP/custom-tool arguments use `json`.
- When content contains a triple-backtick sequence, the outer Markdown fence is
  lengthened so the code remains valid.
- Agents raw output-item events and semantic `tool_called` events are
  deduplicated by tool-call identity.
