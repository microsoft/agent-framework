# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import pytest
from agent_framework import AgentSession, Content

from agent_framework_foundry_hosting._approvals import _APPROVAL_STATE_KEY, SessionApprovalState, _InvalidApproval

from .approval_helpers import (  # pyrefly: ignore[missing-import] - pytest's importlib namespace
    SqliteSessionStore,
    approval_request,
    pending_session,
)


async def test_save_and_load_roundtrip_in_session_state() -> None:
    session = AgentSession()
    state = SessionApprovalState(session)
    await state.save_approval_request("wire", approval_request())
    assert set(session.state[_APPROVAL_STATE_KEY]) == {"wire"}
    assert await state.load_approval_request("wire") == approval_request()


async def test_requests_persist_through_session_store_without_type_rehydration(tmp_path) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    await pending_session(store)
    for alias in ("response-alias", "conversation-alias"):
        session = await store.get(alias)
        assert session is not None
        content = await SessionApprovalState(session).load_approval_request("wire-0")
        assert content == approval_request()
        assert content.function_call is not None
        assert content.function_call.hosted is True
        assert content.function_call.additional_properties["provider"] == {"type": "message", "opaque_id": "original"}


async def test_loading_does_not_consume_so_forks_and_retries_see_the_same_request() -> None:
    session = AgentSession()
    await SessionApprovalState(session).save_approval_request("wire", approval_request())
    fork = AgentSession.from_dict(session.to_dict())
    for state in (SessionApprovalState(session), SessionApprovalState(fork)):
        assert await state.load_approval_request("wire") == approval_request()
        assert await state.load_approval_request("wire") == approval_request()


async def test_unknown_wire_id_raises_invalid_approval() -> None:
    state = SessionApprovalState(AgentSession())
    with pytest.raises(_InvalidApproval, match="not in this session"):
        await state.load_approval_request("missing")
    assert issubclass(_InvalidApproval, ValueError)


@pytest.mark.parametrize("wire_id", ["", None])
async def test_save_rejects_empty_wire_id(wire_id) -> None:
    session = AgentSession()
    with pytest.raises(ValueError, match="non-empty string"):
        await SessionApprovalState(session).save_approval_request(wire_id, approval_request())
    assert _APPROVAL_STATE_KEY not in session.state


async def test_save_rejects_duplicate_wire_id_without_overwriting() -> None:
    session = AgentSession()
    state = SessionApprovalState(session)
    await state.save_approval_request("wire", approval_request(0))
    with pytest.raises(ValueError, match="already exists"):
        await state.save_approval_request("wire", approval_request(1))
    assert await state.load_approval_request("wire") == approval_request(0)


@pytest.mark.parametrize(
    "request_content",
    [
        Content.from_text("not an approval"),
        Content.from_function_approval_request("approval", Content.from_function_call(call_id="", name="tool")),
    ],
)
async def test_save_rejects_incomplete_requests(request_content) -> None:
    session = AgentSession()
    with pytest.raises(ValueError, match="complete function approval requests"):
        await SessionApprovalState(session).save_approval_request("wire", request_content)
    assert _APPROVAL_STATE_KEY not in session.state


@pytest.mark.parametrize(
    "stored",
    [
        [],
        {"wire": 1},
        {"": "{}"},
        {"wire": "not json"},
        {"wire": "[]"},
        {"wire": '{"type":"text","text":"x"}'},
    ],
)
async def test_malformed_stored_map_fails_closed(stored) -> None:
    session = AgentSession()
    session.state[_APPROVAL_STATE_KEY] = stored
    state = SessionApprovalState(session)
    with pytest.raises(RuntimeError, match="start a fresh conversation"):
        await state.load_approval_request("wire")
