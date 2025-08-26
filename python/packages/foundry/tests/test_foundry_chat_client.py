# Copyright (c) Microsoft. All rights reserved.

import os
from typing import Annotated
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import (
    ChatClient,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    ChatRole,
    FunctionCallContent,
    FunctionResultContent,
    TextContent,
    UriContent,
)
from agent_framework.exceptions import ServiceInitializationError
from azure.ai.agents.models import (
    RequiredFunctionToolCall,
    SubmitToolOutputsAction,
    ThreadRun,
)
from azure.core.credentials_async import AsyncTokenCredential
from azure.identity.aio import AzureCliCredential
from pydantic import Field, ValidationError

from agent_framework_foundry import FoundryChatClient, FoundrySettings

skip_if_foundry_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("FOUNDRY_PROJECT_ENDPOINT", "") in ("", "https://test-project.cognitiveservices.azure.com/"),
    reason="No real FOUNDRY_PROJECT_ENDPOINT provided; skipping integration tests."
    if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    else "Integration tests are disabled.",
)


def create_test_foundry_chat_client(
    mock_ai_project_client: MagicMock,
    agent_id: str | None = None,
    thread_id: str | None = None,
    foundry_settings: FoundrySettings | None = None,
    should_delete_agent: bool = False,
) -> FoundryChatClient:
    """Helper function to create FoundryChatClient instances for testing, bypassing Pydantic validation."""
    if foundry_settings is None:
        foundry_settings = FoundrySettings(env_file_path="test.env")

    return FoundryChatClient.model_construct(
        client=mock_ai_project_client,
        agent_id=agent_id,
        thread_id=thread_id,
        _should_delete_agent=should_delete_agent,
        agent_name=foundry_settings.agent_name,  # type: ignore[reportCallIssue]
        ai_model_deployment_name=foundry_settings.model_deployment_name,  # type:
        credential=None,
    )


def test_foundry_settings_init(foundry_unit_test_env: dict[str, str]) -> None:
    """Test FoundrySettings initialization."""
    settings = FoundrySettings()

    assert settings.project_endpoint == foundry_unit_test_env["FOUNDRY_PROJECT_ENDPOINT"]
    assert settings.model_deployment_name == foundry_unit_test_env["FOUNDRY_MODEL_DEPLOYMENT_NAME"]
    assert settings.agent_name == foundry_unit_test_env["FOUNDRY_AGENT_NAME"]


def test_foundry_settings_init_with_explicit_values() -> None:
    """Test FoundrySettings initialization with explicit values."""
    settings = FoundrySettings(
        project_endpoint="https://custom-endpoint.com/",
        model_deployment_name="custom-model",
        agent_name="CustomAgent",
    )

    assert settings.project_endpoint == "https://custom-endpoint.com/"
    assert settings.model_deployment_name == "custom-model"
    assert settings.agent_name == "CustomAgent"


def test_foundry_chat_client_init_with_client(mock_ai_project_client: MagicMock) -> None:
    """Test FoundryChatClient initialization with existing client."""
    chat_client = create_test_foundry_chat_client(
        mock_ai_project_client, agent_id="existing-agent-id", thread_id="test-thread-id"
    )

    assert chat_client.client is mock_ai_project_client
    assert chat_client.agent_id == "existing-agent-id"
    assert chat_client.thread_id == "test-thread-id"
    assert not chat_client._should_delete_agent  # type: ignore
    assert isinstance(chat_client, ChatClient)


def test_foundry_chat_client_init_auto_create_client(
    foundry_unit_test_env: dict[str, str],
    mock_ai_project_client: MagicMock,
) -> None:
    """Test FoundryChatClient initialization with auto-created client."""
    foundry_settings = FoundrySettings(**foundry_unit_test_env)  # type: ignore
    chat_client = FoundryChatClient.model_construct(
        client=mock_ai_project_client,
        agent_id=None,
        thread_id=None,
        _should_delete_agent=False,
        _foundry_settings=foundry_settings,
        credential=None,
    )

    assert chat_client.client is mock_ai_project_client
    assert chat_client.agent_id is None
    assert not chat_client._should_delete_agent  # type: ignore


def test_foundry_chat_client_init_missing_project_endpoint() -> None:
    """Test FoundryChatClient initialization when project_endpoint is missing and no client provided."""
    # Mock FoundrySettings to return settings with None project_endpoint
    with patch("agent_framework_foundry._chat_client.FoundrySettings") as mock_settings:
        mock_settings_instance = MagicMock()
        mock_settings_instance.project_endpoint = None  # This should trigger the error
        mock_settings_instance.model_deployment_name = "test-model"
        mock_settings_instance.agent_name = "test-agent"
        mock_settings.return_value = mock_settings_instance

        with pytest.raises(
            ServiceInitializationError, match="Project endpoint is required when client is not provided"
        ):
            FoundryChatClient(
                client=None,
                agent_id=None,
                project_endpoint=None,  # Missing endpoint
                model_deployment_name="test-model",
                async_credential=AsyncMock(spec=AsyncTokenCredential),
            )


def test_foundry_chat_client_init_missing_model_deployment_for_agent_creation() -> None:
    """Test FoundryChatClient initialization when model deployment is missing for agent creation."""
    # Mock FoundrySettings to return settings with None model_deployment_name
    with patch("agent_framework_foundry._chat_client.FoundrySettings") as mock_settings:
        mock_settings_instance = MagicMock()
        mock_settings_instance.project_endpoint = "https://test.com"
        mock_settings_instance.model_deployment_name = None  # This should trigger the error
        mock_settings_instance.agent_name = "test-agent"
        mock_settings.return_value = mock_settings_instance

        with pytest.raises(ServiceInitializationError, match="Model deployment name is required for agent creation"):
            FoundryChatClient(
                client=None,
                agent_id=None,  # No existing agent
                project_endpoint="https://test.com",
                model_deployment_name=None,  # Missing for agent creation
                async_credential=AsyncMock(spec=AsyncTokenCredential),
            )


def test_foundry_chat_client_from_dict(mock_ai_project_client: MagicMock) -> None:
    """Test FoundryChatClient.from_dict method."""
    settings = {
        "client": mock_ai_project_client,
        "agent_id": "test-agent-id",
        "thread_id": "test-thread-id",
        "project_endpoint": "https://test-endpoint.com/",
        "model_deployment_name": "test-model",
        "agent_name": "TestAgent",
    }

    foundry_settings = FoundrySettings(
        project_endpoint=settings["project_endpoint"],
        model_deployment_name=settings["model_deployment_name"],
        agent_name=settings["agent_name"],
    )

    chat_client: FoundryChatClient = create_test_foundry_chat_client(
        mock_ai_project_client,
        agent_id=settings["agent_id"],  # type: ignore
        thread_id=settings["thread_id"],  # type: ignore
        foundry_settings=foundry_settings,
    )

    assert chat_client.client is mock_ai_project_client
    assert chat_client.agent_id == "test-agent-id"
    assert chat_client.thread_id == "test-thread-id"


def test_foundry_chat_client_init_missing_credential(foundry_unit_test_env: dict[str, str]) -> None:
    """Test FoundryChatClient.__init__ when async_credential is missing and no client provided."""
    with pytest.raises(ServiceInitializationError, match="Azure AD credential is required when client is not provided"):
        FoundryChatClient(
            client=None,
            agent_id="existing-agent",
            project_endpoint=foundry_unit_test_env["FOUNDRY_PROJECT_ENDPOINT"],
            model_deployment_name=foundry_unit_test_env["FOUNDRY_MODEL_DEPLOYMENT_NAME"],
            async_credential=None,  # Missing credential
        )


def test_foundry_chat_client_init_validation_error(mock_azure_credential: MagicMock) -> None:
    """Test that ValidationError in FoundrySettings is properly handled."""
    with patch("agent_framework_foundry._chat_client.FoundrySettings") as mock_settings:
        # Create a proper ValidationError with empty errors list and model dict
        mock_settings.side_effect = ValidationError.from_exception_data("FoundrySettings", [])

        with pytest.raises(ServiceInitializationError, match="Failed to create Foundry settings"):
            FoundryChatClient(
                project_endpoint="https://test.com",
                model_deployment_name="test-model",
                async_credential=mock_azure_credential,
            )


async def test_foundry_chat_client_get_agent_id_or_create_existing_agent(
    mock_ai_project_client: MagicMock,
) -> None:
    """Test _get_agent_id_or_create when agent_id is already provided."""
    chat_client = create_test_foundry_chat_client(mock_ai_project_client, agent_id="existing-agent-id")

    agent_id = await chat_client._get_agent_id_or_create()  # type: ignore

    assert agent_id == "existing-agent-id"
    assert not chat_client._should_delete_agent  # type: ignore


async def test_foundry_chat_client_get_agent_id_or_create_create_new(
    mock_ai_project_client: MagicMock,
    foundry_unit_test_env: dict[str, str],
) -> None:
    """Test _get_agent_id_or_create when creating a new agent."""
    foundry_settings = FoundrySettings(
        model_deployment_name=foundry_unit_test_env["FOUNDRY_MODEL_DEPLOYMENT_NAME"], agent_name="TestAgent"
    )
    chat_client = create_test_foundry_chat_client(mock_ai_project_client, foundry_settings=foundry_settings)

    agent_id = await chat_client._get_agent_id_or_create()  # type: ignore

    assert agent_id == "test-agent-id"
    assert chat_client._should_delete_agent  # type: ignore


async def test_foundry_chat_client_tool_results_without_thread_error_via_public_api(
    mock_ai_project_client: MagicMock,
) -> None:
    """Test that tool results without thread ID raise error through public API."""
    chat_client = create_test_foundry_chat_client(mock_ai_project_client, agent_id="test-agent")

    # Create messages with tool results but no thread/conversation ID
    messages = [
        ChatMessage(role=ChatRole.USER, text="Hello"),
        ChatMessage(
            role=ChatRole.TOOL, contents=[FunctionResultContent(call_id='["run_123", "call_456"]', result="Result")]
        ),
    ]

    # This should raise ValueError when called through public API
    with pytest.raises(ValueError, match="No thread ID was provided, but chat messages includes tool results"):
        async for _ in chat_client.get_streaming_response(messages):
            pass


async def test_foundry_chat_client_thread_management_through_public_api(mock_ai_project_client: MagicMock) -> None:
    """Test thread creation and management through public API."""
    chat_client = create_test_foundry_chat_client(mock_ai_project_client, agent_id="test-agent")

    mock_thread = MagicMock()
    mock_thread.id = "new-thread-456"
    mock_ai_project_client.agents.threads.create = AsyncMock(return_value=mock_thread)

    mock_stream = AsyncMock()
    mock_ai_project_client.agents.runs.stream = AsyncMock(return_value=mock_stream)

    # Create an async iterator that yields nothing (empty stream)
    async def empty_async_iter():
        return
        yield  # Make this a generator (unreachable)

    mock_stream.__aenter__ = AsyncMock(return_value=empty_async_iter())
    mock_stream.__aexit__ = AsyncMock(return_value=None)

    messages = [ChatMessage(role=ChatRole.USER, text="Hello")]

    # Call without existing thread - should create new one
    response = chat_client.get_streaming_response(messages)
    # Consume the generator to trigger the method execution
    async for _ in response:
        pass

    # Verify thread creation was called
    mock_ai_project_client.agents.threads.create.assert_called_once()


@pytest.mark.parametrize("exclude_list", [["FOUNDRY_MODEL_DEPLOYMENT_NAME"]], indirect=True)
async def test_foundry_chat_client_get_agent_id_or_create_missing_model(
    mock_ai_project_client: MagicMock, foundry_unit_test_env: dict[str, str]
) -> None:
    """Test _get_agent_id_or_create when model_deployment_name is missing."""
    chat_client = create_test_foundry_chat_client(mock_ai_project_client)

    with pytest.raises(ServiceInitializationError, match="Model deployment name is required"):
        await chat_client._get_agent_id_or_create()  # type: ignore


async def test_foundry_chat_client_cleanup_agent_if_needed_should_delete(
    mock_ai_project_client: MagicMock,
) -> None:
    """Test _cleanup_agent_if_needed when agent should be deleted."""
    chat_client = create_test_foundry_chat_client(
        mock_ai_project_client, agent_id="agent-to-delete", should_delete_agent=True
    )

    await chat_client._cleanup_agent_if_needed()  # type: ignore

    # Verify agent deletion was called
    mock_ai_project_client.agents.delete_agent.assert_called_once_with("agent-to-delete")
    assert not chat_client._should_delete_agent  # type: ignore


async def test_foundry_chat_client_cleanup_agent_if_needed_should_not_delete(
    mock_ai_project_client: MagicMock,
) -> None:
    """Test _cleanup_agent_if_needed when agent should not be deleted."""
    chat_client = create_test_foundry_chat_client(
        mock_ai_project_client, agent_id="agent-to-keep", should_delete_agent=False
    )

    await chat_client._cleanup_agent_if_needed()  # type: ignore

    # Verify agent deletion was not called
    mock_ai_project_client.agents.delete_agent.assert_not_called()
    assert not chat_client._should_delete_agent  # type: ignore


async def test_foundry_chat_client_cleanup_agent_if_needed_exception_handling(
    mock_ai_project_client: MagicMock,
) -> None:
    """Test _cleanup_agent_if_needed propagates exceptions (it doesn't handle them)."""
    chat_client = create_test_foundry_chat_client(
        mock_ai_project_client, agent_id="agent-to-delete", should_delete_agent=True
    )
    mock_ai_project_client.agents.delete_agent.side_effect = Exception("Deletion failed")

    with pytest.raises(Exception, match="Deletion failed"):
        await chat_client._cleanup_agent_if_needed()  # type: ignore


async def test_foundry_chat_client_aclose(mock_ai_project_client: MagicMock) -> None:
    """Test aclose method calls cleanup."""
    chat_client = create_test_foundry_chat_client(
        mock_ai_project_client, agent_id="agent-to-delete", should_delete_agent=True
    )

    await chat_client.close()

    # Verify agent deletion was called
    mock_ai_project_client.agents.delete_agent.assert_called_once_with("agent-to-delete")


async def test_foundry_chat_client_async_context_manager(mock_ai_project_client: MagicMock) -> None:
    """Test async context manager functionality."""
    chat_client = create_test_foundry_chat_client(
        mock_ai_project_client, agent_id="agent-to-delete", should_delete_agent=True
    )

    # Test context manager
    async with chat_client:
        pass  # Just test that we can enter and exit

    # Verify cleanup was called on exit
    mock_ai_project_client.agents.delete_agent.assert_called_once_with("agent-to-delete")


def test_foundry_chat_client_create_run_options_basic(mock_ai_project_client: MagicMock) -> None:
    """Test _create_run_options with basic ChatOptions."""
    chat_client = create_test_foundry_chat_client(mock_ai_project_client)

    messages = [ChatMessage(role=ChatRole.USER, text="Hello")]
    chat_options = ChatOptions(max_tokens=100, temperature=0.7)

    run_options, tool_results = chat_client._create_run_options(messages, chat_options)  # type: ignore

    assert run_options is not None
    assert tool_results is None


def test_foundry_chat_client_create_run_options_no_chat_options(mock_ai_project_client: MagicMock) -> None:
    """Test _create_run_options with no ChatOptions."""
    chat_client = create_test_foundry_chat_client(mock_ai_project_client)

    messages = [ChatMessage(role=ChatRole.USER, text="Hello")]

    run_options, tool_results = chat_client._create_run_options(messages, None)  # type: ignore

    assert run_options is not None
    assert tool_results is None


def test_foundry_chat_client_create_run_options_with_image_content(mock_ai_project_client: MagicMock) -> None:
    """Test _create_run_options with image content."""

    chat_client = create_test_foundry_chat_client(mock_ai_project_client, agent_id="test-agent")

    image_content = UriContent(uri="https://example.com/image.jpg", media_type="image/jpeg")
    messages = [ChatMessage(role=ChatRole.USER, contents=[image_content])]

    run_options, _ = chat_client._create_run_options(messages, None)  # type: ignore

    assert "additional_messages" in run_options
    assert len(run_options["additional_messages"]) == 1
    # Verify image was converted to MessageInputImageUrlBlock
    message = run_options["additional_messages"][0]
    assert len(message.content) == 1


def test_foundry_chat_client_convert_function_results_to_tool_output(mock_ai_project_client: MagicMock) -> None:
    """Test _convert_function_results_to_tool_output method."""

    chat_client = create_test_foundry_chat_client(mock_ai_project_client)

    function_results = [
        FunctionResultContent(call_id='["run_123", "call_456"]', result="Result 1"),
        FunctionResultContent(call_id='["run_123", "call_789"]', result="Result 2"),
    ]

    run_id, tool_outputs = chat_client._convert_function_results_to_tool_output(function_results)  # type: ignore

    assert run_id == "run_123"
    assert tool_outputs is not None
    assert len(tool_outputs) == 2


def test_foundry_chat_client_convert_function_results_to_tool_output_none(mock_ai_project_client: MagicMock) -> None:
    """Test _convert_function_results_to_tool_output with None input."""
    chat_client = create_test_foundry_chat_client(mock_ai_project_client)

    run_id, tool_outputs = chat_client._convert_function_results_to_tool_output(None)  # type: ignore

    assert run_id is None
    assert tool_outputs is None


async def test_foundry_chat_client_close_client_when_should_close_true(mock_ai_project_client: MagicMock) -> None:
    """Test _close_client_if_needed closes client when should_close_client is True."""
    chat_client = create_test_foundry_chat_client(mock_ai_project_client)
    chat_client._should_close_client = True  # type: ignore

    mock_ai_project_client.close = AsyncMock()

    await chat_client._close_client_if_needed()  # type: ignore

    mock_ai_project_client.close.assert_called_once()


async def test_foundry_chat_client_close_client_when_should_close_false(mock_ai_project_client: MagicMock) -> None:
    """Test _close_client_if_needed does not close client when should_close_client is False."""
    chat_client = create_test_foundry_chat_client(mock_ai_project_client)
    chat_client._should_close_client = False  # type: ignore

    await chat_client._close_client_if_needed()  # type: ignore

    mock_ai_project_client.close.assert_not_called()


def test_foundry_chat_client_update_agent_name_when_current_is_none(mock_ai_project_client: MagicMock) -> None:
    """Test _update_agent_name updates name when current agent_name is None."""
    chat_client = create_test_foundry_chat_client(mock_ai_project_client)
    chat_client.agent_name = None  # type: ignore

    chat_client._update_agent_name("NewAgentName")  # type: ignore

    assert chat_client.agent_name == "NewAgentName"


def test_foundry_chat_client_update_agent_name_when_current_exists(mock_ai_project_client: MagicMock) -> None:
    """Test _update_agent_name does not update when current agent_name exists."""
    chat_client = create_test_foundry_chat_client(mock_ai_project_client)
    chat_client.agent_name = "ExistingName"  # type: ignore

    chat_client._update_agent_name("NewAgentName")  # type: ignore

    assert chat_client.agent_name == "ExistingName"


def test_foundry_chat_client_update_agent_name_with_none_input(mock_ai_project_client: MagicMock) -> None:
    """Test _update_agent_name with None input."""
    chat_client = create_test_foundry_chat_client(mock_ai_project_client)
    chat_client.agent_name = None  # type: ignore

    chat_client._update_agent_name(None)  # type: ignore

    assert chat_client.agent_name is None


def test_foundry_chat_client_create_run_options_with_messages(mock_ai_project_client: MagicMock) -> None:
    """Test _create_run_options with different message types."""
    chat_client = create_test_foundry_chat_client(mock_ai_project_client)

    # Test with system message (becomes instruction)
    messages = [
        ChatMessage(role=ChatRole.SYSTEM, text="You are a helpful assistant"),
        ChatMessage(role=ChatRole.USER, text="Hello"),
    ]

    run_options, _ = chat_client._create_run_options(messages, None)  # type: ignore

    assert "instructions" in run_options
    assert "You are a helpful assistant" in run_options["instructions"]
    assert "additional_messages" in run_options
    assert len(run_options["additional_messages"]) == 1  # Only user message


async def test_foundry_chat_client_inner_get_response(mock_ai_project_client: MagicMock) -> None:
    """Test _inner_get_response method."""
    chat_client = create_test_foundry_chat_client(mock_ai_project_client, agent_id="test-agent")
    messages = [ChatMessage(role=ChatRole.USER, text="Hello")]
    chat_options = ChatOptions()

    async def mock_streaming_response():
        yield ChatResponseUpdate(role=ChatRole.ASSISTANT, text="Hello back")

    with (
        patch.object(chat_client, "_inner_get_streaming_response", return_value=mock_streaming_response()),
        patch("agent_framework.ChatResponse.from_chat_response_generator") as mock_from_generator,
    ):
        mock_response = ChatResponse(role=ChatRole.ASSISTANT, text="Hello back")
        mock_from_generator.return_value = mock_response

        result = await chat_client._inner_get_response(messages=messages, chat_options=chat_options)  # type: ignore

        assert result is mock_response
        mock_from_generator.assert_called_once()


async def test_foundry_chat_client_get_agent_id_or_create_with_run_options(
    mock_ai_project_client: MagicMock, foundry_unit_test_env: dict[str, str]
) -> None:
    """Test _get_agent_id_or_create with run_options containing tools and instructions."""
    foundry_settings = FoundrySettings(
        model_deployment_name=foundry_unit_test_env["FOUNDRY_MODEL_DEPLOYMENT_NAME"], agent_name="TestAgent"
    )
    chat_client = create_test_foundry_chat_client(mock_ai_project_client, foundry_settings=foundry_settings)

    run_options = {
        "tools": [{"type": "function", "function": {"name": "test_tool"}}],
        "instructions": "Test instructions",
        "response_format": {"type": "json_object"},
    }

    agent_id = await chat_client._get_agent_id_or_create(run_options)  # type: ignore

    assert agent_id == "test-agent-id"
    # Verify create_agent was called with run_options parameters
    mock_ai_project_client.agents.create_agent.assert_called_once()
    call_args = mock_ai_project_client.agents.create_agent.call_args[1]
    assert "tools" in call_args
    assert "instructions" in call_args
    assert "response_format" in call_args


async def test_foundry_chat_client_create_agent_stream_with_tool_results(mock_ai_project_client: MagicMock) -> None:
    """Test _create_agent_stream when tool results match active thread run."""
    chat_client = create_test_foundry_chat_client(
        mock_ai_project_client, agent_id="test-agent", thread_id="test-thread"
    )

    mock_thread_run = MagicMock()
    mock_thread_run.id = "run_123"
    mock_thread_run.thread_id = "test-thread"

    with patch.object(chat_client, "_get_active_thread_run", return_value=mock_thread_run):
        tool_results = [FunctionResultContent(call_id='["run_123", "call_456"]', result="Result")]

        mock_handler = MagicMock()
        mock_ai_project_client.agents.runs.submit_tool_outputs_stream = AsyncMock(return_value=None)

        with patch("agent_framework_foundry._chat_client.AsyncAgentEventHandler", return_value=mock_handler):
            stream, thread_id = await chat_client._create_agent_stream("test-thread", "test-agent", {}, tool_results)  # type: ignore

            assert stream is mock_handler
            assert thread_id == "test-thread"
            mock_ai_project_client.agents.runs.submit_tool_outputs_stream.assert_called_once()


async def test_foundry_chat_client_prepare_thread_cancels_active_run(mock_ai_project_client: MagicMock) -> None:
    """Test _prepare_thread cancels active thread run when provided."""
    chat_client = create_test_foundry_chat_client(mock_ai_project_client, agent_id="test-agent")

    mock_thread_run = MagicMock()
    mock_thread_run.id = "run_123"
    mock_thread_run.thread_id = "test-thread"

    run_options = {"additional_messages": []}  # type: ignore

    result = await chat_client._prepare_thread("test-thread", mock_thread_run, run_options)  # type: ignore

    assert result == "test-thread"
    mock_ai_project_client.agents.runs.cancel.assert_called_once_with("test-thread", "run_123")


def test_foundry_chat_client_create_function_call_contents_basic(mock_ai_project_client: MagicMock) -> None:
    """Test _create_function_call_contents with basic function call."""
    chat_client = create_test_foundry_chat_client(mock_ai_project_client)

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


def test_foundry_chat_client_create_function_call_contents_no_submit_action(mock_ai_project_client: MagicMock) -> None:
    """Test _create_function_call_contents when required_action is not SubmitToolOutputsAction."""
    chat_client = create_test_foundry_chat_client(mock_ai_project_client)

    mock_event_data = MagicMock(spec=ThreadRun)
    mock_event_data.required_action = MagicMock()

    result = chat_client._create_function_call_contents(mock_event_data, "response_123")  # type: ignore

    assert result == []


def test_foundry_chat_client_create_function_call_contents_non_function_tool_call(
    mock_ai_project_client: MagicMock,
) -> None:
    """Test _create_function_call_contents with non-function tool call."""
    chat_client = create_test_foundry_chat_client(mock_ai_project_client)

    mock_tool_call = MagicMock()

    mock_submit_action = MagicMock(spec=SubmitToolOutputsAction)
    mock_submit_action.submit_tool_outputs.tool_calls = [mock_tool_call]

    mock_event_data = MagicMock(spec=ThreadRun)
    mock_event_data.required_action = mock_submit_action

    result = chat_client._create_function_call_contents(mock_event_data, "response_123")  # type: ignore

    assert result == []


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    return f"The weather in {location} is sunny with a high of 25°C."


@skip_if_foundry_integration_tests_disabled
async def test_foundry_chat_client_get_response() -> None:
    """Test Foundry Chat Client response."""
    async with FoundryChatClient(async_credential=AzureCliCredential()) as foundry_chat_client:
        assert isinstance(foundry_chat_client, ChatClient)

        messages: list[ChatMessage] = []
        messages.append(
            ChatMessage(
                role="user",
                text="The weather in Seattle is currently sunny with a high of 25°C. "
                "It's a beautiful day for outdoor activities.",
            )
        )
        messages.append(ChatMessage(role="user", text="What's the weather like today?"))

        # Test that the client can be used to get a response
        response = await foundry_chat_client.get_response(messages=messages)

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert any(word in response.text.lower() for word in ["sunny", "25"])


@skip_if_foundry_integration_tests_disabled
async def test_foundry_chat_client_get_response_tools() -> None:
    """Test Foundry Chat Client response with tools."""
    async with FoundryChatClient(async_credential=AzureCliCredential()) as foundry_chat_client:
        assert isinstance(foundry_chat_client, ChatClient)

        messages: list[ChatMessage] = []
        messages.append(ChatMessage(role="user", text="What's the weather like in Seattle?"))

        # Test that the client can be used to get a response
        response = await foundry_chat_client.get_response(
            messages=messages,
            tools=[get_weather],
            tool_choice="auto",
        )

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert any(word in response.text.lower() for word in ["sunny", "25"])


@skip_if_foundry_integration_tests_disabled
async def test_foundry_chat_client_streaming() -> None:
    """Test Foundry Chat Client streaming response."""
    async with FoundryChatClient(async_credential=AzureCliCredential()) as foundry_chat_client:
        assert isinstance(foundry_chat_client, ChatClient)

        messages: list[ChatMessage] = []
        messages.append(
            ChatMessage(
                role="user",
                text="The weather in Seattle is currently sunny with a high of 25°C. "
                "It's a beautiful day for outdoor activities.",
            )
        )
        messages.append(ChatMessage(role="user", text="What's the weather like today?"))

        # Test that the client can be used to get a response
        response = foundry_chat_client.get_streaming_response(messages=messages)

        full_message: str = ""
        async for chunk in response:
            assert chunk is not None
            assert isinstance(chunk, ChatResponseUpdate)
            for content in chunk.contents:
                if isinstance(content, TextContent) and content.text:
                    full_message += content.text

        assert any(word in full_message.lower() for word in ["sunny", "25"])


@skip_if_foundry_integration_tests_disabled
async def test_foundry_chat_client_streaming_tools() -> None:
    """Test Foundry Chat Client streaming response with tools."""
    async with FoundryChatClient(async_credential=AzureCliCredential()) as foundry_chat_client:
        assert isinstance(foundry_chat_client, ChatClient)

        messages: list[ChatMessage] = []
        messages.append(ChatMessage(role="user", text="What's the weather like in Seattle?"))

        # Test that the client can be used to get a response
        response = foundry_chat_client.get_streaming_response(
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
