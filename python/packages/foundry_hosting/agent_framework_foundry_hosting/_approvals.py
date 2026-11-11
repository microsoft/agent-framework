# Copyright (c) Microsoft. All rights reserved.

"""Keep hosted agent approval history separate from conditional pending authority."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

from agent_framework import AgentSession, Content, SessionStore

from ._state_store import _ConditionalSessionStore  # pyright: ignore[reportPrivateUsage]

_APPROVAL_STATE_KEY = "__foundry_agent_approvals_v1"
_AUTHORITY_PREFIX = "__foundry_agent_approval/"
_MAX_HISTORY_REQUESTS = 1024
_MAX_HISTORY_BYTES = 1024 * 1024


class _InvalidApproval(ValueError):
    """Reject invalid approval controls without classifying backend failures."""


@dataclass(frozen=True)
class _ApprovalClaim:
    authority_id: str
    revision: str
    session_id: str
    owner_response_id: str
    requests: tuple[tuple[str, str], ...]


def _conditional_store(storage: SessionStore | None) -> _ConditionalSessionStore:
    if not isinstance(storage, _ConditionalSessionStore):
        raise RuntimeError(
            "Hosted approvals require a session store implementing get_with_revision and compare_and_set "
            "with atomic create-only and exact-revision writes; ordinary get/set is not sufficient."
        )
    return storage


def _mapping(value: object, message: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in cast(dict[object, object], value)):
        raise RuntimeError(message)
    return cast(dict[str, Any], value)


def _requests(value: object) -> dict[str, str]:
    raw = _mapping(value, "Unsupported approval history; start a fresh conversation.")
    if any(not key or not isinstance(item, str) for key, item in raw.items()):
        raise RuntimeError("Unsupported approval history; start a fresh conversation.")
    return cast(dict[str, str], raw)


def _decode_request(value: str) -> Content:
    try:
        raw: object = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Unsupported stored approval content; start a fresh conversation.") from exc
    payload = _mapping(raw, "Unsupported stored approval content; start a fresh conversation.")
    try:
        content = Content.from_dict(payload)
    except (TypeError, ValueError, KeyError) as exc:
        raise RuntimeError("Unsupported stored approval content; start a fresh conversation.") from exc
    if (
        content.type != "function_approval_request"
        or not content.id
        or content.function_call is None
        or content.function_call.type != "function_call"
        or not content.function_call.call_id
        or not content.function_call.name
    ):
        raise RuntimeError("Unsupported stored approval content; start a fresh conversation.")
    return content


class SessionApprovalState:
    """Manage a regular agent's approval aliases through its session store.

    ``save_approval_request`` stages output only. The host must buffer approval
    events until ``seal`` and the ordinary session snapshot writes succeed.
    Input conversion can read history but cannot consume authority. Preflight
    reads the canonical batch; claim conditionally consumes it immediately before
    protected dispatch, after every other request check and reservation.

    A canonical entry is another private ``AgentSession`` in the same store, not
    a separately configured approval backend. Response and conversation snapshots
    contain only a link and historical content. Missing or expired canonical
    entries fail closed, even when a historical snapshot still exists.

    Custom stores must implement revision reads and atomic create-only/exact-
    revision writes. The default local Foundry backend cannot provide this
    capability and raises ``RuntimeError``; ordinary non-approval sessions are
    unaffected. History is capped at 1024 requests and 1 MiB of serialized content.
    Unsupported state and history overflow require a fresh conversation, never
    silent migration or pruning. Native workflow checkpoints do not use this
    authority.
    """

    def __init__(self, session: AgentSession, storage: SessionStore | None, *, response_id: str | None = None) -> None:
        self.session = session
        self._storage = storage
        self._response_id = response_id
        self._staged: dict[str, str] = {}
        self._sealed = False
        value = session.state.get(_APPROVAL_STATE_KEY)
        if _APPROVAL_STATE_KEY not in session.state:
            self._state: dict[str, Any] = {"version": 1, "history": {}, "pending": None}
        else:
            state = _mapping(value, "Unsupported approval session state; start a fresh conversation.")
            if type(state.get("version")) is not int or state["version"] != 1:
                raise RuntimeError("Unsupported approval session version; start a fresh conversation.")
            if "history" not in state or "pending" not in state:
                raise RuntimeError("Unsupported approval session state; start a fresh conversation.")
            _requests(state["history"])
            self._state = state
            self._pending()

    def _pending(self) -> dict[str, Any] | None:
        value = self._state["pending"]
        if value is None:
            return None
        pending = _mapping(value, "Unsupported pending approval link; start a fresh conversation.")
        if (
            not isinstance(pending.get("authority_id"), str)
            or not pending["authority_id"].startswith(_AUTHORITY_PREFIX)
            or not isinstance(pending.get("response_id"), str)
            or not pending["response_id"]
            or not isinstance(pending.get("wire_ids"), list)
        ):
            raise RuntimeError("Unsupported pending approval link; start a fresh conversation.")
        ids = cast(list[object], pending["wire_ids"])
        if not ids or any(not isinstance(item, str) or not item for item in ids) or len(set(ids)) != len(ids):
            raise RuntimeError("Unsupported pending approval link; start a fresh conversation.")
        return pending

    async def load_approval_request(self, approval_request_id: str) -> Content:
        """Reconstruct original content without granting or consuming authority."""
        history = _requests(self._state["history"])
        value = history.get(approval_request_id)
        if value is None:
            raise _InvalidApproval("Approval request is not in this session's history; start a fresh approval turn.")
        return _decode_request(value)

    async def save_approval_request(self, approval_request_id: str, request: Content) -> None:
        """Stage a wire mapping; the host must not publish it until sealing."""
        _conditional_store(self._storage)
        if self._sealed or self._pending() is not None:
            raise RuntimeError("Cannot publish another approval batch while this batch is pending or sealed.")
        if not self._response_id:
            raise RuntimeError("Approval recording requires the owning response ID.")
        if not approval_request_id or not isinstance(approval_request_id, str):
            raise ValueError("Approval wire ID must be a non-empty string.")
        history = _requests(self._state["history"])
        if approval_request_id in history or approval_request_id in self._staged:
            raise ValueError("Approval wire ID already exists in this session.")
        if (
            request.type != "function_approval_request"
            or not request.id
            or request.function_call is None
            or request.function_call.type != "function_call"
            or not request.function_call.call_id
            or not request.function_call.name
        ):
            raise ValueError("Only complete function approval requests can be recorded.")
        if any(_decode_request(value).id == request.id for value in self._staged.values()):
            raise ValueError("Framework approval request ID already exists in this pending batch.")
        # JSON strings prevent session codecs from interpreting nested provider
        # dictionaries with a registered `type` discriminator as live objects.
        encoded = json.dumps(request.to_dict(), allow_nan=False, separators=(",", ":"))
        if len(history) + len(self._staged) + 1 > _MAX_HISTORY_REQUESTS or (
            sum(len(item.encode("utf-8")) for item in (*history.values(), *self._staged.values(), encoded))
            > _MAX_HISTORY_BYTES
        ):
            raise RuntimeError("Hosted approval history limit reached; start a fresh conversation.")
        self._staged[approval_request_id] = encoded

    async def seal(self) -> None:
        """Persist the complete pending batch before publishing its snapshots.

        A failed acknowledgement may still have written an unreachable canonical
        record. No alias is attached until the write succeeds. Never retry a
        cancelled/failed publication as protected dispatch.
        """
        if not self._staged:
            return
        if self._sealed:
            raise RuntimeError("Approval batch is already sealed.")
        storage = _conditional_store(self._storage)
        authority_id = f"{_AUTHORITY_PREFIX}{uuid4()}"
        authority = AgentSession(session_id=self.session.session_id)
        authority.state[_APPROVAL_STATE_KEY] = {
            "version": 1,
            "response_id": self._response_id,
            "phase": "pending",
            "requests": dict(self._staged),
            "claimed_by": None,
        }
        revision = await storage.compare_and_set(authority_id, authority, expected_revision=None)
        if not isinstance(revision, str) or not revision:
            raise RuntimeError("Session storage did not acknowledge the approval revision.")
        self._state["history"] = {**_requests(self._state["history"]), **self._staged}
        self._state["pending"] = {
            "authority_id": authority_id,
            "response_id": self._response_id,
            "wire_ids": list(self._staged),
        }
        self.session.state[_APPROVAL_STATE_KEY] = self._state
        self._sealed = True

    async def preflight(self, approval_ids: Sequence[str]) -> _ApprovalClaim | None:
        """Validate exactly one complete batch without writing any state.

        Missing, duplicate, foreign, stale, and already claimed controls fail
        before the host opens a response stream. A pending batch also rejects a
        new user turn with no decisions; reset by starting a fresh conversation.
        Approval and rejection both count as decisions. The host validates their
        boolean values and rejects conflicting input-control kinds separately.
        Deliberate invalid controls raise ``_InvalidApproval``; storage failures
        propagate unchanged, including backend ``ValueError`` exceptions.
        """
        pending = self._pending()
        if pending is None:
            if approval_ids:
                raise _InvalidApproval("No pending approval batch in this session; start a fresh approval turn.")
            return None
        if (
            any(not isinstance(item, str) or not item for item in approval_ids)
            or len(set(approval_ids)) != len(approval_ids)
            or set(approval_ids) != set(pending["wire_ids"])
        ):
            raise _InvalidApproval("Answer exactly the complete pending MCP approval batch without duplicates.")
        storage = _conditional_store(self._storage)
        authority, revision = await storage.get_with_revision(pending["authority_id"])
        if authority is None:
            raise _InvalidApproval("Pending approval authority is missing or expired; start a fresh conversation.")
        if not isinstance(revision, str) or not revision:
            raise RuntimeError("Session storage returned approval authority without a revision.")
        record = _mapping(
            authority.state.get(_APPROVAL_STATE_KEY),
            "Unsupported canonical approval state; start a fresh conversation.",
        )
        if type(record.get("version")) is not int or record["version"] != 1:
            raise RuntimeError("Unsupported canonical approval version; start a fresh conversation.")
        requests = _requests(record.get("requests"))
        if (
            authority.session_id != self.session.session_id
            or record.get("response_id") != pending["response_id"]
            or set(requests) != set(pending["wire_ids"])
            or any(_requests(self._state["history"]).get(key) != value for key, value in requests.items())
        ):
            raise _InvalidApproval("Pending approval authority does not match this session and response.")
        if record.get("phase") == "claimed":
            raise _InvalidApproval("Pending approval batch was already claimed; start a fresh approval turn.")
        if record.get("phase") != "pending" or "claimed_by" not in record or record["claimed_by"] is not None:
            raise RuntimeError("Unsupported canonical approval phase; start a fresh conversation.")
        for value in requests.values():
            _decode_request(value)
        return _ApprovalClaim(
            pending["authority_id"],
            revision,
            self.session.session_id,
            pending["response_id"],
            tuple(requests.items()),
        )

    async def claim(self, token: _ApprovalClaim, *, response_id: str) -> None:
        """Irreversibly claim a validated revision before protected dispatch.

        Run only after all request validation and other session/conversation
        reservations succeed. A losing writer, storage failure, or cancellation
        must not dispatch. A crash after acknowledgement may lose work; never
        reopen the batch or claim exactly-once external side effects.
        """
        pending = self._pending()
        if not response_id:
            raise ValueError("Claiming response ID must be provided.")
        if (
            pending is None
            or token.session_id != self.session.session_id
            or token.authority_id != pending["authority_id"]
            or token.owner_response_id != pending["response_id"]
            or set(dict(token.requests)) != set(pending["wire_ids"])
        ):
            raise _InvalidApproval("Approval preflight token does not match the current session.")
        authority = AgentSession(session_id=token.session_id)
        authority.state[_APPROVAL_STATE_KEY] = {
            "version": 1,
            "response_id": token.owner_response_id,
            "phase": "claimed",
            "requests": dict(token.requests),
            "claimed_by": response_id,
        }
        revision = await _conditional_store(self._storage).compare_and_set(
            token.authority_id, authority, expected_revision=token.revision
        )
        if not isinstance(revision, str) or not revision:
            raise RuntimeError("Session storage did not acknowledge the approval claim revision.")
        self._state["pending"] = None
        self.session.state[_APPROVAL_STATE_KEY] = self._state
