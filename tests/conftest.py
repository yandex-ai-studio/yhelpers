from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest


@dataclass
class FakeHandle:
    updates: list[Any] = field(default_factory=list)

    def update(self, value: Any) -> None:
        self.updates.append(value)


@dataclass
class DisplayCall:
    value: Any
    display_id: bool
    handle: FakeHandle | None


@dataclass
class DisplayCapture:
    calls: list[DisplayCall] = field(default_factory=list)

    def display(self, value: Any, *, display_id: bool = False) -> FakeHandle | None:
        handle = FakeHandle() if display_id else None
        self.calls.append(DisplayCall(value, display_id, handle))
        return handle

    @property
    def handles(self) -> list[FakeHandle]:
        return [call.handle for call in self.calls if call.handle is not None]


@pytest.fixture
def display_capture(monkeypatch: pytest.MonkeyPatch) -> DisplayCapture:
    from yhelpers.common import streaming

    capture = DisplayCapture()
    monkeypatch.setattr(streaming, "display", capture.display)
    return capture
