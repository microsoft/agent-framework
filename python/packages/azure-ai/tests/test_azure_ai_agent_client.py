# Copyright (c) Microsoft. All rights reserved.

import json
import os
from pathlib import Path
from typing import Annotated, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    AIFunction,
    ChatAgent,
    ChatClientProtocol,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    CitationAnnotation,
    FunctionApprovalRequestContent,
    FunctionApprovalResponseContent,
    FunctionCallContent,
    FunctionResultContent,
    HostedCodeInterpreterTool,
    HostedFileSearchTool,
    HostedMCPTool,
    HostedVectorStoreContent,
    HostedWebSearchTool,
    Role,
    TextContent,
    ToolMode,
    UriContent,
)
from agent_framework._serialization import SerializationMixin
from agent_framework.exceptions import ServiceInitializationError
from azure.ai.agents.models import (
    AgentsNamedToolChoice,
    AgentsNamedToolChoiceType,
    CodeInterpreterToolDefinition,
    FileInfo,
    MessageDeltaChunk,
    MessageDeltaTextContent,
    MessageDeltaTextUrlCitationAnnotation,
    RequiredFunctionToolCall,
    RequiredMcpToolCall,
    RunStatus,
    SubmitToolApprovalAction,
    SubmitToolOutputsAction,
    ThreadRun,
    VectorStore,
)
from azure.core.credentials_async import AsyncTokenCredential
from azure.identity.aio import AzureCliCredential
from pydantic import BaseModel, Field, ValidationError

from agent_framework_azure_ai import AzureAIAgentClient, AzureAISettings

skip_if_azure_ai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("AZURE_AI_PROJECT_ENDPOINT", "") in ("", "https://test-project.cognitiveservices.azure.com/"),
    reason="No real AZURE_AI_PROJECT_ENDPOINT provided; skipping integration tests."
    if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    else "Integration tests are disabled.",
)


def create_test_azure_ai_chat_client(
    mock_agents_client: MagicMock,
    agent_id: str | None = None,
    thread_id: str | None = None,
    azure_ai_settings: AzureAISettings | None = None,
    should_cleanup_agent: bool = True,
    agent_name: str | None = None,
) -> AzureAIAgentClient:
    """Helper function to create AzureAIAgentClient instances for testing, bypassing normal validation."""
    if azure_ai_settings is None:
        azure_ai_settings = AzureAISettings(env_file_path="test.env")

    # Create client instance directly
    client = object.__new__(AzureAIAgentClient)

    # Set attributes directly
    client.agents_client = mock_agents_client
    client.credential = None
    client.agent_id = agent_id
    client.agent_name = agent_name
    client.agent_description = None
    client.model_id = azure_ai_settings.model_deployment_name
    client.thread_id = thread_id
    client.should_cleanup_agent = should_cleanup_agent
    client._agent_created = False
    client._should_close_client = False
    client._agent_definition = None
    client._azure_search_tool_calls = []  # Add the new instance variable
    client.additional_properties = {}
    client.middleware = None

    return client


def test_azure_ai_settings_init(azure_ai_unit_test_env: dict[str, str]) -> None:
    """Test AzureAISettings initialization."""
    settings = AzureAISettings()

    assert settings.project_endpoint == azure_ai_unit_test_env["AZURE_AI_PROJECT_ENDPOINT"]
    assert settings.model_deployment_name == azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"]


def test_azure_ai_settings_init_with_explicit_values() -> None:
    """Test AzureAISettings initialization with explicit values."""
    settings = AzureAISettings(
        project_endpoint="https://custom-endpoint.com/",
        model_deployment_name="custom-model",
    )

    assert settings.project_endpoint == "https://custom-endpoint.com/"
    assert settings.model_deployment_name == "custom-model"


def test_azure_ai_chat_client_init_with_client(mock_agents_client: MagicMock) -> None:
    """Test AzureAIAgentClient initialization with existing agents_client."""
    chat_client = create_test_azure_ai_chat_client(
        mock_agents_client, agent_id="existing-agent-id", thread_id="test-thread-id"
    )

    assert chat_client.agents_client is mock_agents_client
    assert chat_client.agent_id == "existing-agent-id"
    assert chat_client.thread_id == "test-thread-id"
    assert isinstance(chat_client, ChatClientProtocol)


def test_azure_ai_chat_client_init_auto_create_client(
    azure_ai_unit_test_env: dict[str, str],
    mock_agents_client: MagicMock,
) -> None:
    """Test AzureAIAgentClient initialization with auto-created agents_client."""
    azure_ai_settings = AzureAISettings(**azure_ai_unit_test_env)  # type: ignore

    # Create client instance directly
    chat_client = object.__new__(AzureAIAgentClient)
    chat_client.agents_client = mock_agents_client
    chat_client.agent_id = None
    chat_client.thread_id = None
    chat_client._should_close_client = False  # type: ignore
    chat_client.credential = None
    chat_client.model_id = azure_ai_settings.model_deployment_name
    chat_client.agent_name = None
    chat_client.additional_properties = {}
    chat_client.middleware = None

    assert chat_client.agents_client is mock_agents_client
    assert chat_client.agent_id is None


def test_azure_ai_chat_client_init_missing_project_endpoint() -> None:
    """Test AzureAIAgentClient initialization when project_endpoint is missing and no agents_client provided."""
    # Mock AzureAISettings to return settings with None project_endpoint
    with patch("agent_framework_azure_ai._chat_client.AzureAISettings") as mock_settings:
        mock_settings_instance = MagicMock()
        mock_settings_instance.project_endpoint = None  # This should trigger the error
        mock_settings_instance.model_deployment_name = "test-model"
        mock_settings_instance.agent_name = "test-agent"
        mock_settings.return_value = mock_settings_instance

        with pytest.raises(ServiceInitializationError, match="project endpoint is required"):
            AzureAIAgentClient(
                agents_client=None,
                agent_id=None,
                project_endpoint=None,  # Missing endpoint
                model_deployment_name="test-model",
                credential=AsyncMock(spec=AsyncTokenCredential),
            )


def test_azure_ai_chat_client_init_missing_model_deployment_for_agent_creation() -> None:
    """Test AzureAIAgentClient initialization when model deployment is missing for agent creation."""
    # Mock AzureAISettings to return settings with None model_deployment_name
    with patch("agent_framework_azure_ai._chat_client.AzureAISettings") as mock_settings:
        mock_settings_instance = MagicMock()
        mock_settings_instance.project_endpoint = "https://test.com"
        mock_settings_instance.model_deployment_name = None  # This should trigger the error
        mock_settings_instance.agent_name = "test-agent"
        mock_settings.return_value = mock_settings_instance

        with pytest.raises(ServiceInitializationError, match="model deployment name is required"):
            AzureAIAgentClient(
                agents_client=None,
                agent_id=None,  # No existing agent
                project_endpoint="https://test.com",
                model_deployment_name=None,  # Missing for agent creation
                credential=AsyncMock(spec=AsyncTokenCredential),
            )


def test_azure_ai_chat_client_from_dict(mock_agents_client: MagicMock) -> None:
    """Test AzureAIAgentClient.from_dict method."""
    settings = {
        "agents_client": mock_agents_client,
        "agent_id": "test-agent-id",
        "thread_id": "test-thread-id",
        "project_endpoint": "https://test-endpoint.com/",
        "model_deployment_name": "test-model",
        "agent_name": "TestAgent",
    }

    azure_ai_settings = AzureAISettings(
        project_endpoint=settings["project_endpoint"],
        model_deployment_name=settings["model_deployment_name"],
    )

    chat_client: AzureAIAgentClient = create_test_azure_ai_chat_client(
        mock_agents_client,
        agent_id=settings["agent_id"],  # type: ignore
        thread_id=settings["thread_id"],  # type: ignore
        azure_ai_settings=azure_ai_settings,
    )

    assert chat_client.agents_client is mock_agents_client
    assert chat_client.agent_id == "test-agent-id"
    assert chat_client.thread_id == "test-thread-id"


def test_azure_ai_chat_client_init_missing_credential(azure_ai_unit_test_env: dict[str, str]) -> None:
    """Test AzureAIAgentClient.__init__ when credential is missing and no agents_client provided."""
    with pytest.raises(
        ServiceInitializationError, match="Azure credential is required when agents_client is not provided"
    ):
        AzureAIAgentClient(
            agents_client=None,
            agent_id="existing-agent",
            project_endpoint=azure_ai_unit_test_env["AZURE_AI_PROJECT_ENDPOINT"],
            model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=None,  # Missing credential
        )


def test_azure_ai_chat_client_init_validation_error(mock_azure_credential: MagicMock) -> None:
    """Test that ValidationError in AzureAISettings is properly handled."""
    with patch("agent_framework_azure_ai._chat_client.AzureAISettings") as mock_settings:
        # Create a proper ValidationError with empty errors list and model dict
        mock_settings.side_effect = ValidationError.from_exception_data("AzureAISettings", [])

        with pytest.raises(ServiceInitializationError, match="Failed to create Azure AI settings."):
            AzureAIAgentClient(
                project_endpoint="https://test.com",
                model_deployment_name="test-model",
                credential=mock_azure_credential,
            )


def test_azure_ai_chat_client_from_settings() -> None:
    """Test from_settings class method."""
    mock_agents_client = MagicMock()
    settings = {
        "agents_client": mock_agents_client,
        "agent_id": "test-agent",
        "thread_id": "test-thread",
        "project_endpoint": "https://test.com",
        "model_deployment_name": "test-model",
        "agent_name": "TestAgent",
    }

    client = AzureAIAgentClient.from_settings(settings)

    assert client.agents_client is mock_agents_client
    assert client.agent_id == "test-agent"
    assert client.thread_id == "test-thread"
    assert client.agent_name == "TestAgent"


async def test_azure_ai_chat_client_get_agent_id_or_create_with_temperature_and_top_p(
    mock_agents_client: MagicMock, azure_ai_unit_test_env: dict[str, str]
) -> None:
    """Test _get_agent_id_or_create with temperature and top_p in run_options."""
    azure_ai_settings = AzureAISettings(model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"])
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, azure_ai_settings=azure_ai_settings)

    run_options = {
        "model": azure_ai_settings.model_deployment_name,
        "temperature": 0.7,
        "top_p": 0.9,
    }

    agent_id = await chat_client._get_agent_id_or_create(run_options)  # type: ignore

    assert agent_id == "test-agent-id"
    # Verify create_agent was called with temperature and top_p parameters
    mock_agents_client.create_agent.assert_called_once()
    call_kwargs = mock_agents_client.create_agent.call_args[1]
    assert call_kwargs["temperature"] == 0.7
    assert call_kwargs["top_p"] == 0.9


async def test_azure_ai_chat_client_get_agent_id_or_create_existing_agent(
    mock_agents_client: MagicMock,
) -> None:
    """Test _get_agent_id_or_create when agent_id is already provided."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="existing-agent-id")

    agent_id = await chat_client._get_agent_id_or_create()  # type: ignore

    assert agent_id == "existing-agent-id"
    assert not chat_client._agent_created


async def test_azure_ai_chat_client_get_agent_id_or_create_create_new(
    mock_agents_client: MagicMock,
    azure_ai_unit_test_env: dict[str, str],
) -> None:
    """Test _get_agent_id_or_create when creating a new agent."""
    azure_ai_settings = AzureAISettings(model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"])
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, azure_ai_settings=azure_ai_settings)

    agent_id = await chat_client._get_agent_id_or_create(run_options={"model": azure_ai_settings.model_deployment_name})  # type: ignore

    assert agent_id == "test-agent-id"
    assert chat_client._agent_created


async def test_azure_ai_chat_client_thread_management_through_public_api(mock_agents_client: MagicMock) -> None:
    """Test thread creation and management through public API."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Mock get_agent to avoid the async error
    mock_agents_client.get_agent = AsyncMock(return_value=None)

    mock_thread = MagicMock()
    mock_thread.id = "new-thread-456"
    mock_agents_client.threads.create = AsyncMock(return_value=mock_thread)

    mock_stream = AsyncMock()
    mock_agents_client.runs.stream = AsyncMock(return_value=mock_stream)

    # Create an async iterator that yields nothing (empty stream)
    async def empty_async_iter():
        return
        yield  # Make this a generator (unreachable)

    mock_stream.__aenter__ = AsyncMock(return_value=empty_async_iter())
    mock_stream.__aexit__ = AsyncMock(return_value=None)

    messages = [ChatMessage(role=Role.USER, text="Hello")]

    # Call without existing thread - should create new one
    response = chat_client.get_streaming_response(messages)
    # Consume the generator to trigger the method execution
    async for _ in response:
        pass

    # Verify thread creation was called
    mock_agents_client.threads.create.assert_called_once()


@pytest.mark.parametrize("exclude_list", [["AZURE_AI_MODEL_DEPLOYMENT_NAME"]], indirect=True)
async def test_azure_ai_chat_client_get_agent_id_or_create_missing_model(
    mock_agents_client: MagicMock, azure_ai_unit_test_env: dict[str, str]
) -> None:
    """Test _get_agent_id_or_create when model_deployment_name is missing."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    with pytest.raises(ServiceInitializationError, match="Model deployment name is required"):
        await chat_client._get_agent_id_or_create()  # type: ignore


async def test_azure_ai_chat_client_create_run_options_basic(mock_agents_client: MagicMock) -> None:
    """Test _create_run_options with basic ChatOptions."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    messages = [ChatMessage(role=Role.USER, text="Hello")]
    chat_options = ChatOptions(max_tokens=100, temperature=0.7)

    run_options, tool_results = await chat_client._create_run_options(messages, chat_options)  # type: ignore

    assert run_options is not None
    assert tool_results is None


async def test_azure_ai_chat_client_create_run_options_no_chat_options(mock_agents_client: MagicMock) -> None:
    """Test _create_run_options with no ChatOptions."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    messages = [ChatMessage(role=Role.USER, text="Hello")]

    run_options, tool_results = await chat_client._create_run_options(messages, None)  # type: ignore

    assert run_options is not None
    assert tool_results is None


async def test_azure_ai_chat_client_create_run_options_with_image_content(mock_agents_client: MagicMock) -> None:
    """Test _create_run_options with image content."""

    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Mock get_agent
    mock_agents_client.get_agent = AsyncMock(return_value=None)

    image_content = UriContent(uri="https://example.com/image.jpg", media_type="image/jpeg")
    messages = [ChatMessage(role=Role.USER, contents=[image_content])]

    run_options, _ = await chat_client._create_run_options(messages, None)  # type: ignore

    assert "additional_messages" in run_options
    assert len(run_options["additional_messages"]) == 1
    # Verify image was converted to MessageInputImageUrlBlock
    message = run_options["additional_messages"][0]
    assert len(message.content) == 1


def test_azure_ai_chat_client_convert_function_results_to_tool_output_none(mock_agents_client: MagicMock) -> None:
    """Test _convert_required_action_to_tool_output with None input."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    run_id, tool_outputs, tool_approvals = chat_client._convert_required_action_to_tool_output(None)  # type: ignore

    assert run_id is None
    assert tool_outputs is None
    assert tool_approvals is None


async def test_azure_ai_chat_client_close_client_when_should_close_true(mock_agents_client: MagicMock) -> None:
    """Test _close_client_if_needed closes agents_client when should_close_client is True."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)
    chat_client._should_close_client = True  # type: ignore

    mock_agents_client.close = AsyncMock()

    await chat_client._close_client_if_needed()  # type: ignore

    mock_agents_client.close.assert_called_once()


async def test_azure_ai_chat_client_close_client_when_should_close_false(mock_agents_client: MagicMock) -> None:
    """Test _close_client_if_needed does not close agents_client when should_close_client is False."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)
    chat_client._should_close_client = False  # type: ignore

    await chat_client._close_client_if_needed()  # type: ignore

    mock_agents_client.close.assert_not_called()


def test_azure_ai_chat_client_update_agent_name_and_description_when_current_is_none(
    mock_agents_client: MagicMock,
) -> None:
    """Test _update_agent_name_and_description updates name when current agent_name is None."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)
    chat_client.agent_name = None  # type: ignore

    chat_client._update_agent_name_and_description("NewAgentName", "description")  # type: ignore

    assert chat_client.agent_name == "NewAgentName"
    assert chat_client.agent_description == "description"


def test_azure_ai_chat_client_update_agent_name_and_description_when_current_exists(
    mock_agents_client: MagicMock,
) -> None:
    """Test _update_agent_name_and_description does not update when current agent_name exists."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)
    chat_client.agent_name = "ExistingName"  # type: ignore
    chat_client.agent_description = "ExistingDescription"  # type: ignore

    chat_client._update_agent_name_and_description("NewAgentName", "description")  # type: ignore

    assert chat_client.agent_name == "ExistingName"
    assert chat_client.agent_description == "ExistingDescription"


def test_azure_ai_chat_client_update_agent_name_and_description_with_none_input(mock_agents_client: MagicMock) -> None:
    """Test _update_agent_name_and_description with None input."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)
    chat_client.agent_name = None  # type: ignore
    chat_client.agent_description = None  # type: ignore

    chat_client._update_agent_name_and_description(None, None)  # type: ignore

    assert chat_client.agent_name is None
    assert chat_client.agent_description is None


async def test_azure_ai_chat_client_create_run_options_with_messages(mock_agents_client: MagicMock) -> None:
    """Test _create_run_options with different message types."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    # Test with system message (becomes instruction)
    messages = [
        ChatMessage(role=Role.SYSTEM, text="You are a helpful assistant"),
        ChatMessage(role=Role.USER, text="Hello"),
    ]

    run_options, _ = await chat_client._create_run_options(messages, None)  # type: ignore

    assert "instructions" in run_options
    assert "You are a helpful assistant" in run_options["instructions"]
    assert "additional_messages" in run_options
    assert len(run_options["additional_messages"]) == 1  # Only user message


async def test_azure_ai_chat_client_inner_get_response(mock_agents_client: MagicMock) -> None:
    """Test _inner_get_response method."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")
    messages = [ChatMessage(role=Role.USER, text="Hello")]
    chat_options = ChatOptions()

    async def mock_streaming_response():
        yield ChatResponseUpdate(role=Role.ASSISTANT, text="Hello back")

    with (
        patch.object(chat_client, "_inner_get_streaming_response", return_value=mock_streaming_response()),
        patch("agent_framework.ChatResponse.from_chat_response_generator") as mock_from_generator,
    ):
        mock_response = ChatResponse(role=Role.ASSISTANT, text="Hello back")
        mock_from_generator.return_value = mock_response

        result = await chat_client._inner_get_response(messages=messages, chat_options=chat_options)  # type: ignore

        assert result is mock_response
        mock_from_generator.assert_called_once()


async def test_azure_ai_chat_client_get_agent_id_or_create_with_run_options(
    mock_agents_client: MagicMock, azure_ai_unit_test_env: dict[str, str]
) -> None:
    """Test _get_agent_id_or_create with run_options containing tools and instructions."""
    azure_ai_settings = AzureAISettings(model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"])
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, azure_ai_settings=azure_ai_settings)

    run_options = {
        "tools": [{"type": "function", "function": {"name": "test_tool"}}],
        "instructions": "Test instructions",
        "response_format": {"type": "json_object"},
        "model": azure_ai_settings.model_deployment_name,
    }

    agent_id = await chat_client._get_agent_id_or_create(run_options)  # type: ignore

    assert agent_id == "test-agent-id"
    # Verify create_agent was called with run_options parameters
    mock_agents_client.create_agent.assert_called_once()
    call_args = mock_agents_client.create_agent.call_args[1]
    assert "tools" in call_args
    assert "instructions" in call_args
    assert "response_format" in call_args


async def test_azure_ai_chat_client_prepare_thread_cancels_active_run(mock_agents_client: MagicMock) -> None:
    """Test _prepare_thread cancels active thread run when provided."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    mock_thread_run = MagicMock()
    mock_thread_run.id = "run_123"
    mock_thread_run.thread_id = "test-thread"

    run_options = {"additional_messages": []}  # type: ignore

    result = await chat_client._prepare_thread("test-thread", mock_thread_run, run_options)  # type: ignore

    assert result == "test-thread"
    mock_agents_client.runs.cancel.assert_called_once_with("test-thread", "run_123")


def test_azure_ai_chat_client_create_function_call_contents_basic(mock_agents_client: MagicMock) -> None:
    """Test _create_function_call_contents with basic function call."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    mock_tool_call = MagicMock(spec=RequiredFunctionToolCall)
    mock_tool_call.id = "call_123"
    mock_tool_call.function.name = "get_weather"
    mock_tool_call.function.arguments = '{"location": "Seattle"}'

    mock_submit_action = MagicMock(spec=SubmitToolOutputsAction)
    mock_submit_action.submit_tool_outputs.tool_calls = [mock_tool_call]

    mock_event_data = MagicMock(spec=ThreadRun)
    mock_event_data.required_action = mock_submit_action

    result = chat_client._create_function_call_contents(mock_event_data, "response_123")  # type: ignore

    assert len(result) == 1
    assert isinstance(result[0], FunctionCallContent)
    assert result[0].name == "get_weather"
    assert result[0].call_id == '["response_123", "call_123"]'


def test_azure_ai_chat_client_create_function_call_contents_no_submit_action(mock_agents_client: MagicMock) -> None:
    """Test _create_function_call_contents when required_action is not SubmitToolOutputsAction."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    mock_event_data = MagicMock(spec=ThreadRun)
    mock_event_data.required_action = MagicMock()

    result = chat_client._create_function_call_contents(mock_event_data, "response_123")  # type: ignore

    assert result == []


def test_azure_ai_chat_client_create_function_call_contents_non_function_tool_call(
    mock_agents_client: MagicMock,
) -> None:
    """Test _create_function_call_contents with non-function tool call."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    mock_tool_call = MagicMock()

    mock_submit_action = MagicMock(spec=SubmitToolOutputsAction)
    mock_submit_action.submit_tool_outputs.tool_calls = [mock_tool_call]

    mock_event_data = MagicMock(spec=ThreadRun)
    mock_event_data.required_action = mock_submit_action

    result = chat_client._create_function_call_contents(mock_event_data, "response_123")  # type: ignore

    assert result == []


async def test_azure_ai_chat_client_create_run_options_with_none_tool_choice(
    mock_agents_client: MagicMock,
) -> None:
    """Test _create_run_options with tool_choice set to 'none'."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    chat_options = ChatOptions()
    chat_options.tool_choice = "none"

    run_options, _ = await chat_client._create_run_options([], chat_options)  # type: ignore

    from azure.ai.agents.models import AgentsToolChoiceOptionMode

    assert run_options["tool_choice"] == AgentsToolChoiceOptionMode.NONE


async def test_azure_ai_chat_client_create_run_options_with_auto_tool_choice(
    mock_agents_client: MagicMock,
) -> None:
    """Test _create_run_options with tool_choice set to 'auto'."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    chat_options = ChatOptions()
    chat_options.tool_choice = "auto"

    run_options, _ = await chat_client._create_run_options([], chat_options)  # type: ignore

    from azure.ai.agents.models import AgentsToolChoiceOptionMode

    assert run_options["tool_choice"] == AgentsToolChoiceOptionMode.AUTO


async def test_azure_ai_chat_client_prepare_tool_choice_none_string(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_tool_choice when tool_choice is string 'none'."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    # Create a mock tool for testing
    mock_tool = MagicMock()
    chat_options = ChatOptions(tools=[mock_tool], tool_choice="none")

    # Call the method
    chat_client._prepare_tool_choice(chat_options)  # type: ignore

    # Verify tools are cleared and tool_choice is set to NONE mode
    assert chat_options.tools is None
    assert chat_options.tool_choice == ToolMode.NONE.mode


async def test_azure_ai_chat_client_create_run_options_tool_choice_required_specific_function(
    mock_agents_client: MagicMock,
) -> None:
    """Test _create_run_options with ToolMode.REQUIRED specifying a specific function name."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    required_tool_mode = ToolMode.REQUIRED("specific_function_name")

    dict_tool = {"type": "function", "function": {"name": "test_function"}}

    chat_options = ChatOptions(tools=[dict_tool], tool_choice=required_tool_mode)
    messages = [ChatMessage(role=Role.USER, text="Hello")]

    run_options, _ = await chat_client._create_run_options(messages, chat_options)  # type: ignore

    # Verify tool_choice is set to the specific named function
    assert "tool_choice" in run_options
    tool_choice = run_options["tool_choice"]
    assert isinstance(tool_choice, AgentsNamedToolChoice)
    assert tool_choice.type == AgentsNamedToolChoiceType.FUNCTION
    assert tool_choice.function.name == "specific_function_name"  # type: ignore


async def test_azure_ai_chat_client_create_run_options_with_response_format(
    mock_agents_client: MagicMock,
) -> None:
    """Test _create_run_options with response_format configured."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    class TestResponseModel(BaseModel):
        name: str = Field(description="Test name")

    chat_options = ChatOptions()
    chat_options.response_format = TestResponseModel

    run_options, _ = await chat_client._create_run_options([], chat_options)  # type: ignore

    assert "response_format" in run_options
    response_format = run_options["response_format"]
    assert response_format.json_schema.name == "TestResponseModel"


def test_azure_ai_chat_client_service_url_method(mock_agents_client: MagicMock) -> None:
    """Test service_url method returns endpoint."""
    mock_agents_client._config.endpoint = "https://test-endpoint.com/"
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    url = chat_client.service_url()
    assert url == "https://test-endpoint.com/"


async def test_azure_ai_chat_client_prep_tools_ai_function(mock_agents_client: MagicMock) -> None:
    """Test _prep_tools with AIFunction tool."""

    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Create a mock AIFunction
    mock_ai_function = MagicMock(spec=AIFunction)
    mock_ai_function.to_json_schema_spec.return_value = {"type": "function", "function": {"name": "test_function"}}

    result = await chat_client._prep_tools([mock_ai_function])  # type: ignore

    assert len(result) == 1
    assert result[0] == {"type": "function", "function": {"name": "test_function"}}
    mock_ai_function.to_json_schema_spec.assert_called_once()


async def test_azure_ai_chat_client_prep_tools_code_interpreter(mock_agents_client: MagicMock) -> None:
    """Test _prep_tools with HostedCodeInterpreterTool."""

    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    code_interpreter_tool = HostedCodeInterpreterTool()

    result = await chat_client._prep_tools([code_interpreter_tool])  # type: ignore

    assert len(result) == 1
    assert isinstance(result[0], CodeInterpreterToolDefinition)


async def test_azure_ai_chat_client_prep_tools_mcp_tool(mock_agents_client: MagicMock) -> None:
    """Test _prep_tools with HostedMCPTool."""

    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    mcp_tool = HostedMCPTool(name="Test MCP Tool", url="https://example.com/mcp", allowed_tools=["tool1", "tool2"])

    # Mock McpTool to have a definitions attribute
    with patch("agent_framework_azure_ai._chat_client.McpTool") as mock_mcp_tool_class:
        mock_mcp_tool = MagicMock()
        mock_mcp_tool.definitions = [{"type": "mcp", "name": "test_mcp"}]
        mock_mcp_tool_class.return_value = mock_mcp_tool

        result = await chat_client._prep_tools([mcp_tool])  # type: ignore

        assert len(result) == 1
        assert result[0] == {"type": "mcp", "name": "test_mcp"}
        # Check that the call was made (order of allowed_tools may vary)
        mock_mcp_tool_class.assert_called_once()
        call_args = mock_mcp_tool_class.call_args[1]
        assert call_args["server_label"] == "Test_MCP_Tool"
        assert call_args["server_url"] == "https://example.com/mcp"
        assert set(call_args["allowed_tools"]) == {"tool1", "tool2"}


async def test_azure_ai_chat_client_create_run_options_mcp_never_require(mock_agents_client: MagicMock) -> None:
    """Test _create_run_options with HostedMCPTool having never_require approval mode."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    mcp_tool = HostedMCPTool(name="Test MCP Tool", url="https://example.com/mcp", approval_mode="never_require")

    messages = [ChatMessage(role=Role.USER, text="Hello")]
    chat_options = ChatOptions(tools=[mcp_tool], tool_choice="auto")

    with patch("agent_framework_azure_ai._chat_client.McpTool") as mock_mcp_tool_class:
        # Mock _prep_tools to avoid actual tool preparation
        mock_mcp_tool_instance = MagicMock()
        mock_mcp_tool_instance.definitions = [{"type": "mcp", "name": "test_mcp"}]
        mock_mcp_tool_class.return_value = mock_mcp_tool_instance

        run_options, _ = await chat_client._create_run_options(messages, chat_options)  # type: ignore

        # Verify tool_resources is created with correct MCP approval structure
        assert "tool_resources" in run_options, (
            f"Expected 'tool_resources' in run_options keys: {list(run_options.keys())}"
        )
        assert "mcp" in run_options["tool_resources"]
        assert len(run_options["tool_resources"]["mcp"]) == 1

        mcp_resource = run_options["tool_resources"]["mcp"][0]
        assert mcp_resource["server_label"] == "Test_MCP_Tool"
        assert mcp_resource["require_approval"] == "never"


async def test_azure_ai_chat_client_create_run_options_mcp_with_headers(mock_agents_client: MagicMock) -> None:
    """Test _create_run_options with HostedMCPTool having headers."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    # Test with headers
    headers = {"Authorization": "Bearer DUMMY_TOKEN", "X-API-Key": "DUMMY_KEY"}
    mcp_tool = HostedMCPTool(
        name="Test MCP Tool", url="https://example.com/mcp", headers=headers, approval_mode="never_require"
    )

    messages = [ChatMessage(role=Role.USER, text="Hello")]
    chat_options = ChatOptions(tools=[mcp_tool], tool_choice="auto")

    with patch("agent_framework_azure_ai._chat_client.McpTool") as mock_mcp_tool_class:
        # Mock _prep_tools to avoid actual tool preparation
        mock_mcp_tool_instance = MagicMock()
        mock_mcp_tool_instance.definitions = [{"type": "mcp", "name": "test_mcp"}]
        mock_mcp_tool_class.return_value = mock_mcp_tool_instance

        run_options, _ = await chat_client._create_run_options(messages, chat_options)  # type: ignore

        # Verify tool_resources is created with headers
        assert "tool_resources" in run_options
        assert "mcp" in run_options["tool_resources"]
        assert len(run_options["tool_resources"]["mcp"]) == 1

        mcp_resource = run_options["tool_resources"]["mcp"][0]
        assert mcp_resource["server_label"] == "Test_MCP_Tool"
        assert mcp_resource["require_approval"] == "never"
        assert mcp_resource["headers"] == headers


async def test_azure_ai_chat_client_prep_tools_web_search_bing_grounding(mock_agents_client: MagicMock) -> None:
    """Test _prep_tools with HostedWebSearchTool using Bing Grounding."""

    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    web_search_tool = HostedWebSearchTool(
        additional_properties={
            "connection_id": "test-connection-id",
            "count": 5,
            "freshness": "Day",
            "market": "en-US",
            "set_lang": "en",
        }
    )

    # Mock BingGroundingTool
    with patch("agent_framework_azure_ai._chat_client.BingGroundingTool") as mock_bing_grounding:
        mock_bing_tool = MagicMock()
        mock_bing_tool.definitions = [{"type": "bing_grounding"}]
        mock_bing_grounding.return_value = mock_bing_tool

        result = await chat_client._prep_tools([web_search_tool])  # type: ignore

        assert len(result) == 1
        assert result[0] == {"type": "bing_grounding"}
        call_args = mock_bing_grounding.call_args[1]
        assert call_args["count"] == 5
        assert call_args["freshness"] == "Day"
        assert call_args["market"] == "en-US"
        assert call_args["set_lang"] == "en"
        assert "connection_id" in call_args


async def test_azure_ai_chat_client_prep_tools_web_search_bing_grounding_with_connection_id(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prep_tools with HostedWebSearchTool using Bing Grounding with connection_id (no HTTP call)."""

    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    web_search_tool = HostedWebSearchTool(
        additional_properties={
            "connection_id": "direct-connection-id",
            "count": 3,
        }
    )

    # Mock BingGroundingTool
    with patch("agent_framework_azure_ai._chat_client.BingGroundingTool") as mock_bing_grounding:
        mock_bing_tool = MagicMock()
        mock_bing_tool.definitions = [{"type": "bing_grounding"}]
        mock_bing_grounding.return_value = mock_bing_tool

        result = await chat_client._prep_tools([web_search_tool])  # type: ignore

        assert len(result) == 1
        assert result[0] == {"type": "bing_grounding"}
        mock_bing_grounding.assert_called_once_with(connection_id="direct-connection-id", count=3)


async def test_azure_ai_chat_client_prep_tools_web_search_custom_bing(mock_agents_client: MagicMock) -> None:
    """Test _prep_tools with HostedWebSearchTool using Custom Bing Search."""

    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    web_search_tool = HostedWebSearchTool(
        additional_properties={
            "custom_connection_id": "custom-connection-id",
            "custom_instance_name": "custom-instance",
            "count": 10,
        }
    )

    # Mock BingCustomSearchTool
    with patch("agent_framework_azure_ai._chat_client.BingCustomSearchTool") as mock_custom_bing:
        mock_custom_tool = MagicMock()
        mock_custom_tool.definitions = [{"type": "bing_custom_search"}]
        mock_custom_bing.return_value = mock_custom_tool

        result = await chat_client._prep_tools([web_search_tool])  # type: ignore

        assert len(result) == 1
        assert result[0] == {"type": "bing_custom_search"}


async def test_azure_ai_chat_client_prep_tools_file_search_with_vector_stores(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prep_tools with HostedFileSearchTool using vector stores."""

    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    vector_store_input = HostedVectorStoreContent(vector_store_id="vs-123")
    file_search_tool = HostedFileSearchTool(inputs=[vector_store_input])

    # Mock FileSearchTool
    with patch("agent_framework_azure_ai._chat_client.FileSearchTool") as mock_file_search:
        mock_file_tool = MagicMock()
        mock_file_tool.definitions = [{"type": "file_search"}]
        mock_file_tool.resources = {"vector_store_ids": ["vs-123"]}
        mock_file_search.return_value = mock_file_tool

        run_options = {}
        result = await chat_client._prep_tools([file_search_tool], run_options)  # type: ignore

        assert len(result) == 1
        assert result[0] == {"type": "file_search"}
        assert run_options["tool_resources"] == {"vector_store_ids": ["vs-123"]}
        mock_file_search.assert_called_once_with(vector_store_ids=["vs-123"])


async def test_azure_ai_chat_client_create_agent_stream_submit_tool_approvals(
    mock_agents_client: MagicMock,
) -> None:
    """Test _create_agent_stream with tool approvals submission path."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Mock active thread run that matches the tool run ID
    mock_thread_run = MagicMock()
    mock_thread_run.thread_id = "test-thread"
    mock_thread_run.id = "test-run-id"
    chat_client._get_active_thread_run = AsyncMock(return_value=mock_thread_run)  # type: ignore

    # Mock required action results with approval response that matches run ID
    approval_response = FunctionApprovalResponseContent(
        id='["test-run-id", "test-call-id"]',
        function_call=FunctionCallContent(
            call_id='["test-run-id", "test-call-id"]', name="test_function", arguments="{}"
        ),
        approved=True,
    )

    # Mock submit_tool_outputs_stream
    mock_handler = MagicMock()
    mock_agents_client.runs.submit_tool_outputs_stream = AsyncMock()

    with patch("azure.ai.agents.models.AsyncAgentEventHandler", return_value=mock_handler):
        stream, final_thread_id = await chat_client._create_agent_stream(  # type: ignore
            "test-thread", "test-agent", {}, [approval_response]
        )

        # Verify the approvals path was taken
        assert final_thread_id == "test-thread"

        # Verify submit_tool_outputs_stream was called with approvals
        mock_agents_client.runs.submit_tool_outputs_stream.assert_called_once()
        call_args = mock_agents_client.runs.submit_tool_outputs_stream.call_args[1]
        assert "tool_approvals" in call_args
        assert call_args["tool_approvals"][0].tool_call_id == "test-call-id"
        assert call_args["tool_approvals"][0].approve is True


async def test_azure_ai_chat_client_prep_tools_dict_tool(mock_agents_client: MagicMock) -> None:
    """Test _prep_tools with dictionary tool definition."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    dict_tool = {"type": "custom_tool", "config": {"param": "value"}}

    result = await chat_client._prep_tools([dict_tool])  # type: ignore

    assert len(result) == 1
    assert result[0] == dict_tool


async def test_azure_ai_chat_client_prep_tools_unsupported_tool(mock_agents_client: MagicMock) -> None:
    """Test _prep_tools with unsupported tool type."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    unsupported_tool = "not_a_tool"

    with pytest.raises(ServiceInitializationError, match="Unsupported tool type: <class 'str'>"):
        await chat_client._prep_tools([unsupported_tool])  # type: ignore


async def test_azure_ai_chat_client_get_active_thread_run_with_active_run(mock_agents_client: MagicMock) -> None:
    """Test _get_active_thread_run when there's an active run."""

    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Mock an active run
    mock_run = MagicMock()
    mock_run.status = RunStatus.IN_PROGRESS

    async def mock_list_runs(*args, **kwargs):  # type: ignore
        yield mock_run

    mock_agents_client.runs.list = mock_list_runs

    result = await chat_client._get_active_thread_run("thread-123")  # type: ignore

    assert result == mock_run


async def test_azure_ai_chat_client_get_active_thread_run_no_active_run(mock_agents_client: MagicMock) -> None:
    """Test _get_active_thread_run when there's no active run."""

    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Mock a completed run (not active)
    mock_run = MagicMock()
    mock_run.status = RunStatus.COMPLETED

    async def mock_list_runs(*args, **kwargs):  # type: ignore
        yield mock_run

    mock_agents_client.runs.list = mock_list_runs

    result = await chat_client._get_active_thread_run("thread-123")  # type: ignore

    assert result is None


async def test_azure_ai_chat_client_get_active_thread_run_no_thread(mock_agents_client: MagicMock) -> None:
    """Test _get_active_thread_run with None thread_id."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    result = await chat_client._get_active_thread_run(None)  # type: ignore

    assert result is None
    # Should not call list since thread_id is None
    mock_agents_client.runs.list.assert_not_called()


async def test_azure_ai_chat_client_service_url(mock_agents_client: MagicMock) -> None:
    """Test service_url method."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Mock the config endpoint
    mock_config = MagicMock()
    mock_config.endpoint = "https://test-endpoint.com/"
    mock_agents_client._config = mock_config

    result = chat_client.service_url()

    assert result == "https://test-endpoint.com/"


async def test_azure_ai_chat_client_convert_required_action_to_tool_output_function_result(
    mock_agents_client: MagicMock,
) -> None:
    """Test _convert_required_action_to_tool_output with FunctionResultContent."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Test with simple result
    function_result = FunctionResultContent(call_id='["run_123", "call_456"]', result="Simple result")

    run_id, tool_outputs, tool_approvals = chat_client._convert_required_action_to_tool_output([function_result])  # type: ignore

    assert run_id == "run_123"
    assert tool_approvals is None
    assert tool_outputs is not None
    assert len(tool_outputs) == 1
    assert tool_outputs[0].tool_call_id == "call_456"
    assert tool_outputs[0].output == "Simple result"


async def test_azure_ai_chat_client_convert_required_action_invalid_call_id(mock_agents_client: MagicMock) -> None:
    """Test _convert_required_action_to_tool_output with invalid call_id format."""

    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Invalid call_id format - should raise JSONDecodeError
    function_result = FunctionResultContent(call_id="invalid_json", result="result")

    with pytest.raises(json.JSONDecodeError):
        chat_client._convert_required_action_to_tool_output([function_result])  # type: ignore


async def test_azure_ai_chat_client_convert_required_action_invalid_structure(
    mock_agents_client: MagicMock,
) -> None:
    """Test _convert_required_action_to_tool_output with invalid call_id structure."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Valid JSON but invalid structure (missing second element)
    function_result = FunctionResultContent(call_id='["run_123"]', result="result")

    run_id, tool_outputs, tool_approvals = chat_client._convert_required_action_to_tool_output([function_result])  # type: ignore

    # Should return None values when structure is invalid
    assert run_id is None
    assert tool_outputs is None
    assert tool_approvals is None


async def test_azure_ai_chat_client_convert_required_action_serde_model_results(
    mock_agents_client: MagicMock,
) -> None:
    """Test _convert_required_action_to_tool_output with BaseModel results."""

    class MockResult(SerializationMixin):
        def __init__(self, name: str, value: int):
            self.name = name
            self.value = value

    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Test with BaseModel result
    mock_result = MockResult(name="test", value=42)
    function_result = FunctionResultContent(call_id='["run_123", "call_456"]', result=mock_result)

    run_id, tool_outputs, tool_approvals = chat_client._convert_required_action_to_tool_output([function_result])  # type: ignore

    assert run_id == "run_123"
    assert tool_approvals is None
    assert tool_outputs is not None
    assert len(tool_outputs) == 1
    assert tool_outputs[0].tool_call_id == "call_456"
    # Should use model_dump_json for BaseModel
    expected_json = mock_result.to_json()
    assert tool_outputs[0].output == expected_json


async def test_azure_ai_chat_client_convert_required_action_multiple_results(
    mock_agents_client: MagicMock,
) -> None:
    """Test _convert_required_action_to_tool_output with multiple results."""

    class MockResult(SerializationMixin):
        def __init__(self, data: str):
            self.data = data

    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Test with multiple results - mix of BaseModel and regular objects
    mock_basemodel = MockResult(data="model_data")
    results_list = [mock_basemodel, {"key": "value"}, "string_result"]
    function_result = FunctionResultContent(call_id='["run_123", "call_456"]', result=results_list)

    run_id, tool_outputs, tool_approvals = chat_client._convert_required_action_to_tool_output([function_result])  # type: ignore

    assert run_id == "run_123"
    assert tool_outputs is not None
    assert len(tool_outputs) == 1
    assert tool_outputs[0].tool_call_id == "call_456"

    # Should JSON dump the entire results array since len > 1
    expected_results = [
        mock_basemodel.to_dict(),
        {"key": "value"},
        "string_result",
    ]
    expected_output = json.dumps(expected_results)
    assert tool_outputs[0].output == expected_output


async def test_azure_ai_chat_client_convert_required_action_approval_response(
    mock_agents_client: MagicMock,
) -> None:
    """Test _convert_required_action_to_tool_output with FunctionApprovalResponseContent."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Test with approval response - need to provide required fields
    approval_response = FunctionApprovalResponseContent(
        id='["run_123", "call_456"]',
        function_call=FunctionCallContent(call_id='["run_123", "call_456"]', name="test_function", arguments="{}"),
        approved=True,
    )

    run_id, tool_outputs, tool_approvals = chat_client._convert_required_action_to_tool_output([approval_response])  # type: ignore

    assert run_id == "run_123"
    assert tool_outputs is None
    assert tool_approvals is not None
    assert len(tool_approvals) == 1
    assert tool_approvals[0].tool_call_id == "call_456"
    assert tool_approvals[0].approve is True


async def test_azure_ai_chat_client_create_function_call_contents_approval_request(
    mock_agents_client: MagicMock,
) -> None:
    """Test _create_function_call_contents with approval action."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Mock SubmitToolApprovalAction with RequiredMcpToolCall
    mock_tool_call = MagicMock(spec=RequiredMcpToolCall)
    mock_tool_call.id = "approval_call_123"
    mock_tool_call.name = "approve_action"
    mock_tool_call.arguments = '{"action": "approve"}'

    mock_approval_action = MagicMock(spec=SubmitToolApprovalAction)
    mock_approval_action.submit_tool_approval.tool_calls = [mock_tool_call]

    mock_event_data = MagicMock(spec=ThreadRun)
    mock_event_data.required_action = mock_approval_action

    result = chat_client._create_function_call_contents(mock_event_data, "response_123")  # type: ignore

    assert len(result) == 1
    assert isinstance(result[0], FunctionApprovalRequestContent)
    assert result[0].id == '["response_123", "approval_call_123"]'
    assert result[0].function_call.name == "approve_action"
    assert result[0].function_call.call_id == '["response_123", "approval_call_123"]'


async def test_azure_ai_chat_client_get_agent_id_or_create_with_agent_name(
    mock_agents_client: MagicMock, azure_ai_unit_test_env: dict[str, str]
) -> None:
    """Test _get_agent_id_or_create uses default name when no agent_name set."""
    azure_ai_settings = AzureAISettings(model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"])
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, azure_ai_settings=azure_ai_settings)

    # Ensure agent_name is None to test the default
    chat_client.agent_name = None  # type: ignore

    agent_id = await chat_client._get_agent_id_or_create(run_options={"model": azure_ai_settings.model_deployment_name})  # type: ignore

    assert agent_id == "test-agent-id"
    # Verify create_agent was called with default "UnnamedAgent"
    mock_agents_client.create_agent.assert_called_once()
    call_kwargs = mock_agents_client.create_agent.call_args[1]
    assert call_kwargs["name"] == "UnnamedAgent"


async def test_azure_ai_chat_client_get_agent_id_or_create_with_response_format(
    mock_agents_client: MagicMock, azure_ai_unit_test_env: dict[str, str]
) -> None:
    """Test _get_agent_id_or_create with response_format in run_options."""
    azure_ai_settings = AzureAISettings(model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"])
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, azure_ai_settings=azure_ai_settings)

    # Test with response_format in run_options
    run_options = {"response_format": {"type": "json_object"}, "model": azure_ai_settings.model_deployment_name}

    agent_id = await chat_client._get_agent_id_or_create(run_options)  # type: ignore

    assert agent_id == "test-agent-id"
    # Verify create_agent was called with response_format
    mock_agents_client.create_agent.assert_called_once()
    call_kwargs = mock_agents_client.create_agent.call_args[1]
    assert call_kwargs["response_format"] == {"type": "json_object"}


async def test_azure_ai_chat_client_get_agent_id_or_create_with_tool_resources(
    mock_agents_client: MagicMock, azure_ai_unit_test_env: dict[str, str]
) -> None:
    """Test _get_agent_id_or_create with tool_resources in run_options."""
    azure_ai_settings = AzureAISettings(model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"])
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, azure_ai_settings=azure_ai_settings)

    # Test with tool_resources in run_options
    run_options = {
        "tool_resources": {"vector_store_ids": ["vs-123"]},
        "model": azure_ai_settings.model_deployment_name,
    }

    agent_id = await chat_client._get_agent_id_or_create(run_options)  # type: ignore

    assert agent_id == "test-agent-id"
    # Verify create_agent was called with tool_resources
    mock_agents_client.create_agent.assert_called_once()
    call_kwargs = mock_agents_client.create_agent.call_args[1]
    assert call_kwargs["tool_resources"] == {"vector_store_ids": ["vs-123"]}


async def test_azure_ai_chat_client_create_agent_stream_submit_tool_outputs(
    mock_agents_client: MagicMock,
) -> None:
    """Test _create_agent_stream with tool outputs submission path."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Mock active thread run that matches the tool run ID
    mock_thread_run = MagicMock()
    mock_thread_run.thread_id = "test-thread"
    mock_thread_run.id = "test-run-id"
    chat_client._get_active_thread_run = AsyncMock(return_value=mock_thread_run)  # type: ignore

    # Mock required action results with matching run ID
    function_result = FunctionResultContent(call_id='["test-run-id", "test-call-id"]', result="test result")

    # Mock submit_tool_outputs_stream
    mock_handler = MagicMock()
    mock_agents_client.runs.submit_tool_outputs_stream = AsyncMock()

    with patch("azure.ai.agents.models.AsyncAgentEventHandler", return_value=mock_handler):
        stream, final_thread_id = await chat_client._create_agent_stream(  # type: ignore
            thread_id="test-thread", agent_id="test-agent", run_options={}, required_action_results=[function_result]
        )

        # Should call submit_tool_outputs_stream since we have matching run ID
        mock_agents_client.runs.submit_tool_outputs_stream.assert_called_once()
        assert final_thread_id == "test-thread"


def test_azure_ai_chat_client_extract_url_citations_with_citations(mock_agents_client: MagicMock) -> None:
    """Test _extract_url_citations with MessageDeltaChunk containing URL citations."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Create mock URL citation annotation
    mock_url_citation = MagicMock()
    mock_url_citation.url = "https://example.com/test"
    mock_url_citation.title = "Test Title"

    mock_annotation = MagicMock(spec=MessageDeltaTextUrlCitationAnnotation)
    mock_annotation.url_citation = mock_url_citation
    mock_annotation.start_index = 10
    mock_annotation.end_index = 20

    # Create mock text content with annotations
    mock_text = MagicMock()
    mock_text.annotations = [mock_annotation]

    mock_text_content = MagicMock(spec=MessageDeltaTextContent)
    mock_text_content.text = mock_text

    # Create mock delta
    mock_delta = MagicMock()
    mock_delta.content = [mock_text_content]

    # Create mock MessageDeltaChunk
    mock_chunk = MagicMock(spec=MessageDeltaChunk)
    mock_chunk.delta = mock_delta

    # Call the method with empty azure_search_tool_calls
    citations = chat_client._extract_url_citations(mock_chunk, [])  # type: ignore

    # Verify results
    assert len(citations) == 1
    citation = citations[0]
    assert isinstance(citation, CitationAnnotation)
    assert citation.url == "https://example.com/test"
    assert citation.title == "Test Title"
    assert citation.snippet is None
    assert citation.annotated_regions is not None
    assert len(citation.annotated_regions) == 1
    assert citation.annotated_regions[0].start_index == 10
    assert citation.annotated_regions[0].end_index == 20


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    return f"The weather in {location} is sunny with a high of 25°C."


@pytest.mark.flaky
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_get_response() -> None:
    """Test Azure AI Chat Client response."""
    async with AzureAIAgentClient(credential=AzureCliCredential()) as azure_ai_chat_client:
        assert isinstance(azure_ai_chat_client, ChatClientProtocol)

        messages: list[ChatMessage] = []
        messages.append(
            ChatMessage(
                role="user",
                text="The weather in Seattle is currently sunny with a high of 25°C. "
                "It's a beautiful day for outdoor activities.",
            )
        )
        messages.append(ChatMessage(role="user", text="What's the weather like today?"))

        # Test that the agents_client can be used to get a response
        response = await azure_ai_chat_client.get_response(messages=messages)

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert any(word in response.text.lower() for word in ["sunny", "25"])


@pytest.mark.flaky
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_get_response_tools() -> None:
    """Test Azure AI Chat Client response with tools."""
    async with AzureAIAgentClient(credential=AzureCliCredential()) as azure_ai_chat_client:
        assert isinstance(azure_ai_chat_client, ChatClientProtocol)

        messages: list[ChatMessage] = []
        messages.append(ChatMessage(role="user", text="What's the weather like in Seattle?"))

        # Test that the agents_client can be used to get a response
        response = await azure_ai_chat_client.get_response(
            messages=messages,
            tools=[get_weather],
            tool_choice="auto",
        )

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert any(word in response.text.lower() for word in ["sunny", "25"])


@pytest.mark.flaky
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_streaming() -> None:
    """Test Azure AI Chat Client streaming response."""
    async with AzureAIAgentClient(credential=AzureCliCredential()) as azure_ai_chat_client:
        assert isinstance(azure_ai_chat_client, ChatClientProtocol)

        messages: list[ChatMessage] = []
        messages.append(
            ChatMessage(
                role="user",
                text="The weather in Seattle is currently sunny with a high of 25°C. "
                "It's a beautiful day for outdoor activities.",
            )
        )
        messages.append(ChatMessage(role="user", text="What's the weather like today?"))

        # Test that the agents_client can be used to get a response
        response = azure_ai_chat_client.get_streaming_response(messages=messages)

        full_message: str = ""
        async for chunk in response:
            assert chunk is not None
            assert isinstance(chunk, ChatResponseUpdate)
            for content in chunk.contents:
                if isinstance(content, TextContent) and content.text:
                    full_message += content.text

        assert any(word in full_message.lower() for word in ["sunny", "25"])


@pytest.mark.flaky
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_streaming_tools() -> None:
    """Test Azure AI Chat Client streaming response with tools."""
    async with AzureAIAgentClient(credential=AzureCliCredential()) as azure_ai_chat_client:
        assert isinstance(azure_ai_chat_client, ChatClientProtocol)

        messages: list[ChatMessage] = []
        messages.append(ChatMessage(role="user", text="What's the weather like in Seattle?"))

        # Test that the agents_client can be used to get a response
        response = azure_ai_chat_client.get_streaming_response(
            messages=messages,
            tools=[get_weather],
            tool_choice="auto",
        )
        full_message: str = ""
        async for chunk in response:
            assert chunk is not None
            assert isinstance(chunk, ChatResponseUpdate)
            for content in chunk.contents:
                if isinstance(content, TextContent) and content.text:
                    full_message += content.text

        assert any(word in full_message.lower() for word in ["sunny", "25"])


@pytest.mark.flaky
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_basic_run() -> None:
    """Test ChatAgent basic run functionality with AzureAIAgentClient."""
    async with ChatAgent(
        chat_client=AzureAIAgentClient(credential=AzureCliCredential()),
    ) as agent:
        # Run a simple query
        response = await agent.run("Hello! Please respond with 'Hello World' exactly.")

        # Validate response
        assert isinstance(response, AgentRunResponse)
        assert response.text is not None
        assert len(response.text) > 0
        assert "Hello World" in response.text


@pytest.mark.flaky
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_basic_run_streaming() -> None:
    """Test ChatAgent basic streaming functionality with AzureAIAgentClient."""
    async with ChatAgent(
        chat_client=AzureAIAgentClient(credential=AzureCliCredential()),
    ) as agent:
        # Run streaming query
        full_message: str = ""
        async for chunk in agent.run_stream("Please respond with exactly: 'This is a streaming response test.'"):
            assert chunk is not None
            assert isinstance(chunk, AgentRunResponseUpdate)
            if chunk.text:
                full_message += chunk.text

        # Validate streaming response
        assert len(full_message) > 0
        assert "streaming response test" in full_message.lower()


@pytest.mark.flaky
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_thread_persistence() -> None:
    """Test ChatAgent thread persistence across runs with AzureAIAgentClient."""
    async with ChatAgent(
        chat_client=AzureAIAgentClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant with good memory.",
    ) as agent:
        # Create a new thread that will be reused
        thread = agent.get_new_thread()

        # First message - establish context
        first_response = await agent.run(
            "Remember this number: 42. What number did I just tell you to remember?", thread=thread
        )
        assert isinstance(first_response, AgentRunResponse)
        assert "42" in first_response.text

        # Second message - test conversation memory
        second_response = await agent.run(
            "What number did I tell you to remember in my previous message?", thread=thread
        )
        assert isinstance(second_response, AgentRunResponse)
        assert "42" in second_response.text


@pytest.mark.flaky
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_existing_thread_id() -> None:
    """Test ChatAgent existing thread ID functionality with AzureAIAgentClient."""
    async with ChatAgent(
        chat_client=AzureAIAgentClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant with good memory.",
    ) as first_agent:
        # Start a conversation and get the thread ID
        thread = first_agent.get_new_thread()
        first_response = await first_agent.run("My name is Alice. Remember this.", thread=thread)

        # Validate first response
        assert isinstance(first_response, AgentRunResponse)
        assert first_response.text is not None

        # The thread ID is set after the first response
        existing_thread_id = thread.service_thread_id
        assert existing_thread_id is not None

    # Now continue with the same thread ID in a new agent instance
    async with ChatAgent(
        chat_client=AzureAIAgentClient(thread_id=existing_thread_id, credential=AzureCliCredential()),
        instructions="You are a helpful assistant with good memory.",
    ) as second_agent:
        # Create a thread with the existing ID
        thread = AgentThread(service_thread_id=existing_thread_id)

        # Ask about the previous conversation
        response2 = await second_agent.run("What is my name?", thread=thread)

        # Validate that the agent remembers the previous conversation
        assert isinstance(response2, AgentRunResponse)
        assert response2.text is not None
        # Should reference Alice from the previous conversation
        assert "alice" in response2.text.lower()


@pytest.mark.flaky
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_code_interpreter():
    """Test ChatAgent with code interpreter through AzureAIAgentClient."""

    async with ChatAgent(
        chat_client=AzureAIAgentClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant that can write and execute Python code.",
        tools=[HostedCodeInterpreterTool()],
    ) as agent:
        # Request code execution
        response = await agent.run("Write Python code to calculate the factorial of 5 and show the result.")

        # Validate response
        assert isinstance(response, AgentRunResponse)
        assert response.text is not None
        # Factorial of 5 is 120
        assert "120" in response.text or "factorial" in response.text.lower()


@pytest.mark.flaky
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_file_search():
    """Test ChatAgent with file search through AzureAIAgentClient."""

    client = AzureAIAgentClient(credential=AzureCliCredential())
    file: FileInfo | None = None
    vector_store: VectorStore | None = None

    try:
        # 1. Read and upload the test file to the Azure AI agent service
        test_file_path = Path(__file__).parent / "resources" / "employees.pdf"
        file = await client.agents_client.files.upload_and_poll(file_path=str(test_file_path), purpose="assistants")
        vector_store = await client.agents_client.vector_stores.create_and_poll(
            file_ids=[file.id], name="test_employees_vectorstore"
        )

        # 2. Create file search tool with uploaded resources
        file_search_tool = HostedFileSearchTool(inputs=[HostedVectorStoreContent(vector_store_id=vector_store.id)])

        async with ChatAgent(
            chat_client=client,
            instructions="You are a helpful assistant that can search through uploaded employee files.",
            tools=[file_search_tool],
        ) as agent:
            # 3. Test file search functionality
            response = await agent.run("Who is the youngest employee in the files?")

            # Validate response
            assert isinstance(response, AgentRunResponse)
            assert response.text is not None
            # Should find information about Alice Johnson (age 24) being the youngest
            assert any(term in response.text.lower() for term in ["alice", "johnson", "24"])

    finally:
        # 4. Cleanup: Delete the vector store and file
        try:
            if vector_store:
                await client.agents_client.vector_stores.delete(vector_store.id)
            if file:
                await client.agents_client.files.delete(file.id)
        except Exception:
            # Ignore cleanup errors to avoid masking the actual test failure
            pass
        finally:
            await client.close()


@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_hosted_mcp_tool() -> None:
    """Integration test for HostedMCPTool with Azure AI Agent using Microsoft Learn MCP."""

    mcp_tool = HostedMCPTool(
        name="Microsoft Learn MCP",
        url="https://learn.microsoft.com/api/mcp",
        description="A Microsoft Learn MCP server for documentation questions",
        approval_mode="never_require",
    )

    async with ChatAgent(
        chat_client=AzureAIAgentClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=[mcp_tool],
    ) as agent:
        response = await agent.run(
            "How to create an Azure storage account using az cli?",
            max_tokens=200,
        )

        assert isinstance(response, AgentRunResponse)
        assert response.text is not None
        assert len(response.text) > 0

        # With never_require approval mode, there should be no approval requests
        assert len(response.user_input_requests) == 0, (
            f"Expected no approval requests with never_require mode, but got {len(response.user_input_requests)}"
        )

        # Should contain Azure-related content since it's asking about Azure CLI
        assert any(term in response.text.lower() for term in ["azure", "storage", "account", "cli"])


@pytest.mark.flaky
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_level_tool_persistence():
    """Test that agent-level tools persist across multiple runs with AzureAIAgentClient."""
    async with ChatAgent(
        chat_client=AzureAIAgentClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant that uses available tools.",
        tools=[get_weather],
    ) as agent:
        # First run - agent-level tool should be available
        first_response = await agent.run("What's the weather like in Chicago?")

        assert isinstance(first_response, AgentRunResponse)
        assert first_response.text is not None
        # Should use the agent-level weather tool
        assert any(term in first_response.text.lower() for term in ["chicago", "sunny", "25"])

        # Second run - agent-level tool should still be available (persistence test)
        second_response = await agent.run("What's the weather in Miami?")

        assert isinstance(second_response, AgentRunResponse)
        assert second_response.text is not None
        # Should use the agent-level weather tool again
        assert any(term in second_response.text.lower() for term in ["miami", "sunny", "25"])


@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_chat_options_run_level() -> None:
    """Test ChatOptions parameter coverage at run level."""
    async with ChatAgent(
        chat_client=AzureAIAgentClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant.",
    ) as agent:
        response = await agent.run(
            "Provide a brief, helpful response.",
            max_tokens=100,
            temperature=0.7,
            top_p=0.9,
            seed=123,
            user="comprehensive-test-user",
            tools=[get_weather],
            tool_choice="auto",
            frequency_penalty=0.1,
            presence_penalty=0.1,
            stop=["END"],
            store=True,
            logit_bias={"test": 1},
            metadata={"test": "value"},
            additional_properties={"custom_param": "test_value"},
        )

        assert isinstance(response, AgentRunResponse)
        assert response.text is not None
        assert len(response.text) > 0


@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_chat_options_agent_level() -> None:
    """Test ChatOptions parameter coverage agent level."""
    async with ChatAgent(
        chat_client=AzureAIAgentClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant.",
        max_tokens=100,
        temperature=0.7,
        top_p=0.9,
        seed=123,
        user="comprehensive-test-user",
        tools=[get_weather],
        tool_choice="auto",
        frequency_penalty=0.1,
        presence_penalty=0.1,
        stop=["END"],
        store=True,
        logit_bias={"test": 1},
        metadata={"test": "value"},
        request_kwargs={"custom_param": "test_value"},
    ) as agent:
        response = await agent.run(
            "Provide a brief, helpful response.",
        )

        assert isinstance(response, AgentRunResponse)
        assert response.text is not None
        assert len(response.text) > 0


async def test_azure_ai_chat_client_cleanup_agent_when_enabled_and_created(
    mock_agents_client: MagicMock,
) -> None:
    """Test that agent is cleaned up when should_cleanup_agent=True and agent was created by client."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id=None, should_cleanup_agent=True)

    # Simulate agent creation
    chat_client.agent_id = "created-agent-id"
    chat_client._agent_created = True  # type: ignore

    await chat_client._cleanup_agent_if_needed()  # type: ignore

    # Verify agent was deleted
    mock_agents_client.delete_agent.assert_called_once_with("created-agent-id")
    assert chat_client.agent_id is None
    assert chat_client._agent_created is False  # type: ignore


async def test_azure_ai_chat_client_no_cleanup_when_disabled(
    mock_agents_client: MagicMock,
) -> None:
    """Test that agent is not cleaned up when should_cleanup_agent=False."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, agent_id=None, should_cleanup_agent=False)

    # Simulate agent creation
    chat_client.agent_id = "created-agent-id"
    chat_client._agent_created = True

    await chat_client._cleanup_agent_if_needed()  # type: ignore

    # Verify agent was NOT deleted
    mock_agents_client.delete_agent.assert_not_called()
    assert chat_client.agent_id == "created-agent-id"
    assert chat_client._agent_created is True


async def test_azure_ai_chat_client_no_cleanup_when_agent_not_created_by_client(
    mock_agents_client: MagicMock,
) -> None:
    """Test that agent is not cleaned up when it was not created by this client instance."""
    chat_client = create_test_azure_ai_chat_client(
        mock_agents_client, agent_id="existing-agent-id", should_cleanup_agent=True
    )

    # Agent exists but was not created by this client (_agent_created = False)
    assert chat_client._agent_created is False  # type: ignore

    await chat_client._cleanup_agent_if_needed()  # type: ignore

    # Verify agent was NOT deleted
    mock_agents_client.delete_agent.assert_not_called()
    assert chat_client.agent_id == "existing-agent-id"


def test_azure_ai_chat_client_capture_azure_search_tool_calls(mock_agents_client: MagicMock) -> None:
    """Test _capture_azure_search_tool_calls method."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    # Mock Azure AI Search tool call
    mock_tool_call = MagicMock()
    mock_tool_call.type = "azure_ai_search"
    mock_tool_call.id = "call_123"
    mock_tool_call.azure_ai_search = {"input": "test query", "output": "test output"}

    # Mock step data
    mock_step_data = MagicMock()
    mock_step_data.step_details.tool_calls = [mock_tool_call]

    # Call the method with a list to capture tool calls
    azure_search_tool_calls: list[dict[str, Any]] = []
    chat_client._capture_azure_search_tool_calls(mock_step_data, azure_search_tool_calls)  # type: ignore

    # Verify tool call was captured
    assert len(azure_search_tool_calls) == 1
    captured_tool_call = azure_search_tool_calls[0]
    assert captured_tool_call["type"] == "azure_ai_search"
    assert captured_tool_call["id"] == "call_123"
    assert captured_tool_call["azure_ai_search"] == {"input": "test query", "output": "test output"}


def test_azure_ai_chat_client_get_real_url_from_citation_reference_no_tool_calls(
    mock_agents_client: MagicMock,
) -> None:
    """Test _get_real_url_from_citation_reference with no tool calls."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    # No tool calls - pass empty list
    result = chat_client._get_real_url_from_citation_reference("doc_1", [])  # type: ignore
    assert result == "doc_1"


def test_azure_ai_chat_client_get_real_url_from_citation_reference_invalid_output(
    mock_agents_client: MagicMock,
) -> None:
    """Test _get_real_url_from_citation_reference with invalid output format."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    # Tool call with invalid output format
    azure_search_tool_calls = [
        {"id": "call_123", "type": "azure_ai_search", "azure_ai_search": {"output": "invalid_json_format"}}
    ]

    result = chat_client._get_real_url_from_citation_reference("doc_1", azure_search_tool_calls)  # type: ignore
    assert result == "doc_1"


async def test_azure_ai_chat_client_context_manager(mock_agents_client: MagicMock) -> None:
    """Test AzureAIAgentClient as async context manager."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    # Mock close method to avoid actual cleanup
    chat_client.close = AsyncMock()

    async with chat_client as client:
        assert client is chat_client

    # Verify close was called on exit
    chat_client.close.assert_called_once()


async def test_azure_ai_chat_client_close_method(mock_agents_client: MagicMock) -> None:
    """Test AzureAIAgentClient close method."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    # Mock cleanup methods
    chat_client._cleanup_agent_if_needed = AsyncMock()
    chat_client._close_client_if_needed = AsyncMock()

    await chat_client.close()

    # Verify cleanup methods were called
    chat_client._cleanup_agent_if_needed.assert_called_once()
    chat_client._close_client_if_needed.assert_called_once()


def test_azure_ai_chat_client_extract_url_citations_with_azure_search_enhanced_url(
    mock_agents_client: MagicMock,
) -> None:
    """Test _extract_url_citations with Azure AI Search URL enhancement."""
    chat_client = create_test_azure_ai_chat_client(mock_agents_client)

    # Add Azure Search tool calls for URL enhancement
    azure_search_tool_calls = [
        {
            "id": "call_123",
            "type": "azure_ai_search",
            "azure_ai_search": {
                "output": str({
                    "metadata": {"get_urls": ["https://real-example.com/doc1", "https://real-example.com/doc2"]}
                })
            },
        }
    ]

    # Create mock URL citation with doc reference
    mock_url_citation = MagicMock()
    mock_url_citation.url = "doc_1"
    mock_url_citation.title = "Test Title"

    mock_annotation = MagicMock(spec=MessageDeltaTextUrlCitationAnnotation)
    mock_annotation.url_citation = mock_url_citation
    mock_annotation.start_index = 10
    mock_annotation.end_index = 20

    mock_text = MagicMock()
    mock_text.annotations = [mock_annotation]

    mock_text_content = MagicMock(spec=MessageDeltaTextContent)
    mock_text_content.text = mock_text

    mock_delta = MagicMock()
    mock_delta.content = [mock_text_content]

    mock_chunk = MagicMock(spec=MessageDeltaChunk)
    mock_chunk.delta = mock_delta

    citations = chat_client._extract_url_citations(mock_chunk, azure_search_tool_calls)  # type: ignore

    # Verify real URL was used
    assert len(citations) == 1
    citation = citations[0]
    assert citation.url == "https://real-example.com/doc2"  # doc_1 maps to index 1


def test_azure_ai_chat_client_init_with_auto_created_agents_client(
    azure_ai_unit_test_env: dict[str, str], mock_azure_credential: MagicMock
) -> None:
    """Test AzureAIAgentClient initialization when it creates its own AgentsClient."""

    # Mock the AgentsClient constructor
    with patch("agent_framework_azure_ai._chat_client.AgentsClient") as mock_agents_client_class:
        mock_agents_client_instance = MagicMock()
        mock_agents_client_class.return_value = mock_agents_client_instance

        # Create client without providing agents_client - should create its own
        client = AzureAIAgentClient(
            agents_client=None,  # This will trigger creation of AgentsClient
            agent_id="test-agent",
            project_endpoint=azure_ai_unit_test_env["AZURE_AI_PROJECT_ENDPOINT"],
            model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=mock_azure_credential,
        )

        # Verify AgentsClient was created with correct parameters
        mock_agents_client_class.assert_called_once_with(
            endpoint=azure_ai_unit_test_env["AZURE_AI_PROJECT_ENDPOINT"],
            credential=mock_azure_credential,
            user_agent="agent-framework-python/0.0.0",
        )

        # Verify client properties are set correctly
        assert client.agents_client is mock_agents_client_instance
        assert client.agent_id == "test-agent"
        assert client.credential is mock_azure_credential
        assert client._should_close_client is True  # Should close since we created it  # type: ignore[attr-defined]
