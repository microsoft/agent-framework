# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from agent_framework import AgentSession, SessionStore

from agent_framework_foundry_hosting._approvals import _APPROVAL_STATE_KEY, SessionApprovalState

from .approval_helpers import (  # pyrefly: ignore[missing-import] - pytest's importlib namespace
    SqliteSessionStore,
    approval_request,
    pending_session,
    race_claims_in_processes,
)


async def test_batch_is_not_persisted_until_sealed(tmp_path) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    session = AgentSession()
    state = SessionApprovalState(session, store, response_id="response")
    await state.save_approval_request("wire", approval_request())
    assert store.write_count == 0
    assert _APPROVAL_STATE_KEY not in session.state
    await state.seal()
    assert store.write_count == 1
    restored = AgentSession.from_dict(session.to_dict())
    history = SessionApprovalState(restored, store)
    assert await history.load_approval_request("wire") == approval_request()
    assert await history.preflight(["wire"]) is not None


async def test_history_roundtrip_preserves_provider_content_without_type_rehydration(tmp_path) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    await pending_session(store)
    session = await store.get("response-alias")
    assert session is not None
    content = await SessionApprovalState(session, store).load_approval_request("wire-0")
    assert content == approval_request()
    assert content.id == "approval-0"
    assert content.function_call is not None
    assert content.function_call.hosted is True
    assert content.function_call.additional_properties["provider"] == {"type": "message", "opaque_id": "original"}


@pytest.mark.parametrize("ids", [[], ["wire-0"], ["wire-0", "wire-0"], ["wire-0", "foreign"], ["foreign"]])
async def test_invalid_batch_never_mutates_authority_and_complete_retry_succeeds(tmp_path, ids) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    session = await pending_session(store)
    state = SessionApprovalState(session, store)
    before = store.write_count
    with pytest.raises(ValueError, match="complete pending MCP approval batch"):
        await state.preflight(ids)
    assert store.write_count == before
    token = await state.preflight(["wire-1", "wire-0"])
    assert token is not None
    assert store.write_count == before
    await state.claim(token, response_id="resume")
    assert store.write_count == before + 1


async def test_response_and_conversation_aliases_share_one_irreversible_authority(tmp_path) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    await pending_session(store)
    response = await store.get("response-alias")
    conversation = await store.get("conversation-alias")
    assert response is not None and conversation is not None and response is not conversation
    first = SessionApprovalState(response, store)
    second = SessionApprovalState(conversation, store)
    token1 = await first.preflight(["wire-0", "wire-1"])
    token2 = await second.preflight(["wire-0", "wire-1"])
    assert token1 is not None and token2 is not None
    await first.claim(token1, response_id="first")
    with pytest.raises(RuntimeError, match="revision conflict"):
        await second.claim(token2, response_id="second")
    with pytest.raises(ValueError, match="already claimed"):
        await second.preflight(["wire-0", "wire-1"])
    assert await second.load_approval_request("wire-0") == approval_request()
    assert await first.preflight([]) is None


async def test_two_processes_can_preflight_but_only_one_can_claim(tmp_path) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    await pending_session(store)
    assert await race_claims_in_processes(store.path) == ["claimed", "conflict"]


async def test_expired_canonical_is_not_recreated_from_snapshot(tmp_path) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    session = await pending_session(store)
    key = session.state[_APPROVAL_STATE_KEY]["pending"]["authority_id"]
    await store.delete(key)
    before = store.write_count
    state = SessionApprovalState(session, store)
    with pytest.raises(ValueError, match="missing or expired"):
        await state.preflight(["wire-0", "wire-1"])
    assert store.write_count == before
    assert await state.load_approval_request("wire-0") == approval_request()


@pytest.mark.parametrize("storage", [None, SessionStore()])
async def test_unstored_and_nonconditional_stores_cannot_record_approvals(storage) -> None:
    state = SessionApprovalState(AgentSession(), storage, response_id="response")
    with pytest.raises(RuntimeError, match="ordinary get/set is not sufficient"):
        await state.save_approval_request("wire", approval_request())


async def test_empty_fresh_session_has_no_pending_authority() -> None:
    state = SessionApprovalState(AgentSession(), None)
    assert await state.preflight([]) is None
    with pytest.raises(ValueError, match="No pending approval"):
        await state.preflight(["wire"])
    with pytest.raises(ValueError, match="not in this session"):
        await state.load_approval_request("wire")


@pytest.mark.parametrize("value", [None, {}, {"version": 2, "history": {}, "pending": None}])
def test_unsupported_snapshot_format_requires_reset(value) -> None:
    session = AgentSession()
    session.state[_APPROVAL_STATE_KEY] = value
    with pytest.raises(RuntimeError, match="Unsupported approval session"):
        SessionApprovalState(session, None)


async def test_other_session_cannot_claim_copied_pending_link(tmp_path) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    session = await pending_session(store)
    other = AgentSession(session_id="other-session")
    other.state.update(session.state)
    with pytest.raises(ValueError, match="does not match"):
        await SessionApprovalState(other, store).preflight(["wire-0", "wire-1"])


async def test_persistence_failure_does_not_publish_snapshot_link(tmp_path, monkeypatch) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    session = AgentSession()
    state = SessionApprovalState(session, store, response_id="response")
    await state.save_approval_request("wire", approval_request())
    monkeypatch.setattr(store, "compare_and_set", AsyncMock(side_effect=OSError("storage down")))
    with pytest.raises(OSError, match="storage down"):
        await state.seal()
    assert _APPROVAL_STATE_KEY not in session.state


async def test_cancelled_claim_propagates_and_does_not_clear_local_pending(tmp_path, monkeypatch) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    session = await pending_session(store)
    state = SessionApprovalState(session, store)
    token = await state.preflight(["wire-0", "wire-1"])
    assert token is not None
    monkeypatch.setattr(store, "compare_and_set", AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await state.claim(token, response_id="resume")
    assert session.state[_APPROVAL_STATE_KEY]["pending"] is not None


async def test_postclaim_failure_does_not_reopen_authority_on_reload(tmp_path) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    session = await pending_session(store)
    state = SessionApprovalState(session, store)
    token = await state.preflight(["wire-0", "wire-1"])
    assert token is not None
    await state.claim(token, response_id="crashed-before-dispatch")
    # No final session snapshot is saved: a restarted process sees the old alias.
    restarted = await SqliteSessionStore(store.path).get("response-alias")
    assert restarted is not None
    with pytest.raises(ValueError, match="already claimed"):
        await SessionApprovalState(restarted, store).preflight(["wire-0", "wire-1"])


async def test_duplicate_output_wire_id_rejects_before_sealing(tmp_path) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    state = SessionApprovalState(AgentSession(), store, response_id="response")
    await state.save_approval_request("wire", approval_request())
    with pytest.raises(ValueError, match="already exists"):
        await state.save_approval_request("wire", approval_request())
    assert store.write_count == 0


async def test_history_limit_fails_explicitly_without_pruning(tmp_path, monkeypatch) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    state = SessionApprovalState(AgentSession(), store, response_id="response")
    monkeypatch.setattr("agent_framework_foundry_hosting._approvals._MAX_HISTORY_REQUESTS", 1)
    await state.save_approval_request("wire-0", approval_request())
    with pytest.raises(RuntimeError, match="history limit reached"):
        await state.save_approval_request("wire-1", approval_request(1))
    assert store.write_count == 0


async def test_duplicate_original_approval_cannot_get_another_wire_id(tmp_path) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    state = SessionApprovalState(AgentSession(), store, response_id="response")
    await state.save_approval_request("wire-0", approval_request())
    with pytest.raises(ValueError, match="Framework approval request ID already exists"):
        await state.save_approval_request("wire-1", approval_request())
    assert store.write_count == 0


@pytest.mark.parametrize("error", [OSError("lost acknowledgement"), asyncio.CancelledError()])
async def test_lost_claim_acknowledgement_never_reopens_persisted_authority(tmp_path, error) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    session = await pending_session(store)
    state = SessionApprovalState(session, store)
    token = await state.preflight(["wire-0", "wire-1"])
    assert token is not None
    store.error_after_commit = error
    with pytest.raises(type(error)):
        await state.claim(token, response_id="uncertain")
    assert session.state[_APPROVAL_STATE_KEY]["pending"] is not None
    restarted_store = SqliteSessionStore(store.path)
    restarted = await restarted_store.get("response-alias")
    assert restarted is not None
    with pytest.raises(ValueError, match="already claimed"):
        await SessionApprovalState(restarted, restarted_store).preflight(["wire-0", "wire-1"])


async def test_history_byte_limit_rejects_without_persistence(tmp_path, monkeypatch) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    state = SessionApprovalState(AgentSession(), store, response_id="response")
    monkeypatch.setattr("agent_framework_foundry_hosting._approvals._MAX_HISTORY_BYTES", 1)
    with pytest.raises(RuntimeError, match="history limit reached"):
        await state.save_approval_request("wire", approval_request())
    assert store.write_count == 0


@pytest.mark.parametrize("version", [True, 2, None])
async def test_unsupported_canonical_version_fails_without_consumption(tmp_path, version) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    session = await pending_session(store)
    key = session.state[_APPROVAL_STATE_KEY]["pending"]["authority_id"]
    authority, revision = await store.get_with_revision(key)
    assert authority is not None and revision is not None
    authority.state[_APPROVAL_STATE_KEY]["version"] = version
    await store.compare_and_set(key, authority, expected_revision=revision)
    before = store.write_count
    with pytest.raises(RuntimeError, match="Unsupported canonical approval version"):
        await SessionApprovalState(session, store).preflight(["wire-0", "wire-1"])
    assert store.write_count == before


async def test_history_tampering_does_not_authorize_a_different_call(tmp_path) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    session = await pending_session(store)
    session.state[_APPROVAL_STATE_KEY]["history"]["wire-0"] = json.dumps(approval_request(9).to_dict())
    before = store.write_count
    with pytest.raises(ValueError, match="does not match"):
        await SessionApprovalState(session, store).preflight(["wire-0", "wire-1"])
    assert store.write_count == before
