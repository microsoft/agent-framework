# Copyright (c) Microsoft. All rights reserved.

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import ChatAgent, FunctionTool
from agent_framework._mcp import MCPTool
from agent_framework.exceptions import ServiceInitializationError
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    AgentReference,
    AgentVersionDetails,
    PromptAgentDefinition,
)
from azure.ai.projects.models import (
    FunctionTool as AzureFunctionTool,
)
from azure.identity.aio import AzureCliCredential

from agent_framework_azure_ai import AzureAIProjectAgentProvider

skip_if_azure_ai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("AZURE_AI_PROJECT_ENDPOINT", "") in ("", "https://test-project.cognitiveservices.azure.com/")
    or os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "") == "",
    reason=(
        "No real AZURE_AI_PROJECT_ENDPOINT or AZURE_AI_MODEL_DEPLOYMENT_NAME provided; skipping integration tests."
        if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
        else "Integration tests are disabled."
    ),
)


@pytest.fixture
def mock_project_client() -> MagicMock:
    """Fixture that provides a mock AIProjectClient."""
    mock_client = MagicMock()

    # Mock agents property
    mock_client.agents = MagicMock()
    mock_client.agents.create_version = AsyncMock()

    # Mock conversations property
    mock_client.conversations = MagicMock()
    mock_client.conversations.create = AsyncMock()

    # Mock telemetry property
    mock_client.telemetry = MagicMock()
    mock_client.telemetry.get_application_insights_connection_string = AsyncMock()

    # Mock get_openai_client method
    mock_client.get_openai_client = AsyncMock()

    # Mock close method
    mock_client.close = AsyncMock()

    return mock_client


@pytest.fixture
def mock_azure_credential() -> MagicMock:
    """Fixture that provides a mock Azure credential."""
    return MagicMock()


@pytest.fixture
def azure_ai_unit_test_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Fixture that sets up Azure AI environment variables for unit testing."""
    env_vars = {
        "AZURE_AI_PROJECT_ENDPOINT": "https://test-project.cognitiveservices.azure.com/",
        "AZURE_AI_MODEL_DEPLOYMENT_NAME": "test-model-deployment",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    return env_vars


def test_provider_init_with_project_client(mock_project_client: MagicMock) -> None:
    """Test AzureAIProjectAgentProvider initialization with existing project_client."""
    provider = AzureAIProjectAgentProvider(project_client=mock_project_client)

    assert provider._project_client is mock_project_client  # type: ignore
    assert not provider._should_close_client  # type: ignore


def test_provider_init_with_credential_and_endpoint(
    azure_ai_unit_test_env: dict[str, str],
    mock_azure_credential: MagicMock,
) -> None:
    """Test AzureAIProjectAgentProvider initialization with credential and endpoint."""
    with patch("agent_framework_azure_ai._project_provider.AIProjectClient") as mock_ai_project_client:
        mock_client = MagicMock()
        mock_ai_project_client.return_value = mock_client

        provider = AzureAIProjectAgentProvider(
            project_endpoint=azure_ai_unit_test_env["AZURE_AI_PROJECT_ENDPOINT"],
            credential=mock_azure_credential,
        )

        assert provider._project_client is mock_client  # type: ignore
        assert provider._should_close_client  # type: ignore

        # Verify AIProjectClient was called with correct parameters
        mock_ai_project_client.assert_called_once()


def test_provider_init_missing_endpoint() -> None:
    """Test AzureAIProjectAgentProvider initialization when endpoint is missing."""
    with patch("agent_framework_azure_ai._project_provider.AzureAISettings") as mock_settings:
        mock_settings.return_value.project_endpoint = None
        mock_settings.return_value.model_deployment_name = "test-model"

        with pytest.raises(ServiceInitializationError, match="Azure AI project endpoint is required"):
            AzureAIProjectAgentProvider(credential=MagicMock())


def test_provider_init_missing_credential(azure_ai_unit_test_env: dict[str, str]) -> None:
    """Test AzureAIProjectAgentProvider initialization when credential is missing."""
    with pytest.raises(
        ServiceInitializationError, match="Azure credential is required when project_client is not provided"
    ):
        AzureAIProjectAgentProvider(
            project_endpoint=azure_ai_unit_test_env["AZURE_AI_PROJECT_ENDPOINT"],
        )


async def test_provider_create_agent(
    mock_project_client: MagicMock,
    azure_ai_unit_test_env: dict[str, str],
) -> None:
    """Test AzureAIProjectAgentProvider.create_agent method."""
    with patch("agent_framework_azure_ai._project_provider.AzureAISettings") as mock_settings:
        mock_settings.return_value.project_endpoint = azure_ai_unit_test_env["AZURE_AI_PROJECT_ENDPOINT"]
        mock_settings.return_value.model_deployment_name = azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"]

        provider = AzureAIProjectAgentProvider(project_client=mock_project_client)

        # Mock agent creation response
        mock_agent_version = MagicMock(spec=AgentVersionDetails)
        mock_agent_version.id = "agent-id"
        mock_agent_version.name = "test-agent"
        mock_agent_version.version = "1.0"
        mock_agent_version.description = "Test Agent"
        mock_agent_version.definition = MagicMock(spec=PromptAgentDefinition)
        mock_agent_version.definition.model = "gpt-4"
        mock_agent_version.definition.instructions = "Test instructions"
        mock_agent_version.definition.temperature = 0.7
        mock_agent_version.definition.top_p = 0.9
        mock_agent_version.definition.tools = []

        mock_project_client.agents.create_version = AsyncMock(return_value=mock_agent_version)

        agent = await provider.create_agent(
            name="test-agent",
            model="gpt-4",
            instructions="Test instructions",
            description="Test Agent",
        )

        assert isinstance(agent, ChatAgent)
        assert agent.name == "test-agent"
        mock_project_client.agents.create_version.assert_called_once()


async def test_provider_create_agent_with_env_model(
    mock_project_client: MagicMock,
    azure_ai_unit_test_env: dict[str, str],
) -> None:
    """Test AzureAIProjectAgentProvider.create_agent uses model from env var."""
    with patch("agent_framework_azure_ai._project_provider.AzureAISettings") as mock_settings:
        mock_settings.return_value.project_endpoint = azure_ai_unit_test_env["AZURE_AI_PROJECT_ENDPOINT"]
        mock_settings.return_value.model_deployment_name = azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"]

        provider = AzureAIProjectAgentProvider(project_client=mock_project_client)

        # Mock agent creation response
        mock_agent_version = MagicMock(spec=AgentVersionDetails)
        mock_agent_version.id = "agent-id"
        mock_agent_version.name = "test-agent"
        mock_agent_version.version = "1.0"
        mock_agent_version.description = None
        mock_agent_version.definition = MagicMock(spec=PromptAgentDefinition)
        mock_agent_version.definition.model = azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
        mock_agent_version.definition.instructions = None
        mock_agent_version.definition.temperature = None
        mock_agent_version.definition.top_p = None
        mock_agent_version.definition.tools = []

        mock_project_client.agents.create_version = AsyncMock(return_value=mock_agent_version)

        # Call without model parameter - should use env var
        agent = await provider.create_agent(name="test-agent")

        assert isinstance(agent, ChatAgent)
        # Verify the model from env var was used
        call_args = mock_project_client.agents.create_version.call_args
        assert call_args[1]["definition"].model == azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"]


async def test_provider_create_agent_missing_model(mock_project_client: MagicMock) -> None:
    """Test AzureAIProjectAgentProvider.create_agent raises when model is missing."""
    with patch("agent_framework_azure_ai._project_provider.AzureAISettings") as mock_settings:
        mock_settings.return_value.project_endpoint = "https://test.com"
        mock_settings.return_value.model_deployment_name = None

        provider = AzureAIProjectAgentProvider(project_client=mock_project_client)

        with pytest.raises(ServiceInitializationError, match="Model deployment name is required"):
            await provider.create_agent(name="test-agent")


async def test_provider_create_agent_with_rai_config(
    mock_project_client: MagicMock,
    azure_ai_unit_test_env: dict[str, str],
) -> None:
    """Test AzureAIProjectAgentProvider.create_agent passes rai_config from default_options."""
    with patch("agent_framework_azure_ai._project_provider.AzureAISettings") as mock_settings:
        mock_settings.return_value.project_endpoint = azure_ai_unit_test_env["AZURE_AI_PROJECT_ENDPOINT"]
        mock_settings.return_value.model_deployment_name = azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"]

        provider = AzureAIProjectAgentProvider(project_client=mock_project_client)

        # Mock agent creation response
        mock_agent_version = MagicMock(spec=AgentVersionDetails)
        mock_agent_version.id = "agent-id"
        mock_agent_version.name = "test-agent"
        mock_agent_version.version = "1.0"
        mock_agent_version.description = None
        mock_agent_version.definition = MagicMock(spec=PromptAgentDefinition)
        mock_agent_version.definition.model = "gpt-4"
        mock_agent_version.definition.instructions = None
        mock_agent_version.definition.temperature = None
        mock_agent_version.definition.top_p = None
        mock_agent_version.definition.tools = []

        mock_project_client.agents.create_version = AsyncMock(return_value=mock_agent_version)

        # Create a mock RaiConfig-like object
        mock_rai_config = MagicMock()
        mock_rai_config.rai_policy_name = "policy-name"

        # Call create_agent with rai_config in default_options
        await provider.create_agent(
            name="test-agent",
            model="gpt-4",
            default_options={"rai_config": mock_rai_config},
        )

        # Verify rai_config was passed to PromptAgentDefinition
        call_args = mock_project_client.agents.create_version.call_args
        definition = call_args[1]["definition"]
        assert definition.rai_config is mock_rai_config


async def test_provider_create_agent_with_reasoning(
    mock_project_client: MagicMock,
    azure_ai_unit_test_env: dict[str, str],
) -> None:
    """Test AzureAIProjectAgentProvider.create_agent passes reasoning from default_options."""
    with patch("agent_framework_azure_ai._project_provider.AzureAISettings") as mock_settings:
        mock_settings.return_value.project_endpoint = azure_ai_unit_test_env["AZURE_AI_PROJECT_ENDPOINT"]
        mock_settings.return_value.model_deployment_name = azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"]

        provider = AzureAIProjectAgentProvider(project_client=mock_project_client)

        # Mock agent creation response
        mock_agent_version = MagicMock(spec=AgentVersionDetails)
        mock_agent_version.id = "agent-id"
        mock_agent_version.name = "test-agent"
        mock_agent_version.version = "1.0"
        mock_agent_version.description = None
        mock_agent_version.definition = MagicMock(spec=PromptAgentDefinition)
        mock_agent_version.definition.model = "gpt-5.2"
        mock_agent_version.definition.instructions = None
        mock_agent_version.definition.temperature = None
        mock_agent_version.definition.top_p = None
        mock_agent_version.definition.tools = []

        mock_project_client.agents.create_version = AsyncMock(return_value=mock_agent_version)

        # Create a mock Reasoning-like object
        mock_reasoning = MagicMock()
        mock_reasoning.effort = "medium"
        mock_reasoning.summary = "concise"

        # Call create_agent with reasoning in default_options
        await provider.create_agent(
            name="test-agent",
            model="gpt-5.2",
            default_options={"reasoning": mock_reasoning},
        )

        # Verify reasoning was passed to PromptAgentDefinition
        call_args = mock_project_client.agents.create_version.call_args
        definition = call_args[1]["definition"]
        assert definition.reasoning is mock_reasoning


async def test_provider_get_agent_with_name(mock_project_client: MagicMock) -> None:
    """Test AzureAIProjectAgentProvider.get_agent with name parameter."""
    provider = AzureAIProjectAgentProvider(project_client=mock_project_client)

    # Mock agent response
    mock_agent_version = MagicMock(spec=AgentVersionDetails)
    mock_agent_version.id = "agent-id"
    mock_agent_version.name = "test-agent"
    mock_agent_version.version = "1.0"
    mock_agent_version.description = "Test Agent"
    mock_agent_version.definition = MagicMock(spec=PromptAgentDefinition)
    mock_agent_version.definition.model = "gpt-4"
    mock_agent_version.definition.instructions = "Test instructions"
    mock_agent_version.definition.temperature = None
    mock_agent_version.definition.top_p = None
    mock_agent_version.definition.tools = []

    mock_agent_object = MagicMock()
    mock_agent_object.versions.latest = mock_agent_version

    mock_project_client.agents = AsyncMock()
    mock_project_client.agents.get.return_value = mock_agent_object

    agent = await provider.get_agent(name="test-agent")

    assert isinstance(agent, ChatAgent)
    assert agent.name == "test-agent"
    mock_project_client.agents.get.assert_called_with(agent_name="test-agent")


async def test_provider_get_agent_with_reference(mock_project_client: MagicMock) -> None:
    """Test AzureAIProjectAgentProvider.get_agent with reference parameter."""
    provider = AzureAIProjectAgentProvider(project_client=mock_project_client)

    # Mock agent response
    mock_agent_version = MagicMock(spec=AgentVersionDetails)
    mock_agent_version.id = "agent-id"
    mock_agent_version.name = "test-agent"
    mock_agent_version.version = "1.0"
    mock_agent_version.description = "Test Agent"
    mock_agent_version.definition = MagicMock(spec=PromptAgentDefinition)
    mock_agent_version.definition.model = "gpt-4"
    mock_agent_version.definition.instructions = "Test instructions"
    mock_agent_version.definition.temperature = None
    mock_agent_version.definition.top_p = None
    mock_agent_version.definition.tools = []

    mock_project_client.agents = AsyncMock()
    mock_project_client.agents.get_version.return_value = mock_agent_version

    agent_reference = AgentReference(name="test-agent", version="1.0")
    agent = await provider.get_agent(reference=agent_reference)

    assert isinstance(agent, ChatAgent)
    assert agent.name == "test-agent"
    mock_project_client.agents.get_version.assert_called_with(agent_name="test-agent", agent_version="1.0")


async def test_provider_get_agent_missing_parameters(mock_project_client: MagicMock) -> None:
    """Test AzureAIProjectAgentProvider.get_agent raises when no identifier provided."""
    provider = AzureAIProjectAgentProvider(project_client=mock_project_client)

    with pytest.raises(ValueError, match="Either name or reference must be provided"):
        await provider.get_agent()


async def test_provider_get_agent_missing_function_tools(mock_project_client: MagicMock) -> None:
    """Test AzureAIProjectAgentProvider.get_agent raises when required tools are missing."""
    provider = AzureAIProjectAgentProvider(project_client=mock_project_client)

    # Mock agent with function tools
    mock_agent_version = MagicMock(spec=AgentVersionDetails)
    mock_agent_version.id = "agent-id"
    mock_agent_version.name = "test-agent"
    mock_agent_version.version = "1.0"
    mock_agent_version.description = None
    mock_agent_version.definition = MagicMock(spec=PromptAgentDefinition)
    mock_agent_version.definition.tools = [
        AzureFunctionTool(name="test_tool", parameters=[], strict=True, description="Test tool")
    ]

    mock_agent_object = MagicMock()
    mock_agent_object.versions.latest = mock_agent_version

    mock_project_client.agents = AsyncMock()
    mock_project_client.agents.get.return_value = mock_agent_object

    with pytest.raises(
        ValueError, match="The following prompt agent definition required tools were not provided: test_tool"
    ):
        await provider.get_agent(name="test-agent")


def test_provider_as_agent(mock_project_client: MagicMock) -> None:
    """Test AzureAIProjectAgentProvider.as_agent method."""
    provider = AzureAIProjectAgentProvider(project_client=mock_project_client)

    # Create mock agent version
    mock_agent_version = MagicMock(spec=AgentVersionDetails)
    mock_agent_version.id = "agent-id"
    mock_agent_version.name = "test-agent"
    mock_agent_version.version = "1.0"
    mock_agent_version.description = "Test Agent"
    mock_agent_version.definition = MagicMock(spec=PromptAgentDefinition)
    mock_agent_version.definition.model = "gpt-4"
    mock_agent_version.definition.instructions = "Test instructions"
    mock_agent_version.definition.temperature = 0.7
    mock_agent_version.definition.top_p = 0.9
    mock_agent_version.definition.tools = []

    with patch("agent_framework_azure_ai._project_provider.AzureAIClient") as mock_azure_ai_client:
        agent = provider.as_agent(mock_agent_version)

        assert isinstance(agent, ChatAgent)
        assert agent.name == "test-agent"
        assert agent.description == "Test Agent"

        # Verify AzureAIClient was called with correct parameters
        mock_azure_ai_client.assert_called_once()
        call_kwargs = mock_azure_ai_client.call_args[1]
        assert call_kwargs["project_client"] is mock_project_client
        assert call_kwargs["agent_name"] == "test-agent"
        assert call_kwargs["agent_version"] == "1.0"
        assert call_kwargs["agent_description"] == "Test Agent"
        assert call_kwargs["model_deployment_name"] == "gpt-4"


def test_provider_merge_tools_skips_function_tool_dicts(mock_project_client: MagicMock) -> None:
    """Test that _merge_tools skips function tool dicts but keeps other hosted tools."""
    provider = AzureAIProjectAgentProvider(project_client=mock_project_client)

    # Create a mock FunctionTool to provide as implementation
    mock_ai_function = create_mock_ai_function("my_function", "My function description")

    # Definition tools include a function tool (dict) and an MCP tool
    definition_tools = [
        {"type": "function", "name": "my_function", "parameters": {}},  # Should be skipped
        {"type": "mcp", "server_label": "my_mcp", "server_url": "http://localhost:8080"},  # Should be converted
    ]

    # Call _merge_tools with user-provided function implementation
    merged = provider._merge_tools(definition_tools, [mock_ai_function])  # type: ignore

    # Should have 2 items: the converted HostedMCPTool and the user-provided FunctionTool
    assert len(merged) == 2

    # Check that the function tool dict was NOT included (it was skipped)
    function_dicts = [t for t in merged if isinstance(t, dict) and t.get("type") == "function"]
    assert len(function_dicts) == 0

    # Check that the MCP tool was converted to HostedMCPTool
    from agent_framework import HostedMCPTool

    mcp_tools = [t for t in merged if isinstance(t, HostedMCPTool)]
    assert len(mcp_tools) == 1
    assert mcp_tools[0].name == "my mcp"  # server_label with _ replaced by space

    # Check that the user-provided FunctionTool was included
    ai_functions = [t for t in merged if isinstance(t, FunctionTool)]
    assert len(ai_functions) == 1
    assert ai_functions[0].name == "my_function"


async def test_provider_context_manager(mock_project_client: MagicMock) -> None:
    """Test AzureAIProjectAgentProvider async context manager."""
    with patch("agent_framework_azure_ai._project_provider.AIProjectClient") as mock_ai_project_client:
        mock_client = MagicMock()
        mock_client.close = AsyncMock()
        mock_ai_project_client.return_value = mock_client

        with patch("agent_framework_azure_ai._project_provider.AzureAISettings") as mock_settings:
            mock_settings.return_value.project_endpoint = "https://test.com"
            mock_settings.return_value.model_deployment_name = "test-model"

            async with AzureAIProjectAgentProvider(credential=MagicMock()) as provider:
                assert provider._project_client is mock_client  # type: ignore

            # Should call close after exiting context
            mock_client.close.assert_called_once()


async def test_provider_context_manager_with_provided_client(mock_project_client: MagicMock) -> None:
    """Test AzureAIProjectAgentProvider context manager doesn't close provided client."""
    mock_project_client.close = AsyncMock()

    async with AzureAIProjectAgentProvider(project_client=mock_project_client) as provider:
        assert provider._project_client is mock_project_client  # type: ignore

    # Should NOT call close when client was provided
    mock_project_client.close.assert_not_called()


async def test_provider_close_method(mock_project_client: MagicMock) -> None:
    """Test AzureAIProjectAgentProvider.close method."""
    with patch("agent_framework_azure_ai._project_provider.AIProjectClient") as mock_ai_project_client:
        mock_client = MagicMock()
        mock_client.close = AsyncMock()
        mock_ai_project_client.return_value = mock_client

        with patch("agent_framework_azure_ai._project_provider.AzureAISettings") as mock_settings:
            mock_settings.return_value.project_endpoint = "https://test.com"
            mock_settings.return_value.model_deployment_name = "test-model"

            provider = AzureAIProjectAgentProvider(credential=MagicMock())
            await provider.close()

            mock_client.close.assert_called_once()


def test_create_text_format_config_sets_strict_for_pydantic_models() -> None:
    """Test that create_text_format_config sets strict=True for Pydantic models."""
    from pydantic import BaseModel

    from agent_framework_azure_ai._shared import create_text_format_config

    class TestSchema(BaseModel):
        subject: str
        summary: str

    result = create_text_format_config(TestSchema)

    # Verify strict=True is set
    assert result["strict"] is True
    assert result["name"] == "TestSchema"
    assert "schema" in result


class MockMCPTool(MCPTool):  # pyright: ignore[reportGeneralTypeIssues]
    """A mock MCPTool subclass for testing that passes isinstance checks.

    Note: This intentionally does NOT call super().__init__() because MCPTool's
    constructor requires MCP server connection parameters that aren't needed for
    unit testing. We only need isinstance(obj, MCPTool) to return True.
    """

    def __init__(self, functions: list[FunctionTool] | None = None) -> None:
        self.name = "MockMCPTool"
        self.description = "A mock MCP tool for testing"
        self.is_connected = False
        self._mock_functions = functions or []
        self._connect_called = False

    @property
    def functions(self) -> list[FunctionTool]:
        return self._mock_functions

    async def connect(self, *, reset: bool = False) -> None:
        self._connect_called = True
        self.is_connected = True


@pytest.fixture
def mock_mcp_tool() -> MockMCPTool:
    """Fixture that provides a mock MCPTool."""
    mock_functions = [
        create_mock_ai_function("mcp_function_1", "First MCP function"),
        create_mock_ai_function("mcp_function_2", "Second MCP function"),
    ]
    return MockMCPTool(functions=mock_functions)


def create_mock_ai_function(name: str, description: str = "A mock function") -> FunctionTool:
    """Create a real FunctionTool for testing."""

    def mock_func(arg: str) -> str:
        return f"Result from {name}: {arg}"

    return FunctionTool(func=mock_func, name=name, description=description, approval_mode="never_require")


async def test_provider_create_agent_with_mcp_tool(
    mock_project_client: MagicMock,
    azure_ai_unit_test_env: dict[str, str],
    mock_mcp_tool: "MockMCPTool",
) -> None:
    """Test that create_agent connects MCP tools and passes discovered functions to Azure AI."""

    # Patch normalize_tools to return tools as-is in a list (avoids callable check)
    def mock_normalize_tools(tools):
        if tools is None:
            return []
        if isinstance(tools, list):
            return tools
        return [tools]

    with (
        patch("agent_framework_azure_ai._project_provider.AzureAISettings") as mock_settings,
        patch("agent_framework_azure_ai._project_provider.to_azure_ai_tools") as mock_to_azure_tools,
        patch("agent_framework_azure_ai._project_provider.normalize_tools", side_effect=mock_normalize_tools),
    ):
        mock_settings.return_value.project_endpoint = azure_ai_unit_test_env["AZURE_AI_PROJECT_ENDPOINT"]
        mock_settings.return_value.model_deployment_name = azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
        mock_to_azure_tools.return_value = [{"type": "function", "name": "mcp_function_1"}]

        provider = AzureAIProjectAgentProvider(project_client=mock_project_client)

        # Mock agent creation response
        mock_agent_version = MagicMock(spec=AgentVersionDetails)
        mock_agent_version.id = "agent-id"
        mock_agent_version.name = "test-agent"
        mock_agent_version.version = "1.0"
        mock_agent_version.description = "Test Agent"
        mock_agent_version.definition = MagicMock(spec=PromptAgentDefinition)
        mock_agent_version.definition.model = "gpt-4"
        mock_agent_version.definition.instructions = "Test instructions"
        mock_agent_version.definition.tools = []

        mock_project_client.agents.create_version = AsyncMock(return_value=mock_agent_version)

        # Call create_agent with MCP tool
        await provider.create_agent(
            name="test-agent",
            model="gpt-4",
            instructions="Test instructions",
            tools=mock_mcp_tool,
        )

        # Verify MCP tool was connected
        assert mock_mcp_tool._connect_called is True
        assert mock_mcp_tool.is_connected is True

        # Verify to_azure_ai_tools was called with the discovered MCP functions
        mock_to_azure_tools.assert_called_once()
        tools_passed = mock_to_azure_tools.call_args[0][0]
        assert len(tools_passed) == 2
        assert tools_passed[0].name == "mcp_function_1"
        assert tools_passed[1].name == "mcp_function_2"


async def test_provider_create_agent_with_mcp_and_regular_tools(
    mock_project_client: MagicMock,
    azure_ai_unit_test_env: dict[str, str],
    mock_mcp_tool: "MockMCPTool",
) -> None:
    """Test that create_agent handles both MCP tools and regular FunctionTools."""
    # Create a regular FunctionTool
    regular_function = create_mock_ai_function("regular_function", "A regular function")

    # Patch normalize_tools to return tools as-is in a list (avoids callable check)
    def mock_normalize_tools(tools):
        if tools is None:
            return []
        if isinstance(tools, list):
            return tools
        return [tools]

    with (
        patch("agent_framework_azure_ai._project_provider.AzureAISettings") as mock_settings,
        patch("agent_framework_azure_ai._project_provider.to_azure_ai_tools") as mock_to_azure_tools,
        patch("agent_framework_azure_ai._project_provider.normalize_tools", side_effect=mock_normalize_tools),
    ):
        mock_settings.return_value.project_endpoint = azure_ai_unit_test_env["AZURE_AI_PROJECT_ENDPOINT"]
        mock_settings.return_value.model_deployment_name = azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
        mock_to_azure_tools.return_value = []

        provider = AzureAIProjectAgentProvider(project_client=mock_project_client)

        # Mock agent creation response
        mock_agent_version = MagicMock(spec=AgentVersionDetails)
        mock_agent_version.id = "agent-id"
        mock_agent_version.name = "test-agent"
        mock_agent_version.version = "1.0"
        mock_agent_version.description = None
        mock_agent_version.definition = MagicMock(spec=PromptAgentDefinition)
        mock_agent_version.definition.model = "gpt-4"
        mock_agent_version.definition.instructions = None
        mock_agent_version.definition.tools = []

        mock_project_client.agents.create_version = AsyncMock(return_value=mock_agent_version)

        # Pass both MCP tool and regular function
        await provider.create_agent(
            name="test-agent",
            model="gpt-4",
            tools=[mock_mcp_tool, regular_function],
        )

        # Verify to_azure_ai_tools was called with:
        # - The regular FunctionTool (1)
        # - The 2 discovered MCP functions
        mock_to_azure_tools.assert_called_once()
        tools_passed = mock_to_azure_tools.call_args[0][0]
        assert len(tools_passed) == 3  # 1 regular + 2 MCP functions

        # Verify the regular function is in the list
        tool_names = [t.name for t in tools_passed]
        assert "regular_function" in tool_names
        assert "mcp_function_1" in tool_names
        assert "mcp_function_2" in tool_names


@pytest.mark.flaky
@skip_if_azure_ai_integration_tests_disabled
async def test_provider_create_and_get_agent_integration() -> None:
    """Integration test for provider create_agent and get_agent."""
    endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]

    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        provider = AzureAIProjectAgentProvider(project_client=project_client)

        try:
            # Create agent
            agent = await provider.create_agent(
                name="ProviderTestAgent",
                model=model,
                instructions="You are a helpful assistant. Always respond with 'Hello from provider!'",
            )

            assert isinstance(agent, ChatAgent)
            assert agent.name == "ProviderTestAgent"

            # Run the agent
            response = await agent.run("Hi!")
            assert response.text is not None
            assert len(response.text) > 0

            # Get the same agent
            retrieved_agent = await provider.get_agent(name="ProviderTestAgent")
            assert retrieved_agent.name == "ProviderTestAgent"

        finally:
            # Cleanup
            await project_client.agents.delete(agent_name="ProviderTestAgent")
