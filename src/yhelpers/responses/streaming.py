"""Jupyter streaming display for the Responses API."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from typing import TYPE_CHECKING, Any, cast

from yhelpers.common.streaming import NotebookRenderer

if TYPE_CHECKING:
    from openai.types.responses import Response, ResponseStreamEvent


def jstream(
    stream: Iterable[ResponseStreamEvent],
    *,
    events: str | Collection[str] | None = None,
    max_chars: int | None = 2000,
    show_details: bool = False,
) -> Response:
    """Consume a raw Responses API stream and render it in a Jupyter notebook.

    Pass the iterator returned by ``client.responses.create(..., stream=True)``.
    ``events=None`` uses the compact coding-agent preset; use ``events="all"``
    with ``show_details=True`` for protocol names and diagnostic JSON. The
    terminal ``Response`` is returned after the iterator has been exhausted.
    """

    renderer = NotebookRenderer(
        events=events,
        max_chars=max_chars,
        show_details=show_details,
    )
    terminal_response: Any = None
    try:
        for event in stream:
            response = renderer.process_response_event(event)
            if response is not None:
                terminal_response = response
    except BaseException as error:
        renderer.show_exception(error)
        raise
    finally:
        renderer.finalize_all()

    if terminal_response is None:
        error = RuntimeError("Responses stream ended without a terminal response event")
        renderer.show_exception(error)
        raise error
    return cast("Response", terminal_response)


__all__ = ["jstream"]
