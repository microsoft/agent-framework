# Copyright (c) Microsoft. All rights reserved.

"""EventStream assertion helper for AG-UI regression tests."""

from __future__ import annotations

from typing import Any


class EventStream:
    """Wraps a list of AG-UI events with structured assertion methods.

    Usage:
        events = [event async for event in agent.run(payload)]
        stream = EventStream(events)
        stream.assert_bookends()
        stream.assert_text_messages_balanced()
    """

    def __init__(self, events: list[Any]) -> None:
        self.events = events

    def __len__(self) -> int:
        return len(self.events)

    def __iter__(self):
        return iter(self.events)

    def types(self) -> list[str]:
        """Return ordered list of event type strings."""
        return [self._type_str(e) for e in self.events]

    def get(self, event_type: str) -> list[Any]:
        """Filter events matching the given type string."""
        return [e for e in self.events if self._type_str(e) == event_type]

    def first(self, event_type: str) -> Any:
        """Return the first event matching the given type, or raise."""
        matches = self.get(event_type)
        if not matches:
            raise ValueError(f"No event of type {event_type!r} found. Available: {self.types()}")
        return matches[0]

    def last(self, event_type: str) -> Any:
        """Return the last event matching the given type, or raise."""
        matches = self.get(event_type)
        if not matches:
            raise ValueError(f"No event of type {event_type!r} found. Available: {self.types()}")
        return matches[-1]

    def snapshot(self) -> dict[str, Any]:
        """Return the latest StateSnapshotEvent snapshot dict."""
        return self.last("STATE_SNAPSHOT").snapshot

    def messages_snapshot(self) -> list[Any]:
        """Return the latest MessagesSnapshotEvent messages list."""
        return self.last("MESSAGES_SNAPSHOT").messages

    # ── Structural assertions ──

    def assert_bookends(self) -> None:
        """Assert first event is RUN_STARTED and last is RUN_FINISHED."""
        types = self.types()
        assert types, "Event stream is empty"
        assert types[0] == "RUN_STARTED", f"Expected RUN_STARTED first, got {types[0]}"
        assert types[-1] == "RUN_FINISHED", f"Expected RUN_FINISHED last, got {types[-1]}"

    def assert_has_run_lifecycle(self) -> None:
        """Assert RUN_STARTED is first and RUN_FINISHED exists (may not be last).

        Use this instead of assert_bookends() for workflow resume streams where
        _drain_open_message() can emit TEXT_MESSAGE_END after RUN_FINISHED.
        """
        types = self.types()
        assert types, "Event stream is empty"
        assert types[0] == "RUN_STARTED", f"Expected RUN_STARTED first, got {types[0]}"
        assert "RUN_FINISHED" in types, f"Expected RUN_FINISHED in stream. Types: {types}"

    def assert_strict_types(self, expected: list[str]) -> None:
        """Assert exact type sequence match."""
        actual = self.types()
        assert actual == expected, f"Event type mismatch.\nExpected: {expected}\nActual:   {actual}"

    def assert_ordered_types(self, expected: list[str]) -> None:
        """Assert expected types appear as a subsequence (in order, not necessarily contiguous)."""
        actual = self.types()
        actual_idx = 0
        for expected_type in expected:
            found = False
            while actual_idx < len(actual):
                if actual[actual_idx] == expected_type:
                    actual_idx += 1
                    found = True
                    break
                actual_idx += 1
            if not found:
                raise AssertionError(
                    f"Expected subsequence type {expected_type!r} not found after index {actual_idx}.\n"
                    f"Expected subsequence: {expected}\n"
                    f"Actual types: {actual}"
                )

    def assert_text_messages_balanced(self) -> None:
        """Assert every TEXT_MESSAGE_START has a matching TEXT_MESSAGE_END with the same message_id."""
        starts: dict[str, int] = {}
        ends: set[str] = set()
        for i, event in enumerate(self.events):
            t = self._type_str(event)
            if t == "TEXT_MESSAGE_START":
                mid = event.message_id
                assert mid not in starts, f"Duplicate TEXT_MESSAGE_START for message_id={mid}"
                starts[mid] = i
            elif t == "TEXT_MESSAGE_END":
                mid = event.message_id
                assert mid in starts, f"TEXT_MESSAGE_END for unknown message_id={mid}"
                assert mid not in ends, f"Duplicate TEXT_MESSAGE_END for message_id={mid}"
                ends.add(mid)

        unclosed = set(starts.keys()) - ends
        assert not unclosed, f"Unclosed text messages: {unclosed}"

    def assert_tool_calls_balanced(self) -> None:
        """Assert every TOOL_CALL_START has a matching TOOL_CALL_END with the same tool_call_id."""
        starts: dict[str, int] = {}
        ends: set[str] = set()
        for i, event in enumerate(self.events):
            t = self._type_str(event)
            if t == "TOOL_CALL_START":
                tid = event.tool_call_id
                assert tid not in starts, f"Duplicate TOOL_CALL_START for tool_call_id={tid}"
                starts[tid] = i
            elif t == "TOOL_CALL_END":
                tid = event.tool_call_id
                assert tid in starts, f"TOOL_CALL_END for unknown tool_call_id={tid}"
                assert tid not in ends, f"Duplicate TOOL_CALL_END for tool_call_id={tid}"
                ends.add(tid)

        unclosed = set(starts.keys()) - ends
        assert not unclosed, f"Unclosed tool calls: {unclosed}"

    def assert_no_run_error(self) -> None:
        """Assert no RUN_ERROR events exist."""
        errors = self.get("RUN_ERROR")
        if errors:
            messages = [getattr(e, "message", str(e)) for e in errors]
            raise AssertionError(f"Found {len(errors)} RUN_ERROR event(s): {messages}")

    def assert_has_type(self, event_type: str) -> None:
        """Assert at least one event of the given type exists."""
        assert event_type in self.types(), f"Expected {event_type!r} in stream. Available: {self.types()}"

    def assert_message_ids_consistent(self) -> None:
        """Assert TEXT_MESSAGE_CONTENT events reference valid, open message_ids."""
        open_messages: set[str] = set()
        for event in self.events:
            t = self._type_str(event)
            if t == "TEXT_MESSAGE_START":
                open_messages.add(event.message_id)
            elif t == "TEXT_MESSAGE_END":
                open_messages.discard(event.message_id)
            elif t == "TEXT_MESSAGE_CONTENT":
                mid = event.message_id
                assert mid in open_messages, f"TEXT_MESSAGE_CONTENT references message_id={mid} which is not open"

    # ── Internal ──

    @staticmethod
    def _type_str(event: Any) -> str:
        """Extract event type as a plain string."""
        t = getattr(event, "type", None)
        if t is None:
            return type(event).__name__
        if isinstance(t, str):
            return t
        return getattr(t, "value", str(t))
