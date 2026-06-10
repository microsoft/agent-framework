# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import inspect
import os
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from agent_framework import (
    AgentResponse,
    AgentSession,
    ChatContext,
    ChatMiddleware,
    ChatResponse,
    ChatResponseUpdate,
    Message,
    tool,
)
from agent_framework_openai._chat_client import RawOpenAIChatClient
from azure.ai.projects import models as projects_models
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import AzureCliCredential
from azure.identity.aio import AzureCliCredential as AsyncAzureCliCredential

from agent_framework_foundry._agent import (
    FoundryAgent,
    RawFoundryAgent,
    RawFoundryAgentChatClient,
    _FoundryAgentChatClient,
)
from agent_framework_foundry._chat_client import FoundryChatClient

skip_if_foundry_agent_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("FOUNDRY_PROJECT_ENDPOINT", "") in ("", "https://test-project.services.ai.azure.com/")
    or os.getenv("FOUNDRY_AGENT_NAME", "") == "",
    reason="No real FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_AGENT_NAME provided; skipping integration tests.",
)

_FOUNDRY_AZURE_AI_SEARCH_MODEL_ENV_VARS = (
    "FOUNDRY_AZURE_AI_SEARCH_MODEL",
    "OPENAI_MODEL",
    "AZURE_OPENAI_MODEL",
    "AZURE_OPENAI_CHAT_MODEL",
    "FOUNDRY_MODEL",
)


def _get_foundry_azure_ai_search_model() -> str | None:
    """Return the model/deployment to use for local Azure AI Search integration validation."""
    return next((os.environ[key] for key in _FOUNDRY_AZURE_AI_SEARCH_MODEL_ENV_VARS if os.getenv(key)), None)


skip_if_foundry_azure_ai_search_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("FOUNDRY_PROJECT_ENDPOINT", "") in ("", "https://test-project.services.ai.azure.com/")
    or os.getenv("AZURE_SEARCH_ENDPOINT", "") == ""
    or os.getenv("AZURE_SEARCH_INDEX_NAME", "") == ""
    or _get_foundry_azure_ai_search_model() is None,
    reason="No live Foundry project, Azure Search index, or model provided for Azure AI Search integration tests.",
)

_FOUNDRY_AGENT_ENV_VARS = (
    "FOUNDRY_PROJECT_ENDPOINT",
    "FOUNDRY_AGENT_NAME",
    "FOUNDRY_AGENT_VERSION",
    "FOUNDRY_AZURE_AI_SEARCH_AGENT_NAME",
    "FOUNDRY_AZURE_AI_SEARCH_AGENT_VERSION",
    "FOUNDRY_AZURE_AI_SEARCH_MODEL",
)


@pytest.fixture(autouse=True)
def clear_foundry_agent_settings_env(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Prevent unit tests from inheriting Foundry agent settings from the shell."""

    if request.node.get_closest_marker("integration") is not None:
        return

    for env_var in _FOUNDRY_AGENT_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)


def test_raw_foundry_agent_chat_client_init_requires_agent_name() -> None:
    """Test that agent_name is required."""

    with pytest.raises(ValueError, match="Agent name is required"):
        RawFoundryAgentChatClient(
            project_client=MagicMock(),
        )


def test_raw_foundry_agent_chat_client_init_with_agent_name() -> None:
    """Test construction with agent_name and project_client without preview agent binding."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
        agent_version="1.0",
    )

    assert client.agent_name == "test-agent"
    assert client.agent_version == "1.0"
    mock_project.get_openai_client.assert_called_once_with()


def test_raw_foundry_agent_chat_client_init_passes_agent_name_when_preview_enabled() -> None:
    """Test preview-enabled clients bind the OpenAI client to the agent endpoint."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="hosted-agent",
        allow_preview=True,
        default_headers={"x-test": "1"},
    )

    assert client.agent_name == "hosted-agent"
    mock_project.get_openai_client.assert_called_once_with(
        agent_name="hosted-agent",
        default_headers={"x-test": "1"},
    )


def test_raw_foundry_agent_chat_client_init_uses_explicit_parameters() -> None:
    signature = inspect.signature(RawFoundryAgentChatClient.__init__)

    assert "default_headers" in signature.parameters
    assert "instruction_role" in signature.parameters
    assert "compaction_strategy" in signature.parameters
    assert "tokenizer" in signature.parameters
    assert "additional_properties" in signature.parameters
    assert "timeout" in signature.parameters
    assert all(parameter.kind != inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())


def test_raw_foundry_agent_chat_client_init_applies_timeout_to_openai_client() -> None:
    """Test that timeout is applied via with_options without mutating the shared OpenAI client."""

    mock_project = MagicMock()
    openai_client_mock = MagicMock()
    openai_client_mock.timeout = 5.0
    mock_project.get_openai_client.return_value = openai_client_mock

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
        timeout=60.0,
    )

    openai_client_mock.with_options.assert_called_once_with(timeout=60.0)
    assert openai_client_mock.timeout == 5.0, "Original shared client must not be mutated"
    assert client.client is openai_client_mock.with_options.return_value


def test_raw_foundry_agent_chat_client_init_timeout_none_leaves_client_unchanged() -> None:
    """Test that timeout=None does not call with_options and leaves the shared client intact."""

    mock_project = MagicMock()
    openai_client_mock = MagicMock()
    openai_client_mock.timeout = 5.0
    mock_project.get_openai_client.return_value = openai_client_mock

    RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
        timeout=None,
    )

    openai_client_mock.with_options.assert_not_called()
    assert openai_client_mock.timeout == 5.0


def test_raw_foundry_agent_chat_client_init_applies_timeout_with_preview_enabled() -> None:
    """Test that timeout uses with_options even when allow_preview=True (hosted agent path)."""

    mock_project = MagicMock()
    openai_client_mock = MagicMock()
    openai_client_mock.timeout = 5.0
    mock_project.get_openai_client.return_value = openai_client_mock

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="hosted-agent",
        allow_preview=True,
        timeout=120.0,
    )

    openai_client_mock.with_options.assert_called_once_with(timeout=120.0)
    assert openai_client_mock.timeout == 5.0, "Original shared client must not be mutated"
    assert client.client is openai_client_mock.with_options.return_value


def test_raw_foundry_agent_chat_client_as_agent_preserves_client_type() -> None:
    """Test that as_agent() wraps the client in FoundryAgent using the same client class."""

    class CustomClient(RawFoundryAgentChatClient):
        pass

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = CustomClient(
        project_client=mock_project,
        agent_name="test-agent",
        agent_version="1.0",
    )

    agent = client.as_agent(instructions="You are helpful.")

    assert isinstance(agent, FoundryAgent)
    assert agent.name == "test-agent"
    assert isinstance(agent.client, CustomClient)
    assert agent.client.project_client is mock_project
    assert agent.client.agent_name == "test-agent"
    assert agent.client.agent_version == "1.0"

    named_agent = client.as_agent(name="display-name", instructions="You are helpful.")
    assert named_agent.name == "display-name"
    assert named_agent.client.agent_name == "test-agent"


def test_raw_foundry_agent_chat_client_as_agent_uses_explicit_parameters() -> None:
    signature = inspect.signature(RawFoundryAgentChatClient.as_agent)

    assert "compaction_strategy" in signature.parameters
    assert "tokenizer" in signature.parameters
    assert "additional_properties" in signature.parameters
    assert all(parameter.kind != inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())


async def test_raw_foundry_agent_chat_client_prepare_options_validates_tools() -> None:
    """Test that _prepare_options rejects non-FunctionTool objects."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
    )

    with pytest.raises(TypeError, match="Only FunctionTool objects are accepted"):
        await client._prepare_options(
            messages=[Message(role="user", contents="hi")],
            options={"tools": [{"type": "function", "function": {"name": "bad"}}]},
        )


async def test_raw_foundry_agent_chat_client_prepare_options_accepts_function_tools() -> None:
    """Test that _prepare_options accepts FunctionTool objects."""

    mock_project = MagicMock()
    mock_openai = MagicMock()
    mock_project.get_openai_client.return_value = mock_openai

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
    )

    @tool(approval_mode="never_require")
    def my_func() -> str:
        """A test function."""

        return "ok"

    with patch(
        "agent_framework_openai._chat_client.RawOpenAIChatClient._prepare_options",
        new_callable=AsyncMock,
        return_value={},
    ):
        result = await client._prepare_options(
            messages=[Message(role="user", contents="hi")],
            options={"tools": [my_func]},
        )

    # agent_reference is required so the Responses API can resolve model server-side; see #5582.
    assert result == {
        "extra_body": {"agent_reference": {"name": "test-agent", "type": "agent_reference"}},
    }


async def test_raw_foundry_agent_chat_client_prepare_options_strips_client_side_fields() -> None:
    """Test that _prepare_options strips client-side fields for Prompt Agent requests."""

    mock_project = MagicMock()
    mock_openai = MagicMock()
    mock_project.get_openai_client.return_value = mock_openai

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
    )

    @tool(approval_mode="never_require")
    def my_func() -> str:
        """A test function."""

        return "ok"

    with patch(
        "agent_framework_openai._chat_client.RawOpenAIChatClient._prepare_options",
        new_callable=AsyncMock,
        return_value={
            "model": "gpt-4.1",
            "tools": [{"type": "function", "function": {"name": "my_func"}}],
            "tool_choice": "auto",
            "parallel_tool_calls": True,
        },
    ):
        result = await client._prepare_options(
            messages=[Message(role="user", contents="hi")],
            options={"tools": [my_func]},
        )

    assert "model" not in result
    assert "tools" not in result
    assert "tool_choice" not in result
    assert "parallel_tool_calls" not in result
    # agent_reference is required so the Responses API can resolve model server-side; see #5582.
    assert result == {
        "extra_body": {"agent_reference": {"name": "test-agent", "type": "agent_reference"}},
    }


async def test_raw_foundry_agent_chat_client_prepare_options_strips_model_for_hosted_session() -> None:
    """Test that model is stripped when using a hosted agent session (not a PromptAgent)."""

    mock_project = MagicMock()
    mock_openai = MagicMock()
    mock_project.get_openai_client.return_value = mock_openai

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
    )

    with patch(
        "agent_framework_openai._chat_client.RawOpenAIChatClient._prepare_options",
        new_callable=AsyncMock,
        return_value={
            "model": "gpt-4.1",
            "previous_response_id": "resp_abc",
        },
    ):
        result = await client._prepare_options(
            messages=[Message(role="user", contents="hi")],
            options={"conversation_id": "agent-session-123"},
        )

    assert "model" not in result
    assert "previous_response_id" not in result
    assert result["extra_body"]["agent_session_id"] == "agent-session-123"
    assert result["extra_body"]["agent_reference"] == {"name": "test-agent", "type": "agent_reference"}


async def test_raw_foundry_agent_chat_client_prepare_options_injects_agent_reference_first_turn() -> None:
    """First-turn (no conversation_id) Prompt Agent calls must carry agent_reference in extra_body.

    Regression test for https://github.com/microsoft/agent-framework/issues/5582 — without this
    the Responses API rejects with "Missing required parameter: 'model'", because both ``model``
    and ``agent_reference`` are absent from the request body.
    """

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
        agent_version="2",
    )

    with patch(
        "agent_framework_openai._chat_client.RawOpenAIChatClient._prepare_options",
        new_callable=AsyncMock,
        return_value={"model": "gpt-4.1"},
    ):
        result = await client._prepare_options(
            messages=[Message(role="user", contents="hi")],
            options={},
        )

    assert result["extra_body"] == {
        "agent_reference": {"name": "test-agent", "type": "agent_reference", "version": "2"},
    }


async def test_raw_foundry_agent_chat_client_prepare_options_agent_reference_omits_version_when_unset() -> None:
    """When agent_version is unset, agent_reference should omit the version key entirely."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="hosted-agent",
    )

    with patch(
        "agent_framework_openai._chat_client.RawOpenAIChatClient._prepare_options",
        new_callable=AsyncMock,
        return_value={"model": "gpt-4.1"},
    ):
        result = await client._prepare_options(
            messages=[Message(role="user", contents="hi")],
            options={},
        )

    assert result["extra_body"] == {
        "agent_reference": {"name": "hosted-agent", "type": "agent_reference"},
    }


async def test_raw_foundry_agent_chat_client_prepare_options_skips_agent_reference_when_allow_preview() -> None:
    """Hosted-agent (allow_preview=True) requests must NOT add agent_reference in the body.

    The preview path injects the agent identity via ``project_client.get_openai_client(agent_name=...)``
    at the SDK wrapper level. Adding it again in extra_body would either duplicate or conflict
    with the wrapper's injection. Keep this gate aligned with the constructor branch in
    ``RawFoundryAgentChatClient.__init__``.
    """

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="hosted-agent",
        agent_version="3",
        allow_preview=True,
    )

    with patch(
        "agent_framework_openai._chat_client.RawOpenAIChatClient._prepare_options",
        new_callable=AsyncMock,
        return_value={"model": "gpt-4.1"},
    ):
        result = await client._prepare_options(
            messages=[Message(role="user", contents="hi")],
            options={},
        )

    # model is preserved for non-session requests (platform tolerates it for hosted agents)
    assert result["model"] == "gpt-4.1"
    # No extra_body at all is the cleanest signal — agent_reference must not be injected here.
    assert "extra_body" not in result


async def test_raw_foundry_agent_chat_client_prepare_options_respects_caller_agent_reference() -> None:
    """A caller-supplied extra_body['agent_reference'] should not be overwritten."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="default-agent",
    )

    caller_reference = {"name": "override-agent", "type": "agent_reference", "version": "5"}
    with patch(
        "agent_framework_openai._chat_client.RawOpenAIChatClient._prepare_options",
        new_callable=AsyncMock,
        return_value={"model": "gpt-4.1", "extra_body": {"agent_reference": caller_reference}},
    ):
        result = await client._prepare_options(
            messages=[Message(role="user", contents="hi")],
            options={"extra_body": {"agent_reference": caller_reference}},
        )

    assert "model" not in result
    assert result["extra_body"]["agent_reference"] == caller_reference


async def test_raw_foundry_agent_chat_client_prepare_options_preserves_model_for_resp_continuation() -> None:
    """Test that model is preserved when conversation_id is a resp_* continuation (HostedAgent v1 / v2-no-session)."""

    mock_project = MagicMock()
    mock_openai = MagicMock()
    mock_project.get_openai_client.return_value = mock_openai

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
    )

    with patch(
        "agent_framework_openai._chat_client.RawOpenAIChatClient._prepare_options",
        new_callable=AsyncMock,
        return_value={
            "model": "gpt-4.1",
            "previous_response_id": "resp_abc123",
        },
    ):
        result = await client._prepare_options(
            messages=[Message(role="user", contents="hi")],
            options={"conversation_id": "resp_abc123"},
        )

    # model preserved — resp_* is standard Responses API continuity, not a hosted session
    assert result["model"] == "gpt-4.1"
    # previous_response_id preserved — not stripped outside hosted session path
    assert result["previous_response_id"] == "resp_abc123"
    # no agent_session_id injected
    assert "extra_body" not in result or "agent_session_id" not in result.get("extra_body", {})


async def test_raw_foundry_agent_chat_client_prepare_options_maps_agent_session_id_to_extra_body() -> None:
    """Test that service_session_id is forwarded as agent_session_id for hosted sessions."""

    mock_project = MagicMock()
    mock_openai = MagicMock()
    mock_project.get_openai_client.return_value = mock_openai

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
    )

    with patch(
        "agent_framework_openai._chat_client.RawOpenAIChatClient._prepare_options",
        new_callable=AsyncMock,
        return_value={
            "extra_body": {"custom": "value"},
            "previous_response_id": "should-be-removed",
        },
    ):
        result = await client._prepare_options(
            messages=[Message(role="user", contents="hi")],
            options={"conversation_id": "agent-session-123", "isolation_key": "iso-key"},
        )

    assert result["extra_body"] == {
        "custom": "value",
        "agent_session_id": "agent-session-123",
        "agent_reference": {"name": "test-agent", "type": "agent_reference"},
    }
    assert "previous_response_id" not in result
    assert "conversation" not in result
    assert "isolation_key" not in result


def test_raw_foundry_agent_chat_client_parse_response_suppresses_conversation_id_for_agent_sessions() -> None:
    """Test that agent-session continuations do not overwrite session.service_session_id."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
    )

    parsed = ChatResponse(conversation_id="resp_123")
    with patch(
        "agent_framework_openai._chat_client.RawOpenAIChatClient._parse_response_from_openai",
        return_value=parsed,
    ):
        result = client._parse_response_from_openai(
            response=MagicMock(),
            options={"conversation_id": "agent-session-123"},
        )

    assert result.conversation_id is None


def test_raw_foundry_agent_chat_client_parse_chunk_suppresses_conversation_id_for_agent_sessions() -> None:
    """Test that agent-session stream updates do not overwrite session.service_session_id."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
    )

    parsed = ChatResponseUpdate(conversation_id="resp_123")
    with patch(
        "agent_framework_openai._chat_client.RawOpenAIChatClient._parse_chunk_from_openai",
        return_value=parsed,
    ):
        result = client._parse_chunk_from_openai(
            event=MagicMock(type="response.output_text.delta"),
            options={"conversation_id": "agent-session-123"},
            function_call_ids={},
        )

    assert result.conversation_id is None


def test_raw_foundry_agent_chat_client_check_model_presence_is_noop() -> None:
    """Test that _check_model_presence does nothing (model is on service)."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
    )

    options: dict[str, Any] = {}
    client._check_model_presence(options)
    assert "model" not in options


def test_foundry_agent_chat_client_init() -> None:
    """Test construction of the full-middleware client."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = _FoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
        agent_version="1.0",
    )

    assert client.agent_name == "test-agent"


def test_foundry_agent_chat_client_init_uses_explicit_parameters() -> None:
    signature = inspect.signature(_FoundryAgentChatClient.__init__)

    assert "default_headers" in signature.parameters
    assert "instruction_role" in signature.parameters
    assert "compaction_strategy" in signature.parameters
    assert "tokenizer" in signature.parameters
    assert "additional_properties" in signature.parameters
    assert "timeout" in signature.parameters
    assert all(parameter.kind != inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())


def test_foundry_agent_chat_client_init_propagates_timeout() -> None:
    """Test that _FoundryAgentChatClient calls with_options instead of mutating the shared client."""

    mock_project = MagicMock()
    openai_client_mock = MagicMock()
    openai_client_mock.timeout = 5.0
    mock_project.get_openai_client.return_value = openai_client_mock

    client = _FoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
        timeout=45.0,
    )

    openai_client_mock.with_options.assert_called_once_with(timeout=45.0)
    assert openai_client_mock.timeout == 5.0, "Original shared client must not be mutated"
    assert client.client is openai_client_mock.with_options.return_value


def test_raw_foundry_agent_init_creates_client() -> None:
    """Test that RawFoundryAgent creates a client internally."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    agent = RawFoundryAgent(
        project_client=mock_project,
        agent_name="test-agent",
        agent_version="1.0",
    )

    assert agent.client is not None
    assert agent.client.agent_name == "test-agent"


def test_raw_foundry_agent_init_passes_default_headers_to_client() -> None:
    """Test that RawFoundryAgent passes default_headers to the underlying client."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()
    default_headers = {"x-ms-user-isolation-key": "user-1"}

    RawFoundryAgent(
        project_client=mock_project,
        agent_name="hosted-agent",
        default_headers=default_headers,
    )

    mock_project.get_openai_client.assert_called_once()
    assert mock_project.get_openai_client.call_args.kwargs["default_headers"] == default_headers


def test_foundry_agent_init_passes_default_headers_to_client() -> None:
    """Test that FoundryAgent passes default_headers to the underlying client."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()
    default_headers = {"x-ms-user-isolation-key": "user-1"}

    FoundryAgent(
        project_client=mock_project,
        agent_name="hosted-agent",
        default_headers=default_headers,
    )

    mock_project.get_openai_client.assert_called_once()
    assert mock_project.get_openai_client.call_args.kwargs["default_headers"] == default_headers


def test_raw_foundry_agent_init_with_custom_client_type() -> None:
    """Test that client_type parameter is respected."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    agent = RawFoundryAgent(
        project_client=mock_project,
        agent_name="test-agent",
        client_type=RawFoundryAgentChatClient,
    )

    assert isinstance(agent.client, RawFoundryAgentChatClient)


def test_raw_foundry_agent_init_uses_explicit_parameters() -> None:
    signature = inspect.signature(RawFoundryAgent.__init__)

    assert "default_headers" in signature.parameters
    assert "instructions" in signature.parameters
    assert "default_options" in signature.parameters
    assert "compaction_strategy" in signature.parameters
    assert "tokenizer" in signature.parameters
    assert "additional_properties" in signature.parameters
    assert "timeout" in signature.parameters
    assert all(parameter.kind != inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())


def test_foundry_agent_init_uses_explicit_parameters() -> None:
    signature = inspect.signature(FoundryAgent.__init__)

    assert "default_headers" in signature.parameters
    assert "instructions" in signature.parameters
    assert "default_options" in signature.parameters
    assert "compaction_strategy" in signature.parameters
    assert "tokenizer" in signature.parameters
    assert "additional_properties" in signature.parameters
    assert "timeout" in signature.parameters
    assert all(parameter.kind != inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())


def test_foundry_agent_init_propagates_timeout_to_openai_client() -> None:
    """Test that FoundryAgent uses with_options instead of mutating the shared OpenAI client."""

    mock_project = MagicMock()
    openai_client_mock = MagicMock()
    openai_client_mock.timeout = 5.0
    mock_project.get_openai_client.return_value = openai_client_mock

    agent = FoundryAgent(
        project_client=mock_project,
        agent_name="test-agent",
        timeout=90.0,
    )

    openai_client_mock.with_options.assert_called_once_with(timeout=90.0)
    assert openai_client_mock.timeout == 5.0, "Original shared client must not be mutated"
    assert agent.client.client is openai_client_mock.with_options.return_value


def test_foundry_agent_init_timeout_none_leaves_client_default() -> None:
    """Test that FoundryAgent with timeout=None does not call with_options or mutate the client."""

    mock_project = MagicMock()
    openai_client_mock = MagicMock()
    openai_client_mock.timeout = 5.0
    mock_project.get_openai_client.return_value = openai_client_mock

    FoundryAgent(
        project_client=mock_project,
        agent_name="test-agent",
        timeout=None,
    )

    openai_client_mock.with_options.assert_not_called()
    assert openai_client_mock.timeout == 5.0


def test_raw_foundry_agent_init_rejects_invalid_client_type() -> None:
    """Test that invalid client_type raises TypeError."""

    with pytest.raises(TypeError, match="must be a subclass of RawFoundryAgentChatClient"):
        RawFoundryAgent(
            project_client=MagicMock(),
            agent_name="test-agent",
            client_type=object,  # type: ignore[arg-type]
        )


def test_raw_foundry_agent_init_with_function_tools() -> None:
    """Test that FunctionTool and callables are accepted."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    @tool(approval_mode="never_require")
    def my_func() -> str:
        """A test function."""

        return "ok"

    agent = RawFoundryAgent(
        project_client=mock_project,
        agent_name="test-agent",
        tools=[my_func],
    )

    assert agent.default_options.get("tools") is not None


async def test_raw_foundry_agent_prepare_run_context_creates_service_session_from_isolation_key() -> None:
    """Test that RawFoundryAgent lazily creates a hosted session and stores it on service_session_id."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()
    mock_project.beta = SimpleNamespace(
        agents=SimpleNamespace(
            create_session=AsyncMock(return_value=SimpleNamespace(agent_session_id="agent-session-123"))
        )
    )

    agent = RawFoundryAgent(
        project_client=mock_project,
        agent_name="test-agent",
        agent_version="1.0",
        allow_preview=True,
    )
    session = AgentSession()

    with patch(
        "agent_framework._agents.RawAgent._prepare_run_context",
        new=AsyncMock(return_value={"ok": True}),
    ) as mock_prepare_run_context:
        result = await agent._prepare_run_context(
            messages="hi",
            session=session,
            tools=None,
            options={"isolation_key": "iso-key"},
            compaction_strategy=None,
            tokenizer=None,
            function_invocation_kwargs=None,
            client_kwargs=None,
        )

    assert result == {"ok": True}
    assert session.service_session_id == "agent-session-123"
    mock_project.beta.agents.create_session.assert_awaited_once()
    create_session_kwargs = mock_project.beta.agents.create_session.await_args.kwargs
    assert create_session_kwargs["agent_name"] == "test-agent"
    assert create_session_kwargs["isolation_key"] == "iso-key"
    assert "version_indicator" in create_session_kwargs
    mock_prepare_run_context.assert_awaited_once()


async def test_raw_foundry_agent_prepare_run_context_requires_preview_for_hosted_sessions() -> None:
    """Test that hosted-agent sessions require allow_preview=True."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    agent = RawFoundryAgent(
        project_client=mock_project,
        agent_name="test-agent",
    )

    with pytest.raises(RuntimeError, match="allow_preview=True"):
        await agent._prepare_run_context(
            messages="hi",
            session=AgentSession(),
            tools=None,
            options={"isolation_key": "iso-key"},
            compaction_strategy=None,
            tokenizer=None,
            function_invocation_kwargs=None,
            client_kwargs=None,
        )


def test_foundry_agent_init() -> None:
    """Test construction of the full-middleware agent."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    agent = FoundryAgent(
        project_client=mock_project,
        agent_name="test-agent",
        agent_version="1.0",
    )

    assert agent.client is not None
    assert agent.client.agent_name == "test-agent"


def test_foundry_agent_init_with_middleware() -> None:
    """Test that agent-level middleware is accepted."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    class MyMiddleware(ChatMiddleware):
        async def process(self, context: ChatContext) -> None:
            pass

    agent = FoundryAgent(
        project_client=mock_project,
        agent_name="test-agent",
        middleware=[MyMiddleware()],
    )

    assert agent.client is not None


async def test_foundry_agent_configure_azure_monitor() -> None:
    """Test configure_azure_monitor delegates through the underlying client."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()
    mock_project.telemetry.get_application_insights_connection_string = AsyncMock(
        return_value="InstrumentationKey=test-key;IngestionEndpoint=https://test.endpoint"
    )
    agent = FoundryAgent(project_client=mock_project, agent_name="test-agent")

    mock_configure = MagicMock()
    mock_views = MagicMock(return_value=[])
    mock_resource = MagicMock()
    mock_enable = MagicMock()

    with (
        patch.dict(
            "sys.modules",
            {"azure.monitor.opentelemetry": MagicMock(configure_azure_monitor=mock_configure)},
        ),
        patch("agent_framework.observability.create_metric_views", mock_views),
        patch("agent_framework.observability.create_resource", return_value=mock_resource),
        patch("agent_framework.observability.enable_instrumentation", mock_enable),
    ):
        await agent.configure_azure_monitor(enable_sensitive_data=True)

    mock_project.telemetry.get_application_insights_connection_string.assert_called_once()
    call_kwargs = mock_configure.call_args.kwargs
    assert call_kwargs["connection_string"] == "InstrumentationKey=test-key;IngestionEndpoint=https://test.endpoint"
    assert call_kwargs["views"] == []
    assert call_kwargs["resource"] is mock_resource
    mock_enable.assert_called_once_with(enable_sensitive_data=True)


async def test_foundry_agent_configure_azure_monitor_resource_not_found() -> None:
    """Test configure_azure_monitor handles ResourceNotFoundError gracefully."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()
    mock_project.telemetry.get_application_insights_connection_string = AsyncMock(
        side_effect=ResourceNotFoundError("No Application Insights found")
    )
    agent = FoundryAgent(project_client=mock_project, agent_name="test-agent")

    await agent.configure_azure_monitor()

    mock_project.telemetry.get_application_insights_connection_string.assert_called_once()


async def test_foundry_agent_configure_azure_monitor_import_error() -> None:
    """Test configure_azure_monitor raises ImportError when Azure Monitor is unavailable."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()
    mock_project.telemetry.get_application_insights_connection_string = AsyncMock(
        return_value="InstrumentationKey=test-key"
    )
    agent = FoundryAgent(project_client=mock_project, agent_name="test-agent")
    original_import = __import__

    def _import_with_missing_azure_monitor(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "azure.monitor.opentelemetry":
            raise ImportError("No module named 'azure.monitor.opentelemetry'")
        return original_import(name, globals, locals, fromlist, level)

    with (
        patch.dict(sys.modules, {"azure.monitor.opentelemetry": None}),
        patch("builtins.__import__", side_effect=_import_with_missing_azure_monitor),
        pytest.raises(ImportError, match="azure-monitor-opentelemetry is required"),
    ):
        await agent.configure_azure_monitor()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_foundry_agent_integration_tests_disabled
async def test_foundry_agent_basic_run() -> None:
    """Smoke-test FoundryAgent against a real configured agent."""
    async with FoundryAgent(credential=AzureCliCredential(), allow_preview=True) as agent:
        response = await agent.run("Please respond with exactly: 'This is a response test.'")

    assert isinstance(response, AgentResponse)
    assert response.text is not None
    assert "response test" in response.text.lower()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_foundry_agent_integration_tests_disabled
async def test_foundry_agent_custom_client_run() -> None:
    """Smoke-test FoundryAgent against a real configured agent."""
    async with FoundryAgent(
        credential=AzureCliCredential(), client_type=RawFoundryAgentChatClient, allow_preview=True
    ) as agent:
        response = await agent.run("Please respond with exactly: 'This is a response test.'")

    assert isinstance(response, AgentResponse)
    assert response.text is not None
    assert "response test" in response.text.lower()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_foundry_azure_ai_search_integration_tests_disabled
async def test_foundry_agent_azure_ai_search_streaming_citation_get_url() -> None:
    """Live regression for Foundry server-side Azure AI Search streaming output."""
    credential = AsyncAzureCliCredential()
    project_client: Any | None = None
    agent_created = False
    agent_name = f"af-5995-{uuid4().hex[:12]}"
    query = os.getenv("FOUNDRY_AZURE_AI_SEARCH_QUERY") or "Search the knowledge base for hotels and cite one result."
    model = _get_foundry_azure_ai_search_model()
    assert model is not None

    try:
        from azure.ai.projects.aio import AIProjectClient

        project_client = AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            credential=credential,
            allow_preview=True,
        )
        try:
            search_connection = await project_client.connections.get_default(
                projects_models.ConnectionType.AZURE_AI_SEARCH
            )
        except Exception as exc:
            pytest.skip(f"No default Azure AI Search connection is configured in the Foundry project: {exc}")
        if not search_connection.id:
            pytest.skip("Default Azure AI Search connection does not expose an id.")

        tool = FoundryChatClient.get_azure_ai_search_tool(
            index_connection_id=search_connection.id,
            index_name=os.environ["AZURE_SEARCH_INDEX_NAME"],
            query_type="simple",
            top_k=3,
        )
        definition = projects_models.PromptAgentDefinition(
            model=model,
            instructions="You must use Azure AI Search for every answer and cite retrieved documents.",
            tools=[tool],
            tool_choice="required",
        )
        await project_client.agents.create_version(agent_name, definition=definition)
        agent_created = True

        async with FoundryAgent(project_client=project_client, agent_name=agent_name, allow_preview=False) as agent:
            stream = agent.run(query, stream=True)
            async for _ in stream:
                pass
            response = await stream.get_final_response()

        raw_events = []
        for raw_agent_update in response.raw_representation or []:
            raw_chat_update = getattr(raw_agent_update, "raw_representation", raw_agent_update)
            raw_events.append(getattr(raw_chat_update, "raw_representation", raw_chat_update))

        live_get_urls = [
            get_url for event in raw_events for get_url in RawOpenAIChatClient._extract_azure_ai_search_get_urls(event)
        ]
        assert live_get_urls, "Expected the live Azure AI Search stream to include get_urls."

        citations = [
            annotation
            for message in response.messages
            for content in message.contents
            for annotation in (content.annotations or [])
            if annotation.get("type") == "citation"
        ]
        doc_citations = [
            annotation
            for annotation in citations
            if isinstance(annotation.get("title"), str) and annotation["title"].startswith("doc_")
        ]
        if doc_citations:
            assert any(
                isinstance((annotation.get("additional_properties") or {}).get("get_url"), str)
                for annotation in doc_citations
            ), "Expected doc_N citations to be enriched with additional_properties.get_url."
    finally:
        if project_client is not None:
            if agent_created:
                await project_client.agents.delete(agent_name, force=True)
            await project_client.close()
        await credential.close()


def test_parse_chunk_surfaces_oauth_consent_request() -> None:
    """An oauth_consent_request output item surfaces as Content with consent_link."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
    )

    mock_event = MagicMock()
    mock_event.type = "response.output_item.added"
    mock_item = MagicMock()
    mock_item.type = "oauth_consent_request"
    mock_item.consent_link = "https://consent-host.example.com/login?data=abc123"
    mock_item.id = "oauth-item-1"
    mock_event.item = mock_item
    mock_event.output_index = 0

    update = client._parse_chunk_from_openai(mock_event, {}, {})

    consent_contents = [c for c in update.contents if c.type == "oauth_consent_request"]
    assert len(consent_contents) == 1
    assert consent_contents[0].consent_link == "https://consent-host.example.com/login?data=abc123"
    assert update.role == "assistant"
    assert update.raw_representation is mock_event


def test_parse_chunk_skips_non_https_oauth_consent() -> None:
    """An oauth_consent_request with a non-HTTPS link is rejected."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
    )

    mock_event = MagicMock()
    mock_event.type = "response.output_item.added"
    mock_item = MagicMock()
    mock_item.type = "oauth_consent_request"
    mock_item.consent_link = "http://insecure.example.com/login"
    mock_item.id = "oauth-item-2"
    mock_event.item = mock_item
    mock_event.output_index = 0

    update = client._parse_chunk_from_openai(mock_event, {}, {})

    consent_contents = [c for c in update.contents if c.type == "oauth_consent_request"]
    assert len(consent_contents) == 0


def test_parse_chunk_handles_missing_consent_link() -> None:
    """An oauth_consent_request without a consent_link produces no content."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
    )

    mock_event = MagicMock()
    mock_event.type = "response.output_item.added"
    mock_item = MagicMock()
    mock_item.type = "oauth_consent_request"
    mock_item.consent_link = None
    mock_item.id = "oauth-item-3"
    mock_event.item = mock_item
    mock_event.output_index = 0

    update = client._parse_chunk_from_openai(mock_event, {}, {})

    consent_contents = [c for c in update.contents if c.type == "oauth_consent_request"]
    assert len(consent_contents) == 0


def test_parse_chunk_handles_empty_string_consent_link() -> None:
    """An oauth_consent_request with empty-string consent_link produces no content."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
    )

    mock_event = MagicMock()
    mock_event.type = "response.output_item.added"
    mock_item = MagicMock()
    mock_item.type = "oauth_consent_request"
    mock_item.consent_link = ""
    mock_item.id = "oauth-item-4"
    mock_event.item = mock_item
    mock_event.output_index = 0

    update = client._parse_chunk_from_openai(mock_event, {}, {})

    consent_contents = [c for c in update.contents if c.type == "oauth_consent_request"]
    assert len(consent_contents) == 0


def test_parse_chunk_delegates_non_oauth_events_to_super() -> None:
    """Non-oauth events are delegated to super()._parse_chunk_from_openai()."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
    )

    mock_event = MagicMock()
    mock_event.type = "response.output_text.delta"

    with patch.object(
        RawOpenAIChatClient,
        "_parse_chunk_from_openai",
        return_value=MagicMock(),
    ) as mock_super:
        client._parse_chunk_from_openai(mock_event, {}, {})
        mock_super.assert_called_once_with(mock_event, {}, {}, None)


def test_parse_chunk_surfaces_oauth_consent_requested_event() -> None:
    """A top-level response.oauth_consent_requested event surfaces as Content."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
    )

    mock_event = MagicMock()
    mock_event.type = "response.oauth_consent_requested"
    mock_event.consent_link = "https://consent-host.example.com/authorize?code=xyz"
    mock_event.id = "consent-event-1"

    update = client._parse_chunk_from_openai(mock_event, {}, {})

    consent_contents = [c for c in update.contents if c.type == "oauth_consent_request"]
    assert len(consent_contents) == 1
    assert consent_contents[0].consent_link == "https://consent-host.example.com/authorize?code=xyz"
    assert update.role == "assistant"
    assert update.raw_representation is mock_event
