# YHelpers

Small helpers for using Yandex AI Studio, the OpenAI-compatible Responses API,
and the OpenAI Agents SDK from Python notebooks.

The first release provides rich Jupyter streaming displays. Text is shown as it
arrives and is replaced in place with rendered Markdown when the corresponding
delta section completes. The default view resembles a coding-agent transcript:
answers, tool/search progress, generated code, results, approvals, and errors
are visible, while protocol lifecycle events, usage accounting, and JSON
payloads stay hidden until requested. Model answers are black, reasoning is
light gray, and tool, search, Code Interpreter, and shell activity use distinct
colors without overriding notebook font sizes. Empty label-only blocks are
omitted.
Reasoning-part boundary events and transient search statuses such as
`searching…` are also hidden in the compact view, as are Code Interpreter
`starting…`, `running Python…`, and `completed` lifecycle cards. Code
Interpreter displays both the generated Python and non-empty execution logs
when outputs are included in the response.

## Installation

Install the Responses API helper directly from Git:

```bash
pip install "yhelpers @ git+https://github.com/yandex-ai-studio/yhelpers.git"
```

Install the optional OpenAI Agents SDK support:

```bash
pip install "yhelpers[agents] @ git+https://github.com/yandex-ai-studio/yhelpers.git"
```

The import namespace is `yhelpers`.

## Responses API streaming

`yhelpers.responses.streaming.jstream` consumes the raw iterator returned by
`client.responses.create(..., stream=True)` and returns its terminal `Response`.

```python
from openai import OpenAI
from yhelpers.responses.streaming import jstream

client = OpenAI(
    base_url="https://ai.api.cloud.yandex.net/v1",
    api_key=api_key,
    project=folder_id,
)

stream = client.responses.create(
    model=f"gpt://{folder_id}/qwen3-235b-a22b-fp8",
    input="Explain generators with a short Python example.",
    stream=True,
)
response = jstream(stream)
print(response.id)
```

To display Code Interpreter results as well as its source, request outputs:

```python
stream = client.responses.create(
    model=f"gpt://{folder_id}/qwen3-235b-a22b-fp8",
    input="Use Python to sum the squares from 1 through 100 and print the result.",
    include=["code_interpreter_call.outputs"],
    tools=[{"type": "code_interpreter", "container": {"type": "auto"}}],
    stream=True,
)
response = jstream(stream)
```

## Agents SDK streaming

`yhelpers.agents.streaming.jstream` consumes a `RunResultStreaming` and returns
the same object after the run settles.

```python
from agents import Runner
from yhelpers.agents.streaming import jstream

result = Runner.run_streamed(agent, "Use the word-count tool, then summarize.")
result = await jstream(result)
print(result.final_output)
```

## Choosing events

By default, `jstream` displays a concise coding-agent preset. Pass `events` to
select friendly categories or exact SDK event names:

```python
jstream(stream, events={"text", "tools", "errors"})
jstream(stream, events={"response.output_text.delta", "response.completed"})
await jstream(result, events={"text", "tool_called", "agent_updated_stream_event"})
```

Available categories are `text`, `reasoning`, `tools`, `search`, `code`,
`media`, `handoffs`, `approvals`, `lifecycle`, `usage`, `errors`, and
`unknown`. `events=None` uses the compact preset. `events="all"` includes every
category, including lifecycle and usage. An empty collection consumes the
stream without displaying it.

Event cards contain short human-readable summaries by default. Opt into event
names and bounded JSON payloads only while diagnosing an integration:

```python
response = jstream(
    stream,
    events="all",
    show_reasoning=False,
    show_details=True,
    max_chars=1000,
)
```

Auxiliary payloads are limited to 2,000 characters by default; model text and
streamed code are not truncated. Use `max_chars=None` for complete diagnostics.
`show_reasoning=False` suppresses reasoning even if `events="all"` or an exact
reasoning event name was selected.

Override any subset of the display colors with `colormap`; unspecified fields
retain their defaults:

```python
response = jstream(
    stream,
    colormap={
        "reasoning": "#b8b8b8",
        "tools": "#2563eb",
        "search": "#0f766e",
        "code_interpreter": "#7c3aed",
        "shell": "#c2410c",
    },
)
```

The remaining color keys are `text`, `code`, `media`, `handoffs`, `approvals`,
`lifecycle`, `usage`, `errors`, and `unknown`. See the function reference for
the complete default map.

The [Responses notebook](examples/streaming/responses.ipynb) demonstrates Web
Search, Code Interpreter, category filtering, silent consumption, and detailed
diagnostics. The [Agents notebook](examples/streaming/agents.ipynb) uses Web
Search and Code Interpreter with compact, filtered, and diagnostic streams.
See [`docs/reference.md`](docs/reference.md) for the full API.

## Development

```bash
pip install -e ".[agents,test]"
pytest
```

Live tests are opt-in and require `folder_id` and `api_key` environment
variables. They create and clean up a temporary uploaded file, vector store,
and Code Interpreter container, and exercise direct Responses plus a combined
Agents run with Web Search, File Search, and Code Interpreter:

```bash
YHELPERS_RUN_LIVE=1 pytest -m live
```
