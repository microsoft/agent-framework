# Copyright (c) Microsoft. All rights reserved.

import json
import os
from pathlib import Path
from typing import Annotated, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import (
    Agent,
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    SupportsChatGetResponse,
    tool,
)
from agent_framework._serialization import SerializationMixin
from agent_framework._settings import load_settings
from agent_framework.exceptions import ChatClientInvalidRequestException
from azure.ai.agents.models import (
    AgentsNamedToolChoice,
    AgentsNamedToolChoiceType,
    AgentsToolChoiceOptionMode,
    CodeInterpreterToolDefinition,
    FileInfo,
    MessageDeltaChunk,
    MessageDeltaTextContent,
    MessageDeltaTextFileCitationAnnotation,
    MessageDeltaTextFilePathAnnotation,
    MessageDeltaTextUrlCitationAnnotation,
    MessageInputTextBlock,
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
from pydantic import BaseModel, Field

from agent_framework_azure_ai import AzureAIAgentClient, AzureAISettings

skip_if_azure_ai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("AZURE_AI_PROJECT_ENDPOINT", "") in ("", "https://test-project.cognitiveservices.azure.com/"),
    reason="No real AZURE_AI_PROJECT_ENDPOINT provided; skipping integration tests.",
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
        azure_ai_settings = load_settings(AzureAISettings, env_prefix="AZURE_AI_")

    # Create client instance directly
    client = object.__new__(AzureAIAgentClient)

    # Set attributes directly
    client.agents_client = mock_agents_client
    client.credential = None
    client.agent_id = agent_id
    client.agent_name = agent_name
    client.agent_description = None
    client.model_id = azure_ai_settings.get("model_deployment_name")
    client.thread_id = thread_id
    client.should_cleanup_agent = should_cleanup_agent
    client._agent_created = False
    client._should_close_client = False
    client._agent_definition = None
    client._azure_search_tool_calls = []  # Add the new instance variable
    client.additional_properties = {}
    client.middleware = None
    client.chat_middleware = []
    client.function_middleware = []
    client.otel_provider_name = "azure.ai"
    client.function_invocation_configuration = {
        "enabled": True,
        "max_iterations": 5,
        "max_consecutive_errors_per_request": 0,
        "terminate_on_unknown_calls": False,
        "additional_tools": [],
        "include_detailed_errors": False,
    }

    return client


def test_azure_ai_settings_init(azure_ai_unit_test_env: dict[str, str]) -> None:
    """Test AzureAISettings initialization."""
    settings = load_settings(AzureAISettings, env_prefix="AZURE_AI_")

    assert settings["project_endpoint"] == azure_ai_unit_test_env["AZURE_AI_PROJECT_ENDPOINT"]
    assert settings["model_deployment_name"] == azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"]


def test_azure_ai_settings_init_with_explicit_values() -> None:
    """Test AzureAISettings initialization with explicit values."""
    settings = load_settings(
        AzureAISettings,
        env_prefix="AZURE_AI_",
        project_endpoint="https://custom-endpoint.com/",
        model_deployment_name="custom-model",
    )

    assert settings["project_endpoint"] == "https://custom-endpoint.com/"
    assert settings["model_deployment_name"] == "custom-model"


def test_azure_ai_chat_client_init_with_client(mock_agents_client: MagicMock) -> None:
    """Test AzureAIAgentClient initialization with existing agents_client."""
    client = create_test_azure_ai_chat_client(
        mock_agents_client, agent_id="existing-agent-id", thread_id="test-thread-id"
    )

    assert client.agents_client is mock_agents_client
    assert client.agent_id == "existing-agent-id"
    assert client.thread_id == "test-thread-id"
    assert isinstance(client, SupportsChatGetResponse)


def test_azure_ai_chat_client_init_auto_create_client(
    azure_ai_unit_test_env: dict[str, str],
    mock_agents_client: MagicMock,
) -> None:
    """Test AzureAIAgentClient initialization with auto-created agents_client."""
    azure_ai_settings = load_settings(AzureAISettings, env_prefix="AZURE_AI_", **azure_ai_unit_test_env)  # type: ignore

    # Create client instance directly
    chat_client = object.__new__(AzureAIAgentClient)
    chat_client.agents_client = mock_agents_client
    chat_client.agent_id = None
    chat_client.thread_id = None
    chat_client._should_close_client = False  # type: ignore
    chat_client.credential = None
    chat_client.model_id = azure_ai_settings.get("model_deployment_name")
    chat_client.agent_name = None
    chat_client.additional_properties = {}
    chat_client.middleware = None

    assert chat_client.agents_client is mock_agents_client
    assert chat_client.agent_id is None


def test_azure_ai_chat_client_init_missing_project_endpoint() -> None:
    """Test AzureAIAgentClient initialization when project_endpoint is missing and no agents_client provided."""
    # Mock AzureAISettings to return settings with None project_endpoint
    with patch("agent_framework_azure_ai._chat_client.load_settings") as mock_load_settings:
        mock_load_settings.return_value = {"project_endpoint": None, "model_deployment_name": "test-model"}

        with pytest.raises(ValueError, match="project endpoint is required"):
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
    with patch("agent_framework_azure_ai._chat_client.load_settings") as mock_load_settings:
        mock_load_settings.return_value = {"project_endpoint": "https://test.com", "model_deployment_name": None}

        with pytest.raises(ValueError, match="model deployment name is required"):
            AzureAIAgentClient(
                agents_client=None,
                agent_id=None,  # No existing agent
                project_endpoint="https://test.com",
                model_deployment_name=None,  # Missing for agent creation
                credential=AsyncMock(spec=AsyncTokenCredential),
            )


def test_azure_ai_chat_client_init_missing_credential(azure_ai_unit_test_env: dict[str, str]) -> None:
    """Test AzureAIAgentClient.__init__ when credential is missing and no agents_client provided."""
    with pytest.raises(ValueError, match="Azure credential is required when agents_client is not provided"):
        AzureAIAgentClient(
            agents_client=None,
            agent_id="existing-agent",
            project_endpoint=azure_ai_unit_test_env["AZURE_AI_PROJECT_ENDPOINT"],
            model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=None,  # Missing credential
        )


def test_azure_ai_chat_client_from_dict() -> None:
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

    client = AzureAIAgentClient.from_dict(settings)

    assert client.agents_client is mock_agents_client
    assert client.agent_id == "test-agent"
    assert client.thread_id == "test-thread"
    assert client.agent_name == "TestAgent"


async def test_azure_ai_chat_client_get_agent_id_or_create_with_temperature_and_top_p(
    mock_agents_client: MagicMock, azure_ai_unit_test_env: dict[str, str]
) -> None:
    """Test _get_agent_id_or_create with temperature and top_p in run_options."""
    azure_ai_settings = load_settings(
        AzureAISettings,
        env_prefix="AZURE_AI_",
        model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
    )
    client = create_test_azure_ai_chat_client(mock_agents_client, azure_ai_settings=azure_ai_settings)

    run_options = {
        "model": azure_ai_settings.get("model_deployment_name"),
        "temperature": 0.7,
        "top_p": 0.9,
    }

    agent_id = await client._get_agent_id_or_create(run_options)  # type: ignore

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
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="existing-agent-id")

    agent_id = await client._get_agent_id_or_create()  # type: ignore

    assert agent_id == "existing-agent-id"
    assert not client._agent_created


async def test_azure_ai_chat_client_get_agent_id_or_create_create_new(
    mock_agents_client: MagicMock,
    azure_ai_unit_test_env: dict[str, str],
) -> None:
    """Test _get_agent_id_or_create when creating a new agent."""
    azure_ai_settings = load_settings(
        AzureAISettings,
        env_prefix="AZURE_AI_",
        model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
    )
    chat_client = create_test_azure_ai_chat_client(mock_agents_client, azure_ai_settings=azure_ai_settings)

    agent_id = await chat_client._get_agent_id_or_create(
        run_options={"model": azure_ai_settings.get("model_deployment_name")}
    )  # type: ignore

    assert agent_id == "test-agent-id"
    assert chat_client._agent_created


async def test_azure_ai_chat_client_thread_management_through_public_api(mock_agents_client: MagicMock) -> None:
    """Test thread creation and management through public API."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

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

    messages = [Message(role="user", text="Hello")]

    # Call without existing thread - should create new one
    response = client.get_response(messages, stream=True)
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
    client = create_test_azure_ai_chat_client(mock_agents_client)

    with pytest.raises(ValueError, match="Model deployment name is required"):
        await client._get_agent_id_or_create()  # type: ignore


async def test_azure_ai_chat_client_prepare_options_basic(mock_agents_client: MagicMock) -> None:
    """Test _prepare_options with basic ChatOptions."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    messages = [Message(role="user", text="Hello")]
    chat_options: ChatOptions = {"max_tokens": 100, "temperature": 0.7}

    run_options, tool_results = await client._prepare_options(messages, chat_options)  # type: ignore

    assert run_options is not None
    assert tool_results is None


async def test_azure_ai_chat_client_prepare_options_no_chat_options(mock_agents_client: MagicMock) -> None:
    """Test _prepare_options with default ChatOptions."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    messages = [Message(role="user", text="Hello")]

    run_options, tool_results = await client._prepare_options(messages, {})  # type: ignore

    assert run_options is not None
    assert tool_results is None


async def test_azure_ai_chat_client_prepare_options_with_image_content(mock_agents_client: MagicMock) -> None:
    """Test _prepare_options with image content."""

    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Mock get_agent
    mock_agents_client.get_agent = AsyncMock(return_value=None)

    image_content = Content.from_uri(uri="https://example.com/image.jpg", media_type="image/jpeg")
    messages = [Message(role="user", contents=[image_content])]

    run_options, _ = await client._prepare_options(messages, {})  # type: ignore

    assert "additional_messages" in run_options
    assert len(run_options["additional_messages"]) == 1
    # Verify image was converted to MessageInputImageUrlBlock
    message = run_options["additional_messages"][0]
    assert len(message.content) == 1


def test_azure_ai_chat_client_prepare_tool_outputs_for_azure_ai_none(mock_agents_client: MagicMock) -> None:
    """Test _prepare_tool_outputs_for_azure_ai with None input."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    run_id, tool_outputs, tool_approvals = client._prepare_tool_outputs_for_azure_ai(None)  # type: ignore

    assert run_id is None
    assert tool_outputs is None
    assert tool_approvals is None


async def test_azure_ai_chat_client_close_client_when_should_close_true(mock_agents_client: MagicMock) -> None:
    """Test _close_client_if_needed closes agents_client when should_close_client is True."""
    client = create_test_azure_ai_chat_client(mock_agents_client)
    client._should_close_client = True  # type: ignore

    mock_agents_client.close = AsyncMock()

    await client._close_client_if_needed()  # type: ignore

    mock_agents_client.close.assert_called_once()


async def test_azure_ai_chat_client_close_client_when_should_close_false(mock_agents_client: MagicMock) -> None:
    """Test _close_client_if_needed does not close agents_client when should_close_client is False."""
    client = create_test_azure_ai_chat_client(mock_agents_client)
    client._should_close_client = False  # type: ignore

    await client._close_client_if_needed()  # type: ignore

    mock_agents_client.close.assert_not_called()


def test_azure_ai_chat_client_update_agent_name_and_description_when_current_is_none(
    mock_agents_client: MagicMock,
) -> None:
    """Test _update_agent_name_and_description updates name when current agent_name is None."""
    client = create_test_azure_ai_chat_client(mock_agents_client)
    client.agent_name = None  # type: ignore

    client._update_agent_name_and_description("NewAgentName", "description")  # type: ignore

    assert client.agent_name == "NewAgentName"
    assert client.agent_description == "description"


def test_azure_ai_chat_client_update_agent_name_and_description_when_current_exists(
    mock_agents_client: MagicMock,
) -> None:
    """Test _update_agent_name_and_description does not update when current agent_name exists."""
    client = create_test_azure_ai_chat_client(mock_agents_client)
    client.agent_name = "ExistingName"  # type: ignore
    client.agent_description = "ExistingDescription"  # type: ignore

    client._update_agent_name_and_description("NewAgentName", "description")  # type: ignore

    assert client.agent_name == "ExistingName"
    assert client.agent_description == "ExistingDescription"


def test_azure_ai_chat_client_update_agent_name_and_description_with_none_input(mock_agents_client: MagicMock) -> None:
    """Test _update_agent_name_and_description with None input."""
    client = create_test_azure_ai_chat_client(mock_agents_client)
    client.agent_name = None  # type: ignore
    client.agent_description = None  # type: ignore

    client._update_agent_name_and_description(None, None)  # type: ignore

    assert client.agent_name is None
    assert client.agent_description is None


async def test_azure_ai_chat_client_prepare_options_with_messages(mock_agents_client: MagicMock) -> None:
    """Test _prepare_options with different message types."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    # Test with system message (becomes instruction)
    messages = [
        Message(role="system", text="You are a helpful assistant"),
        Message(role="user", text="Hello"),
    ]

    run_options, _ = await client._prepare_options(messages, {})  # type: ignore

    assert "instructions" in run_options
    assert "You are a helpful assistant" in run_options["instructions"]
    assert "additional_messages" in run_options
    assert len(run_options["additional_messages"]) == 1  # Only user message


async def test_azure_ai_chat_client_prepare_options_with_instructions_from_options(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_options includes instructions passed via options.

    This verifies that agent instructions set via as_agent(instructions=...)
    are properly included in the API call.
    """
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")
    mock_agents_client.get_agent = AsyncMock(return_value=None)

    messages = [Message(role="user", text="Hello")]
    chat_options: ChatOptions = {
        "instructions": "You are a thoughtful reviewer. Give brief feedback.",
    }

    run_options, _ = await client._prepare_options(messages, chat_options)  # type: ignore

    assert "instructions" in run_options
    assert "reviewer" in run_options["instructions"].lower()


async def test_azure_ai_chat_client_prepare_options_merges_instructions_from_messages_and_options(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_options merges instructions from both system messages and options.

    When instructions come from both system/developer messages AND from options,
    both should be included in the final instructions.
    """
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")
    mock_agents_client.get_agent = AsyncMock(return_value=None)

    messages = [
        Message(role="system", text="Context: You are reviewing marketing copy."),
        Message(role="user", text="Review this tagline"),
    ]
    chat_options: ChatOptions = {
        "instructions": "Be concise and constructive in your feedback.",
    }

    run_options, _ = await client._prepare_options(messages, chat_options)  # type: ignore

    assert "instructions" in run_options
    instructions_text = run_options["instructions"]
    # Both instruction sources should be present
    assert "marketing" in instructions_text.lower()
    assert "concise" in instructions_text.lower()


async def test_azure_ai_chat_client_inner_get_response(mock_agents_client: MagicMock) -> None:
    """Test _inner_get_response method."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    async def mock_streaming_response():
        yield ChatResponseUpdate(role="assistant", contents=[Content.from_text("Hello back")])

    with (
        patch.object(client, "_inner_get_response", return_value=mock_streaming_response()),
        patch("agent_framework.ChatResponse.from_update_generator") as mock_from_generator,
    ):
        mock_response = ChatResponse(messages=[Message(role="assistant", text="Hello back")])
        mock_from_generator.return_value = mock_response

        result = await ChatResponse.from_update_generator(mock_streaming_response())

        assert result is mock_response
        mock_from_generator.assert_called_once()


async def test_azure_ai_chat_client_get_agent_id_or_create_with_run_options(
    mock_agents_client: MagicMock, azure_ai_unit_test_env: dict[str, str]
) -> None:
    """Test _get_agent_id_or_create with run_options containing tools and instructions."""
    azure_ai_settings = load_settings(
        AzureAISettings,
        env_prefix="AZURE_AI_",
        model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
    )
    client = create_test_azure_ai_chat_client(mock_agents_client, azure_ai_settings=azure_ai_settings)

    run_options = {
        "tools": [{"type": "function", "function": {"name": "test_tool"}}],
        "instructions": "Test instructions",
        "response_format": {"type": "json_object"},
        "model": azure_ai_settings.get("model_deployment_name"),
    }

    agent_id = await client._get_agent_id_or_create(run_options)  # type: ignore

    assert agent_id == "test-agent-id"
    # Verify create_agent was called with run_options parameters
    mock_agents_client.create_agent.assert_called_once()
    call_args = mock_agents_client.create_agent.call_args[1]
    assert "tools" in call_args
    assert "instructions" in call_args
    assert "response_format" in call_args


async def test_azure_ai_chat_client_prepare_thread_cancels_active_run(mock_agents_client: MagicMock) -> None:
    """Test _prepare_thread cancels active thread run when provided."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    mock_thread_run = MagicMock()
    mock_thread_run.id = "run_123"
    mock_thread_run.thread_id = "test-thread"

    run_options = {"additional_messages": []}  # type: ignore

    result = await client._prepare_thread("test-thread", mock_thread_run, run_options)  # type: ignore

    assert result == "test-thread"
    mock_agents_client.runs.cancel.assert_called_once_with("test-thread", "run_123")


def test_azure_ai_chat_client_parse_function_calls_from_azure_ai_basic(mock_agents_client: MagicMock) -> None:
    """Test _parse_function_calls_from_azure_ai with basic function call."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    mock_tool_call = MagicMock(spec=RequiredFunctionToolCall)
    mock_tool_call.id = "call_123"
    mock_tool_call.function.name = "get_weather"
    mock_tool_call.function.arguments = '{"location": "Seattle"}'

    mock_submit_action = MagicMock(spec=SubmitToolOutputsAction)
    mock_submit_action.submit_tool_outputs.tool_calls = [mock_tool_call]

    mock_event_data = MagicMock(spec=ThreadRun)
    mock_event_data.required_action = mock_submit_action

    result = client._parse_function_calls_from_azure_ai(mock_event_data, "response_123")  # type: ignore

    assert len(result) == 1
    assert result[0].type == "function_call"
    assert result[0].name == "get_weather"
    assert result[0].call_id == '["response_123", "call_123"]'


def test_azure_ai_chat_client_parse_function_calls_from_azure_ai_no_submit_action(
    mock_agents_client: MagicMock,
) -> None:
    """Test _parse_function_calls_from_azure_ai when required_action is not SubmitToolOutputsAction."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    mock_event_data = MagicMock(spec=ThreadRun)
    mock_event_data.required_action = MagicMock()

    result = client._parse_function_calls_from_azure_ai(mock_event_data, "response_123")  # type: ignore

    assert result == []


def test_azure_ai_chat_client_parse_function_calls_from_azure_ai_non_function_tool_call(
    mock_agents_client: MagicMock,
) -> None:
    """Test _parse_function_calls_from_azure_ai with non-function tool call."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    mock_tool_call = MagicMock()

    mock_submit_action = MagicMock(spec=SubmitToolOutputsAction)
    mock_submit_action.submit_tool_outputs.tool_calls = [mock_tool_call]

    mock_event_data = MagicMock(spec=ThreadRun)
    mock_event_data.required_action = mock_submit_action

    result = client._parse_function_calls_from_azure_ai(mock_event_data, "response_123")  # type: ignore

    assert result == []


async def test_azure_ai_chat_client_prepare_options_with_none_tool_choice(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_options with tool_choice set to 'none'."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    chat_options: ChatOptions = {"tool_choice": "none"}

    run_options, _ = await client._prepare_options([], chat_options)  # type: ignore

    assert run_options["tool_choice"] == AgentsToolChoiceOptionMode.NONE


async def test_azure_ai_chat_client_prepare_options_with_auto_tool_choice(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_options with tool_choice set to 'auto'."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    chat_options = {"tool_choice": "auto"}

    run_options, _ = await client._prepare_options([], chat_options)  # type: ignore

    assert run_options["tool_choice"] == AgentsToolChoiceOptionMode.AUTO


async def test_azure_ai_chat_client_prepare_options_tool_choice_required_specific_function(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_options with required tool_choice specifying a specific function name."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    required_tool_mode = {"mode": "required", "required_function_name": "specific_function_name"}

    dict_tool = {"type": "function", "function": {"name": "test_function"}}

    chat_options = {"tools": [dict_tool], "tool_choice": required_tool_mode}
    messages = [Message(role="user", text="Hello")]

    run_options, _ = await client._prepare_options(messages, chat_options)  # type: ignore

    # Verify tool_choice is set to the specific named function
    assert "tool_choice" in run_options
    tool_choice = run_options["tool_choice"]
    assert isinstance(tool_choice, AgentsNamedToolChoice)
    assert tool_choice.type == AgentsNamedToolChoiceType.FUNCTION
    assert tool_choice.function.name == "specific_function_name"  # type: ignore


async def test_azure_ai_chat_client_prepare_options_with_response_format(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_options with response_format configured."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    class TestResponseModel(BaseModel):
        name: str = Field(description="Test name")

    chat_options: ChatOptions = {"response_format": TestResponseModel}

    run_options, _ = await client._prepare_options([], chat_options)  # type: ignore

    assert "response_format" in run_options
    response_format = run_options["response_format"]
    assert response_format.json_schema.name == "TestResponseModel"


def test_azure_ai_chat_client_service_url_method(mock_agents_client: MagicMock) -> None:
    """Test service_url method returns endpoint."""
    mock_agents_client._config.endpoint = "https://test-endpoint.com/"
    client = create_test_azure_ai_chat_client(mock_agents_client)

    url = client.service_url()
    assert url == "https://test-endpoint.com/"


async def test_azure_ai_chat_client_prepare_options_mcp_never_require(mock_agents_client: MagicMock) -> None:
    """Test _prepare_options with MCP dict tool having never_require approval mode."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    # Create MCP tool with approval_mode parameter
    mcp_tool = AzureAIAgentClient.get_mcp_tool(
        name="Test MCP Tool", url="https://example.com/mcp", approval_mode="never_require"
    )

    messages = [Message(role="user", text="Hello")]
    chat_options: ChatOptions = {"tools": [mcp_tool], "tool_choice": "auto"}

    run_options, _ = await client._prepare_options(messages, chat_options)  # type: ignore

    # Verify tool_resources is created with correct MCP approval structure
    assert "tool_resources" in run_options, f"Expected 'tool_resources' in run_options keys: {list(run_options.keys())}"
    assert "mcp" in run_options["tool_resources"]
    assert len(run_options["tool_resources"]["mcp"]) == 1

    mcp_resource = run_options["tool_resources"]["mcp"][0]
    assert mcp_resource["server_label"] == "Test_MCP_Tool"
    assert mcp_resource["require_approval"] == "never"


async def test_azure_ai_chat_client_prepare_options_mcp_with_headers(mock_agents_client: MagicMock) -> None:
    """Test _prepare_options with MCP dict tool having headers."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    # Test with headers - create MCP tool with all options
    headers = {"Authorization": "Bearer DUMMY_TOKEN", "X-API-Key": "DUMMY_KEY"}
    mcp_tool = AzureAIAgentClient.get_mcp_tool(
        name="Test MCP Tool",
        url="https://example.com/mcp",
        headers=headers,
        approval_mode="never_require",
    )

    messages = [Message(role="user", text="Hello")]
    chat_options: ChatOptions = {"tools": [mcp_tool], "tool_choice": "auto"}

    run_options, _ = await client._prepare_options(messages, chat_options)  # type: ignore

    # Verify tool_resources is created with headers
    assert "tool_resources" in run_options
    assert "mcp" in run_options["tool_resources"]
    assert len(run_options["tool_resources"]["mcp"]) == 1

    mcp_resource = run_options["tool_resources"]["mcp"][0]
    assert mcp_resource["server_label"] == "Test_MCP_Tool"
    assert mcp_resource["require_approval"] == "never"
    assert mcp_resource["headers"] == headers


async def test_azure_ai_chat_client_prepare_tools_for_azure_ai_web_search_bing_grounding(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_tools_for_azure_ai with BingGroundingTool from get_web_search_tool()."""

    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Mock BingGroundingTool to avoid SDK validation of connection ID
    with patch("agent_framework_azure_ai._chat_client.BingGroundingTool") as mock_bing_grounding:
        mock_bing_tool = MagicMock()
        mock_bing_tool.definitions = [{"type": "bing_grounding"}]
        mock_bing_grounding.return_value = mock_bing_tool

        # get_web_search_tool now returns a BingGroundingTool directly
        web_search_tool = client.get_web_search_tool(bing_connection_id="test-connection-id")

        # Verify the factory method created the tool with correct args
        mock_bing_grounding.assert_called_once_with(connection_id="test-connection-id")

        result = await client._prepare_tools_for_azure_ai([web_search_tool])  # type: ignore

        # BingGroundingTool.definitions should be extended into result
        assert len(result) == 1
        assert result[0] == {"type": "bing_grounding"}


async def test_azure_ai_chat_client_prepare_tools_for_azure_ai_web_search_bing_grounding_with_connection_id(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_tools_for_azure_ai with BingGroundingTool using explicit connection_id."""

    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Mock BingGroundingTool to avoid SDK validation of connection ID
    with patch("agent_framework_azure_ai._chat_client.BingGroundingTool") as mock_bing_grounding:
        mock_bing_tool = MagicMock()
        mock_bing_tool.definitions = [{"type": "bing_grounding"}]
        mock_bing_grounding.return_value = mock_bing_tool

        web_search_tool = client.get_web_search_tool(bing_connection_id="direct-connection-id")

        mock_bing_grounding.assert_called_once_with(connection_id="direct-connection-id")

        result = await client._prepare_tools_for_azure_ai([web_search_tool])  # type: ignore

        assert len(result) == 1
        assert result[0] == {"type": "bing_grounding"}


async def test_azure_ai_chat_client_prepare_tools_for_azure_ai_web_search_custom_bing(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_tools_for_azure_ai with BingCustomSearchTool from get_web_search_tool()."""

    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Mock BingCustomSearchTool to avoid SDK validation
    with patch("agent_framework_azure_ai._chat_client.BingCustomSearchTool") as mock_custom_bing:
        mock_custom_tool = MagicMock()
        mock_custom_tool.definitions = [{"type": "bing_custom_search"}]
        mock_custom_bing.return_value = mock_custom_tool

        web_search_tool = client.get_web_search_tool(
            bing_custom_connection_id="custom-connection-id",
            bing_custom_instance_id="custom-instance",
        )

        mock_custom_bing.assert_called_once_with(
            connection_id="custom-connection-id",
            instance_name="custom-instance",
        )

        result = await client._prepare_tools_for_azure_ai([web_search_tool])  # type: ignore

        assert len(result) == 1
        assert result[0] == {"type": "bing_custom_search"}


async def test_azure_ai_chat_client_prepare_tools_for_azure_ai_file_search_with_vector_stores(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_tools_for_azure_ai with FileSearchTool from get_file_search_tool()."""

    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # get_file_search_tool() now returns a FileSearchTool instance directly
    file_search_tool = client.get_file_search_tool(vector_store_ids=["vs-123"])

    run_options: dict[str, Any] = {}
    result = await client._prepare_tools_for_azure_ai([file_search_tool], run_options)  # type: ignore

    assert len(result) == 1
    assert result[0] == {"type": "file_search"}
    assert run_options["tool_resources"] == {"file_search": {"vector_store_ids": ["vs-123"]}}


async def test_azure_ai_chat_client_create_agent_stream_submit_tool_approvals(
    mock_agents_client: MagicMock,
) -> None:
    """Test _create_agent_stream with tool approvals submission path."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Mock active thread run that matches the tool run ID
    mock_thread_run = MagicMock()
    mock_thread_run.thread_id = "test-thread"
    mock_thread_run.id = "test-run-id"
    client._get_active_thread_run = AsyncMock(return_value=mock_thread_run)  # type: ignore

    # Mock required action results with approval response that matches run ID
    approval_response = Content.from_function_approval_response(
        id='["test-run-id", "test-call-id"]',
        function_call=Content.from_function_call(
            call_id='["test-run-id", "test-call-id"]', name="test_function", arguments="{}"
        ),
        approved=True,
    )

    # Mock submit_tool_outputs_stream
    mock_handler = MagicMock()
    mock_agents_client.runs.submit_tool_outputs_stream = AsyncMock()

    with patch("azure.ai.agents.models.AsyncAgentEventHandler", return_value=mock_handler):
        stream, final_thread_id = await client._create_agent_stream(  # type: ignore
            "test-agent", {"thread_id": "test-thread"}, [approval_response]
        )

        # Verify the approvals path was taken
        assert final_thread_id == "test-thread"

        # Verify submit_tool_outputs_stream was called with approvals
        mock_agents_client.runs.submit_tool_outputs_stream.assert_called_once()
        call_args = mock_agents_client.runs.submit_tool_outputs_stream.call_args[1]
        assert "tool_approvals" in call_args
        assert call_args["tool_approvals"][0].tool_call_id == "test-call-id"
        assert call_args["tool_approvals"][0].approve is True


async def test_azure_ai_chat_client_get_active_thread_run_with_active_run(mock_agents_client: MagicMock) -> None:
    """Test _get_active_thread_run when there's an active run."""

    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Mock an active run
    mock_run = MagicMock()
    mock_run.status = RunStatus.IN_PROGRESS

    async def mock_list_runs(*args, **kwargs):  # type: ignore
        yield mock_run

    mock_agents_client.runs.list = mock_list_runs

    result = await client._get_active_thread_run("thread-123")  # type: ignore

    assert result == mock_run


async def test_azure_ai_chat_client_get_active_thread_run_no_active_run(mock_agents_client: MagicMock) -> None:
    """Test _get_active_thread_run when there's no active run."""

    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Mock a completed run (not active)
    mock_run = MagicMock()
    mock_run.status = RunStatus.COMPLETED

    async def mock_list_runs(*args, **kwargs):  # type: ignore
        yield mock_run

    mock_agents_client.runs.list = mock_list_runs

    result = await client._get_active_thread_run("thread-123")  # type: ignore

    assert result is None


async def test_azure_ai_chat_client_get_active_thread_run_no_thread(mock_agents_client: MagicMock) -> None:
    """Test _get_active_thread_run with None thread_id."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    result = await client._get_active_thread_run(None)  # type: ignore

    assert result is None
    # Should not call list since thread_id is None
    mock_agents_client.runs.list.assert_not_called()


async def test_azure_ai_chat_client_service_url(mock_agents_client: MagicMock) -> None:
    """Test service_url method."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Mock the config endpoint
    mock_config = MagicMock()
    mock_config.endpoint = "https://test-endpoint.com/"
    mock_agents_client._config = mock_config

    result = client.service_url()

    assert result == "https://test-endpoint.com/"


async def test_azure_ai_chat_client_prepare_tool_outputs_for_azure_tool_result(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_tool_outputs_for_azure_ai with FunctionResultContent."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Test with simple result
    function_result = Content.from_function_result(call_id='["run_123", "call_456"]', result="Simple result")

    run_id, tool_outputs, tool_approvals = client._prepare_tool_outputs_for_azure_ai([function_result])  # type: ignore

    assert run_id == "run_123"
    assert tool_approvals is None
    assert tool_outputs is not None
    assert len(tool_outputs) == 1
    assert tool_outputs[0].tool_call_id == "call_456"
    assert tool_outputs[0].output == "Simple result"


async def test_azure_ai_chat_client_convert_required_action_invalid_call_id(mock_agents_client: MagicMock) -> None:
    """Test _prepare_tool_outputs_for_azure_ai with invalid call_id format."""

    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Invalid call_id format - should raise JSONDecodeError
    function_result = Content.from_function_result(call_id="invalid_json", result="result")

    with pytest.raises(json.JSONDecodeError):
        client._prepare_tool_outputs_for_azure_ai([function_result])  # type: ignore


async def test_azure_ai_chat_client_convert_required_action_invalid_structure(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_tool_outputs_for_azure_ai with invalid call_id structure."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Valid JSON but invalid structure (missing second element)
    function_result = Content.from_function_result(call_id='["run_123"]', result="result")

    run_id, tool_outputs, tool_approvals = client._prepare_tool_outputs_for_azure_ai([function_result])  # type: ignore

    # Should return None values when structure is invalid
    assert run_id is None
    assert tool_outputs is None
    assert tool_approvals is None


async def test_azure_ai_chat_client_convert_required_action_serde_model_results(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_tool_outputs_for_azure_ai with BaseModel results."""

    class MockResult(SerializationMixin):
        def __init__(self, name: str, value: int):
            self.name = name
            self.value = value

    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Test with BaseModel result (pre-parsed as it would be from FunctionTool.invoke)
    mock_result = MockResult(name="test", value=42)
    expected_json = mock_result.to_json()
    function_result = Content.from_function_result(call_id='["run_123", "call_456"]', result=expected_json)

    run_id, tool_outputs, tool_approvals = client._prepare_tool_outputs_for_azure_ai([function_result])  # type: ignore

    assert run_id == "run_123"
    assert tool_approvals is None
    assert tool_outputs is not None
    assert len(tool_outputs) == 1
    assert tool_outputs[0].tool_call_id == "call_456"
    # Should use pre-parsed result string directly
    assert tool_outputs[0].output == expected_json


async def test_azure_ai_chat_client_convert_required_action_multiple_results(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_tool_outputs_for_azure_ai with multiple results."""

    class MockResult(SerializationMixin):
        def __init__(self, data: str):
            self.data = data

    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Test with multiple results - pre-parsed as FunctionTool.invoke would produce
    mock_basemodel = MockResult(data="model_data")
    results_list = [mock_basemodel, {"key": "value"}, "string_result"]
    # FunctionTool.parse_result would serialize this to a JSON string
    from agent_framework import FunctionTool

    pre_parsed = FunctionTool.parse_result(results_list)
    function_result = Content.from_function_result(call_id='["run_123", "call_456"]', result=pre_parsed)

    run_id, tool_outputs, tool_approvals = client._prepare_tool_outputs_for_azure_ai([function_result])  # type: ignore

    assert run_id == "run_123"
    assert tool_outputs is not None
    assert len(tool_outputs) == 1
    assert tool_outputs[0].tool_call_id == "call_456"

    # Result is pre-parsed string (already JSON)
    assert tool_outputs[0].output == pre_parsed


async def test_azure_ai_chat_client_convert_required_action_approval_response(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_tool_outputs_for_azure_ai with FunctionApprovalResponseContent."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Test with approval response - need to provide required fields
    approval_response = Content.from_function_approval_response(
        id='["run_123", "call_456"]',
        function_call=Content.from_function_call(
            call_id='["run_123", "call_456"]', name="test_function", arguments="{}"
        ),
        approved=True,
    )

    run_id, tool_outputs, tool_approvals = client._prepare_tool_outputs_for_azure_ai([approval_response])  # type: ignore

    assert run_id == "run_123"
    assert tool_outputs is None
    assert tool_approvals is not None
    assert len(tool_approvals) == 1
    assert tool_approvals[0].tool_call_id == "call_456"
    assert tool_approvals[0].approve is True


async def test_azure_ai_chat_client_parse_function_calls_from_azure_ai_approval_request(
    mock_agents_client: MagicMock,
) -> None:
    """Test _parse_function_calls_from_azure_ai with approval action."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Mock SubmitToolApprovalAction with RequiredMcpToolCall
    mock_tool_call = MagicMock(spec=RequiredMcpToolCall)
    mock_tool_call.id = "approval_call_123"
    mock_tool_call.name = "approve_action"
    mock_tool_call.arguments = '{"action": "approve"}'

    mock_approval_action = MagicMock(spec=SubmitToolApprovalAction)
    mock_approval_action.submit_tool_approval.tool_calls = [mock_tool_call]

    mock_event_data = MagicMock(spec=ThreadRun)
    mock_event_data.required_action = mock_approval_action

    result = client._parse_function_calls_from_azure_ai(mock_event_data, "response_123")  # type: ignore

    assert len(result) == 1
    assert result[0].type == "function_approval_request"
    assert result[0].id == '["response_123", "approval_call_123"]'
    assert result[0].function_call.name == "approve_action"
    assert result[0].function_call.call_id == '["response_123", "approval_call_123"]'


async def test_azure_ai_chat_client_get_agent_id_or_create_with_agent_name(
    mock_agents_client: MagicMock, azure_ai_unit_test_env: dict[str, str]
) -> None:
    """Test _get_agent_id_or_create uses default name when no agent_name set."""
    azure_ai_settings = load_settings(
        AzureAISettings,
        env_prefix="AZURE_AI_",
        model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
    )
    client = create_test_azure_ai_chat_client(mock_agents_client, azure_ai_settings=azure_ai_settings)

    # Ensure agent_name is None to test the default
    client.agent_name = None  # type: ignore

    agent_id = await client._get_agent_id_or_create(
        run_options={"model": azure_ai_settings.get("model_deployment_name")}
    )  # type: ignore

    assert agent_id == "test-agent-id"
    # Verify create_agent was called with default "UnnamedAgent"
    mock_agents_client.create_agent.assert_called_once()
    call_kwargs = mock_agents_client.create_agent.call_args[1]
    assert call_kwargs["name"] == "UnnamedAgent"


async def test_azure_ai_chat_client_get_agent_id_or_create_with_response_format(
    mock_agents_client: MagicMock, azure_ai_unit_test_env: dict[str, str]
) -> None:
    """Test _get_agent_id_or_create with response_format in run_options."""
    azure_ai_settings = load_settings(
        AzureAISettings,
        env_prefix="AZURE_AI_",
        model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
    )
    client = create_test_azure_ai_chat_client(mock_agents_client, azure_ai_settings=azure_ai_settings)

    # Test with response_format in run_options
    run_options = {"response_format": {"type": "json_object"}, "model": azure_ai_settings.get("model_deployment_name")}

    agent_id = await client._get_agent_id_or_create(run_options)  # type: ignore

    assert agent_id == "test-agent-id"
    # Verify create_agent was called with response_format
    mock_agents_client.create_agent.assert_called_once()
    call_kwargs = mock_agents_client.create_agent.call_args[1]
    assert call_kwargs["response_format"] == {"type": "json_object"}


async def test_azure_ai_chat_client_get_agent_id_or_create_with_tool_resources(
    mock_agents_client: MagicMock, azure_ai_unit_test_env: dict[str, str]
) -> None:
    """Test _get_agent_id_or_create with tool_resources in run_options."""
    azure_ai_settings = load_settings(
        AzureAISettings,
        env_prefix="AZURE_AI_",
        model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
    )
    client = create_test_azure_ai_chat_client(mock_agents_client, azure_ai_settings=azure_ai_settings)

    # Test with tool_resources in run_options
    run_options = {
        "tool_resources": {"vector_store_ids": ["vs-123"]},
        "model": azure_ai_settings.get("model_deployment_name"),
    }

    agent_id = await client._get_agent_id_or_create(run_options)  # type: ignore

    assert agent_id == "test-agent-id"
    # Verify create_agent was called with tool_resources
    mock_agents_client.create_agent.assert_called_once()
    call_kwargs = mock_agents_client.create_agent.call_args[1]
    assert call_kwargs["tool_resources"] == {"vector_store_ids": ["vs-123"]}


async def test_azure_ai_chat_client_create_agent_stream_submit_tool_outputs(
    mock_agents_client: MagicMock,
) -> None:
    """Test _create_agent_stream with tool outputs submission path."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Mock active thread run that matches the tool run ID
    mock_thread_run = MagicMock()
    mock_thread_run.thread_id = "test-thread"
    mock_thread_run.id = "test-run-id"
    client._get_active_thread_run = AsyncMock(return_value=mock_thread_run)  # type: ignore

    # Mock required action results with matching run ID
    function_result = Content.from_function_result(call_id='["test-run-id", "test-call-id"]', result="test result")

    # Mock submit_tool_outputs_stream
    mock_handler = MagicMock()
    mock_agents_client.runs.submit_tool_outputs_stream = AsyncMock()

    with patch("azure.ai.agents.models.AsyncAgentEventHandler", return_value=mock_handler):
        stream, final_thread_id = await client._create_agent_stream(  # type: ignore
            agent_id="test-agent", run_options={"thread_id": "test-thread"}, required_action_results=[function_result]
        )

        # Should call submit_tool_outputs_stream since we have matching run ID
        mock_agents_client.runs.submit_tool_outputs_stream.assert_called_once()
        assert final_thread_id == "test-thread"


def test_azure_ai_chat_client_extract_url_citations_with_citations(mock_agents_client: MagicMock) -> None:
    """Test _extract_url_citations with MessageDeltaChunk containing URL citations."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

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
    citations = client._extract_url_citations(mock_chunk, [])  # type: ignore

    # Verify results
    assert len(citations) == 1
    citation = citations[0]
    assert citation["url"] == "https://example.com/test"
    assert citation["title"] == "Test Title"
    assert citation["snippet"] is None
    assert citation["annotated_regions"] is not None
    assert len(citation["annotated_regions"]) == 1
    assert citation["annotated_regions"][0]["start_index"] == 10
    assert citation["annotated_regions"][0]["end_index"] == 20


def test_azure_ai_chat_client_extract_file_path_contents_with_file_path_annotation(
    mock_agents_client: MagicMock,
) -> None:
    """Test _extract_file_path_contents with MessageDeltaChunk containing file path annotation."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Create mock file_path annotation
    mock_file_path = MagicMock()
    mock_file_path.file_id = "assistant-test-file-123"

    mock_annotation = MagicMock(spec=MessageDeltaTextFilePathAnnotation)
    mock_annotation.file_path = mock_file_path

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

    # Call the method
    file_contents = client._extract_file_path_contents(mock_chunk)

    # Verify results
    assert len(file_contents) == 1
    assert file_contents[0].type == "hosted_file"
    assert file_contents[0].file_id == "assistant-test-file-123"


def test_azure_ai_chat_client_extract_file_path_contents_with_file_citation_annotation(
    mock_agents_client: MagicMock,
) -> None:
    """Test _extract_file_path_contents with MessageDeltaChunk containing file citation annotation."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Create mock file_citation annotation
    mock_file_citation = MagicMock()
    mock_file_citation.file_id = "cfile_test-citation-456"

    mock_annotation = MagicMock(spec=MessageDeltaTextFileCitationAnnotation)
    mock_annotation.file_citation = mock_file_citation

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

    # Call the method
    file_contents = client._extract_file_path_contents(mock_chunk)

    # Verify results
    assert len(file_contents) == 1
    assert file_contents[0].type == "hosted_file"
    assert file_contents[0].file_id == "cfile_test-citation-456"


def test_azure_ai_chat_client_extract_file_path_contents_empty_annotations(
    mock_agents_client: MagicMock,
) -> None:
    """Test _extract_file_path_contents with no annotations returns empty list."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Create mock text content with no annotations
    mock_text = MagicMock()
    mock_text.annotations = []

    mock_text_content = MagicMock(spec=MessageDeltaTextContent)
    mock_text_content.text = mock_text

    # Create mock delta
    mock_delta = MagicMock()
    mock_delta.content = [mock_text_content]

    # Create mock MessageDeltaChunk
    mock_chunk = MagicMock(spec=MessageDeltaChunk)
    mock_chunk.delta = mock_delta

    # Call the method
    file_contents = client._extract_file_path_contents(mock_chunk)

    # Verify results
    assert len(file_contents) == 0


@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    return f"The weather in {location} is sunny with a high of 25°C."


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_get_response() -> None:
    """Test Azure AI Chat Client response."""
    async with AzureAIAgentClient(credential=AzureCliCredential()) as azure_ai_chat_client:
        assert isinstance(azure_ai_chat_client, SupportsChatGetResponse)

        messages: list[Message] = []
        messages.append(
            Message(
                role="user",
                text="The weather in Seattle is currently sunny with a high of 25°C. "
                "It's a beautiful day for outdoor activities.",
            )
        )
        messages.append(Message(role="user", text="What's the weather like today?"))

        # Test that the agents_client can be used to get a response
        response = await azure_ai_chat_client.get_response(messages=messages)

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert any(word in response.text.lower() for word in ["sunny", "25"])


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_get_response_tools() -> None:
    """Test Azure AI Chat Client response with tools."""
    async with AzureAIAgentClient(credential=AzureCliCredential()) as azure_ai_chat_client:
        assert isinstance(azure_ai_chat_client, SupportsChatGetResponse)

        messages: list[Message] = []
        messages.append(Message(role="user", text="What's the weather like in Seattle?"))

        # Test that the agents_client can be used to get a response
        response = await azure_ai_chat_client.get_response(
            messages=messages,
            options={"tools": [get_weather], "tool_choice": "auto"},
        )

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert any(word in response.text.lower() for word in ["sunny", "25"])


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_streaming() -> None:
    """Test Azure AI Chat Client streaming response."""
    async with AzureAIAgentClient(credential=AzureCliCredential()) as azure_ai_chat_client:
        assert isinstance(azure_ai_chat_client, SupportsChatGetResponse)

        messages: list[Message] = []
        messages.append(
            Message(
                role="user",
                text="The weather in Seattle is currently sunny with a high of 25°C. "
                "It's a beautiful day for outdoor activities.",
            )
        )
        messages.append(Message(role="user", text="What's the weather like today?"))

        # Test that the agents_client can be used to get a response
        response = azure_ai_chat_client.get_response(messages=messages, stream=True)

        full_message: str = ""
        async for chunk in response:
            assert chunk is not None
            assert isinstance(chunk, ChatResponseUpdate)
            for content in chunk.contents:
                if content.type == "text" and content.text:
                    full_message += content.text

        assert any(word in full_message.lower() for word in ["sunny", "25"])


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_streaming_tools() -> None:
    """Test Azure AI Chat Client streaming response with tools."""
    async with AzureAIAgentClient(credential=AzureCliCredential()) as azure_ai_chat_client:
        assert isinstance(azure_ai_chat_client, SupportsChatGetResponse)

        messages: list[Message] = []
        messages.append(Message(role="user", text="What's the weather like in Seattle?"))

        # Test that the agents_client can be used to get a response
        response = azure_ai_chat_client.get_response(
            messages=messages,
            stream=True,
            options={"tools": [get_weather], "tool_choice": "auto"},
        )
        full_message: str = ""
        async for chunk in response:
            assert chunk is not None
            assert isinstance(chunk, ChatResponseUpdate)
            for content in chunk.contents:
                if content.type == "text" and content.text:
                    full_message += content.text

        assert any(word in full_message.lower() for word in ["sunny", "25"])


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_basic_run() -> None:
    """Test Agent basic run functionality with AzureAIAgentClient."""
    async with Agent(
        client=AzureAIAgentClient(credential=AzureCliCredential()),
    ) as agent:
        # Run a simple query
        response = await agent.run("Hello! Please respond with 'Hello World' exactly.")

        # Validate response
        assert isinstance(response, AgentResponse)
        assert response.text is not None
        assert len(response.text) > 0
        assert "Hello World" in response.text


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_basic_run_streaming() -> None:
    """Test Agent basic streaming functionality with AzureAIAgentClient."""
    async with Agent(
        client=AzureAIAgentClient(credential=AzureCliCredential()),
    ) as agent:
        # Run streaming query
        full_message: str = ""
        async for chunk in agent.run("Please respond with exactly: 'This is a streaming response test.'", stream=True):
            assert chunk is not None
            assert isinstance(chunk, AgentResponseUpdate)
            if chunk.text:
                full_message += chunk.text

        # Validate streaming response
        assert len(full_message) > 0
        assert "streaming response test" in full_message.lower()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_thread_persistence() -> None:
    """Test Agent session persistence across runs with AzureAIAgentClient."""
    async with Agent(
        client=AzureAIAgentClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant with good memory.",
    ) as agent:
        # Create a new session that will be reused
        session = agent.create_session()

        # First message - establish context
        first_response = await agent.run(
            "Remember this number: 42. What number did I just tell you to remember?", session=session
        )
        assert isinstance(first_response, AgentResponse)
        assert "42" in first_response.text

        # Second message - test conversation memory
        second_response = await agent.run(
            "What number did I tell you to remember in my previous message?", session=session
        )
        assert isinstance(second_response, AgentResponse)
        assert "42" in second_response.text


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_existing_thread_id() -> None:
    """Test Agent existing thread ID functionality with AzureAIAgentClient."""
    async with Agent(
        client=AzureAIAgentClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant with good memory.",
    ) as first_agent:
        # Start a conversation and get the session ID
        session = first_agent.create_session()
        first_response = await first_agent.run("My name is Alice. Remember this.", session=session)

        # Validate first response
        assert isinstance(first_response, AgentResponse)
        assert first_response.text is not None

        # The thread ID is set after the first response
        existing_thread_id = session.service_session_id
        assert existing_thread_id is not None

    # Now continue with the same thread ID in a new agent instance
    async with Agent(
        client=AzureAIAgentClient(thread_id=existing_thread_id, credential=AzureCliCredential()),
        instructions="You are a helpful assistant with good memory.",
    ) as second_agent:
        # Create a session with the existing ID
        session = AgentSession(service_session_id=existing_thread_id)

        # Ask about the previous conversation
        response2 = await second_agent.run("What is my name?", session=session)

        # Validate that the agent remembers the previous conversation
        assert isinstance(response2, AgentResponse)
        assert response2.text is not None
        # Should reference Alice from the previous conversation
        assert "alice" in response2.text.lower()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_code_interpreter():
    """Test Agent with code interpreter through AzureAIAgentClient."""

    async with Agent(
        client=AzureAIAgentClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant that can write and execute Python code.",
        tools=[AzureAIAgentClient.get_code_interpreter_tool()],
    ) as agent:
        # Request code execution
        response = await agent.run("Write Python code to calculate the factorial of 5 and show the result.")

        # Validate response
        assert isinstance(response, AgentResponse)
        assert response.text is not None
        # Factorial of 5 is 120
        assert "120" in response.text or "factorial" in response.text.lower()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_file_search():
    """Test Agent with file search through AzureAIAgentClient."""

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
        file_search_tool = AzureAIAgentClient.get_file_search_tool(vector_store_ids=[vector_store.id])

        async with Agent(
            client=client,
            instructions="You are a helpful assistant that can search through uploaded employee files.",
            tools=[file_search_tool],
        ) as agent:
            # 3. Test file search functionality
            response = await agent.run("Who is the youngest employee in the files?")

            # Validate response
            assert isinstance(response, AgentResponse)
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


@pytest.mark.integration
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_hosted_mcp_tool() -> None:
    """Integration test for MCP tool with Azure AI Agent using Microsoft Learn MCP."""

    mcp_tool = AzureAIAgentClient.get_mcp_tool(
        name="Microsoft Learn MCP",
        url="https://learn.microsoft.com/api/mcp",
        description="A Microsoft Learn MCP server for documentation questions",
        approval_mode="never_require",
    )

    async with Agent(
        client=AzureAIAgentClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=[mcp_tool],
    ) as agent:
        response = await agent.run(
            "How to create an Azure storage account using az cli?",
            options={"max_tokens": 200},
        )

        assert isinstance(response, AgentResponse)
        assert response.text is not None
        assert len(response.text) > 0

        # With never_require approval mode, there should be no approval requests
        assert len(response.user_input_requests) == 0, (
            f"Expected no approval requests with never_require mode, but got {len(response.user_input_requests)}"
        )

        # Should contain Azure-related content since it's asking about Azure CLI
        assert any(term in response.text.lower() for term in ["azure", "storage", "account", "cli"])


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_level_tool_persistence():
    """Test that agent-level tools persist across multiple runs with AzureAIAgentClient."""
    async with Agent(
        client=AzureAIAgentClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant that uses available tools.",
        tools=[get_weather],
    ) as agent:
        # First run - agent-level tool should be available
        first_response = await agent.run("What's the weather like in Chicago?")

        assert isinstance(first_response, AgentResponse)
        assert first_response.text is not None
        # Should use the agent-level weather tool
        assert any(term in first_response.text.lower() for term in ["chicago", "sunny", "25"])

        # Second run - agent-level tool should still be available (persistence test)
        second_response = await agent.run("What's the weather in Miami?")

        assert isinstance(second_response, AgentResponse)
        assert second_response.text is not None
        # Should use the agent-level weather tool again
        assert any(term in second_response.text.lower() for term in ["miami", "sunny", "25"])


@pytest.mark.integration
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_chat_options_run_level() -> None:
    """Test ChatOptions parameter coverage at run level."""
    async with Agent(
        client=AzureAIAgentClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant.",
    ) as agent:
        response = await agent.run(
            "Provide a brief, helpful response.",
            tools=[get_weather],
            options={
                "max_tokens": 100,
                "temperature": 0.7,
                "top_p": 0.9,
                "tool_choice": "auto",
                "metadata": {"test": "value"},
            },
        )

        assert isinstance(response, AgentResponse)
        assert response.text is not None
        assert len(response.text) > 0


@pytest.mark.integration
@skip_if_azure_ai_integration_tests_disabled
async def test_azure_ai_chat_client_agent_chat_options_agent_level() -> None:
    """Test ChatOptions parameter coverage agent level."""
    async with Agent(
        client=AzureAIAgentClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant.",
        tools=[get_weather],
        default_options={
            "max_tokens": 100,
            "temperature": 0.7,
            "top_p": 0.9,
            "tool_choice": "auto",
            "metadata": {"test": "value"},
        },
    ) as agent:
        response = await agent.run(
            "Provide a brief, helpful response.",
        )

        assert isinstance(response, AgentResponse)
        assert response.text is not None
        assert len(response.text) > 0


async def test_azure_ai_chat_client_cleanup_agent_when_enabled_and_created(
    mock_agents_client: MagicMock,
) -> None:
    """Test that agent is cleaned up when should_cleanup_agent=True and agent was created by client."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id=None, should_cleanup_agent=True)

    # Simulate agent creation
    client.agent_id = "created-agent-id"
    client._agent_created = True  # type: ignore

    await client._cleanup_agent_if_needed()  # type: ignore

    # Verify agent was deleted
    mock_agents_client.delete_agent.assert_called_once_with("created-agent-id")
    assert client.agent_id is None
    assert client._agent_created is False  # type: ignore


async def test_azure_ai_chat_client_no_cleanup_when_disabled(
    mock_agents_client: MagicMock,
) -> None:
    """Test that agent is not cleaned up when should_cleanup_agent=False."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id=None, should_cleanup_agent=False)

    # Simulate agent creation
    client.agent_id = "created-agent-id"
    client._agent_created = True

    await client._cleanup_agent_if_needed()  # type: ignore

    # Verify agent was NOT deleted
    mock_agents_client.delete_agent.assert_not_called()
    assert client.agent_id == "created-agent-id"
    assert client._agent_created is True


async def test_azure_ai_chat_client_no_cleanup_when_agent_not_created_by_client(
    mock_agents_client: MagicMock,
) -> None:
    """Test that agent is not cleaned up when it was not created by this client instance."""
    client = create_test_azure_ai_chat_client(
        mock_agents_client, agent_id="existing-agent-id", should_cleanup_agent=True
    )

    # Agent exists but was not created by this client (_agent_created = False)
    assert client._agent_created is False  # type: ignore

    await client._cleanup_agent_if_needed()  # type: ignore

    # Verify agent was NOT deleted
    mock_agents_client.delete_agent.assert_not_called()
    assert client.agent_id == "existing-agent-id"


def test_azure_ai_chat_client_capture_azure_search_tool_calls(mock_agents_client: MagicMock) -> None:
    """Test _capture_azure_search_tool_calls method."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

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
    client._capture_azure_search_tool_calls(mock_step_data, azure_search_tool_calls)  # type: ignore

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
    client = create_test_azure_ai_chat_client(mock_agents_client)

    # No tool calls - pass empty list
    result = client._get_real_url_from_citation_reference("doc_1", [])  # type: ignore
    assert result == "doc_1"


def test_azure_ai_chat_client_get_real_url_from_citation_reference_invalid_output(
    mock_agents_client: MagicMock,
) -> None:
    """Test _get_real_url_from_citation_reference with invalid output format."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    # Tool call with invalid output format
    azure_search_tool_calls = [
        {"id": "call_123", "type": "azure_ai_search", "azure_ai_search": {"output": "invalid_json_format"}}
    ]

    result = client._get_real_url_from_citation_reference("doc_1", azure_search_tool_calls)  # type: ignore
    assert result == "doc_1"


async def test_azure_ai_chat_client_context_manager(mock_agents_client: MagicMock) -> None:
    """Test AzureAIAgentClient as async context manager."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    # Mock close method to avoid actual cleanup
    client.close = AsyncMock()

    async with client as client:
        assert client is client

    # Verify close was called on exit
    client.close.assert_called_once()


async def test_azure_ai_chat_client_close_method(mock_agents_client: MagicMock) -> None:
    """Test AzureAIAgentClient close method."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    # Mock cleanup methods
    client._cleanup_agent_if_needed = AsyncMock()
    client._close_client_if_needed = AsyncMock()

    await client.close()

    # Verify cleanup methods were called
    client._cleanup_agent_if_needed.assert_called_once()
    client._close_client_if_needed.assert_called_once()


def test_azure_ai_chat_client_extract_url_citations_with_azure_search_enhanced_url(
    mock_agents_client: MagicMock,
) -> None:
    """Test _extract_url_citations with Azure AI Search URL enhancement."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

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

    citations = client._extract_url_citations(mock_chunk, azure_search_tool_calls)  # type: ignore

    # Verify real URL was used
    assert len(citations) == 1
    citation = citations[0]
    assert citation["url"] == "https://real-example.com/doc2"  # doc_1 maps to index 1


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


async def test_azure_ai_chat_client_prepare_options_with_mapping_response_format(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_options with Mapping-based response_format (runtime JSON schema)."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    # Runtime JSON schema dict
    response_format_dict = {
        "type": "json_schema",
        "json_schema": {
            "name": "TestSchema",
            "schema": {"type": "object", "properties": {"name": {"type": "string"}}},
        },
    }

    chat_options: ChatOptions = {"response_format": response_format_dict}  # type: ignore[typeddict-item]

    run_options, _ = await client._prepare_options([], chat_options)  # type: ignore

    assert "response_format" in run_options
    # Should pass through as-is for Mapping types
    assert run_options["response_format"] == response_format_dict


async def test_azure_ai_chat_client_prepare_options_with_invalid_response_format(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_options with invalid response_format raises error."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    # Invalid response_format (not BaseModel or Mapping)
    chat_options: ChatOptions = {"response_format": "invalid_format"}  # type: ignore[typeddict-item]

    with pytest.raises(ChatClientInvalidRequestException, match="response_format must be a Pydantic BaseModel"):
        await client._prepare_options([], chat_options)  # type: ignore


async def test_azure_ai_chat_client_prepare_tool_definitions_with_agent_tool_resources(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_tool_definitions_and_resources copies tool_resources from agent definition."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Create mock agent definition with tool_resources
    mock_agent_definition = MagicMock()
    mock_agent_definition.tools = []
    mock_agent_definition.tool_resources = {"code_interpreter": {"file_ids": ["file-123"]}}

    run_options: dict[str, Any] = {}
    options: dict[str, Any] = {}

    await client._prepare_tool_definitions_and_resources(options, mock_agent_definition, run_options)  # type: ignore

    # Verify tool_resources was copied to run_options
    assert "tool_resources" in run_options
    assert run_options["tool_resources"] == {"code_interpreter": {"file_ids": ["file-123"]}}


def test_azure_ai_chat_client_prepare_mcp_resources_with_dict_approval_mode(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_mcp_resources with dict-based approval mode (always_require_approval)."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    # MCP tool with dict-based approval mode - use approval_mode parameter
    mcp_tool = AzureAIAgentClient.get_mcp_tool(
        name="Test MCP",
        url="https://example.com/mcp",
        approval_mode={"always_require_approval": ["tool1", "tool2"]},
    )

    result = client._prepare_mcp_resources([mcp_tool])  # type: ignore

    assert len(result) == 1
    assert result[0]["server_label"] == "Test_MCP"
    assert "require_approval" in result[0]


def test_azure_ai_chat_client_prepare_mcp_resources_with_never_require_dict(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_mcp_resources with dict-based approval mode (never_require_approval)."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    # MCP tool with never require approval - use approval_mode parameter
    mcp_tool = AzureAIAgentClient.get_mcp_tool(
        name="Test MCP",
        url="https://example.com/mcp",
        approval_mode={"never_require_approval": ["safe_tool"]},
    )

    result = client._prepare_mcp_resources([mcp_tool])  # type: ignore

    assert len(result) == 1
    assert "require_approval" in result[0]


def test_azure_ai_chat_client_prepare_messages_with_function_result(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_messages extracts function_result content."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    function_result = Content.from_function_result(call_id='["run_123", "call_456"]', result="test result")
    messages = [Message(role="user", contents=[function_result])]

    additional_messages, instructions, required_action_results = client._prepare_messages(messages)  # type: ignore

    # function_result should be extracted, not added to additional_messages
    assert additional_messages is None
    assert required_action_results is not None
    assert len(required_action_results) == 1
    assert required_action_results[0].type == "function_result"


def test_azure_ai_chat_client_prepare_messages_with_raw_content_block(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_messages handles raw MessageInputContentBlock in content."""
    client = create_test_azure_ai_chat_client(mock_agents_client)

    # Create content with raw_representation that is a MessageInputContentBlock
    raw_block = MessageInputTextBlock(text="Raw block text")
    custom_content = Content(type="custom", raw_representation=raw_block)
    messages = [Message(role="user", contents=[custom_content])]

    additional_messages, instructions, required_action_results = client._prepare_messages(messages)  # type: ignore

    assert additional_messages is not None
    assert len(additional_messages) == 1
    assert len(additional_messages[0].content) == 1
    assert additional_messages[0].content[0] == raw_block


async def test_azure_ai_chat_client_prepare_tools_for_azure_ai_mcp_tool(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_tools_for_azure_ai with MCP dict tool."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    mcp_tool = AzureAIAgentClient.get_mcp_tool(
        name="Test MCP Server",
        url="https://example.com/mcp",
    )

    tool_definitions = await client._prepare_tools_for_azure_ai([mcp_tool])  # type: ignore

    assert len(tool_definitions) >= 1
    # The McpTool.definitions property returns the tool definitions
    # Verify the MCP tool was converted correctly by checking the definition type
    mcp_def = tool_definitions[0]
    assert mcp_def.get("type") == "mcp"


async def test_azure_ai_chat_client_prepare_tools_for_azure_ai_tool_definition(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_tools_for_azure_ai with ToolDefinition passthrough."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Pass a ToolDefinition directly - should be passed through as-is
    tool_def = CodeInterpreterToolDefinition()

    tool_definitions = await client._prepare_tools_for_azure_ai([tool_def])  # type: ignore

    assert len(tool_definitions) == 1
    assert tool_definitions[0] is tool_def


async def test_azure_ai_chat_client_prepare_tools_for_azure_ai_dict_passthrough(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_tools_for_azure_ai with dict passthrough."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Pass a dict tool definition - should be passed through as-is
    dict_tool = {"type": "function", "function": {"name": "test_func", "parameters": {}}}

    tool_definitions = await client._prepare_tools_for_azure_ai([dict_tool])  # type: ignore

    assert len(tool_definitions) == 1
    assert tool_definitions[0] is dict_tool


async def test_azure_ai_chat_client_prepare_tools_for_azure_ai_unsupported_type(
    mock_agents_client: MagicMock,
) -> None:
    """Test _prepare_tools_for_azure_ai passes through unsupported tool types."""
    client = create_test_azure_ai_chat_client(mock_agents_client, agent_id="test-agent")

    # Pass an unsupported tool type - it should be passed through unchanged
    class UnsupportedTool:
        pass

    unsupported_tool = UnsupportedTool()

    # Unsupported tools are now passed through unchanged (server will reject if invalid)
    tool_definitions = await client._prepare_tools_for_azure_ai([unsupported_tool])  # type: ignore
    assert len(tool_definitions) == 1
    assert tool_definitions[0] is unsupported_tool
