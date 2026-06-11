# Copyright (c) Microsoft. All rights reserved.

"""SSE parsing helpers for AG-UI HTTP round-trip tests."""

from __future__ import annotations

import json
from typing import Any

from event_stream import EventStream


def parse_sse_response(response_content: bytes) -> list[dict[str, Any]]:
    """Parse raw SSE bytes from TestClient into a list of event dicts.

    Each SSE event is a ``data: {...}`` line followed by a blank line.
    """
    text = response_content.decode("utf-8")
    events: list[dict[str, Any]] = []
    decode_errors: list[str] = []
    for line in text.splitlines():
        if line.startswith("data: "):
            payload = line[6:]
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError as exc:
                decode_errors.append(f"payload={payload!r}, error={exc}")
                continue
    if decode_errors:
        joined = "; ".join(decode_errors)
        raise AssertionError(f"Failed to decode one or more SSE data lines: {joined}")
    return events


def parse_sse_to_event_stream(response_content: bytes) -> EventStream:
    """Parse SSE bytes and wrap in EventStream for structured assertions.

    Returns an EventStream over lightweight SimpleNamespace objects that
    mirror AG-UI event attributes (type, message_id, tool_call_id, etc.)
    so that EventStream assertion methods work.
    """
    from types import SimpleNamespace

    raw_events = parse_sse_response(response_content)
    events: list[Any] = []
    for raw in raw_events:
        # Normalize camelCase keys to snake_case attributes that EventStream expects
        ns = SimpleNamespace()
        ns.type = raw.get("type", "")
        ns.raw = raw
        # Map common camelCase fields
        for camel, snake in _FIELD_MAP.items():
            if camel in raw:
                setattr(ns, snake, raw[camel])
        # Also keep camelCase as attributes for direct access
        for key, value in raw.items():
            if not hasattr(ns, key):
                setattr(ns, key, value)
        events.append(ns)
    return EventStream(events)


_FIELD_MAP: dict[str, str] = {
    "messageId": "message_id",
    "runId": "run_id",
    "threadId": "thread_id",
    "toolCallId": "tool_call_id",
    "toolCallName": "tool_call_name",
    "toolName": "tool_call_name",
    "parentMessageId": "parent_message_id",
    "stepName": "step_name",
}
