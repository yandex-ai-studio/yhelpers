"""Jupyter streaming display for the OpenAI Agents SDK."""

from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING

from yhelpers.common.streaming import NotebookRenderer

try:
    from agents.result import RunResultStreaming
except ImportError as error:  # pragma: no cover - exercised in an isolated install test
    raise ImportError(
        "yhelpers.agents requires the optional Agents SDK dependency. "
        "Install it with: pip install 'yhelpers[agents]'"
    ) from error

if TYPE_CHECKING:
    from agents.stream_events import StreamEvent


async def jstream(
    result: RunResultStreaming,
    *,
    events: str | Collection[str] | None = None,
    max_chars: int | None = 2000,
    show_details: bool = False,
) -> RunResultStreaming:
    """Consume and render an Agents SDK ``RunResultStreaming`` in Jupyter.

    ``events=None`` uses the compact coding-agent preset; use ``events="all"``
    with ``show_details=True`` for protocol names and diagnostic JSON.
    """

    renderer = NotebookRenderer(
        events=events,
        max_chars=max_chars,
        show_details=show_details,
    )
    try:
        async for event in result.stream_events():
            _process_event(renderer, event)
    except BaseException as error:
        renderer.show_exception(error)
        raise
    finally:
        renderer.finalize_all()

    for interruption in getattr(result, "interruptions", ()) or ():
        renderer.show_interruption(interruption)

    run_loop_exception = getattr(result, "run_loop_exception", None)
    if run_loop_exception is not None:
        renderer.show_exception(run_loop_exception)
        raise run_loop_exception

    renderer.ensure_final_output(getattr(result, "final_output", None))
    return result


def _process_event(renderer: NotebookRenderer, event: StreamEvent) -> None:
    event_type = str(getattr(event, "type", type(event).__name__))
    if event_type == "raw_response_event":
        renderer.process_response_event(event.data, outer_names=(event_type,))
    elif event_type == "run_item_stream_event":
        renderer.process_agent_item(
            str(getattr(event, "name", "run_item")),
            getattr(event, "item", None),
            outer_name=event_type,
        )
    elif event_type == "agent_updated_stream_event":
        renderer.process_agent_update(event)
    elif renderer.enabled("unknown", event_type):
        renderer.event_card(
            renderer.label_for_event(event_type),
            event_type,
            event,
            "unknown",
        )


__all__ = ["jstream"]
