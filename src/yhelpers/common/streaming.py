"""Shared notebook rendering for Responses API and Agents SDK streams."""

from __future__ import annotations

import dataclasses
import html
import json
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from IPython.display import HTML, Markdown, display

EVENT_CATEGORIES = frozenset(
    {
        "text",
        "reasoning",
        "tools",
        "search",
        "code",
        "media",
        "handoffs",
        "approvals",
        "lifecycle",
        "usage",
        "errors",
        "unknown",
    }
)

# The default resembles a coding-agent transcript: useful work and results are
# visible, while protocol bookkeeping and token accounting stay out of the way.
DEFAULT_EVENT_CATEGORIES = frozenset(
    {
        "text",
        "reasoning",
        "tools",
        "search",
        "code",
        "media",
        "handoffs",
        "approvals",
        "errors",
    }
)

DEFAULT_COLORMAP = {
    "text": "#000000",
    "reasoning": "#9ca3af",
    "tools": "#2563eb",
    "search": "#0f766e",
    "code": "#7c3aed",
    "code_interpreter": "#7c3aed",
    "shell": "#c2410c",
    "media": "#a21caf",
    "handoffs": "#7c3aed",
    "approvals": "#c2410c",
    "lifecycle": "#64748b",
    "usage": "#475569",
    "errors": "#b91c1c",
    "unknown": "#6b7280",
}

_TERMINAL_EVENTS = {
    "response.completed",
    "response.failed",
    "response.incomplete",
}

_DELTA_SPECS: dict[str, tuple[str, str | None, str | None]] = {
    "response.output_text.delta": ("text", None, None),
    "response.refusal.delta": ("errors", "Refusal", None),
    "response.reasoning_summary_text.delta": (
        "reasoning",
        "Reasoning summary",
        None,
    ),
    "response.reasoning_text.delta": ("reasoning", "Reasoning", None),
    "response.function_call_arguments.delta": (
        "tools",
        "Function arguments",
        "json",
    ),
    "response.custom_tool_call_input.delta": (
        "tools",
        "Custom tool input",
        "json",
    ),
    "response.mcp_call_arguments.delta": ("tools", "MCP arguments", "json"),
    "response.code_interpreter_call_code.delta": (
        "code",
        "Code Interpreter",
        "python",
    ),
    "response.shell_call_command.delta": ("code", "Shell command", "bash"),
    "response.shell_call_output_content.delta": ("code", "Shell output", "text"),
    "response.audio_transcript.delta": ("media", "Audio transcript", None),
}

_DONE_TO_DELTA = {
    "response.output_text.done": "response.output_text.delta",
    "response.refusal.done": "response.refusal.delta",
    "response.reasoning_summary_text.done": "response.reasoning_summary_text.delta",
    "response.reasoning_text.done": "response.reasoning_text.delta",
    "response.function_call_arguments.done": "response.function_call_arguments.delta",
    "response.custom_tool_call_input.done": "response.custom_tool_call_input.delta",
    "response.mcp_call_arguments.done": "response.mcp_call_arguments.delta",
    "response.code_interpreter_call_code.done": (
        "response.code_interpreter_call_code.delta"
    ),
    "response.shell_call_command.done": "response.shell_call_command.delta",
    "response.shell_call_output_content.done": (
        "response.shell_call_output_content.delta"
    ),
    "response.audio_transcript.done": "response.audio_transcript.delta",
}

_DONE_VALUE_FIELDS = (
    "text",
    "refusal",
    "arguments",
    "input",
    "code",
    "command",
    "output",
    "transcript",
)

_TOOL_ITEM_TYPES = {
    "function_call",
    "custom_tool_call",
    "mcp_call",
    "web_search_call",
    "file_search_call",
    "code_interpreter_call",
    "shell_call",
    "computer_call",
    "image_generation_call",
}

_BASE64_RE = re.compile(r"^[A-Za-z0-9+/\r\n]+={0,2}$")


class EventSelector:
    """Normalize the default preset, categories, and exact event selectors."""

    def __init__(self, events: str | Collection[str] | None) -> None:
        self.is_default = events is None
        if events is None:
            self.all = False
            self.names = DEFAULT_EVENT_CATEGORIES
            return
        if events == "all":
            self.all = True
            self.names: frozenset[str] = frozenset()
            return
        if isinstance(events, str):
            names = {events}
        else:
            names = set(events)
        if not all(isinstance(name, str) for name in names):
            raise TypeError("events must contain only strings")
        self.all = "all" in names
        self.names = frozenset(names - {"all"})

    def enabled(self, categories: str | Collection[str], *event_names: str) -> bool:
        if self.all:
            return True
        if isinstance(categories, str):
            category_names = {categories}
        else:
            category_names = set(categories)
        return bool(
            self.names.intersection(category_names)
            or self.names.intersection(event_names)
        )

    def exact(self, *event_names: str) -> bool:
        """Return whether an exact/wrapper name, rather than a category, matched."""

        return self.all or bool(self.names.intersection(event_names))


@dataclass
class _Segment:
    category: str
    style_key: str
    label: str | None
    language: str | None
    text: str = ""
    handle: Any = None
    visible: bool = False
    finalized: bool = False


class NotebookRenderer:
    """Render semantic stream events into replaceable Jupyter display regions."""

    def __init__(
        self,
        events: str | Collection[str] | None = None,
        max_chars: int | None = 2000,
        *,
        colormap: Mapping[str, str] | None = None,
        show_reasoning: bool = True,
        show_details: bool = False,
    ) -> None:
        if max_chars is not None and (not isinstance(max_chars, int) or max_chars <= 0):
            raise ValueError("max_chars must be a positive integer or None")
        if not isinstance(show_details, bool):
            raise TypeError("show_details must be a bool")
        if not isinstance(show_reasoning, bool):
            raise TypeError("show_reasoning must be a bool")
        if colormap is not None and not isinstance(colormap, Mapping):
            raise TypeError("colormap must be a mapping or None")
        colors = dict(DEFAULT_COLORMAP)
        if colormap is not None:
            unknown = set(colormap) - set(DEFAULT_COLORMAP)
            if unknown:
                names = ", ".join(sorted(str(name) for name in unknown))
                raise ValueError(f"unknown colormap field(s): {names}")
            for name, color in colormap.items():
                if not isinstance(color, str) or not color.strip():
                    raise TypeError("colormap values must be non-empty strings")
                colors[name] = color.strip()
        self.selector = EventSelector(events)
        self.max_chars = max_chars
        self.colormap = colors
        self.show_reasoning = show_reasoning
        self.show_details = show_details
        self._style_marker = f"yhelpers-stream-{id(self):x}"
        self._segments: dict[tuple[Any, ...], _Segment] = {}
        self._response_serial = 0
        self._seen_tool_items: set[str] = set()
        self._seen_code_outputs: set[str] = set()
        self.saw_output_text = False

    def enabled(self, categories: str | Collection[str], *event_names: str) -> bool:
        category_names = (
            {categories} if isinstance(categories, str) else set(categories)
        )
        if not self.show_reasoning and "reasoning" in category_names:
            return False
        return self.selector.enabled(categories, *event_names)

    def process_response_event(
        self, event: Any, *, outer_names: tuple[str, ...] = ()
    ) -> Any | None:
        event_type = str(getattr(event, "type", type(event).__name__))
        names = (event_type, *outer_names)

        if event_type == "response.created":
            self.finalize_all()
            self._response_serial += 1

        if event_type in _DELTA_SPECS:
            category, label, language = _DELTA_SPECS[event_type]
            delta = getattr(event, "delta", "")
            if delta:
                self._append_segment(
                    event_type, event, str(delta), category, label, language, names
                )
            return None

        if event_type in _DONE_TO_DELTA:
            family = _DONE_TO_DELTA[event_type]
            category, label, language = _DELTA_SPECS[family]
            value = self._done_value(event)
            self._finish_segment(family, event, value, category, label, language, names)
            if (
                language == "json"
                and not self.show_details
                and self.selector.exact(*names)
            ):
                self.event_card(
                    label or self.label_for_event(event_type),
                    event_type,
                    event,
                    category,
                    summary="ready",
                )
            return None

        if event_type in {"response.content_part.done", "response.output_item.done"}:
            self._finalize_matching(event)

        if event_type in _TERMINAL_EVENTS:
            self.finalize_all()
            response = getattr(event, "response", None)
            terminal_category = (
                "lifecycle" if event_type == "response.completed" else "errors"
            )
            label = {
                "response.completed": "Response completed",
                "response.failed": "Response failed",
                "response.incomplete": "Response incomplete",
            }[event_type]
            if self.enabled(terminal_category, *names):
                self.event_card(
                    label,
                    event_type,
                    {"response": response},
                    terminal_category,
                    summary=self._terminal_summary(response),
                )
            usage = getattr(response, "usage", None)
            if usage is not None and self.enabled("usage", "usage", *names):
                self.event_card(
                    "Usage",
                    "usage",
                    usage,
                    "usage",
                    summary=self._usage_summary(usage),
                )
            return response

        categories = set(self.categories_for_response_event(event_type))
        item = getattr(event, "item", None)
        item_type = str(getattr(item, "type", ""))
        if item_type:
            categories.update(
                self.categories_for_response_event(f"response.{item_type}")
                - {"unknown"}
            )
        if not self.enabled(categories, *names):
            return None

        if (
            event_type == "response.output_item.done"
            and item_type == "code_interpreter_call"
        ):
            self._show_code_interpreter_outputs(item, names)

        compact = self._compact_response_event(event_type, event, item_type)
        if compact is None:
            return None
        label, summary = compact
        primary = self.primary_category(categories)
        self.event_card(
            label,
            event_type,
            event,
            primary,
            summary=summary,
            style_key=self.style_key(primary, event_type, item_type),
        )
        if event_type == "response.output_item.done" and item_type in _TOOL_ITEM_TYPES:
            identity = self._tool_identity(item)
            if identity:
                self._seen_tool_items.add(identity)
        return None

    def process_agent_item(
        self,
        event_name: str,
        item: Any,
        *,
        outer_name: str = "run_item_stream_event",
    ) -> None:
        item_type = str(getattr(item, "type", type(item).__name__))
        raw = getattr(item, "raw_item", None)
        raw_type = str(getattr(raw, "type", ""))
        categories = self.categories_for_agent_item(event_name, item_type, raw_type)
        names = (event_name, item_type, raw_type, outer_name)
        if not self.enabled(categories, *names):
            return

        identity = self._tool_identity(raw) or self._tool_identity(item)
        if event_name == "tool_called" and identity in self._seen_tool_items:
            return
        if event_name == "message_output_created" and not self.selector.exact(
            event_name, outer_name
        ):
            return

        labels = {
            "message_output_created": "Message completed",
            "handoff_requested": "Handoff requested",
            "handoff_occured": "Handoff occurred",
            "tool_called": "Tool called",
            "tool_search_called": "Tool search called",
            "tool_search_output_created": "Tool search result",
            "tool_output": "Tool result",
            "reasoning_item_created": "Reasoning",
            "mcp_approval_requested": "MCP approval requested",
            "mcp_approval_response": "MCP approval response",
            "mcp_list_tools": "MCP tools listed",
        }
        payload = self._agent_item_payload(item, raw, item_type, raw_type)
        label, summary = self._compact_agent_item(
            labels.get(event_name, self.label_for_event(event_name)),
            event_name,
            item,
            raw,
            raw_type,
        )
        primary = self.primary_category(categories)
        self.event_card(
            label,
            event_name,
            payload,
            primary,
            summary=summary,
            style_key=self.style_key(primary, event_name, item_type, raw_type),
        )

    @staticmethod
    def _agent_item_payload(
        item: Any, raw: Any, item_type: str, raw_type: str
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "item_type": item_type,
            "agent": getattr(getattr(item, "agent", None), "name", None),
            "raw_type": raw_type or None,
        }
        for field in (
            "id",
            "name",
            "call_id",
            "status",
            "arguments",
            "action",
            "queries",
            "code",
        ):
            value = getattr(raw, field, None)
            if value is None:
                value = getattr(item, field, None)
            if value is not None:
                payload[field] = value
        output = getattr(item, "output", None)
        if output is not None:
            payload["output"] = output
        for field in ("source_agent", "target_agent"):
            agent = getattr(item, field, None)
            if agent is not None:
                payload[field] = getattr(agent, "name", str(agent))
        return {key: value for key, value in payload.items() if value is not None}

    def process_agent_update(self, event: Any) -> None:
        event_type = str(getattr(event, "type", "agent_updated_stream_event"))
        if not self.enabled(("handoffs", "lifecycle"), event_type):
            return
        agent = getattr(event, "new_agent", None)
        name = getattr(agent, "name", str(agent))
        self.event_card(
            "Agent",
            event_type,
            {"name": name},
            "handoffs",
            summary=name,
        )

    def show_interruption(self, interruption: Any) -> None:
        if self.enabled("approvals", "approval_interruption", "mcp_approval_requested"):
            item_type = str(getattr(interruption, "type", type(interruption).__name__))
            raw = getattr(interruption, "raw_item", None)
            raw_type = str(getattr(raw, "type", ""))
            payload = self._agent_item_payload(interruption, raw, item_type, raw_type)
            summary = self._tool_summary(raw or interruption, raw_type or item_type)
            self.event_card(
                "Approval required",
                "approval_interruption",
                payload,
                "approvals",
                summary=summary,
            )

    def ensure_final_output(self, value: Any) -> None:
        if (
            value is None
            or self.saw_output_text
            or not self.enabled("text", "final_output")
        ):
            return
        if isinstance(value, str):
            if not value.strip():
                return
            display(self._styled_markdown(value, "text"))
            self.saw_output_text = True
            return
        display(
            self._styled_markdown(
                self.fenced(self._json_text(value), "json", label="Final output"),
                "text",
            )
        )
        self.saw_output_text = True

    def show_exception(self, error: BaseException) -> None:
        self.finalize_all()
        if self.enabled("errors", "exception"):
            self.event_card(
                "Streaming error",
                "exception",
                {"type": type(error).__name__, "message": str(error)},
                "errors",
                summary=f"{type(error).__name__}: {error}",
            )

    def finalize_all(self) -> None:
        for key in list(self._segments):
            self._finalize_segment(key)

    def event_card(
        self,
        label: str,
        event_name: str,
        payload: Any,
        category: str,
        *,
        summary: str | None = None,
        style_key: str | None = None,
    ) -> None:
        style_key = style_key or self.style_key(category, event_name)
        color = self.colormap.get(style_key, self.colormap["unknown"])
        safe_label = html.escape(label)
        compact = self._truncate_compact(summary or "")
        inline = f" <span>{html.escape(compact)}</span>" if compact else ""
        event_tag = (
            f" <code style='color:#64748b'>{html.escape(event_name)}</code>"
            if self.show_details
            else ""
        )
        body = ""
        if self.show_details:
            details = self._payload_text(payload)
            if details and details not in {"{}", "null"}:
                body = (
                    "<pre style='margin:0.35rem 0 0;white-space:pre-wrap;"
                    "word-break:break-word'>"
                    f"{html.escape(details)}</pre>"
                )
        if not compact and not body:
            return
        display(
            HTML(
                f"<div style='border-left:3px solid {color};color:{color};"
                "padding:0.3rem 0.65rem;"
                "margin:0.3rem 0;line-height:1.4'>"
                f"<strong>{safe_label}</strong>{inline}{event_tag}{body}</div>"
            )
        )

    @staticmethod
    def style_key(category: str, *names: str) -> str:
        """Return the most specific colormap key for an event or segment."""

        value = " ".join(names).lower()
        if "code_interpreter" in value:
            return "code_interpreter"
        if "shell" in value:
            return "shell"
        if any(name in value for name in ("web_search", "file_search", "tool_search")):
            return "search"
        return category

    @staticmethod
    def categories_for_response_event(event_type: str) -> frozenset[str]:
        if event_type in _DELTA_SPECS:
            return frozenset({_DELTA_SPECS[event_type][0]})
        if event_type in _DONE_TO_DELTA:
            return frozenset({_DELTA_SPECS[_DONE_TO_DELTA[event_type]][0]})
        lower = event_type.lower()
        categories: set[str] = set()
        if (
            "error" in lower
            or "failed" in lower
            or "incomplete" in lower
            or "refusal" in lower
        ):
            categories.add("errors")
        if "reasoning" in lower:
            categories.add("reasoning")
        if "web_search" in lower or "file_search" in lower or "tool_search" in lower:
            categories.update(("search", "tools"))
        if "code_interpreter" in lower or "shell" in lower or "apply_patch" in lower:
            categories.update(("code", "tools"))
        if "function_call" in lower or "custom_tool" in lower or "mcp" in lower:
            categories.add("tools")
        if "audio" in lower or "image_gen" in lower or "image_generation" in lower:
            categories.add("media")
        if "output_text" in lower or "annotation" in lower:
            categories.add("text")
        if lower.startswith("response.") and any(
            token in lower
            for token in (
                "created",
                "queued",
                "in_progress",
                "completed",
                "compaction",
                "content_part",
                "output_item",
                "steer",
            )
        ):
            categories.add("lifecycle")
        if not categories:
            categories.add("unknown")
        return frozenset(categories)

    @staticmethod
    def categories_for_agent_item(
        event_name: str, item_type: str, raw_type: str
    ) -> frozenset[str]:
        value = f"{event_name} {item_type} {raw_type}".lower()
        categories: set[str] = set()
        if "handoff" in value:
            categories.add("handoffs")
        if "approval" in value:
            categories.add("approvals")
        if "reasoning" in value:
            categories.add("reasoning")
        if "message" in value:
            categories.add("text")
        if "search" in value:
            categories.update(("search", "tools"))
        if "code_interpreter" in value or "shell" in value or "computer" in value:
            categories.update(("code", "tools"))
        if "tool" in value or "function" in value or "mcp" in value:
            categories.add("tools")
        if not categories:
            categories.add("unknown")
        return frozenset(categories)

    @staticmethod
    def primary_category(categories: Collection[str]) -> str:
        priority = (
            "errors",
            "approvals",
            "handoffs",
            "code",
            "search",
            "tools",
            "reasoning",
            "media",
            "text",
            "usage",
            "lifecycle",
            "unknown",
        )
        return next((name for name in priority if name in categories), "unknown")

    @staticmethod
    def label_for_event(event_type: str) -> str:
        label = (
            event_type.removeprefix("response.").replace("_", " ").replace(".", " · ")
        )
        return label[:1].upper() + label[1:]

    @staticmethod
    def fenced(text: str, language: str, *, label: str | None = None) -> str:
        longest = max(
            (len(match.group(0)) for match in re.finditer(r"`+", text)), default=0
        )
        fence = "`" * max(3, longest + 1)
        heading = f"**{label}**\n\n" if label else ""
        return f"{heading}{fence}{language}\n{text}\n{fence}"

    def _append_segment(
        self,
        family: str,
        event: Any,
        delta: str,
        category: str,
        label: str | None,
        language: str | None,
        names: tuple[str, ...],
    ) -> None:
        key = self._segment_key(family, event)
        style_key = self.style_key(category, family)
        segment = self._segments.setdefault(
            key, _Segment(category, style_key, label, language)
        )
        segment.text += delta
        can_render = language != "json" or self.show_details
        segment.visible = segment.visible or (
            can_render and self.enabled(category, *names)
        )
        if family == "response.output_text.delta":
            self.saw_output_text = True
        if segment.visible and segment.text.strip():
            self._update_live(segment)

    def _finish_segment(
        self,
        family: str,
        event: Any,
        value: str | None,
        category: str,
        label: str | None,
        language: str | None,
        names: tuple[str, ...],
    ) -> None:
        key = self._segment_key(family, event)
        style_key = self.style_key(category, family)
        segment = self._segments.setdefault(
            key, _Segment(category, style_key, label, language)
        )
        if value is not None:
            segment.text = value
        can_render = language != "json" or self.show_details
        segment.visible = segment.visible or (
            can_render and self.enabled(category, *names)
        )
        if family == "response.output_text.delta" and segment.text:
            self.saw_output_text = True
        self._finalize_segment(key)

    def _update_live(self, segment: _Segment) -> None:
        label = (
            f"<strong>{html.escape(segment.label)}</strong>" if segment.label else ""
        )
        color = self.colormap.get(segment.style_key, self.colormap["unknown"])
        obj = HTML(
            f"<div style='border-left:3px solid {color};color:{color};"
            "line-height:1.5;"
            "padding:0.35rem 0.65rem;margin:0.35rem 0'>"
            f"{label}<pre style='margin:0;white-space:pre-wrap;word-break:break-word'>"
            f"{html.escape(segment.text)}</pre></div>"
        )
        if segment.handle is None:
            segment.handle = display(obj, display_id=True)
        elif hasattr(segment.handle, "update"):
            segment.handle.update(obj)

    def _finalize_segment(self, key: tuple[Any, ...]) -> None:
        segment = self._segments.get(key)
        if segment is None or segment.finalized:
            return
        segment.finalized = True
        if not segment.visible:
            return
        text = segment.text
        if not text.strip():
            return
        if segment.language == "json":
            text = self._pretty_json_string(text)
        if segment.language:
            rendered = self.fenced(text, segment.language, label=segment.label)
        elif segment.label:
            rendered = f"**{segment.label}**\n\n{text}"
        else:
            rendered = text
        obj = self._styled_markdown(rendered, segment.style_key)
        if segment.handle is not None and hasattr(segment.handle, "update"):
            segment.handle.update(obj)
        else:
            display(obj)

    def _styled_markdown(self, rendered: str, style_key: str) -> Markdown:
        color = html.escape(
            self.colormap.get(style_key, self.colormap["unknown"]), quote=True
        )
        marker = f"{self._style_marker}-{style_key.replace('_', '-')}"
        selector = f".{marker} ~ *"
        prefix = (
            f"<style>{selector}{{color:{color};line-height:1.5}}</style>"
            f"<div class='{marker}' style='display:none'></div>"
        )
        return Markdown(f"{prefix}\n\n{rendered}")

    def _finalize_matching(self, event: Any) -> None:
        item_id = getattr(event, "item_id", None)
        output_index = getattr(event, "output_index", None)
        content_index = getattr(event, "content_index", None)
        item = getattr(event, "item", None)
        if item_id is None:
            item_id = getattr(item, "id", None)
        for key in list(self._segments):
            _serial, _family, key_item, key_output, key_content, _command = key
            if item_id is not None and key_item != item_id:
                continue
            if (
                item_id is None
                and output_index is not None
                and key_output != output_index
            ):
                continue
            if content_index is not None and key_content != content_index:
                continue
            self._finalize_segment(key)

    def _segment_key(self, family: str, event: Any) -> tuple[Any, ...]:
        return (
            self._response_serial,
            family,
            getattr(event, "item_id", None),
            getattr(event, "output_index", None),
            getattr(event, "content_index", None),
            getattr(event, "command_index", None),
        )

    def _compact_response_event(
        self, event_type: str, event: Any, item_type: str
    ) -> tuple[str, str | None] | None:
        if (
            event_type
            in {
                "response.reasoning_summary_part.added",
                "response.reasoning_summary_part.done",
            }
            and not self.show_details
        ):
            return None
        if (
            event_type in {"response.output_item.added", "response.content_part.added"}
            and not self.show_details
            and self.selector.is_default
        ):
            return None
        if event_type == "response.output_item.added":
            if item_type == "message":
                return "Message started", None
            item = getattr(event, "item", None)
            return self._tool_label(item_type), self._tool_summary(item, item_type)
        if (
            event_type == "response.content_part.done"
            and not self.show_details
            and self.selector.is_default
        ):
            return None
        if event_type == "response.output_item.done":
            if item_type == "message":
                if not self.show_details and self.selector.is_default:
                    return None
                return "Message completed", None
            item = getattr(event, "item", None)
            if (
                item_type == "code_interpreter_call"
                and getattr(item, "outputs", None)
                and not self.show_details
            ):
                return None
            return self._tool_label(item_type), self._tool_summary(item, item_type)

        status_events = {
            "response.web_search_call.in_progress": ("Web search", "starting…"),
            "response.web_search_call.searching": ("Web search", "searching…"),
            "response.web_search_call.completed": ("Web search", "completed"),
            "response.file_search_call.in_progress": ("File search", "starting…"),
            "response.file_search_call.searching": ("File search", "searching…"),
            "response.file_search_call.completed": ("File search", "completed"),
            "response.code_interpreter_call.in_progress": (
                "Code Interpreter",
                "starting…",
            ),
            "response.code_interpreter_call.interpreting": (
                "Code Interpreter",
                "running Python…",
            ),
            "response.code_interpreter_call.completed": (
                "Code Interpreter",
                "completed",
            ),
        }
        if event_type in status_events:
            if (
                event_type
                in {
                    "response.web_search_call.searching",
                    "response.file_search_call.searching",
                    "response.code_interpreter_call.in_progress",
                    "response.code_interpreter_call.interpreting",
                    "response.code_interpreter_call.completed",
                }
                and not self.show_details
            ):
                return None
            label, summary = status_events[event_type]
            noisy = event_type.endswith((".in_progress", ".completed"))
            if noisy and not self.show_details and self.selector.is_default:
                return None
            return label, summary
        if event_type == "response.output_text.annotation.added":
            annotation = getattr(event, "annotation", None)
            title = getattr(annotation, "title", None)
            url = getattr(annotation, "url", None)
            return "Citation", " — ".join(value for value in (title, url) if value)
        if event_type == "response.error":
            return "Response error", str(getattr(event, "message", ""))
        return self.label_for_event(event_type), self._scalar_summary(event)

    def _show_code_interpreter_outputs(
        self, item: Any, names: tuple[str, ...]
    ) -> None:
        if not self.enabled("code", *names):
            return
        identity = self._tool_identity(item) or str(id(item))
        if identity in self._seen_code_outputs:
            return

        outputs = getattr(item, "outputs", None) or ()
        rendered = False
        for index, output in enumerate(outputs):
            data = _object_mapping(output)
            output_type = str(getattr(output, "type", data.get("type", "")))
            logs = getattr(output, "logs", data.get("logs"))
            if output_type == "logs" and isinstance(logs, str) and logs.strip():
                text = self._truncate_text(logs)
                display(
                    self._styled_markdown(
                        self.fenced(text, "text", label="Python output"),
                        "code_interpreter",
                    )
                )
                rendered = True
                continue

            url = getattr(output, "url", data.get("url"))
            if output_type == "image" and url:
                self.event_card(
                    "Python image output",
                    f"code_interpreter.output.{index}",
                    output,
                    "code",
                    summary=str(url),
                    style_key="code_interpreter",
                )
                rendered = True

        if rendered:
            self._seen_code_outputs.add(identity)

    def _compact_agent_item(
        self,
        label: str,
        event_name: str,
        item: Any,
        raw: Any,
        raw_type: str,
    ) -> tuple[str, str | None]:
        if event_name == "message_output_created":
            return label, "completed"
        if event_name == "tool_called":
            return self._tool_label(raw_type), self._tool_summary(raw, raw_type)
        if event_name in {"tool_output", "tool_search_output_created"}:
            return label, self._compact_value(getattr(item, "output", None))
        if event_name in {"handoff_requested", "handoff_occured"}:
            source = getattr(getattr(item, "source_agent", None), "name", None)
            target = getattr(getattr(item, "target_agent", None), "name", None)
            return label, " → ".join(value for value in (source, target) if value)
        if event_name == "reasoning_item_created":
            summary = getattr(raw, "summary", None)
            return label, self._compact_value(summary)
        return label, self._scalar_summary(raw or item)

    @staticmethod
    def _tool_label(item_type: str) -> str:
        labels = {
            "web_search_call": "Web search",
            "file_search_call": "File search",
            "code_interpreter_call": "Code Interpreter",
            "shell_call": "Shell",
            "computer_call": "Computer tool",
            "function_call": "Function",
            "custom_tool_call": "Custom tool",
            "mcp_call": "MCP tool",
            "image_generation_call": "Image generation",
        }
        return labels.get(item_type, "Tool")

    def _tool_summary(self, item: Any, item_type: str) -> str | None:
        if item is None:
            return None
        if item_type == "web_search_call":
            action = getattr(item, "action", None)
            query = getattr(action, "query", None)
            queries = getattr(action, "queries", None)
            return self._compact_value(query or queries) or "completed"
        if item_type == "file_search_call":
            return self._compact_value(getattr(item, "queries", None)) or "completed"
        if item_type in {"function_call", "custom_tool_call", "mcp_call"}:
            name = getattr(item, "name", None) or getattr(item, "server_label", None)
            arguments = getattr(item, "arguments", None)
            return self._format_call(name or item_type, arguments)
        if item_type == "code_interpreter_call":
            status = getattr(item, "status", None)
            outputs = getattr(item, "outputs", None)
            suffix = f" · {len(outputs)} output(s)" if outputs else ""
            return f"{status or 'completed'}{suffix}"
        status = getattr(item, "status", None)
        name = getattr(item, "name", None)
        return self._compact_value(name or status)

    def _format_call(self, name: str, arguments: Any) -> str:
        if arguments in (None, ""):
            return f"{name}()"
        parsed = arguments
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except (json.JSONDecodeError, TypeError):
                parsed = arguments
        if isinstance(parsed, Mapping):
            parts = [
                f"{key}={self._compact_value(value)}"
                for key, value in list(parsed.items())[:5]
            ]
            if len(parsed) > 5:
                parts.append("…")
            return f"{name}({', '.join(parts)})"
        return f"{name}({self._compact_value(parsed)})"

    @staticmethod
    def _tool_identity(item: Any) -> str | None:
        if item is None:
            return None
        value = getattr(item, "call_id", None) or getattr(item, "id", None)
        return str(value) if value else None

    def _scalar_summary(self, payload: Any) -> str | None:
        data = _object_mapping(payload)
        values: list[str] = []
        for key in (
            "message",
            "name",
            "status",
            "query",
            "value",
            "item_id",
            "output_index",
        ):
            value = data.get(key)
            if value not in (None, ""):
                values.append(f"{key}={self._compact_value(value)}")
            if len(values) == 3:
                break
        if not values and data.get("response") is not None:
            response = _object_mapping(data["response"])
            for key in ("status", "id"):
                value = response.get(key)
                if value not in (None, ""):
                    values.append(f"{key}={self._compact_value(value)}")
        return " · ".join(values) or None

    def _compact_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            result = " ".join(value.split())
        elif isinstance(value, Mapping):
            result = ", ".join(
                f"{key}={self._compact_value(item)}"
                for key, item in list(value.items())[:5]
            )
        elif isinstance(value, Sequence) and not isinstance(
            value, (bytes, bytearray, memoryview)
        ):
            result = ", ".join(self._compact_value(item) for item in value[:5])
        else:
            data = _object_mapping(value)
            result = self._compact_value(data) if data else str(value)
        return self._truncate_compact(result)

    def _truncate_compact(self, value: str) -> str:
        if self.max_chars is None or len(value) <= self.max_chars:
            return value
        omitted = len(value) - self.max_chars
        return f"{value[: self.max_chars]} … ({omitted} characters omitted)"

    def _truncate_text(self, value: str) -> str:
        if self.max_chars is None or len(value) <= self.max_chars:
            return value
        omitted = len(value) - self.max_chars
        return f"{value[: self.max_chars]}\n… truncated {omitted} characters"

    @staticmethod
    def _terminal_summary(response: Any) -> str | None:
        error = getattr(response, "error", None)
        incomplete = getattr(response, "incomplete_details", None)
        value = error or incomplete
        if value is not None:
            message = getattr(value, "message", None) or getattr(value, "reason", None)
            return str(message or value)
        status = getattr(response, "status", None)
        response_id = getattr(response, "id", None)
        if status is not None:
            return str(status)
        return str(response_id) if response_id is not None else None

    @staticmethod
    def _usage_summary(usage: Any) -> str | None:
        total = getattr(usage, "total_tokens", None)
        inputs = getattr(usage, "input_tokens", None)
        outputs = getattr(usage, "output_tokens", None)
        parts = []
        if total is not None:
            parts.append(f"{total} total")
        if inputs is not None:
            parts.append(f"{inputs} input")
        if outputs is not None:
            parts.append(f"{outputs} output")
        return " · ".join(parts) or None

    @staticmethod
    def _done_value(event: Any) -> str | None:
        for field in _DONE_VALUE_FIELDS:
            value = getattr(event, field, None)
            if value is not None:
                if isinstance(value, str):
                    return value
                return json.dumps(_safe_value(value), ensure_ascii=False)
        return None

    def _payload_text(self, payload: Any) -> str:
        text = self._json_text(self._summarize_payload(payload))
        if self.max_chars is not None and len(text) > self.max_chars:
            omitted = len(text) - self.max_chars
            return f"{text[: self.max_chars]}\n… truncated {omitted} characters"
        return text

    @staticmethod
    def _json_text(value: Any) -> str:
        return json.dumps(
            _safe_value(value), ensure_ascii=False, indent=2, sort_keys=True
        )

    @staticmethod
    def _pretty_json_string(value: str) -> str:
        try:
            return json.dumps(
                json.loads(value), ensure_ascii=False, indent=2, sort_keys=True
            )
        except (json.JSONDecodeError, TypeError):
            return value

    @staticmethod
    def _summarize_payload(payload: Any) -> Any:
        if payload is None or isinstance(
            payload, (str, int, float, bool, bytes, bytearray)
        ):
            return payload
        data = _object_mapping(payload)
        if not data:
            return str(payload)
        data.pop("sequence_number", None)
        data.pop("obfuscation", None)
        data.pop("type", None)
        if "response" in data:
            response_data = _object_mapping(data["response"])
            data["response"] = {
                key: response_data.get(key)
                for key in ("id", "status", "model", "error", "incomplete_details")
                if response_data.get(key) is not None
            }
        if "item" in data:
            item_data = _object_mapping(data["item"])
            data["item"] = {
                key: item_data.get(key)
                for key in (
                    "id",
                    "type",
                    "status",
                    "name",
                    "call_id",
                    "action",
                    "queries",
                    "arguments",
                    "code",
                    "outputs",
                    "results",
                )
                if item_data.get(key) is not None
            }
        if "part" in data:
            part_data = _object_mapping(data["part"])
            text = part_data.get("text")
            annotations = part_data.get("annotations")
            data["part"] = {
                key: part_data.get(key)
                for key in ("type", "valid")
                if part_data.get(key) is not None
            }
            if isinstance(text, str):
                data["part"]["text_chars"] = len(text)
            if isinstance(annotations, Sequence):
                data["part"]["annotations"] = len(annotations)
        return data


def _object_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: getattr(value, field.name)
            for field in dataclasses.fields(value)
        }
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return dict(model_dump(mode="python"))
        except TypeError:
            return dict(model_dump())
    attrs = getattr(value, "__dict__", None)
    if isinstance(attrs, dict):
        return {key: item for key, item in attrs.items() if not key.startswith("_")}
    return {}


def _safe_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "<maximum depth reached>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<binary data: {len(value)} bytes>"
    if isinstance(value, str):
        compact = value.replace("\r", "").replace("\n", "")
        if len(compact) > 256 and _BASE64_RE.fullmatch(compact):
            return f"<encoded data: {len(value)} characters>"
        return value
    if isinstance(value, Mapping):
        items = list(value.items())
        result = {
            str(key): _safe_value(item, depth=depth + 1)
            for key, item in items[:50]
            if str(key) not in {"obfuscation"}
        }
        if len(items) > 50:
            result["…"] = f"{len(items) - 50} more entries"
        return result
    if isinstance(value, Sequence):
        result = [_safe_value(item, depth=depth + 1) for item in value[:50]]
        if len(value) > 50:
            result.append(f"<{len(value) - 50} more items>")
        return result
    data = _object_mapping(value)
    if data:
        return _safe_value(data, depth=depth + 1)
    return str(value)


__all__ = [
    "DEFAULT_COLORMAP",
    "DEFAULT_EVENT_CATEGORIES",
    "EVENT_CATEGORIES",
    "EventSelector",
    "NotebookRenderer",
]
