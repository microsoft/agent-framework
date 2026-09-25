# Copyright (c) Microsoft. All rights reserved.

"""Tests for trusted Foundry request identity."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext

from agent_framework_foundry_hosting import FoundryRequestScope


def _config(*, is_hosted: bool) -> AgentConfig:
    config = MagicMock(spec=AgentConfig)
    config.is_hosted = is_hosted
    return config


@pytest.mark.parametrize(
    ("session_id", "user_id", "call_id", "error"),
    [
        (None, "user", "call", "session ID"),
        ("", "user", "call", "session ID"),
        ("sandbox", None, "call", "user ID and call ID"),
        ("sandbox", "", "call", "user ID and call ID"),
        ("sandbox", "user", None, "user ID and call ID"),
        ("sandbox", "user", "", "user ID and call ID"),
    ],
)
def test_hosted_scope_requires_platform_identity(
    session_id: str | None, user_id: str | None, call_id: str | None, error: str
) -> None:
    context = FoundryAgentRequestContext(session_id=session_id, user_id=user_id, call_id=call_id)
    with pytest.raises(RuntimeError, match=error):
        FoundryRequestScope.from_context(_config(is_hosted=True), context, local_session_id="caller-supplied")


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
    config = _config(is_hosted=True)

    def scope(user: str, sandbox: str, call: str) -> FoundryRequestScope:
        return FoundryRequestScope.from_context(
            config, FoundryAgentRequestContext(user_id=user, session_id=sandbox, call_id=call)
        )

    first = scope("user/a", "b", "call-1")
    assert first.storage_key == scope("user/a", "b", "call-2").storage_key
    assert first.storage_key != scope("user", "a/b", "call-1").storage_key
    assert first.storage_key != scope("user/a", "other", "call-1").storage_key
    assert first.storage_key != scope("other", "b", "call-1").storage_key
    assert len(first.storage_key) == 64
    int(first.storage_key, 16)
    assert "user" not in first.storage_key and "sandbox" not in first.storage_key
