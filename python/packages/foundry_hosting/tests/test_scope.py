# Copyright (c) Microsoft. All rights reserved.

"""Tests for trusted Foundry request identity."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext

from agent_framework_foundry_hosting import FoundryRequestScope


def _config(*, is_hosted: bool, session_id: str = "sandbox") -> AgentConfig:
    config = MagicMock(spec=AgentConfig)
    config.is_hosted = is_hosted
    config.session_id = session_id
    return config


@pytest.mark.parametrize(
    ("platform_session_id", "request_session_id", "user_id", "call_id", "error"),
    [
        ("", "sandbox", "user", "call", "FOUNDRY_AGENT_SESSION_ID"),
        ("  ", "sandbox", "user", "call", "FOUNDRY_AGENT_SESSION_ID"),
        ("sandbox", "other-sandbox", "user", "call", "does not match"),
        ("sandbox", "sandbox", None, "call", "user ID and call ID"),
        ("sandbox", "sandbox", "", "call", "user ID and call ID"),
        ("sandbox", "sandbox", "user", None, "user ID and call ID"),
        ("sandbox", "sandbox", "user", "", "user ID and call ID"),
    ],
)
def test_hosted_scope_requires_platform_identity(
    platform_session_id: str,
    request_session_id: str,
    user_id: str | None,
    call_id: str | None,
    error: str,
) -> None:
    context = FoundryAgentRequestContext(session_id=request_session_id, user_id=user_id, call_id=call_id)
    with pytest.raises(RuntimeError, match=error):
        FoundryRequestScope.from_context(
            _config(is_hosted=True, session_id=platform_session_id), context, local_session_id="caller-supplied"
        )


def test_hosted_scope_uses_platform_session_when_request_omits_it() -> None:
    scope = FoundryRequestScope.from_context(
        _config(is_hosted=True),
        FoundryAgentRequestContext(user_id="user", call_id="call"),
    )
    assert scope.session_id == "sandbox"
    assert scope.is_hosted is True


def test_local_scope_can_use_a_local_session_without_hosted_identity() -> None:
    scope = FoundryRequestScope.from_context(
        _config(is_hosted=False),
        FoundryAgentRequestContext(),
        local_session_id="local-session",
    )
    assert scope == FoundryRequestScope(session_id="local-session", user_id=None, call_id=None, is_hosted=False)
    with pytest.raises(RuntimeError, match="session ID"):
        FoundryRequestScope.from_context(_config(is_hosted=False), FoundryAgentRequestContext())


def test_store_key_frames_user_and_sandbox_but_not_call_id() -> None:
    def scope(user: str, sandbox: str, call: str) -> FoundryRequestScope:
        return FoundryRequestScope.from_context(
            _config(is_hosted=True, session_id=sandbox),
            FoundryAgentRequestContext(user_id=user, session_id=sandbox, call_id=call),
        )

    first = scope("user/a", "b", "call-1")
    assert first.storage_key == scope("user/a", "b", "call-2").storage_key
    assert first.storage_key != scope("user", "a/b", "call-1").storage_key
    assert first.storage_key != scope("user/a", "other", "call-1").storage_key
    assert first.storage_key != scope("other", "b", "call-1").storage_key
    assert len(first.storage_key) == 64
    int(first.storage_key, 16)
    assert "user" not in first.storage_key and "sandbox" not in first.storage_key
