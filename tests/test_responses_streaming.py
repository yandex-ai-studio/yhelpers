from __future__ import annotations

from types import SimpleNamespace

import pytest
from IPython.display import HTML, Markdown

from yhelpers.responses.streaming import jstream


def event(event_type: str, **values):
    return SimpleNamespace(type=event_type, **values)


def terminal(status: str = "completed", *, usage=None):
    return SimpleNamespace(id="resp_test", status=status, model="test", usage=usage)


def completed(response=None):
    return event("response.completed", response=response or terminal())


def test_text_delta_becomes_markdown_and_returns_response(display_capture):
    response = terminal(
        usage=SimpleNamespace(input_tokens=2, output_tokens=3, total_tokens=5)
    )
    result = jstream(
        [
            event(
                "response.created",
                response=SimpleNamespace(id="resp_test", status="in_progress"),
            ),
            event(
                "response.output_text.delta",
                item_id="msg_1",
                output_index=0,
                content_index=0,
                delta="# Hello",
            ),
            event(
                "response.output_text.delta",
                item_id="msg_1",
                output_index=0,
                content_index=0,
                delta="\n\n**world**",
            ),
            event(
                "response.output_text.done",
                item_id="msg_1",
                output_index=0,
                content_index=0,
                text="# Hello\n\n**world**",
            ),
            completed(response),
        ]
    )

    assert result is response
    assert len(display_capture.handles) == 1
    handle = display_capture.handles[0]
    assert isinstance(handle.updates[0], HTML)
    assert isinstance(handle.updates[-1], Markdown)
    assert handle.updates[-1].data.endswith("# Hello\n\n**world**")
    assert "color:#000000" in handle.updates[-1].data
    assert "font-size:1.05rem" in handle.updates[-1].data
    assert not any(
        "Response completed" in call.value.data for call in display_capture.calls
    )


def test_multiple_open_sections_finalize_at_terminal(display_capture):
    response = terminal()
    result = jstream(
        [
            event(
                "response.output_text.delta",
                item_id="msg_1",
                output_index=0,
                content_index=0,
                delta="First",
            ),
            event(
                "response.output_text.delta",
                item_id="msg_2",
                output_index=1,
                content_index=0,
                delta="Second",
            ),
            completed(response),
        ],
        events={"text"},
    )

    assert result is response
    assert len(display_capture.handles) == 2
    assert all(
        isinstance(handle.updates[-1], Markdown) for handle in display_capture.handles
    )


def test_empty_selection_consumes_without_display(display_capture):
    response = terminal()
    assert jstream([completed(response)], events=[]) is response
    assert display_capture.calls == []


def test_exact_event_selection(display_capture):
    response = terminal()
    jstream(
        [
            event("response.web_search_call.in_progress", item_id="ws_1"),
            completed(response),
        ],
        events={"response.completed"},
    )
    assert len(display_capture.calls) == 1
    assert "Response completed" in display_capture.calls[0].value.data


def test_tool_category_includes_tool_output_items(display_capture):
    tool_item = SimpleNamespace(
        type="function_call",
        id="fn_1",
        name="word_count",
        call_id="call_1",
        status="in_progress",
    )
    jstream(
        [
            event("response.output_item.added", output_index=0, item=tool_item),
            completed(),
        ],
        events={"tools"},
    )
    assert len(display_capture.calls) == 1
    assert "word_count" in display_capture.calls[0].value.data


@pytest.mark.parametrize(
    ("category", "sample"),
    [
        (
            "reasoning",
            event(
                "response.reasoning_text.done",
                item_id="r_1",
                output_index=0,
                content_index=0,
                text="Useful reasoning",
            ),
        ),
        ("tools", event("response.mcp_call.in_progress", item_id="mcp_1")),
        (
            "search",
            event(
                "response.output_item.done",
                output_index=0,
                item=SimpleNamespace(
                    type="web_search_call",
                    id="ws_1",
                    status="completed",
                    action=SimpleNamespace(query="Python docs", queries=None),
                ),
            ),
        ),
        (
            "code",
            event(
                "response.code_interpreter_call_code.done",
                item_id="ci_1",
                output_index=0,
                code="print(1)",
            ),
        ),
        (
            "media",
            event(
                "response.image_gen_call.generating",
                item_id="img_1",
                partial_image="abc",
            ),
        ),
        ("lifecycle", event("response.in_progress", response=SimpleNamespace(id="r"))),
        ("errors", event("response.error", message="boom")),
        ("unknown", event("response.future_widget", value=3)),
    ],
)
def test_every_response_category_is_selectable(display_capture, category, sample):
    jstream([sample, completed()], events={category})
    assert display_capture.calls


def test_code_and_arguments_use_language_fences(display_capture):
    jstream(
        [
            event(
                "response.code_interpreter_call_code.delta",
                item_id="ci_1",
                output_index=0,
                delta="print('ok')",
            ),
            event(
                "response.code_interpreter_call_code.done",
                item_id="ci_1",
                output_index=0,
                code="print('ok')",
            ),
            event(
                "response.shell_call_command.delta",
                item_id="sh_1",
                output_index=1,
                command_index=0,
                delta="python --version",
            ),
            event(
                "response.shell_call_command.done",
                item_id="sh_1",
                output_index=1,
                command_index=0,
                command="python --version",
            ),
            event(
                "response.function_call_arguments.delta",
                item_id="fn_1",
                output_index=2,
                delta='{"value": 2}',
            ),
            event(
                "response.function_call_arguments.done",
                item_id="fn_1",
                output_index=2,
                arguments='{"value": 2}',
            ),
            completed(),
        ],
        events={"code", "tools"},
        show_details=True,
    )

    markdown = [
        update.data
        for handle in display_capture.handles
        for update in handle.updates
        if isinstance(update, Markdown)
    ]
    assert any("```python" in value for value in markdown)
    assert any("```bash" in value for value in markdown)
    assert any("```json" in value and '"value": 2' in value for value in markdown)


def test_diagnostic_truncation_escaping_and_binary_suppression(display_capture):
    jstream(
        [
            event(
                "response.future_widget",
                markup="<script>alert(1)</script>" * 3,
                blob=b"secret bytes",
            ),
            completed(),
        ],
        events={"unknown"},
        max_chars=60,
        show_details=True,
    )

    rendered = display_capture.calls[0].value.data
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "truncated" in rendered


def test_base64_like_media_is_not_embedded(display_capture):
    encoded = "A" * 300
    jstream(
        [
            event("response.image_gen_call.partial_image", partial_image=encoded),
            completed(),
        ],
        events={"media"},
        show_details=True,
    )
    assert "encoded data: 300 characters" in display_capture.calls[0].value.data
    assert encoded not in display_capture.calls[0].value.data


def test_failed_and_incomplete_responses_are_returned(display_capture):
    failed = terminal("failed")
    incomplete = terminal("incomplete")
    assert (
        jstream([event("response.failed", response=failed)], events={"errors"})
        is failed
    )
    assert (
        jstream([event("response.incomplete", response=incomplete)], events={"errors"})
        is incomplete
    )


def test_missing_terminal_response_raises(display_capture):
    with pytest.raises(RuntimeError, match="without a terminal response"):
        jstream([], events={"errors"})
    assert "Streaming error" in display_capture.calls[-1].value.data


def test_iterator_exception_is_displayed_and_reraised(display_capture):
    def broken_stream():
        yield event("response.in_progress")
        raise ValueError("bad stream")

    with pytest.raises(ValueError, match="bad stream"):
        jstream(broken_stream(), events={"errors"})
    assert "bad stream" in display_capture.calls[-1].value.data


def test_validation_errors():
    with pytest.raises(ValueError, match="max_chars"):
        jstream([], max_chars=0)
    with pytest.raises(TypeError, match="events"):
        jstream([], events={1})
    with pytest.raises(TypeError, match="show_details"):
        jstream([], show_details=1)
    with pytest.raises(TypeError, match="show_reasoning"):
        jstream([], show_reasoning=1)
    with pytest.raises(TypeError, match="colormap"):
        jstream([], colormap=[])
    with pytest.raises(ValueError, match="unknown colormap"):
        jstream([], colormap={"not_a_category": "red"})
    with pytest.raises(TypeError, match="colormap values"):
        jstream([], colormap={"text": ""})


def test_default_tool_output_is_compact_and_deduplicated(display_capture):
    action = SimpleNamespace(query="current Python documentation", queries=None)
    tool_item = SimpleNamespace(
        type="web_search_call",
        id="ws_1",
        status="completed",
        action=action,
    )
    jstream(
        [
            event("response.created", response=SimpleNamespace(id="r")),
            event("response.web_search_call.in_progress", item_id="ws_1"),
            event("response.web_search_call.searching", item_id="ws_1"),
            event("response.web_search_call.completed", item_id="ws_1"),
            event("response.output_item.done", output_index=0, item=tool_item),
            completed(),
        ]
    )

    rendered = [call.value.data for call in display_capture.calls]
    assert len(rendered) == 1
    assert all("searching" not in value for value in rendered)
    assert any("current Python documentation" in value for value in rendered)
    assert all("<pre" not in value for value in rendered)
    assert all("response." not in value for value in rendered)


def test_all_with_details_renders_protocol_json(display_capture):
    jstream(
        [event("response.in_progress", response=SimpleNamespace(id="r")), completed()],
        events="all",
        show_details=True,
    )
    rendered = display_capture.calls[0].value.data
    assert "response.in_progress" in rendered
    assert "<pre" in rendered
    assert "&quot;response&quot;" in rendered


def test_function_arguments_are_hidden_by_default(display_capture):
    jstream(
        [
            event(
                "response.function_call_arguments.delta",
                item_id="fn_1",
                output_index=0,
                delta='{"large":"payload"}',
            ),
            event(
                "response.function_call_arguments.done",
                item_id="fn_1",
                output_index=0,
                arguments='{"large":"payload"}',
            ),
            completed(),
        ]
    )
    assert display_capture.calls == []


def test_reasoning_can_be_hidden_even_when_explicitly_selected(display_capture):
    jstream(
        [
            event(
                "response.reasoning_text.delta",
                item_id="reasoning_1",
                output_index=0,
                content_index=0,
                delta="Private chain",
            ),
            event(
                "response.reasoning_text.done",
                item_id="reasoning_1",
                output_index=0,
                content_index=0,
                text="Private chain",
            ),
            event(
                "response.output_text.delta",
                item_id="message_1",
                output_index=1,
                content_index=0,
                delta="Visible answer",
            ),
            event(
                "response.output_text.done",
                item_id="message_1",
                output_index=1,
                content_index=0,
                text="Visible answer",
            ),
            completed(),
        ],
        events={"reasoning", "text"},
        show_reasoning=False,
    )

    assert len(display_capture.handles) == 1
    assert "Visible answer" in display_capture.handles[0].updates[-1].data
    assert all(
        "Private chain" not in getattr(call.value, "data", "")
        for call in display_capture.calls
    )


def test_reasoning_uses_light_gray_and_smaller_type_by_default(display_capture):
    jstream(
        [
            event(
                "response.reasoning_text.delta",
                item_id="reasoning_1",
                output_index=0,
                content_index=0,
                delta="Check the inputs",
            ),
            event(
                "response.reasoning_text.done",
                item_id="reasoning_1",
                output_index=0,
                content_index=0,
                text="Check the inputs",
            ),
            completed(),
        ],
        events={"reasoning"},
    )

    handle = display_capture.handles[0]
    assert "color:#9ca3af" in handle.updates[0].data
    assert "font-size:0.875rem" in handle.updates[0].data
    assert "color:#9ca3af" in handle.updates[-1].data


def test_partial_colormap_merges_defaults_and_distinguishes_tools(display_capture):
    function = SimpleNamespace(
        type="function_call",
        id="function_1",
        name="lookup",
        arguments="{}",
        status="completed",
    )
    jstream(
        [
            event("response.output_item.done", output_index=0, item=function),
            event(
                "response.output_item.done",
                output_index=1,
                item=SimpleNamespace(
                    type="web_search_call",
                    id="search_1",
                    status="completed",
                    action=SimpleNamespace(query="documentation", queries=None),
                ),
            ),
            event(
                "response.code_interpreter_call_code.delta",
                item_id="code_1",
                output_index=1,
                delta="print(1)",
            ),
            event(
                "response.code_interpreter_call_code.done",
                item_id="code_1",
                output_index=1,
                code="print(1)",
            ),
            event(
                "response.shell_call_command.delta",
                item_id="shell_1",
                output_index=2,
                command_index=0,
                delta="pwd",
            ),
            event(
                "response.shell_call_command.done",
                item_id="shell_1",
                output_index=2,
                command_index=0,
                command="pwd",
            ),
            completed(),
        ],
        colormap={
            "tools": "#111111",
            "code_interpreter": "#333333",
            "shell": "#444444",
        },
    )

    html_values = [
        call.value.data
        for call in display_capture.calls
        if isinstance(call.value, HTML)
    ]
    assert any("#111111" in value and "lookup" in value for value in html_values)
    assert any(
        "#0f766e" in value and "documentation" in value for value in html_values
    )
    assert any("#333333" in value and "print(1)" in value for value in html_values)
    assert any("#444444" in value and "pwd" in value for value in html_values)


def test_whitespace_only_segment_is_not_displayed(display_capture):
    jstream(
        [
            event(
                "response.reasoning_text.delta",
                item_id="reasoning_1",
                output_index=0,
                content_index=0,
                delta="   ",
            ),
            event(
                "response.reasoning_text.done",
                item_id="reasoning_1",
                output_index=0,
                content_index=0,
                text="   ",
            ),
            completed(),
        ],
        events={"reasoning"},
    )
    assert display_capture.calls == []


def test_uninformative_progress_events_are_hidden(display_capture):
    jstream(
        [
            event(
                "response.reasoning_summary_part.done",
                item_id="reasoning_1",
                output_index=0,
                summary_index=0,
            ),
            event("response.web_search_call.searching", item_id="search_1"),
            event("response.code_interpreter_call.in_progress", item_id="code_1"),
            event("response.code_interpreter_call.interpreting", item_id="code_1"),
            event("response.code_interpreter_call.completed", item_id="code_1"),
            completed(),
        ]
    )

    assert display_capture.calls == []


def test_code_interpreter_renders_code_and_execution_results(display_capture):
    code = "result = sum(i * i for i in range(1, 11))\nprint(result)"
    tool_item = SimpleNamespace(
        type="code_interpreter_call",
        id="code_1",
        status="completed",
        code=code,
        outputs=[SimpleNamespace(type="logs", logs="385\n")],
    )
    jstream(
        [
            event(
                "response.code_interpreter_call_code.delta",
                item_id="code_1",
                output_index=0,
                delta=code,
            ),
            event(
                "response.code_interpreter_call_code.done",
                item_id="code_1",
                output_index=0,
                code=code,
            ),
            event("response.output_item.done", output_index=0, item=tool_item),
            completed(),
        ]
    )

    markdown = [
        value.data
        for call in display_capture.calls
        for value in ([call.value] + (call.handle.updates if call.handle else []))
        if isinstance(value, Markdown)
    ]
    assert any("```python" in value and "print(result)" in value for value in markdown)
    assert any("Python output" in value and "385" in value for value in markdown)
