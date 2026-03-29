# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import inspect
import os
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import AgentResponse, ChatContext, ChatMiddleware, Message, tool
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import AzureCliCredential

from agent_framework_foundry._agent import (
    FoundryAgent,
    RawFoundryAgent,
    RawFoundryAgentChatClient,
    _FoundryAgentChatClient,
)

skip_if_foundry_agent_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("FOUNDRY_PROJECT_ENDPOINT", "") in ("", "https://test-project.services.ai.azure.com/")
    or os.getenv("FOUNDRY_AGENT_NAME", "") == "",
    reason="No real FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_AGENT_NAME provided; skipping integration tests.",
)

_FOUNDRY_AGENT_ENV_VARS = (
    "FOUNDRY_PROJECT_ENDPOINT",
    "FOUNDRY_AGENT_NAME",
    "FOUNDRY_AGENT_VERSION",
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
    """Test construction with agent_name and project_client."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="test-agent",
        agent_version="1.0",
    )

    assert client.agent_name == "test-agent"
    assert client.agent_version == "1.0"


def test_raw_foundry_agent_chat_client_init_uses_explicit_parameters() -> None:
    signature = inspect.signature(RawFoundryAgentChatClient.__init__)

    assert "default_headers" in signature.parameters
    assert "instruction_role" in signature.parameters
    assert "compaction_strategy" in signature.parameters
    assert "tokenizer" in signature.parameters
    assert "additional_properties" in signature.parameters
    assert all(parameter.kind != inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())


def test_raw_foundry_agent_chat_client_get_agent_reference_with_version() -> None:
    """Test agent reference includes version when provided."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="my-agent",
        agent_version="2.0",
    )

    ref = client._get_agent_reference()
    assert ref == {"name": "my-agent", "version": "2.0", "type": "agent_reference"}


def test_raw_foundry_agent_chat_client_get_agent_reference_without_version() -> None:
    """Test agent reference omits version for HostedAgents."""

    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()

    client = RawFoundryAgentChatClient(
        project_client=mock_project,
        agent_name="hosted-agent",
    )

    ref = client._get_agent_reference()
    assert ref == {"name": "hosted-agent", "type": "agent_reference"}
    assert "version" not in ref


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

    assert "extra_body" in result
    assert result["extra_body"]["agent_reference"]["name"] == "test-agent"


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
    assert all(parameter.kind != inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())


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

    assert "instructions" in signature.parameters
    assert "default_options" in signature.parameters
    assert "compaction_strategy" in signature.parameters
    assert "tokenizer" in signature.parameters
    assert "additional_properties" in signature.parameters
    assert all(parameter.kind != inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())


def test_foundry_agent_init_uses_explicit_parameters() -> None:
    signature = inspect.signature(FoundryAgent.__init__)

    assert "instructions" in signature.parameters
    assert "default_options" in signature.parameters
    assert "compaction_strategy" in signature.parameters
    assert "tokenizer" in signature.parameters
    assert "additional_properties" in signature.parameters
    assert all(parameter.kind != inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())


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
    async with FoundryAgent(credential=AzureCliCredential()) as agent:
        response = await agent.run("Please respond with exactly: 'This is a response test.'")

    assert isinstance(response, AgentResponse)
    assert response.text is not None
    assert "response test" in response.text.lower()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_foundry_agent_integration_tests_disabled
async def test_foundry_agent_custom_client_run() -> None:
    """Smoke-test FoundryAgent against a real configured agent."""
    async with FoundryAgent(credential=AzureCliCredential(), client_type=RawFoundryAgentChatClient) as agent:
        response = await agent.run("Please respond with exactly: 'This is a response test.'")

    assert isinstance(response, AgentResponse)
    assert response.text is not None
    assert "response test" in response.text.lower()
