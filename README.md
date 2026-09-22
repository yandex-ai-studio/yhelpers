# AI Studio Helpers

Small helpers for using Yandex AI Studio, the OpenAI-compatible Responses API,
and the OpenAI Agents SDK from Python notebooks.

The first release provides rich Jupyter streaming displays. Text is shown as it
arrives and is replaced in place with rendered Markdown when the corresponding
delta section completes. The default view resembles a coding-agent transcript:
answers, tool/search progress, generated code, results, approvals, and errors
are visible, while protocol lifecycle events, usage accounting, and JSON
payloads stay hidden until requested.

## Installation

Install the Responses API helper directly from Git:

```bash
pip install "ai-studio-helpers @ git+https://github.com/yandex-ai-studio/ai-studio-helpers.git"
```

Install the optional OpenAI Agents SDK support:

```bash
pip install "ai-studio-helpers[agents] @ git+https://github.com/yandex-ai-studio/ai-studio-helpers.git"
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
    show_details=True,
    max_chars=1000,
)
```

Auxiliary payloads are limited to 2,000 characters by default; model text and
streamed code are not truncated. Use `max_chars=None` for complete diagnostics.

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
