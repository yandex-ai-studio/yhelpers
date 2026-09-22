# Architecture

## Package layout

The distribution and import namespace are both named `yhelpers`. The project
uses a `src` layout. Public integrations live in
`yhelpers.responses.streaming` and `yhelpers.agents.streaming`; shared notebook
rendering lives in `yhelpers.common.streaming`.

The `yhelpers` wheel includes only `src/yhelpers`. Repository documentation, tests, and
example notebooks are deliberately excluded from installation.

## Stream ownership

The helpers consume streams but do not create requests or execute tools.

- Responses `jstream` accepts the raw synchronous iterator produced by
  `responses.create(stream=True)` and obtains the final response from a terminal
  stream event.
- Agents `jstream` consumes the SDK-owned asynchronous event stream. It leaves
  approval decisions and any later resumed run to the caller.

This boundary keeps model choice, authentication, retry policy, tools, and
request arguments in application code.

## Rendering model

The renderer is stateful for one stream consumption. Delta buffers are keyed by
response generation, item, output/content indexes, and shell command index.
Each visible buffer owns one Jupyter display handle. Interim content is escaped
HTML; completed content updates the same handle with Markdown.

Known high-volume deltas are coalesced rather than emitted as individual event
cards. Other events use concise, HTML-escaped cards. The default selector is a
coding-agent preset that excludes lifecycle, usage, and unknown protocol noise;
`events="all"` restores those categories.

Diagnostic serialization is a separate presentation choice. With
`show_details=False`, event cards contain short summaries and no JSON blocks.
With `show_details=True`, Pydantic models, dataclasses, mappings, and ordinary
objects share a bounded serializer. Binary and base64-like values are summarized
instead of embedded. This separation lets category selection control *which*
events appear without making ordinary notebook output verbose.

Event selection uses both semantic categories and exact SDK strings. Unknown
event strings remain selectable and use the generic card renderer, avoiding a
hard dependency on an exhaustive event-class union.

Agents SDK streams expose hosted tool calls twice: first as raw Responses events
and later as semantic run items. The renderer uses raw events for timely search
and code progress, records completed tool-call identities, and suppresses the
later duplicate `tool_called` card. Tool outputs, handoffs, approvals, and agent
updates still come from semantic events.

## Live compatibility coverage

Credential-gated tests call Yandex AI Studio with direct streamed Web Search,
Code Interpreter, and File Search requests. A combined Agents test requires all
three hosted tools in one streamed run. Test-owned files, vector stores, and
containers are deleted in fixture teardown; the container also has a 20-minute
inactivity expiry as a fallback.

## Dependencies

`openai` and IPython are core dependencies. `openai-agents` is an optional extra
so Responses-only users do not install the agent framework. The Agents module
raises an actionable import error when that extra is absent.
