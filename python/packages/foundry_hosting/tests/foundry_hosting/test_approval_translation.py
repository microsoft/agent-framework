# Copyright (c) Microsoft. All rights reserved.

"""Responses approval translation against the read-only lookup and staging recorder protocols."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from agent_framework import Content
from azure.ai.agentserver.responses.aio import ResponseEventStream
from azure.ai.agentserver.responses.models import (
    OutputItemMcpApprovalRequest,
    OutputItemMcpApprovalResponseResource,
)

from agent_framework_foundry_hosting._responses_shared import (
    _output_items_to_messages,
    _OutputItemTracker,
    _PublicResponseFailure,
)


def _approval_request(request_id: str = "orig-1") -> Content:
    return Content.from_function_approval_request(
        id=request_id,
        function_call=Content.from_function_call("call-1", "dangerous", arguments='{"x": 1}'),
    )


class _RecordingLookup:
    """Read-only lookup that records every access and exposes no mutating method."""

    def __init__(self, requests: Mapping[str, Content]) -> None:
        self._requests = dict(requests)
        self.loads: list[str] = []

    async def load_approval_request(self, approval_request_id: str) -> Content:
        self.loads.append(approval_request_id)
        return self._requests[approval_request_id]


class _OrderedRecorder:
    def __init__(self, log: list[str]) -> None:
        self._log = log
        self.saved: list[tuple[str, Content]] = []

    async def save_approval_request(self, approval_request_id: str, request: Content) -> None:
        self._log.append(f"save:{approval_request_id}")
        self.saved.append((approval_request_id, request))


def _event_type(event: Any) -> str:
    return event.get("type") if isinstance(event, Mapping) else event.type


async def test_history_conversion_only_reads_approval_requests() -> None:
    lookup = _RecordingLookup({"wire-1": _approval_request()})
    items = [
        OutputItemMcpApprovalRequest({
            "type": "mcp_approval_request",
            "id": "wire-1",
            "server_label": "srv",
            "name": "dangerous",
            "arguments": "{}",
        }),
        OutputItemMcpApprovalResponseResource({
            "type": "mcp_approval_response",
            "id": "resp-1",
            "approval_request_id": "wire-1",
            "approve": False,
        }),
    ]

    messages = await _output_items_to_messages(items, approval_storage=lookup)  # type: ignore[arg-type]

    assert lookup.loads == ["wire-1", "wire-1"]
    assert not hasattr(lookup, "save_approval_request")
    assert messages[0].contents[0].type == "function_approval_request"
    assert messages[1].contents[0].type == "function_approval_response"
    assert messages[1].contents[0].approved is False


async def test_history_conversion_rejects_unknown_approval_ids() -> None:
    lookup = _RecordingLookup({})
    item = OutputItemMcpApprovalResponseResource({
        "type": "mcp_approval_response",
        "id": "resp-1",
        "approval_request_id": "missing",
        "approve": True,
    })

    with pytest.raises(_PublicResponseFailure):
        await _output_items_to_messages([item], approval_storage=lookup)  # type: ignore[arg-type]


async def test_history_conversion_requires_lookup() -> None:
    item = OutputItemMcpApprovalResponseResource({
        "type": "mcp_approval_response",
        "id": "resp-1",
        "approval_request_id": "wire-1",
        "approve": True,
    })

    with pytest.raises(ValueError, match="ApprovalStorage is required"):
        await _output_items_to_messages([item])


async def test_tracker_records_approval_before_yielding_its_events() -> None:
    stream = ResponseEventStream(response_id="resp_approval")
    stream.emit_created()
    stream.emit_in_progress()
    tracker = _OutputItemTracker(stream)
    log: list[str] = []
    recorder = _OrderedRecorder(log)
    request = _approval_request()

    async for event in tracker.handle(request, approval_storage=recorder):
        log.append(_event_type(event))
    log.extend(_event_type(event) for event in tracker.close())

    assert len(recorder.saved) == 1
    wire_id, saved = recorder.saved[0]
    assert wire_id
    assert saved is request
    assert log[0] == f"save:{wire_id}"
    assert "response.output_item.added" in log[1:]


async def test_tracker_fails_explicitly_without_generated_approval_id(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = ResponseEventStream(response_id="resp_approval")
    stream.emit_created()
    stream.emit_in_progress()

    async def _events_without_id(*_: Any, **__: Any) -> Any:
        yield {"type": "response.output_item.added", "item": {"type": "mcp_approval_request"}}

    monkeypatch.setattr(stream, "output_item_mcp_approval_request", _events_without_id)
    tracker = _OutputItemTracker(stream)
    recorder = _OrderedRecorder([])

    with pytest.raises(RuntimeError, match="approval request ID could not be extracted"):
        async for _ in tracker.handle(_approval_request(), approval_storage=recorder):
            pass

    assert recorder.saved == []
