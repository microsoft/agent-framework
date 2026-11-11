# Copyright (c) Microsoft. All rights reserved.

"""Translate hosted MCP approval wire IDs to the agent's approval requests."""

from __future__ import annotations

import json
from typing import Any, cast

from agent_framework import AgentSession, Content

_APPROVAL_STATE_KEY = "__foundry_agent_approval_requests_v1"
_UNSUPPORTED = "Unsupported stored approval requests; start a fresh conversation."


class _InvalidApproval(ValueError):
    """Reject an approval reply that names no request in this session."""


def _is_approval_request(content: Content) -> bool:
    return (
        content.type == "function_approval_request"
        and bool(content.id)
        and content.function_call is not None
        and content.function_call.type == "function_call"
        and bool(content.function_call.call_id)
        and bool(content.function_call.name)
    )


class SessionApprovalState:
    """Keep the wire-ID to approval-request map in the agent's own session state.

    The Responses protocol uses wire IDs minted by the host, so the host must map
    a reply back to the original ``function_approval_request``. This class does
    no I/O and grants no authority. The host persists the map with the ordinary
    session snapshot, and Core's session approval tracking alone binds and
    consumes pending requests. A forked or retried session snapshot can therefore
    answer the same approval again.
    """

    def __init__(self, session: AgentSession) -> None:
        self.session = session

    def _requests(self) -> dict[str, str]:
        value = self.session.state.get(_APPROVAL_STATE_KEY)
        if value is None:
            return {}
        if not isinstance(value, dict) or any(
            not isinstance(key, str) or not key or not isinstance(item, str)
            for key, item in cast(dict[object, object], value).items()
        ):
            raise RuntimeError(_UNSUPPORTED)
        return cast(dict[str, str], value)

    async def save_approval_request(self, approval_request_id: str, request: Content) -> None:
        """Record the request emitted under ``approval_request_id``."""
        if not isinstance(approval_request_id, str) or not approval_request_id:
            raise ValueError("Approval wire ID must be a non-empty string.")
        if not _is_approval_request(request):
            raise ValueError("Only complete function approval requests can be recorded.")
        requests = self._requests()
        if approval_request_id in requests:
            raise ValueError("Approval wire ID already exists in this session.")
        # JSON strings prevent session codecs from interpreting nested provider
        # dictionaries with a registered `type` discriminator as live objects.
        requests[approval_request_id] = json.dumps(request.to_dict(), allow_nan=False, separators=(",", ":"))
        self.session.state[_APPROVAL_STATE_KEY] = requests

    async def load_approval_request(self, approval_request_id: str) -> Content:
        """Return the request recorded under ``approval_request_id``.

        Raises:
            _InvalidApproval: If this session has no request with that wire ID.
            RuntimeError: If the stored map or entry is malformed.
        """
        value = self._requests().get(approval_request_id)
        if value is None:
            raise _InvalidApproval("Approval request is not in this session; start a fresh approval turn.")
        try:
            payload: Any = json.loads(value)
            if not isinstance(payload, dict):
                raise TypeError
            content = Content.from_dict(cast(dict[str, Any], payload))
        except (TypeError, ValueError, KeyError) as exc:
            raise RuntimeError(_UNSUPPORTED) from exc
        if not _is_approval_request(content):
            raise RuntimeError(_UNSUPPORTED)
        return content
