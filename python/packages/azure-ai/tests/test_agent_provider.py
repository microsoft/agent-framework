# Copyright (c) Microsoft. All rights reserved.

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import (
    ChatAgent,
    Content,
    HostedCodeInterpreterTool,
    HostedFileSearchTool,
    HostedMCPTool,
    HostedWebSearchTool,
    tool,
)
from agent_framework.exceptions import ServiceInitializationError
from azure.ai.agents.models import (
    Agent,
    CodeInterpreterToolDefinition,
)
from azure.identity.aio import AzureCliCredential
from pydantic import BaseModel

from agent_framework_azure_ai import (
    AzureAIAgentsProvider,
    AzureAISettings,
)
from agent_framework_azure_ai._shared import (
    from_azure_ai_agent_tools,
    to_azure_ai_agent_tools,
)

skip_if_azure_ai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("AZURE_AI_PROJECT_ENDPOINT", "") in ("", "https://test-project.cognitiveservices.azure.com/"),
    reason="No real AZURE_AI_PROJECT_ENDPOINT provided; skipping integration tests."
    if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    else "Integration tests are disabled.",
)


# region Provider Initialization Tests


def test_provider_init_with_agents_client(mock_agents_client: MagicMock) -> None:
    """Test AzureAIAgentsProvider initialization with existing AgentsClient."""
    provider = AzureAIAgentsProvider(agents_client=mock_agents_client)

    assert provider._agents_client is mock_agents_client  # type: ignore
    assert provider._should_close_client is False  # type: ignore


def test_provider_init_with_credential(
    azure_ai_unit_test_env: dict[str, str],
    mock_azure_credential: MagicMock,
) -> None:
    """Test AzureAIAgentsProvider initialization with credential."""
    with patch("agent_framework_azure_ai._agent_provider.AgentsClient") as mock_client_class:
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance

        provider = AzureAIAgentsProvider(credential=mock_azure_credential)

        mock_client_class.assert_called_once()
        assert provider._agents_client is mock_client_instance  # type: ignore
        assert provider._should_close_client is True  # type: ignore


def test_provider_init_with_explicit_endpoint(mock_azure_credential: MagicMock) -> None:
    """Test AzureAIAgentsProvider initialization with explicit endpoint."""
    with patch("agent_framework_azure_ai._agent_provider.AgentsClient") as mock_client_class:
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance

        provider = AzureAIAgentsProvider(
            project_endpoint="https://custom-endpoint.com/",
            credential=mock_azure_credential,
        )

        mock_client_class.assert_called_once()
        call_kwargs = mock_client_class.call_args.kwargs
        assert call_kwargs["endpoint"] == "https://custom-endpoint.com/"
        assert provider._should_close_client is True  # type: ignore


def test_provider_init_missing_endpoint_raises(
    mock_azure_credential: MagicMock,
) -> None:
    """Test AzureAIAgentsProvider raises error when endpoint is missing."""
    # Mock AzureAISettings to return None for project_endpoint
    with patch("agent_framework_azure_ai._agent_provider.AzureAISettings") as mock_settings_class:
        mock_settings = MagicMock()
        mock_settings.project_endpoint = None
        mock_settings.model_deployment_name = "test-model"
        mock_settings_class.return_value = mock_settings

        with pytest.raises(ServiceInitializationError) as exc_info:
            AzureAIAgentsProvider(credential=mock_azure_credential)

        assert "project endpoint is required" in str(exc_info.value).lower()


def test_provider_init_missing_credential_raises(azure_ai_unit_test_env: dict[str, str]) -> None:
    """Test AzureAIAgentsProvider raises error when credential is missing."""
    with pytest.raises(ServiceInitializationError) as exc_info:
        AzureAIAgentsProvider()

    assert "credential is required" in str(exc_info.value).lower()


# endregion


# region Context Manager Tests


async def test_provider_context_manager_closes_client(mock_agents_client: MagicMock) -> None:
    """Test that context manager closes client when it was created by provider."""
    with patch("agent_framework_azure_ai._agent_provider.AgentsClient") as mock_client_class:
        mock_client_instance = AsyncMock()
        mock_client_class.return_value = mock_client_instance

        with patch.object(AzureAIAgentsProvider, "__init__", lambda self: None):  # type: ignore
            provider = AzureAIAgentsProvider.__new__(AzureAIAgentsProvider)
            provider._agents_client = mock_client_instance  # type: ignore
            provider._should_close_client = True  # type: ignore
            provider._settings = AzureAISettings(project_endpoint="https://test.com")  # type: ignore

        async with provider:
            pass

        mock_client_instance.close.assert_called_once()


async def test_provider_context_manager_does_not_close_external_client(mock_agents_client: MagicMock) -> None:
    """Test that context manager does not close externally provided client."""
    mock_agents_client.close = AsyncMock()

    provider = AzureAIAgentsProvider(agents_client=mock_agents_client)

    async with provider:
        pass

    mock_agents_client.close.assert_not_called()


# endregion


# region create_agent Tests


async def test_create_agent_basic(
    azure_ai_unit_test_env: dict[str, str],
    mock_agents_client: MagicMock,
) -> None:
    """Test creating a basic agent."""
    mock_agent = MagicMock(spec=Agent)
    mock_agent.id = "test-agent-id"
    mock_agent.name = "TestAgent"
    mock_agent.description = "A test agent"
    mock_agent.instructions = "Be helpful"
    mock_agent.model = "gpt-4"
    mock_agent.temperature = 0.7
    mock_agent.top_p = 0.9
    mock_agent.tools = []
    mock_agents_client.create_agent = AsyncMock(return_value=mock_agent)

    provider = AzureAIAgentsProvider(agents_client=mock_agents_client)

    agent = await provider.create_agent(
        name="TestAgent",
        instructions="Be helpful",
        description="A test agent",
    )

    assert isinstance(agent, ChatAgent)
    assert agent.name == "TestAgent"
    assert agent.id == "test-agent-id"
    mock_agents_client.create_agent.assert_called_once()


async def test_create_agent_with_model(
    azure_ai_unit_test_env: dict[str, str],
    mock_agents_client: MagicMock,
) -> None:
    """Test creating an agent with explicit model."""
    mock_agent = MagicMock(spec=Agent)
    mock_agent.id = "test-agent-id"
    mock_agent.name = "TestAgent"
    mock_agent.description = None
    mock_agent.instructions = None
    mock_agent.model = "custom-model"
    mock_agent.temperature = None
    mock_agent.top_p = None
    mock_agent.tools = []
    mock_agents_client.create_agent = AsyncMock(return_value=mock_agent)

    provider = AzureAIAgentsProvider(agents_client=mock_agents_client)

    await provider.create_agent(name="TestAgent", model="custom-model")

    call_kwargs = mock_agents_client.create_agent.call_args.kwargs
    assert call_kwargs["model"] == "custom-model"


async def test_create_agent_with_tools(
    azure_ai_unit_test_env: dict[str, str],
    mock_agents_client: MagicMock,
) -> None:
    """Test creating an agent with tools."""
    mock_agent = MagicMock(spec=Agent)
    mock_agent.id = "test-agent-id"
    mock_agent.name = "TestAgent"
    mock_agent.description = None
    mock_agent.instructions = None
    mock_agent.model = "gpt-4"
    mock_agent.temperature = None
    mock_agent.top_p = None
    mock_agent.tools = []
    mock_agents_client.create_agent = AsyncMock(return_value=mock_agent)

    provider = AzureAIAgentsProvider(agents_client=mock_agents_client)

    @tool(approval_mode="never_require")
    def get_weather(city: str) -> str:
        """Get weather for a city."""
        return f"Weather in {city}"

    await provider.create_agent(name="TestAgent", tools=get_weather)

    call_kwargs = mock_agents_client.create_agent.call_args.kwargs
    assert "tools" in call_kwargs
    assert len(call_kwargs["tools"]) > 0


async def test_create_agent_with_response_format(
    azure_ai_unit_test_env: dict[str, str],
    mock_agents_client: MagicMock,
) -> None:
    """Test creating an agent with structured response format via default_options."""

    class WeatherResponse(BaseModel):
        temperature: float
        description: str

    mock_agent = MagicMock(spec=Agent)
    mock_agent.id = "test-agent-id"
    mock_agent.name = "TestAgent"
    mock_agent.description = None
    mock_agent.instructions = None
    mock_agent.model = "gpt-4"
    mock_agent.temperature = None
    mock_agent.top_p = None
    mock_agent.tools = []
    mock_agents_client.create_agent = AsyncMock(return_value=mock_agent)

    provider = AzureAIAgentsProvider(agents_client=mock_agents_client)

    await provider.create_agent(
        name="TestAgent",
        default_options={"response_format": WeatherResponse},
    )

    call_kwargs = mock_agents_client.create_agent.call_args.kwargs
    assert "response_format" in call_kwargs


async def test_create_agent_missing_model_raises(
    mock_agents_client: MagicMock,
) -> None:
    """Test that create_agent raises error when model is not specified."""
    # Create provider with mocked settings that has no model
    with patch("agent_framework_azure_ai._agent_provider.AzureAISettings") as mock_settings_class:
        mock_settings = MagicMock()
        mock_settings.project_endpoint = "https://test.com"
        mock_settings.model_deployment_name = None  # No model configured
        mock_settings_class.return_value = mock_settings

        provider = AzureAIAgentsProvider(agents_client=mock_agents_client)

        with pytest.raises(ServiceInitializationError) as exc_info:
            await provider.create_agent(name="TestAgent")

        assert "model deployment name is required" in str(exc_info.value).lower()


# endregion


# region get_agent Tests


async def test_get_agent_by_id(
    azure_ai_unit_test_env: dict[str, str],
    mock_agents_client: MagicMock,
) -> None:
    """Test getting an agent by ID."""
    mock_agent = MagicMock(spec=Agent)
    mock_agent.id = "existing-agent-id"
    mock_agent.name = "ExistingAgent"
    mock_agent.description = "An existing agent"
    mock_agent.instructions = "Be helpful"
    mock_agent.model = "gpt-4"
    mock_agent.temperature = 0.7
    mock_agent.top_p = 0.9
    mock_agent.tools = []
    mock_agents_client.get_agent = AsyncMock(return_value=mock_agent)

    provider = AzureAIAgentsProvider(agents_client=mock_agents_client)

    agent = await provider.get_agent("existing-agent-id")

    assert isinstance(agent, ChatAgent)
    assert agent.id == "existing-agent-id"
    mock_agents_client.get_agent.assert_called_once_with("existing-agent-id")


async def test_get_agent_with_function_tools(
    azure_ai_unit_test_env: dict[str, str],
    mock_agents_client: MagicMock,
) -> None:
    """Test getting an agent that has function tools requires tool implementations."""
    mock_function_tool = MagicMock()
    mock_function_tool.type = "function"
    mock_function_tool.function = MagicMock()
    mock_function_tool.function.name = "get_weather"

    mock_agent = MagicMock(spec=Agent)
    mock_agent.id = "agent-with-tools"
    mock_agent.name = "AgentWithTools"
    mock_agent.description = None
    mock_agent.instructions = None
    mock_agent.model = "gpt-4"
    mock_agent.temperature = None
    mock_agent.top_p = None
    mock_agent.tools = [mock_function_tool]
    mock_agents_client.get_agent = AsyncMock(return_value=mock_agent)

    provider = AzureAIAgentsProvider(agents_client=mock_agents_client)

    with pytest.raises(ServiceInitializationError) as exc_info:
        await provider.get_agent("agent-with-tools")

    assert "get_weather" in str(exc_info.value)


async def test_get_agent_with_provided_function_tools(
    azure_ai_unit_test_env: dict[str, str],
    mock_agents_client: MagicMock,
) -> None:
    """Test getting an agent with function tools when implementations are provided."""
    mock_function_tool = MagicMock()
    mock_function_tool.type = "function"
    mock_function_tool.function = MagicMock()
    mock_function_tool.function.name = "get_weather"

    mock_agent = MagicMock(spec=Agent)
    mock_agent.id = "agent-with-tools"
    mock_agent.name = "AgentWithTools"
    mock_agent.description = None
    mock_agent.instructions = None
    mock_agent.model = "gpt-4"
    mock_agent.temperature = None
    mock_agent.top_p = None
    mock_agent.tools = [mock_function_tool]
    mock_agents_client.get_agent = AsyncMock(return_value=mock_agent)

    @tool(approval_mode="never_require")
    def get_weather(city: str) -> str:
        """Get weather for a city."""
        return f"Weather in {city}"

    provider = AzureAIAgentsProvider(agents_client=mock_agents_client)

    agent = await provider.get_agent("agent-with-tools", tools=get_weather)

    assert isinstance(agent, ChatAgent)
    assert agent.id == "agent-with-tools"


# endregion


# region as_agent Tests


def test_as_agent_wraps_without_http(
    azure_ai_unit_test_env: dict[str, str],
    mock_agents_client: MagicMock,
) -> None:
    """Test as_agent wraps Agent object without making HTTP calls."""
    mock_agent = MagicMock(spec=Agent)
    mock_agent.id = "wrap-agent-id"
    mock_agent.name = "WrapAgent"
    mock_agent.description = "Wrapped agent"
    mock_agent.instructions = "Be helpful"
    mock_agent.model = "gpt-4"
    mock_agent.temperature = 0.5
    mock_agent.top_p = 0.8
    mock_agent.tools = []

    provider = AzureAIAgentsProvider(agents_client=mock_agents_client)

    agent = provider.as_agent(mock_agent)

    assert isinstance(agent, ChatAgent)
    assert agent.id == "wrap-agent-id"
    assert agent.name == "WrapAgent"
    # Ensure no HTTP calls were made
    mock_agents_client.get_agent.assert_not_called()
    mock_agents_client.create_agent.assert_not_called()


def test_as_agent_with_function_tools_validates(
    azure_ai_unit_test_env: dict[str, str],
    mock_agents_client: MagicMock,
) -> None:
    """Test as_agent validates that function tool implementations are provided."""
    mock_function_tool = MagicMock()
    mock_function_tool.type = "function"
    mock_function_tool.function = MagicMock()
    mock_function_tool.function.name = "my_function"

    mock_agent = MagicMock(spec=Agent)
    mock_agent.id = "agent-id"
    mock_agent.name = "Agent"
    mock_agent.description = None
    mock_agent.instructions = None
    mock_agent.model = "gpt-4"
    mock_agent.temperature = None
    mock_agent.top_p = None
    mock_agent.tools = [mock_function_tool]

    provider = AzureAIAgentsProvider(agents_client=mock_agents_client)

    with pytest.raises(ServiceInitializationError) as exc_info:
        provider.as_agent(mock_agent)

    assert "my_function" in str(exc_info.value)


def test_as_agent_with_hosted_tools(
    azure_ai_unit_test_env: dict[str, str],
    mock_agents_client: MagicMock,
) -> None:
    """Test as_agent handles hosted tools correctly."""
    mock_code_interpreter = MagicMock()
    mock_code_interpreter.type = "code_interpreter"

    mock_agent = MagicMock(spec=Agent)
    mock_agent.id = "agent-id"
    mock_agent.name = "Agent"
    mock_agent.description = None
    mock_agent.instructions = None
    mock_agent.model = "gpt-4"
    mock_agent.temperature = None
    mock_agent.top_p = None
    mock_agent.tools = [mock_code_interpreter]

    provider = AzureAIAgentsProvider(agents_client=mock_agents_client)

    agent = provider.as_agent(mock_agent)

    assert isinstance(agent, ChatAgent)
    # Should have HostedCodeInterpreterTool in the default_options tools
    assert any(isinstance(t, HostedCodeInterpreterTool) for t in (agent.default_options.get("tools") or []))  # type: ignore


def test_as_agent_with_dict_function_tools_validates(
    azure_ai_unit_test_env: dict[str, str],
    mock_agents_client: MagicMock,
) -> None:
    """Test as_agent validates dict-format function tools require implementations."""
    # Dict-based function tool (as returned by some Azure AI SDK operations)
    dict_function_tool = {  # type: ignore
        "type": "function",
        "function": {
            "name": "dict_based_function",
            "description": "A function defined as dict",
            "parameters": {"type": "object", "properties": {}},
        },
    }

    mock_agent = MagicMock(spec=Agent)
    mock_agent.id = "agent-id"
    mock_agent.name = "Agent"
    mock_agent.description = None
    mock_agent.instructions = None
    mock_agent.model = "gpt-4"
    mock_agent.temperature = None
    mock_agent.top_p = None
    mock_agent.tools = [dict_function_tool]

    provider = AzureAIAgentsProvider(agents_client=mock_agents_client)

    with pytest.raises(ServiceInitializationError) as exc_info:
        provider.as_agent(mock_agent)

    assert "dict_based_function" in str(exc_info.value)


def test_as_agent_with_dict_function_tools_provided(
    azure_ai_unit_test_env: dict[str, str],
    mock_agents_client: MagicMock,
) -> None:
    """Test as_agent succeeds when dict-format function tools have implementations provided."""
    dict_function_tool = {  # type: ignore
        "type": "function",
        "function": {
            "name": "dict_based_function",
            "description": "A function defined as dict",
            "parameters": {"type": "object", "properties": {}},
        },
    }

    mock_agent = MagicMock(spec=Agent)
    mock_agent.id = "agent-id"
    mock_agent.name = "Agent"
    mock_agent.description = None
    mock_agent.instructions = None
    mock_agent.model = "gpt-4"
    mock_agent.temperature = None
    mock_agent.top_p = None
    mock_agent.tools = [dict_function_tool]

    @tool
    def dict_based_function() -> str:
        """A function implementation."""
        return "result"

    provider = AzureAIAgentsProvider(agents_client=mock_agents_client)

    agent = provider.as_agent(mock_agent, tools=dict_based_function)

    assert isinstance(agent, ChatAgent)
    assert agent.id == "agent-id"


# endregion


# region Tool Conversion Tests - to_azure_ai_agent_tools


def test_to_azure_ai_agent_tools_empty() -> None:
    """Test converting empty tools list."""
    result = to_azure_ai_agent_tools(None)
    assert result == []

    result = to_azure_ai_agent_tools([])
    assert result == []


def test_to_azure_ai_agent_tools_function() -> None:
    """Test converting FunctionTool to Azure tool definition."""

    @tool(approval_mode="never_require")
    def get_weather(city: str) -> str:
        """Get weather for a city."""
        return f"Weather in {city}"

    result = to_azure_ai_agent_tools([get_weather])

    assert len(result) == 1
    assert result[0]["type"] == "function"
    assert result[0]["function"]["name"] == "get_weather"


def test_to_azure_ai_agent_tools_code_interpreter() -> None:
    """Test converting HostedCodeInterpreterTool."""
    tool = HostedCodeInterpreterTool()

    result = to_azure_ai_agent_tools([tool])

    assert len(result) == 1
    assert isinstance(result[0], CodeInterpreterToolDefinition)


def test_to_azure_ai_agent_tools_file_search() -> None:
    """Test converting HostedFileSearchTool with vector stores."""
    tool = HostedFileSearchTool(inputs=[Content.from_hosted_vector_store(vector_store_id="vs-123")])
    run_options: dict[str, Any] = {}

    result = to_azure_ai_agent_tools([tool], run_options)

    assert len(result) == 1
    assert "tool_resources" in run_options


def test_to_azure_ai_agent_tools_web_search_bing_grounding(monkeypatch: Any) -> None:
    """Test converting HostedWebSearchTool for Bing Grounding."""
    # Use a properly formatted connection ID as required by Azure SDK
    valid_conn_id = (
        "/subscriptions/test-sub/resourceGroups/test-rg/"
        "providers/Microsoft.CognitiveServices/accounts/test-account/"
        "projects/test-project/connections/test-connection"
    )
    monkeypatch.setenv("BING_CONNECTION_ID", valid_conn_id)
    tool = HostedWebSearchTool()

    result = to_azure_ai_agent_tools([tool])

    assert len(result) > 0


def test_to_azure_ai_agent_tools_web_search_custom(monkeypatch: Any) -> None:
    """Test converting HostedWebSearchTool for Custom Bing Search."""
    monkeypatch.setenv("BING_CUSTOM_CONNECTION_ID", "custom-conn-id")
    monkeypatch.setenv("BING_CUSTOM_INSTANCE_NAME", "my-instance")
    tool = HostedWebSearchTool()

    result = to_azure_ai_agent_tools([tool])

    assert len(result) > 0


def test_to_azure_ai_agent_tools_web_search_missing_config(monkeypatch: Any) -> None:
    """Test converting HostedWebSearchTool raises error when config is missing."""
    monkeypatch.delenv("BING_CONNECTION_ID", raising=False)
    monkeypatch.delenv("BING_CUSTOM_CONNECTION_ID", raising=False)
    monkeypatch.delenv("BING_CUSTOM_INSTANCE_NAME", raising=False)
    tool = HostedWebSearchTool()

    with pytest.raises(ServiceInitializationError):
        to_azure_ai_agent_tools([tool])


def test_to_azure_ai_agent_tools_mcp() -> None:
    """Test converting HostedMCPTool."""
    tool = HostedMCPTool(
        name="my mcp server",
        url="https://mcp.example.com",
        allowed_tools=["tool1", "tool2"],
    )

    result = to_azure_ai_agent_tools([tool])

    assert len(result) > 0


def test_to_azure_ai_agent_tools_dict_passthrough() -> None:
    """Test that dict tools are passed through."""
    tool = {"type": "custom_tool", "config": {"key": "value"}}

    result = to_azure_ai_agent_tools([tool])

    assert len(result) == 1
    assert result[0] == tool


def test_to_azure_ai_agent_tools_unsupported_type() -> None:
    """Test that unsupported tool types raise error."""

    class UnsupportedTool:
        pass

    with pytest.raises(ServiceInitializationError):
        to_azure_ai_agent_tools([UnsupportedTool()])  # type: ignore


# endregion


# region Tool Conversion Tests - from_azure_ai_agent_tools


def test_from_azure_ai_agent_tools_empty() -> None:
    """Test converting empty tools list."""
    result = from_azure_ai_agent_tools(None)
    assert result == []

    result = from_azure_ai_agent_tools([])
    assert result == []


def test_from_azure_ai_agent_tools_code_interpreter() -> None:
    """Test converting CodeInterpreterToolDefinition."""
    tool = CodeInterpreterToolDefinition()

    result = from_azure_ai_agent_tools([tool])

    assert len(result) == 1
    assert isinstance(result[0], HostedCodeInterpreterTool)


def test_from_azure_ai_agent_tools_code_interpreter_dict() -> None:
    """Test converting code_interpreter dict."""
    tool = {"type": "code_interpreter"}

    result = from_azure_ai_agent_tools([tool])

    assert len(result) == 1
    assert isinstance(result[0], HostedCodeInterpreterTool)


def test_from_azure_ai_agent_tools_file_search_dict() -> None:
    """Test converting file_search dict with vector store IDs."""
    tool = {
        "type": "file_search",
        "file_search": {"vector_store_ids": ["vs-123", "vs-456"]},
    }

    result = from_azure_ai_agent_tools([tool])

    assert len(result) == 1
    assert isinstance(result[0], HostedFileSearchTool)
    assert len(result[0].inputs or []) == 2


def test_from_azure_ai_agent_tools_bing_grounding_dict() -> None:
    """Test converting bing_grounding dict."""
    tool = {
        "type": "bing_grounding",
        "bing_grounding": {"connection_id": "conn-123"},
    }

    result = from_azure_ai_agent_tools([tool])

    assert len(result) == 1
    assert isinstance(result[0], HostedWebSearchTool)

    additional_properties = result[0].additional_properties

    assert additional_properties
    assert additional_properties.get("connection_id") == "conn-123"


def test_from_azure_ai_agent_tools_bing_custom_search_dict() -> None:
    """Test converting bing_custom_search dict."""
    tool = {
        "type": "bing_custom_search",
        "bing_custom_search": {
            "connection_id": "custom-conn",
            "instance_name": "my-instance",
        },
    }

    result = from_azure_ai_agent_tools([tool])

    assert len(result) == 1
    assert isinstance(result[0], HostedWebSearchTool)
    additional_properties = result[0].additional_properties

    assert additional_properties
    assert additional_properties.get("custom_connection_id") == "custom-conn"


def test_from_azure_ai_agent_tools_mcp_dict() -> None:
    """Test that mcp dict is skipped (hosted on Azure, no local handling needed)."""
    tool = {
        "type": "mcp",
        "mcp": {
            "server_label": "my_server",
            "server_url": "https://mcp.example.com",
            "allowed_tools": ["tool1"],
        },
    }

    result = from_azure_ai_agent_tools([tool])

    # MCP tools are hosted on Azure agent, skipped in conversion
    assert len(result) == 0


def test_from_azure_ai_agent_tools_function_dict() -> None:
    """Test converting function tool dict (returned as-is)."""
    tool: dict[str, Any] = {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather",
            "parameters": {},
        },
    }

    result = from_azure_ai_agent_tools([tool])

    assert len(result) == 1
    assert result[0] == tool


def test_from_azure_ai_agent_tools_unknown_dict() -> None:
    """Test converting unknown tool type dict."""
    tool = {"type": "unknown_tool", "config": "value"}

    result = from_azure_ai_agent_tools([tool])

    assert len(result) == 1
    assert result[0] == tool


# endregion


# region Integration Tests


@skip_if_azure_ai_integration_tests_disabled
async def test_integration_create_agent() -> None:
    """Integration test: Create an agent using the provider."""
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentsProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="IntegrationTestAgent",
            instructions="You are a helpful assistant for testing.",
        )

        try:
            assert isinstance(agent, ChatAgent)
            assert agent.name == "IntegrationTestAgent"
            assert agent.id is not None
        finally:
            # Cleanup: delete the agent
            if agent.id:
                await provider._agents_client.delete_agent(agent.id)  # type: ignore


@skip_if_azure_ai_integration_tests_disabled
async def test_integration_get_agent() -> None:
    """Integration test: Get an existing agent using the provider."""
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentsProvider(credential=credential) as provider,
    ):
        # First create an agent
        created = await provider._agents_client.create_agent(  # type: ignore
            model=os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o"),
            name="GetAgentTest",
            instructions="Test agent",
        )

        try:
            # Then get it using the provider
            agent = await provider.get_agent(created.id)

            assert isinstance(agent, ChatAgent)
            assert agent.id == created.id
        finally:
            await provider._agents_client.delete_agent(created.id)  # type: ignore


@skip_if_azure_ai_integration_tests_disabled
async def test_integration_create_and_run() -> None:
    """Integration test: Create an agent and run a conversation."""
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentsProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="RunTestAgent",
            instructions="You are a helpful assistant. Always respond with 'Hello!' to any greeting.",
        )

        try:
            result = await agent.run("Hi there!")

            assert result is not None
            assert len(result.messages) > 0
        finally:
            if agent.id:
                await provider._agents_client.delete_agent(agent.id)  # type: ignore


# endregion
