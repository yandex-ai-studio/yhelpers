# Function reference

## `yhelpers.responses.streaming.jstream`

```python
def jstream(
    stream: Iterable[ResponseStreamEvent],
    *,
    events: str | Collection[str] | None = None,
    max_chars: int | None = 2000,
    colormap: Mapping[str, str] | None = None,
    show_reasoning: bool = True,
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
    colormap: Mapping[str, str] | None = None,
    show_reasoning: bool = True,
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

### `colormap`

An optional mapping from semantic style keys to CSS color values. The mapping
is merged over the defaults, so callers can override one color without copying
the whole structure. Unknown keys, non-string values, and empty strings are
rejected.

```python
jstream(
    stream,
    colormap={
        "reasoning": "#b8b8b8",
        "code_interpreter": "rebeccapurple",
    },
)
```

| Key | Default | Applied to |
| --- | --- | --- |
| `text` | `#000000` | Normal model output |
| `reasoning` | `#9ca3af` | Reasoning text, summaries, and cards |
| `tools` | `#2563eb` | Function, custom, MCP, and generic tool activity |
| `search` | `#0f766e` | Web, file, and dynamic tool search |
| `code` | `#7c3aed` | Generic code/computer/patch activity |
| `code_interpreter` | `#7c3aed` | Code Interpreter status and source |
| `shell` | `#c2410c` | Shell commands and output |
| `media` | `#a21caf` | Image and audio activity |
| `handoffs` | `#7c3aed` | Agent handoffs |
| `approvals` | `#c2410c` | Approval requests and responses |
| `lifecycle` | `#64748b` | Protocol lifecycle events |
| `usage` | `#475569` | Token usage |
| `errors` | `#b91c1c` | Errors, refusals, and incomplete responses |
| `unknown` | `#6b7280` | Unrecognized events and color fallback |

The complete defaults are also available as
`yhelpers.common.streaming.DEFAULT_COLORMAP`.

### `show_reasoning`

`True` by default. Set `show_reasoning=False` to suppress all reasoning blocks.
This is an absolute presentation gate: reasoning stays hidden even when the
`reasoning` category, an exact reasoning event, a wrapper event, or
`events="all"` would otherwise enable it. Reasoning events are still consumed.

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
- Model output is black and uses `1.05rem` type. Reasoning, tool activity, and
  other event cards use compact `0.875rem` type. Reasoning is light gray by
  default.
- Tool calls, search activity, Code Interpreter, and shell activity resolve to
  separate color-map keys.
- Label-only cards and whitespace-only streamed sections are not displayed.
- Content/item boundaries, terminal events, and stream exhaustion finalize any
  open display as a compatibility fallback.
- Code Interpreter source uses a `python` fence and shell commands use `bash`.
  With `show_details=True`, function/MCP/custom-tool arguments use `json`.
- When content contains a triple-backtick sequence, the outer Markdown fence is
  lengthened so the code remains valid.
- Agents raw output-item events and semantic `tool_called` events are
  deduplicated by tool-call identity.
