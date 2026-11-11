# Copyright (c) Microsoft. All rights reserved.

"""Responses approval translation and output staging."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from agent_framework import AgentSession
from azure.ai.agentserver.responses.aio import ResponseEventStream
from azure.ai.agentserver.responses.models import (
    Item,
    ItemMcpApprovalRequest,
    MCPApprovalResponse,
    OutputItem,
    OutputItemMcpApprovalRequest,
    OutputItemMcpApprovalResponseResource,
)

from agent_framework_foundry_hosting._approvals import SessionApprovalState
from agent_framework_foundry_hosting._responses_shared import (
    _items_to_messages,
    _output_items_to_messages,
    _OutputItemTracker,
    _PublicResponseFailure,
)

from .approval_helpers import (  # pyrefly: ignore[missing-import] - pytest's importlib namespace
    SqliteSessionStore,
    approval_request,
    pending_session,
)
from .approval_translation_helpers import (  # pyrefly: ignore[missing-import] - pytest's importlib namespace
    _approval_request,
    _event_type,
    _events_without_id,
    _OrderedRecorder,
)


@pytest.mark.parametrize("approved", [True, False])
async def test_history_and_input_conversions_only_read_approval_state(tmp_path: Path, approved: bool) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    session = await pending_session(store)
    state = SessionApprovalState(session, store)
    token = await state.preflight(["wire-0", "wire-1"])
    assert token is not None
    session_before = deepcopy(session.to_dict())
    writes_before = store.write_count
    stored_before: dict[str, tuple[dict[str, Any], str | None]] = {}
    for key in ("response-alias", "conversation-alias", token.authority_id):
        stored, revision = await store.get_with_revision(key)
        assert stored is not None
        stored_before[key] = (stored.to_dict(), revision)

    output_items: list[OutputItem] = [
        OutputItemMcpApprovalRequest({
            "type": "mcp_approval_request",
            "id": "wire-0",
            "server_label": "untrusted",
            "name": "untrusted",
            "arguments": '{"index": 999}',
        }),
        OutputItemMcpApprovalResponseResource({
            "type": "mcp_approval_response",
            "id": "resp-1",
            "approval_request_id": "wire-0",
            "approve": approved,
        }),
    ]
    input_items: list[Item] = [
        ItemMcpApprovalRequest({
            "type": "mcp_approval_request",
            "id": "wire-0",
            "server_label": "untrusted",
            "name": "untrusted",
            "arguments": '{"index": 999}',
        }),
        MCPApprovalResponse({
            "type": "mcp_approval_response",
            "approval_request_id": "wire-0",
            "approve": approved,
        }),
    ]

    output_messages = await _output_items_to_messages(output_items, approval_storage=state)
    input_messages = await _items_to_messages(input_items, approval_storage=state)

    for messages in (output_messages, input_messages):
        assert [message.role for message in messages] == ["assistant", "user"]
        request = messages[0].contents[0]
        response = messages[1].contents[0]
        assert request == approval_request()
        assert response.type == "function_approval_response"
        assert response.id == "approval-0"
        assert response.approved is approved
        assert response.function_call == request.function_call

    assert session.to_dict() == session_before
    assert store.write_count == writes_before
    assert await state.preflight(["wire-0", "wire-1"]) == token
    for key, expected in stored_before.items():
        stored, revision = await store.get_with_revision(key)
        assert stored is not None
        assert (stored.to_dict(), revision) == expected


async def test_partial_input_conversion_does_not_consume_pending_approvals(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    session = await pending_session(store)
    state = SessionApprovalState(session, store)
    token = await state.preflight(["wire-0", "wire-1"])
    assert token is not None
    session_before = deepcopy(session.to_dict())
    writes_before = store.write_count
    items: list[Item] = [
        MCPApprovalResponse({"type": "mcp_approval_response", "approval_request_id": "wire-0", "approve": True}),
        MCPApprovalResponse({"type": "mcp_approval_response", "approval_request_id": "missing", "approve": False}),
    ]

    with pytest.raises(_PublicResponseFailure, match="not in this session's history"):
        await _items_to_messages(items, approval_storage=state)

    assert session.to_dict() == session_before
    assert store.write_count == writes_before
    assert await state.preflight(["wire-0", "wire-1"]) == token


@pytest.mark.parametrize(
    "item",
    [
        OutputItemMcpApprovalRequest({
            "type": "mcp_approval_request",
            "id": "missing",
            "server_label": "srv",
            "name": "dangerous",
            "arguments": "{}",
        }),
        OutputItemMcpApprovalResponseResource({
            "type": "mcp_approval_response",
            "id": "resp-1",
            "approval_request_id": "missing",
            "approve": True,
        }),
    ],
    ids=["request", "response"],
)
async def test_history_conversion_rejects_unknown_approval_ids(item: OutputItem) -> None:
    state = SessionApprovalState(AgentSession(), None)

    with pytest.raises(_PublicResponseFailure, match="not in this session's history"):
        await _output_items_to_messages([item], approval_storage=state)


@pytest.mark.parametrize(
    ("input_item", "output_item"),
    [
        (
            ItemMcpApprovalRequest({
                "type": "mcp_approval_request",
                "id": "wire-1",
                "server_label": "srv",
                "name": "dangerous",
                "arguments": "{}",
            }),
            OutputItemMcpApprovalRequest({
                "type": "mcp_approval_request",
                "id": "wire-1",
                "server_label": "srv",
                "name": "dangerous",
                "arguments": "{}",
            }),
        ),
        (
            MCPApprovalResponse({"type": "mcp_approval_response", "approval_request_id": "wire-1", "approve": True}),
            OutputItemMcpApprovalResponseResource({
                "type": "mcp_approval_response",
                "id": "resp-1",
                "approval_request_id": "wire-1",
                "approve": True,
            }),
        ),
    ],
    ids=["request", "response"],
)
async def test_approval_conversion_requires_session_state(input_item: Item, output_item: OutputItem) -> None:
    with pytest.raises(ValueError, match="ApprovalStorage is required"):
        await _items_to_messages([input_item])
    with pytest.raises(ValueError, match="ApprovalStorage is required"):
        await _output_items_to_messages([output_item])


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

    monkeypatch.setattr(stream, "output_item_mcp_approval_request", _events_without_id)
    tracker = _OutputItemTracker(stream)
    recorder = _OrderedRecorder([])

    with pytest.raises(RuntimeError, match="approval request ID could not be extracted"):
        async for _ in tracker.handle(_approval_request(), approval_storage=recorder):
            pass

    assert recorder.saved == []
