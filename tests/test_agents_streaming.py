from __future__ import annotations

from types import SimpleNamespace

import pytest
from IPython.display import Markdown

from yhelpers.agents.streaming import jstream


def event(event_type: str, **values):
    return SimpleNamespace(type=event_type, **values)


class FakeResult:
    def __init__(self, events, *, final_output="Done", interruptions=(), error=None):
        self._events = events
        self.final_output = final_output
        self.interruptions = interruptions
        self.run_loop_exception = error

    async def stream_events(self):
        for value in self._events:
            yield value


@pytest.mark.asyncio
async def test_agents_raw_text_updates_markdown_and_returns_same_result(
    display_capture,
):
    response = SimpleNamespace(id="resp", status="completed", usage=None)
    result = FakeResult(
        [
            event(
                "raw_response_event",
                data=event(
                    "response.output_text.delta",
                    item_id="msg",
                    output_index=0,
                    content_index=0,
                    delta="**Hello**",
                ),
            ),
            event(
                "raw_response_event",
                data=event(
                    "response.output_text.done",
                    item_id="msg",
                    output_index=0,
                    content_index=0,
                    text="**Hello**",
                ),
            ),
            event(
                "raw_response_event",
                data=event("response.completed", response=response),
            ),
        ]
    )

    returned = await jstream(result, events={"text"})
    assert returned is result
    assert isinstance(display_capture.handles[0].updates[-1], Markdown)


@pytest.mark.asyncio
async def test_run_item_wrapper_selector_and_message_deduplication(display_capture):
    item = SimpleNamespace(
        type="message_output_item",
        raw_item=SimpleNamespace(type="message", content=[{"text": "do not repeat"}]),
        agent=SimpleNamespace(name="Writer"),
    )
    result = FakeResult(
        [event("run_item_stream_event", name="message_output_created", item=item)],
        final_output="do not repeat",
    )

    await jstream(result, events={"run_item_stream_event"})
    assert len(display_capture.calls) == 1
    assert "Message completed" in display_capture.calls[0].value.data
    assert "do not repeat" not in display_capture.calls[0].value.data


@pytest.mark.asyncio
async def test_tool_item_does_not_serialize_full_agent(display_capture):
    item = SimpleNamespace(
        type="tool_call_item",
        agent=SimpleNamespace(name="Writer", instructions="private internals"),
        raw_item=SimpleNamespace(
            type="function_call",
            name="word_count",
            call_id="call_1",
            arguments='{"text":"hello"}',
        ),
    )
    result = FakeResult(
        [event("run_item_stream_event", name="tool_called", item=item)],
        final_output="   ",
    )
    await jstream(result, events={"tools"})
    rendered = display_capture.calls[0].value.data
    assert "word_count" in rendered
    assert "Writer" not in rendered
    assert "private internals" not in rendered


@pytest.mark.asyncio
async def test_agent_details_are_opt_in(display_capture):
    item = SimpleNamespace(
        type="tool_call_item",
        agent=SimpleNamespace(name="Writer"),
        raw_item=SimpleNamespace(
            type="function_call",
            name="word_count",
            call_id="call_1",
            arguments='{"text":"hello"}',
        ),
    )
    result = FakeResult(
        [event("run_item_stream_event", name="tool_called", item=item)],
        final_output=None,
    )
    await jstream(result, events={"tools"}, show_details=True)
    rendered = display_capture.calls[0].value.data
    assert "<pre" in rendered
    assert "tool_called" in rendered
    assert "Writer" in rendered


@pytest.mark.asyncio
async def test_raw_and_semantic_hosted_tool_events_are_deduplicated(display_capture):
    raw_tool = SimpleNamespace(
        type="web_search_call",
        id="ws_1",
        status="completed",
        action=SimpleNamespace(query="Python documentation", queries=None),
    )
    run_item = SimpleNamespace(
        type="tool_call_item",
        raw_item=raw_tool,
        agent=SimpleNamespace(name="Researcher"),
    )
    response = SimpleNamespace(id="r", status="completed", usage=None)
    result = FakeResult(
        [
            event(
                "raw_response_event",
                data=event("response.web_search_call.searching", item_id="ws_1"),
            ),
            event(
                "raw_response_event",
                data=event("response.output_item.done", item=raw_tool, output_index=0),
            ),
            event(
                "raw_response_event",
                data=event("response.completed", response=response),
            ),
            event("run_item_stream_event", name="tool_called", item=run_item),
        ],
        final_output=None,
    )

    await jstream(result)
    rendered = [call.value.data for call in display_capture.calls]
    assert len(rendered) == 1
    assert sum("Python documentation" in value for value in rendered) == 1
    assert all("searching" not in value for value in rendered)
    assert all("<pre" not in value for value in rendered)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "item_type", "category"),
    [
        ("tool_called", "tool_call_item", "tools"),
        ("tool_search_called", "tool_call_item", "search"),
        ("reasoning_item_created", "reasoning_item", "reasoning"),
        ("handoff_requested", "handoff_call_item", "handoffs"),
        ("mcp_approval_requested", "tool_approval_item", "approvals"),
    ],
)
async def test_agent_item_categories(display_capture, name, item_type, category):
    item = SimpleNamespace(type=item_type, raw_item=SimpleNamespace(type=item_type))
    result = FakeResult(
        [event("run_item_stream_event", name=name, item=item)], final_output=None
    )
    await jstream(result, events={category}, show_details=True)
    assert display_capture.calls


@pytest.mark.asyncio
async def test_empty_label_only_agent_item_is_ignored(display_capture):
    item = SimpleNamespace(
        type="tool_call_item",
        raw_item=SimpleNamespace(type="tool_call_item"),
    )
    result = FakeResult(
        [event("run_item_stream_event", name="tool_called", item=item)],
        final_output=None,
    )

    await jstream(result, events={"tools"})
    assert display_capture.calls == []


@pytest.mark.asyncio
async def test_agents_show_reasoning_flag_is_forwarded(display_capture):
    item = SimpleNamespace(
        type="reasoning_item",
        raw_item=SimpleNamespace(type="reasoning_item", summary=["hidden"]),
    )
    result = FakeResult(
        [event("run_item_stream_event", name="reasoning_item_created", item=item)],
        final_output=None,
    )

    await jstream(result, events={"reasoning"}, show_reasoning=False)
    assert display_capture.calls == []


@pytest.mark.asyncio
async def test_agent_update_exact_selector(display_capture):
    result = FakeResult(
        [
            event(
                "agent_updated_stream_event",
                new_agent=SimpleNamespace(name="Researcher"),
            )
        ],
        final_output=None,
    )
    await jstream(result, events={"agent_updated_stream_event"})
    assert "Researcher" in display_capture.calls[0].value.data


@pytest.mark.asyncio
async def test_interruptions_and_structured_final_output(display_capture):
    result = FakeResult(
        [],
        final_output={"answer": 42},
        interruptions=[SimpleNamespace(name="delete_file", arguments={"path": "x"})],
    )
    await jstream(result, events={"approvals", "text"})
    assert any("Approval required" in call.value.data for call in display_capture.calls)
    assert any(
        isinstance(call.value, Markdown) and "```json" in call.value.data
        for call in display_capture.calls
    )


@pytest.mark.asyncio
async def test_run_loop_exception_is_displayed_and_raised(display_capture):
    error = RuntimeError("background failed")
    result = FakeResult([], final_output=None, error=error)
    with pytest.raises(RuntimeError, match="background failed"):
        await jstream(result, events={"errors"})
    assert "background failed" in display_capture.calls[-1].value.data


@pytest.mark.asyncio
async def test_stream_exception_is_displayed_and_raised(display_capture):
    class BrokenResult(FakeResult):
        async def stream_events(self):
            if False:
                yield None
            raise ValueError("agent stream failed")

    with pytest.raises(ValueError, match="agent stream failed"):
        await jstream(BrokenResult([]), events={"errors"})
    assert "agent stream failed" in display_capture.calls[-1].value.data
