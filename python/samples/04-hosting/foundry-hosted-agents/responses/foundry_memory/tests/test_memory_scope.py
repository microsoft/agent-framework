# Copyright (c) Microsoft. All rights reserved.

"""Focused checks of the trusted Memory namespace and per-request binding."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest
from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext
from openai import AsyncOpenAI


@pytest.fixture
def sample() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sample_foundry_memory", Path(__file__).parents[1] / "main.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_memory_is_user_wide_but_never_shared_between_users(sample: ModuleType) -> None:
    first = sample.memory_scope(
        MagicMock(spec=AgentConfig, is_hosted=True, session_id="a"),
        FoundryAgentRequestContext(user_id="user", session_id="a", call_id="call-1"),
    )
    second = sample.memory_scope(
        MagicMock(spec=AgentConfig, is_hosted=True, session_id="b"),
        FoundryAgentRequestContext(user_id="user", session_id="b", call_id="call-2"),
    )
    other = sample.memory_scope(
        MagicMock(spec=AgentConfig, is_hosted=True, session_id="a"),
        FoundryAgentRequestContext(user_id="other-user", session_id="a", call_id="call-3"),
    )
    assert first == second and first != other and len(first) == 64
    assert "user" not in first


def test_missing_or_spoofed_context_cannot_select_a_memory_scope(
    sample: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_MEMORY_USER_ID", "configured-local-user")
    hosted = MagicMock(spec=AgentConfig, is_hosted=True, session_id="sandbox")
    for context in (
        FoundryAgentRequestContext(call_id="call", session_id="sandbox"),
        FoundryAgentRequestContext(user_id="user", session_id="sandbox"),
        FoundryAgentRequestContext(user_id="user", call_id="call", session_id="other"),
    ):
        with pytest.raises(RuntimeError):
            sample.memory_scope(hosted, context)
    local = MagicMock(spec=AgentConfig, is_hosted=False)
    assert sample.memory_scope(local, FoundryAgentRequestContext())
    with pytest.raises(RuntimeError, match="does not trust"):
        sample.memory_scope(local, FoundryAgentRequestContext(user_id="caller-controlled-user"))
    monkeypatch.delenv("LOCAL_MEMORY_USER_ID")
    with pytest.raises(RuntimeError, match="Set LOCAL_MEMORY_USER_ID"):
        sample.memory_scope(local, FoundryAgentRequestContext())


async def test_each_provider_captures_its_own_call_id_and_owns_cleanup(
    sample: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://project.test")
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "model")
    monkeypatch.setenv("MEMORY_STORE_NAME", "memory")
    projects: list[MagicMock] = []
    credentials: list[MagicMock] = []
    request_headers: list[dict[str, str]] = []

    def project(*, headers: dict[str, str], **kwargs: object) -> MagicMock:
        client = MagicMock()
        openai = MagicMock(spec=AsyncOpenAI)
        openai.close = AsyncMock()
        client.get_openai_client.return_value = openai
        client.close = AsyncMock()
        projects.append(client)
        request_headers.append(dict(headers))
        return client

    def credential(**kwargs: object) -> MagicMock:
        created = MagicMock()
        created.close = AsyncMock()
        credentials.append(created)
        return created

    monkeypatch.setattr(sample, "AIProjectClient", project)
    monkeypatch.setattr(sample, "ManagedIdentityCredential", credential)
    providers = []
    for sandbox, call_id in (("a", "call-1"), ("b", "call-2")):
        config = MagicMock(spec=AgentConfig, is_hosted=True, session_id=sandbox)
        monkeypatch.setattr(sample.AgentConfig, "from_env", lambda config=config: config)
        context = FoundryAgentRequestContext(user_id="user", session_id=sandbox, call_id=call_id)
        monkeypatch.setattr(sample, "get_request_context", lambda context=context: context)
        agent = sample.create_agent()
        providers.append(agent.context_providers[0])
        async with agent:
            assert agent.client.project_client is projects[-1]
        await agent.close()
    assert providers[0] is not providers[1]
    assert providers[0].scope == providers[1].scope
    assert request_headers == [{"x-agent-foundry-call-id": "call-1"}, {"x-agent-foundry-call-id": "call-2"}]
    for client, identity in zip(projects, credentials):
        client.close.assert_awaited_once()
        client.get_openai_client.return_value.close.assert_awaited_once()
        identity.close.assert_awaited_once()
