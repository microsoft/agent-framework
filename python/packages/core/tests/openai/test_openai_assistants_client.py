# Copyright (c) Microsoft. All rights reserved.

import json
import os
from typing import Annotated, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai.types.beta.threads import MessageDeltaEvent, Run, TextDeltaBlock
from openai.types.beta.threads.runs import RunStep
from pydantic import Field

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentThread,
    ChatAgent,
    ChatClientProtocol,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    HostedCodeInterpreterTool,
    HostedFileSearchTool,
    Role,
    tool,
)
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.openai import OpenAIAssistantsClient

skip_if_openai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("OPENAI_API_KEY", "") in ("", "test-dummy-key"),
    reason="No real OPENAI_API_KEY provided; skipping integration tests."
    if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    else "Integration tests are disabled.",
)

INTEGRATION_TEST_MODEL = "gpt-4.1-nano"


def create_test_openai_assistants_client(
    mock_async_openai: MagicMock,
    model_id: str | None = None,
    assistant_id: str | None = None,
    assistant_name: str | None = None,
    thread_id: str | None = None,
    should_delete_assistant: bool = False,
) -> OpenAIAssistantsClient:
    """Helper function to create OpenAIAssistantsClient instances for testing."""
    client = OpenAIAssistantsClient(
        model_id=model_id or "gpt-4",
        assistant_id=assistant_id,
        assistant_name=assistant_name,
        thread_id=thread_id,
        api_key="test-api-key",
        org_id="test-org-id",
        async_client=mock_async_openai,
    )
    # Set the _should_delete_assistant flag directly if needed
    if should_delete_assistant:
        object.__setattr__(client, "_should_delete_assistant", True)
    return client


async def create_vector_store(client: OpenAIAssistantsClient) -> tuple[str, Content]:
    """Create a vector store with sample documents for testing."""
    file = await client.client.files.create(
        file=("todays_weather.txt", b"The weather today is sunny with a high of 25C."), purpose="user_data"
    )
    vector_store = await client.client.vector_stores.create(
        name="knowledge_base",
        expires_after={"anchor": "last_active_at", "days": 1},
    )
    result = await client.client.vector_stores.files.create_and_poll(vector_store_id=vector_store.id, file_id=file.id)
    if result.last_error is not None:
        raise Exception(f"Vector store file processing failed with status: {result.last_error.message}")

    return file.id, Content.from_hosted_vector_store(vector_store_id=vector_store.id)


async def delete_vector_store(client: OpenAIAssistantsClient, file_id: str, vector_store_id: str) -> None:
    """Delete the vector store after tests."""

    await client.client.vector_stores.delete(vector_store_id=vector_store_id)
    await client.client.files.delete(file_id=file_id)


@pytest.fixture
def mock_async_openai() -> MagicMock:
    """Mock AsyncOpenAI client."""
    mock_client = MagicMock()

    # Mock beta.assistants
    mock_client.beta.assistants.create = AsyncMock(return_value=MagicMock(id="test-assistant-id"))
    mock_client.beta.assistants.delete = AsyncMock()

    # Mock beta.threads
    mock_client.beta.threads.create = AsyncMock(return_value=MagicMock(id="test-thread-id"))
    mock_client.beta.threads.delete = AsyncMock()

    # Mock beta.threads.runs
    mock_client.beta.threads.runs.create = AsyncMock(return_value=MagicMock(id="test-run-id"))
    mock_client.beta.threads.runs.retrieve = AsyncMock()
    mock_client.beta.threads.runs.submit_tool_outputs = AsyncMock()
    mock_client.beta.threads.runs.cancel = AsyncMock()

    # Mock beta.threads.messages
    mock_client.beta.threads.messages.create = AsyncMock()
    mock_client.beta.threads.messages.list = AsyncMock(return_value=MagicMock(data=[]))

    return mock_client


def test_init_with_client(mock_async_openai: MagicMock) -> None:
    """Test OpenAIAssistantsClient initialization with existing client."""
    chat_client = create_test_openai_assistants_client(
        mock_async_openai, model_id="gpt-4", assistant_id="existing-assistant-id", thread_id="test-thread-id"
    )

    assert chat_client.client is mock_async_openai
    assert chat_client.model_id == "gpt-4"
    assert chat_client.assistant_id == "existing-assistant-id"
    assert chat_client.thread_id == "test-thread-id"
    assert not chat_client._should_delete_assistant  # type: ignore
    assert isinstance(chat_client, ChatClientProtocol)


def test_init_auto_create_client(
    openai_unit_test_env: dict[str, str],
    mock_async_openai: MagicMock,
) -> None:
    """Test OpenAIAssistantsClient initialization with auto-created client."""
    chat_client = OpenAIAssistantsClient(
        model_id=openai_unit_test_env["OPENAI_CHAT_MODEL_ID"],
        assistant_name="TestAssistant",
        api_key=openai_unit_test_env["OPENAI_API_KEY"],
        org_id=openai_unit_test_env["OPENAI_ORG_ID"],
        async_client=mock_async_openai,
    )

    assert chat_client.client is mock_async_openai
    assert chat_client.model_id == openai_unit_test_env["OPENAI_CHAT_MODEL_ID"]
    assert chat_client.assistant_id is None
    assert chat_client.assistant_name == "TestAssistant"
    assert not chat_client._should_delete_assistant  # type: ignore


def test_init_validation_fail() -> None:
    """Test OpenAIAssistantsClient initialization with validation failure."""
    with pytest.raises(ServiceInitializationError):
        # Force failure by providing invalid model ID type - this should cause validation to fail
        OpenAIAssistantsClient(model_id=123, api_key="valid-key")  # type: ignore


@pytest.mark.parametrize("exclude_list", [["OPENAI_CHAT_MODEL_ID"]], indirect=True)
def test_init_missing_model_id(openai_unit_test_env: dict[str, str]) -> None:
    """Test OpenAIAssistantsClient initialization with missing model ID."""
    with pytest.raises(ServiceInitializationError):
        OpenAIAssistantsClient(
            api_key=openai_unit_test_env.get("OPENAI_API_KEY", "test-key"), env_file_path="nonexistent.env"
        )


@pytest.mark.parametrize("exclude_list", [["OPENAI_API_KEY"]], indirect=True)
def test_init_missing_api_key(openai_unit_test_env: dict[str, str]) -> None:
    """Test OpenAIAssistantsClient initialization with missing API key."""
    with pytest.raises(ServiceInitializationError):
        OpenAIAssistantsClient(model_id="gpt-4", env_file_path="nonexistent.env")


def test_init_with_default_headers(openai_unit_test_env: dict[str, str]) -> None:
    """Test OpenAIAssistantsClient initialization with default headers."""
    default_headers = {"X-Unit-Test": "test-guid"}

    chat_client = OpenAIAssistantsClient(
        model_id="gpt-4",
        api_key=openai_unit_test_env["OPENAI_API_KEY"],
        default_headers=default_headers,
    )

    assert chat_client.model_id == "gpt-4"
    assert isinstance(chat_client, ChatClientProtocol)

    # Assert that the default header we added is present in the client's default headers
    for key, value in default_headers.items():
        assert key in chat_client.client.default_headers
        assert chat_client.client.default_headers[key] == value


async def test_get_assistant_id_or_create_existing_assistant(
    mock_async_openai: MagicMock,
) -> None:
    """Test _get_assistant_id_or_create when assistant_id is already provided."""
    chat_client = create_test_openai_assistants_client(mock_async_openai, assistant_id="existing-assistant-id")

    assistant_id = await chat_client._get_assistant_id_or_create()  # type: ignore

    assert assistant_id == "existing-assistant-id"
    assert not chat_client._should_delete_assistant  # type: ignore
    mock_async_openai.beta.assistants.create.assert_not_called()


async def test_get_assistant_id_or_create_create_new(
    mock_async_openai: MagicMock,
) -> None:
    """Test _get_assistant_id_or_create when creating a new assistant."""
    chat_client = create_test_openai_assistants_client(
        mock_async_openai, model_id="gpt-4", assistant_name="TestAssistant"
    )

    assistant_id = await chat_client._get_assistant_id_or_create()  # type: ignore

    assert assistant_id == "test-assistant-id"
    assert chat_client._should_delete_assistant  # type: ignore
    mock_async_openai.beta.assistants.create.assert_called_once()


async def test_aclose_should_not_delete(
    mock_async_openai: MagicMock,
) -> None:
    """Test close when assistant should not be deleted."""
    chat_client = create_test_openai_assistants_client(
        mock_async_openai, assistant_id="assistant-to-keep", should_delete_assistant=False
    )

    await chat_client.close()  # type: ignore

    # Verify assistant deletion was not called
    mock_async_openai.beta.assistants.delete.assert_not_called()
    assert not chat_client._should_delete_assistant  # type: ignore


async def test_aclose_should_delete(mock_async_openai: MagicMock) -> None:
    """Test close method calls cleanup."""
    chat_client = create_test_openai_assistants_client(
        mock_async_openai, assistant_id="assistant-to-delete", should_delete_assistant=True
    )

    await chat_client.close()

    # Verify assistant deletion was called
    mock_async_openai.beta.assistants.delete.assert_called_once_with("assistant-to-delete")
    assert not chat_client._should_delete_assistant  # type: ignore


async def test_async_context_manager(mock_async_openai: MagicMock) -> None:
    """Test async context manager functionality."""
    chat_client = create_test_openai_assistants_client(
        mock_async_openai, assistant_id="assistant-to-delete", should_delete_assistant=True
    )

    # Test context manager
    async with chat_client:
        pass  # Just test that we can enter and exit

    # Verify cleanup was called on exit
    mock_async_openai.beta.assistants.delete.assert_called_once_with("assistant-to-delete")


def test_serialize(openai_unit_test_env: dict[str, str]) -> None:
    """Test serialization of OpenAIAssistantsClient."""
    default_headers = {"X-Unit-Test": "test-guid"}

    # Test basic initialization and to_dict
    chat_client = OpenAIAssistantsClient(
        model_id="gpt-4",
        assistant_id="test-assistant-id",
        assistant_name="TestAssistant",
        thread_id="test-thread-id",
        api_key=openai_unit_test_env["OPENAI_API_KEY"],
        org_id=openai_unit_test_env["OPENAI_ORG_ID"],
        default_headers=default_headers,
    )

    dumped_settings = chat_client.to_dict()

    assert dumped_settings["model_id"] == "gpt-4"
    assert dumped_settings["assistant_id"] == "test-assistant-id"
    assert dumped_settings["assistant_name"] == "TestAssistant"
    assert dumped_settings["thread_id"] == "test-thread-id"
    assert dumped_settings["org_id"] == openai_unit_test_env["OPENAI_ORG_ID"]

    # Assert that the default header we added is present in the dumped_settings default headers
    for key, value in default_headers.items():
        assert key in dumped_settings["default_headers"]
        assert dumped_settings["default_headers"][key] == value
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]


async def test_get_active_thread_run_none_thread_id(mock_async_openai: MagicMock) -> None:
    """Test _get_active_thread_run with None thread_id returns None."""
    chat_client = create_test_openai_assistants_client(mock_async_openai)

    result = await chat_client._get_active_thread_run(None)  # type: ignore

    assert result is None
    # Should not call the API when thread_id is None
    mock_async_openai.beta.threads.runs.list.assert_not_called()


async def test_get_active_thread_run_with_active_run(mock_async_openai: MagicMock) -> None:
    """Test _get_active_thread_run finds an active run."""

    chat_client = create_test_openai_assistants_client(mock_async_openai)

    # Mock an active run (status not in completed states)
    mock_run = MagicMock()
    mock_run.status = "in_progress"  # Active status

    # Mock the async iterator for runs.list
    async def mock_runs_list(*args: Any, **kwargs: Any) -> Any:
        yield mock_run

    mock_async_openai.beta.threads.runs.list.return_value.__aiter__ = mock_runs_list

    result = await chat_client._get_active_thread_run("thread-123")  # type: ignore

    assert result == mock_run
    mock_async_openai.beta.threads.runs.list.assert_called_once_with(thread_id="thread-123", limit=1, order="desc")


async def test_prepare_thread_create_new(mock_async_openai: MagicMock) -> None:
    """Test _prepare_thread creates new thread when thread_id is None."""
    chat_client = create_test_openai_assistants_client(mock_async_openai)

    # Mock thread creation
    mock_thread = MagicMock()
    mock_thread.id = "new-thread-123"
    mock_async_openai.beta.threads.create.return_value = mock_thread

    # Prepare run options with additional messages
    run_options: dict[str, Any] = {
        "additional_messages": [{"role": "user", "content": "Hello"}],
        "tool_resources": {"code_interpreter": {}},
        "metadata": {"test": "true"},
    }

    result = await chat_client._prepare_thread(None, None, run_options)  # type: ignore

    assert result == "new-thread-123"
    assert run_options["additional_messages"] == []  # Should be cleared
    mock_async_openai.beta.threads.create.assert_called_once_with(
        messages=[{"role": "user", "content": "Hello"}],
        tool_resources={"code_interpreter": {}},
        metadata={"test": "true"},
    )


async def test_prepare_thread_cancel_existing_run(mock_async_openai: MagicMock) -> None:
    """Test _prepare_thread cancels existing run when provided."""
    chat_client = create_test_openai_assistants_client(mock_async_openai)

    # Mock an existing thread run
    mock_thread_run = MagicMock()
    mock_thread_run.id = "run-456"

    run_options: dict[str, Any] = {"additional_messages": []}

    result = await chat_client._prepare_thread("thread-123", mock_thread_run, run_options)  # type: ignore

    assert result == "thread-123"
    mock_async_openai.beta.threads.runs.cancel.assert_called_once_with(run_id="run-456", thread_id="thread-123")


async def test_prepare_thread_existing_no_run(mock_async_openai: MagicMock) -> None:
    """Test _prepare_thread with existing thread_id but no active run."""
    chat_client = create_test_openai_assistants_client(mock_async_openai)

    run_options: dict[str, list[dict[str, str]]] = {"additional_messages": []}

    result = await chat_client._prepare_thread("thread-123", None, run_options)  # type: ignore

    assert result == "thread-123"
    # Should not call cancel since no thread_run provided
    mock_async_openai.beta.threads.runs.cancel.assert_not_called()


async def test_process_stream_events_thread_run_created(mock_async_openai: MagicMock) -> None:
    """Test _process_stream_events with thread.run.created event."""
    chat_client = create_test_openai_assistants_client(mock_async_openai)

    # Create a mock stream response for thread.run.created
    mock_response = MagicMock()
    mock_response.event = "thread.run.created"
    mock_response.data = MagicMock()

    # Create a proper async iterator
    async def async_iterator() -> Any:
        yield mock_response

    # Create a mock stream that yields the response
    mock_stream = MagicMock()
    mock_stream.__aenter__ = AsyncMock(return_value=async_iterator())
    mock_stream.__aexit__ = AsyncMock(return_value=None)

    thread_id = "thread-123"
    updates: list[ChatResponseUpdate] = []
    async for update in chat_client._process_stream_events(mock_stream, thread_id):  # type: ignore
        updates.append(update)

    # Should yield one ChatResponseUpdate for thread.run.created
    assert len(updates) == 1
    update = updates[0]
    assert isinstance(update, ChatResponseUpdate)
    assert update.conversation_id == thread_id
    assert update.role == Role.ASSISTANT
    assert update.contents == []
    assert update.raw_representation == mock_response.data


async def test_process_stream_events_message_delta_text(mock_async_openai: MagicMock) -> None:
    """Test _process_stream_events with thread.message.delta event containing text."""
    chat_client = create_test_openai_assistants_client(mock_async_openai)

    # Create a mock TextDeltaBlock with proper spec
    mock_delta_block = MagicMock(spec=TextDeltaBlock)
    mock_delta_block.text = MagicMock()
    mock_delta_block.text.value = "Hello from assistant"

    mock_delta = MagicMock()
    mock_delta.role = "assistant"
    mock_delta.content = [mock_delta_block]

    mock_message_delta = MagicMock(spec=MessageDeltaEvent)
    mock_message_delta.delta = mock_delta

    mock_response = MagicMock()
    mock_response.event = "thread.message.delta"
    mock_response.data = mock_message_delta

    # Create a proper async iterator
    async def async_iterator() -> Any:
        yield mock_response

    # Create a mock stream
    mock_stream = MagicMock()
    mock_stream.__aenter__ = AsyncMock(return_value=async_iterator())
    mock_stream.__aexit__ = AsyncMock(return_value=None)

    thread_id = "thread-456"
    updates: list[ChatResponseUpdate] = []
    async for update in chat_client._process_stream_events(mock_stream, thread_id):  # type: ignore
        updates.append(update)

    # Should yield one text update
    assert len(updates) == 1
    update = updates[0]
    assert isinstance(update, ChatResponseUpdate)
    assert update.conversation_id == thread_id
    assert update.role == Role.ASSISTANT
    assert update.text == "Hello from assistant"
    assert update.raw_representation == mock_message_delta


async def test_process_stream_events_requires_action(mock_async_openai: MagicMock) -> None:
    """Test _process_stream_events with thread.run.requires_action event."""
    chat_client = create_test_openai_assistants_client(mock_async_openai)

    # Mock the _parse_function_calls_from_assistants method to return test content
    test_function_content = Content.from_function_call(call_id="call-123", name="test_func", arguments={"arg": "value"})
    chat_client._parse_function_calls_from_assistants = MagicMock(return_value=[test_function_content])  # type: ignore

    # Create a mock Run object
    mock_run = MagicMock(spec=Run)

    mock_response = MagicMock()
    mock_response.event = "thread.run.requires_action"
    mock_response.data = mock_run

    # Create a proper async iterator
    async def async_iterator() -> Any:
        yield mock_response

    # Create a mock stream
    mock_stream = MagicMock()
    mock_stream.__aenter__ = AsyncMock(return_value=async_iterator())
    mock_stream.__aexit__ = AsyncMock(return_value=None)

    thread_id = "thread-789"
    updates: list[ChatResponseUpdate] = []
    async for update in chat_client._process_stream_events(mock_stream, thread_id):  # type: ignore
        updates.append(update)

    # Should yield one function call update
    assert len(updates) == 1
    update = updates[0]
    assert isinstance(update, ChatResponseUpdate)
    assert update.conversation_id == thread_id
    assert update.role == Role.ASSISTANT
    assert len(update.contents) == 1
    assert update.contents[0] == test_function_content
    assert update.raw_representation == mock_run

    # Verify _parse_function_calls_from_assistants was called correctly
    chat_client._parse_function_calls_from_assistants.assert_called_once_with(mock_run, None)  # type: ignore


async def test_process_stream_events_run_step_created(mock_async_openai: MagicMock) -> None:
    """Test _process_stream_events with thread.run.step.created event."""

    chat_client = create_test_openai_assistants_client(mock_async_openai)

    # Create a mock RunStep object
    mock_run_step = MagicMock(spec=RunStep)
    mock_run_step.run_id = "run-456"

    mock_response = MagicMock()
    mock_response.event = "thread.run.step.created"
    mock_response.data = mock_run_step

    # Create a proper async iterator
    async def async_iterator() -> Any:
        yield mock_response

    # Create a mock stream
    mock_stream = MagicMock()
    mock_stream.__aenter__ = AsyncMock(return_value=async_iterator())
    mock_stream.__aexit__ = AsyncMock(return_value=None)

    thread_id = "thread-789"
    updates: list[ChatResponseUpdate] = []
    async for update in chat_client._process_stream_events(mock_stream, thread_id):  # type: ignore
        updates.append(update)

    # The run step creation itself doesn't yield an update,
    # but it should set the response_id for subsequent events
    assert len(updates) == 0


async def test_process_stream_events_run_completed_with_usage(
    mock_async_openai: MagicMock,
) -> None:
    """Test _process_stream_events with thread.run.completed event containing usage."""

    chat_client = create_test_openai_assistants_client(mock_async_openai)

    # Create a mock Run object with usage information
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 100
    mock_usage.completion_tokens = 50
    mock_usage.total_tokens = 150

    mock_run = MagicMock(spec=Run)
    mock_run.usage = mock_usage

    mock_response = MagicMock()
    mock_response.event = "thread.run.completed"
    mock_response.data = mock_run

    # Create a proper async iterator
    async def async_iterator() -> Any:
        yield mock_response

    # Create a mock stream
    mock_stream = MagicMock()
    mock_stream.__aenter__ = AsyncMock(return_value=async_iterator())
    mock_stream.__aexit__ = AsyncMock(return_value=None)

    thread_id = "thread-999"
    updates: list[ChatResponseUpdate] = []
    async for update in chat_client._process_stream_events(mock_stream, thread_id):  # type: ignore
        updates.append(update)

    # Should yield one usage update
    assert len(updates) == 1
    update = updates[0]
    assert isinstance(update, ChatResponseUpdate)
    assert update.conversation_id == thread_id
    assert update.role == Role.ASSISTANT
    assert len(update.contents) == 1

    # Check the usage content
    usage_content = update.contents[0]
    assert usage_content.type == "usage"
    assert usage_content.usage_details["input_token_count"] == 100
    assert usage_content.usage_details["output_token_count"] == 50
    assert usage_content.usage_details["total_token_count"] == 150
    assert update.raw_representation == mock_run


def test_parse_function_calls_from_assistants_basic(mock_async_openai: MagicMock) -> None:
    """Test _parse_function_calls_from_assistants with a simple function call."""

    chat_client = create_test_openai_assistants_client(mock_async_openai)

    # Create a mock Run event that requires action
    mock_run = MagicMock()
    mock_run.required_action = MagicMock()
    mock_run.required_action.submit_tool_outputs = MagicMock()

    # Create a mock tool call
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_abc123"
    mock_tool_call.function.name = "get_weather"
    mock_tool_call.function.arguments = '{"location": "Seattle"}'

    mock_run.required_action.submit_tool_outputs.tool_calls = [mock_tool_call]

    # Call the method
    response_id = "response_456"
    contents = chat_client._parse_function_calls_from_assistants(mock_run, response_id)  # type: ignore

    # Test that one function call content was created
    assert len(contents) == 1
    assert contents[0].type == "function_call"
    assert contents[0].name == "get_weather"
    assert contents[0].arguments == {"location": "Seattle"}


def test_parse_run_step_with_code_interpreter_tool_call(mock_async_openai: MagicMock) -> None:
    """Test _parse_run_step_tool_call with code_interpreter type creates CodeInterpreterToolCallContent."""
    client = create_test_openai_assistants_client(
        mock_async_openai,
        model_id="test-model",
        assistant_id="test-assistant",
    )

    # Mock a run with required_action containing code_interpreter tool call
    mock_run = MagicMock()
    mock_run.id = "run_123"
    mock_run.status = "requires_action"

    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_code_123"
    mock_tool_call.type = "code_interpreter"
    mock_code_interpreter = MagicMock()
    mock_code_interpreter.input = "print('Hello, World!')"
    mock_tool_call.code_interpreter = mock_code_interpreter

    mock_required_action = MagicMock()
    mock_required_action.submit_tool_outputs = MagicMock()
    mock_required_action.submit_tool_outputs.tool_calls = [mock_tool_call]
    mock_run.required_action = mock_required_action

    # Parse the run step
    contents = client._parse_function_calls_from_assistants(mock_run, "response_123")

    # Should have CodeInterpreterToolCallContent
    assert len(contents) == 1
    assert contents[0].type == "code_interpreter_tool_call"
    assert contents[0].call_id == '["response_123", "call_code_123"]'
    assert contents[0].inputs is not None
    assert len(contents[0].inputs) == 1
    assert contents[0].inputs[0].type == "text"
    assert contents[0].inputs[0].text == "print('Hello, World!')"


def test_parse_run_step_with_mcp_tool_call(mock_async_openai: MagicMock) -> None:
    """Test _parse_run_step_tool_call with mcp type creates MCPServerToolCallContent."""
    client = create_test_openai_assistants_client(
        mock_async_openai,
        model_id="test-model",
        assistant_id="test-assistant",
    )

    # Mock a run with required_action containing mcp tool call
    mock_run = MagicMock()
    mock_run.id = "run_456"
    mock_run.status = "requires_action"

    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_mcp_456"
    mock_tool_call.type = "mcp"
    mock_tool_call.name = "fetch_data"
    mock_tool_call.server_label = "DataServer"
    mock_tool_call.args = {"key": "value"}

    mock_required_action = MagicMock()
    mock_required_action.submit_tool_outputs = MagicMock()
    mock_required_action.submit_tool_outputs.tool_calls = [mock_tool_call]
    mock_run.required_action = mock_required_action

    # Parse the run step
    contents = client._parse_function_calls_from_assistants(mock_run, "response_456")

    # Should have MCPServerToolCallContent
    assert len(contents) == 1
    assert contents[0].type == "mcp_server_tool_call"
    assert contents[0].call_id == '["response_456", "call_mcp_456"]'
    assert contents[0].tool_name == "fetch_data"
    assert contents[0].server_name == "DataServer"
    assert contents[0].arguments == {"key": "value"}


def test_prepare_options_basic(mock_async_openai: MagicMock) -> None:
    """Test _prepare_options with basic chat options."""
    chat_client = create_test_openai_assistants_client(mock_async_openai)

    # Create basic chat options as a dict
    options = {
        "max_tokens": 100,
        "model_id": "gpt-4",
        "temperature": 0.7,
        "top_p": 0.9,
    }

    messages = [ChatMessage(role=Role.USER, text="Hello")]

    # Call the method
    run_options, tool_results = chat_client._prepare_options(messages, options)  # type: ignore

    # Check basic options were set
    assert run_options["max_completion_tokens"] == 100
    assert run_options["model"] == "gpt-4"
    assert run_options["temperature"] == 0.7
    assert run_options["top_p"] == 0.9
    assert tool_results is None


def test_prepare_options_with_tool_tool(mock_async_openai: MagicMock) -> None:
    """Test _prepare_options with a FunctionTool."""

    chat_client = create_test_openai_assistants_client(mock_async_openai)

    # Create a simple function for testing and decorate it
    @tool(approval_mode="never_require")
    def test_function(query: str) -> str:
        """A test function."""
        return f"Result for {query}"

    options = {
        "tools": [test_function],
        "tool_choice": "auto",
    }

    messages = [ChatMessage(role=Role.USER, text="Hello")]

    # Call the method
    run_options, tool_results = chat_client._prepare_options(messages, options)  # type: ignore

    # Check tools were set correctly
    assert "tools" in run_options
    assert len(run_options["tools"]) == 1
    assert run_options["tools"][0]["type"] == "function"
    assert "function" in run_options["tools"][0]
    assert run_options["tool_choice"] == "auto"


def test_prepare_options_with_code_interpreter(mock_async_openai: MagicMock) -> None:
    """Test _prepare_options with HostedCodeInterpreterTool."""
    chat_client = create_test_openai_assistants_client(mock_async_openai)

    # Create a real HostedCodeInterpreterTool
    code_tool = HostedCodeInterpreterTool()

    options = {
        "tools": [code_tool],
        "tool_choice": "auto",
    }

    messages = [ChatMessage(role=Role.USER, text="Calculate something")]

    # Call the method
    run_options, tool_results = chat_client._prepare_options(messages, options)  # type: ignore

    # Check code interpreter tool was set correctly
    assert "tools" in run_options
    assert len(run_options["tools"]) == 1
    assert run_options["tools"][0] == {"type": "code_interpreter"}
    assert run_options["tool_choice"] == "auto"


def test_prepare_options_tool_choice_none(mock_async_openai: MagicMock) -> None:
    """Test _prepare_options with tool_choice set to 'none'."""
    chat_client = create_test_openai_assistants_client(mock_async_openai)

    options = {
        "tool_choice": "none",
    }

    messages = [ChatMessage(role=Role.USER, text="Hello")]

    # Call the method
    run_options, tool_results = chat_client._prepare_options(messages, options)  # type: ignore

    # Should set tool_choice to none and not include tools
    assert run_options["tool_choice"] == "none"
    assert "tools" not in run_options


def test_prepare_options_required_function(mock_async_openai: MagicMock) -> None:
    """Test _prepare_options with required function tool choice."""
    chat_client = create_test_openai_assistants_client(mock_async_openai)

    # Create a required function tool choice as dict
    tool_choice = {"mode": "required", "required_function_name": "specific_function"}

    options = {
        "tool_choice": tool_choice,
    }

    messages = [ChatMessage(role=Role.USER, text="Hello")]

    # Call the method
    run_options, tool_results = chat_client._prepare_options(messages, options)  # type: ignore

    # Check required function tool choice was set correctly
    expected_tool_choice = {
        "type": "function",
        "function": {"name": "specific_function"},
    }
    assert run_options["tool_choice"] == expected_tool_choice


def test_prepare_options_with_file_search_tool(mock_async_openai: MagicMock) -> None:
    """Test _prepare_options with HostedFileSearchTool."""

    chat_client = create_test_openai_assistants_client(mock_async_openai)

    # Create a HostedFileSearchTool with max_results
    file_search_tool = HostedFileSearchTool(max_results=10)

    options = {
        "tools": [file_search_tool],
        "tool_choice": "auto",
    }

    messages = [ChatMessage(role=Role.USER, text="Search for information")]

    # Call the method
    run_options, tool_results = chat_client._prepare_options(messages, options)  # type: ignore

    # Check file search tool was set correctly
    assert "tools" in run_options
    assert len(run_options["tools"]) == 1
    expected_tool = {"type": "file_search", "max_num_results": 10}
    assert run_options["tools"][0] == expected_tool
    assert run_options["tool_choice"] == "auto"


def test_prepare_options_with_mapping_tool(mock_async_openai: MagicMock) -> None:
    """Test _prepare_options with MutableMapping tool."""
    chat_client = create_test_openai_assistants_client(mock_async_openai)

    # Create a tool as a MutableMapping (dict)
    mapping_tool = {"type": "custom_tool", "parameters": {"setting": "value"}}

    options = {
        "tools": [mapping_tool],  # type: ignore
        "tool_choice": "auto",
    }

    messages = [ChatMessage(role=Role.USER, text="Use custom tool")]

    # Call the method
    run_options, tool_results = chat_client._prepare_options(messages, options)  # type: ignore

    # Check mapping tool was set correctly
    assert "tools" in run_options
    assert len(run_options["tools"]) == 1
    assert run_options["tools"][0] == mapping_tool
    assert run_options["tool_choice"] == "auto"


def test_prepare_options_with_pydantic_response_format(mock_async_openai: MagicMock) -> None:
    """Test _prepare_options sets strict=True for Pydantic response_format."""
    from pydantic import BaseModel, ConfigDict

    class TestResponse(BaseModel):
        name: str
        value: int
        model_config = ConfigDict(extra="forbid")

    chat_client = create_test_openai_assistants_client(mock_async_openai)
    messages = [ChatMessage(role=Role.USER, text="Test")]
    options = {"response_format": TestResponse}

    run_options, _ = chat_client._prepare_options(messages, options)  # type: ignore

    assert "response_format" in run_options
    assert run_options["response_format"]["type"] == "json_schema"
    assert run_options["response_format"]["json_schema"]["name"] == "TestResponse"
    assert run_options["response_format"]["json_schema"]["strict"] is True


def test_prepare_options_with_system_message(mock_async_openai: MagicMock) -> None:
    """Test _prepare_options with system message converted to instructions."""
    chat_client = create_test_openai_assistants_client(mock_async_openai)

    messages = [
        ChatMessage(role=Role.SYSTEM, text="You are a helpful assistant."),
        ChatMessage(role=Role.USER, text="Hello"),
    ]

    # Call the method
    run_options, tool_results = chat_client._prepare_options(messages, {})  # type: ignore

    # Check that additional_messages only contains the user message
    # System message should be converted to instructions (though this is handled internally)
    assert "additional_messages" in run_options
    assert len(run_options["additional_messages"]) == 1
    assert run_options["additional_messages"][0]["role"] == "user"


def test_prepare_options_with_image_content(mock_async_openai: MagicMock) -> None:
    """Test _prepare_options with image content."""

    chat_client = create_test_openai_assistants_client(mock_async_openai)

    # Create message with image content
    image_content = Content.from_uri(uri="https://example.com/image.jpg", media_type="image/jpeg")
    messages = [ChatMessage(role=Role.USER, contents=[image_content])]

    # Call the method
    run_options, tool_results = chat_client._prepare_options(messages, {})  # type: ignore

    # Check that image content was processed
    assert "additional_messages" in run_options
    assert len(run_options["additional_messages"]) == 1
    message = run_options["additional_messages"][0]
    assert message["role"] == "user"
    assert len(message["content"]) == 1
    assert message["content"][0]["type"] == "image_url"
    assert message["content"][0]["image_url"]["url"] == "https://example.com/image.jpg"


def test_prepare_tool_outputs_for_assistants_empty(mock_async_openai: MagicMock) -> None:
    """Test _prepare_tool_outputs_for_assistants with empty list."""
    chat_client = create_test_openai_assistants_client(mock_async_openai)

    run_id, tool_outputs = chat_client._prepare_tool_outputs_for_assistants([])  # type: ignore

    assert run_id is None
    assert tool_outputs is None


def test_prepare_tool_outputs_for_assistants_valid(mock_async_openai: MagicMock) -> None:
    """Test _prepare_tool_outputs_for_assistants with valid function results."""
    chat_client = create_test_openai_assistants_client(mock_async_openai)

    call_id = json.dumps(["run-123", "call-456"])
    function_result = Content.from_function_result(call_id=call_id, result="Function executed successfully")

    run_id, tool_outputs = chat_client._prepare_tool_outputs_for_assistants([function_result])  # type: ignore

    assert run_id == "run-123"
    assert tool_outputs is not None
    assert len(tool_outputs) == 1
    assert tool_outputs[0].get("tool_call_id") == "call-456"
    assert tool_outputs[0].get("output") == "Function executed successfully"


def test_prepare_tool_outputs_for_assistants_mismatched_run_ids(
    mock_async_openai: MagicMock,
) -> None:
    """Test _prepare_tool_outputs_for_assistants with mismatched run IDs."""
    chat_client = create_test_openai_assistants_client(mock_async_openai)

    # Create function results with different run IDs
    call_id1 = json.dumps(["run-123", "call-456"])
    call_id2 = json.dumps(["run-789", "call-xyz"])  # Different run ID
    function_result1 = Content.from_function_result(call_id=call_id1, result="Result 1")
    function_result2 = Content.from_function_result(call_id=call_id2, result="Result 2")

    run_id, tool_outputs = chat_client._prepare_tool_outputs_for_assistants([function_result1, function_result2])  # type: ignore

    # Should only process the first one since run IDs don't match
    assert run_id == "run-123"
    assert tool_outputs is not None
    assert len(tool_outputs) == 1
    assert tool_outputs[0].get("tool_call_id") == "call-456"


def test_update_agent_name_and_description(mock_async_openai: MagicMock) -> None:
    """Test _update_agent_name_and_description method updates assistant_name when not already set."""
    # Test updating agent name when assistant_name is None
    chat_client = create_test_openai_assistants_client(mock_async_openai, assistant_name=None)

    # Call the private method to update agent name
    chat_client._update_agent_name_and_description("New Assistant Name")  # type: ignore

    assert chat_client.assistant_name == "New Assistant Name"


def test_update_agent_name_and_description_existing(mock_async_openai: MagicMock) -> None:
    """Test _update_agent_name_and_description method doesn't override existing assistant_name."""
    # Test that existing assistant_name is not overridden
    chat_client = create_test_openai_assistants_client(mock_async_openai, assistant_name="Existing Assistant")

    # Call the private method to update agent name
    chat_client._update_agent_name_and_description("New Assistant Name")  # type: ignore

    # Should keep the existing name
    assert chat_client.assistant_name == "Existing Assistant"


def test_update_agent_name_and_description_none(mock_async_openai: MagicMock) -> None:
    """Test _update_agent_name_and_description method with None agent_name parameter."""
    # Test that None agent_name doesn't change anything
    chat_client = create_test_openai_assistants_client(mock_async_openai, assistant_name=None)

    # Call the private method with None
    chat_client._update_agent_name_and_description(None)  # type: ignore

    # Should remain None
    assert chat_client.assistant_name is None


@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    return f"The weather in {location} is sunny with a high of 25°C."


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_get_response() -> None:
    """Test OpenAI Assistants Client response."""
    async with OpenAIAssistantsClient(model_id=INTEGRATION_TEST_MODEL) as openai_assistants_client:
        assert isinstance(openai_assistants_client, ChatClientProtocol)

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
        response = await openai_assistants_client.get_response(messages=messages)

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert any(word in response.text.lower() for word in ["sunny", "25", "weather", "seattle"])


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_get_response_tools() -> None:
    """Test OpenAI Assistants Client response with tools."""
    async with OpenAIAssistantsClient(model_id=INTEGRATION_TEST_MODEL) as openai_assistants_client:
        assert isinstance(openai_assistants_client, ChatClientProtocol)

        messages: list[ChatMessage] = []
        messages.append(ChatMessage(role="user", text="What's the weather like in Seattle?"))

        # Test that the client can be used to get a response
        response = await openai_assistants_client.get_response(
            messages=messages,
            options={"tools": [get_weather], "tool_choice": "auto"},
        )

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert any(word in response.text.lower() for word in ["sunny", "25", "weather"])


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_streaming() -> None:
    """Test OpenAI Assistants Client streaming response."""
    async with OpenAIAssistantsClient(model_id=INTEGRATION_TEST_MODEL) as openai_assistants_client:
        assert isinstance(openai_assistants_client, ChatClientProtocol)

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
        response = openai_assistants_client.get_streaming_response(messages=messages)

        full_message: str = ""
        async for chunk in response:
            assert chunk is not None
            assert isinstance(chunk, ChatResponseUpdate)
            for content in chunk.contents:
                if content.type == "text" and content.text:
                    full_message += content.text

        assert any(word in full_message.lower() for word in ["sunny", "25", "weather", "seattle"])


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_streaming_tools() -> None:
    """Test OpenAI Assistants Client streaming response with tools."""
    async with OpenAIAssistantsClient(model_id=INTEGRATION_TEST_MODEL) as openai_assistants_client:
        assert isinstance(openai_assistants_client, ChatClientProtocol)

        messages: list[ChatMessage] = []
        messages.append(ChatMessage(role="user", text="What's the weather like in Seattle?"))

        # Test that the client can be used to get a response
        response = openai_assistants_client.get_streaming_response(
            messages=messages,
            options={
                "tools": [get_weather],
                "tool_choice": "auto",
            },
        )
        full_message: str = ""
        async for chunk in response:
            assert chunk is not None
            assert isinstance(chunk, ChatResponseUpdate)
            for content in chunk.contents:
                if content.type == "text" and content.text:
                    full_message += content.text

        assert any(word in full_message.lower() for word in ["sunny", "25", "weather"])


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_with_existing_assistant() -> None:
    """Test OpenAI Assistants Client with existing assistant ID."""
    # First create an assistant to use in the test
    async with OpenAIAssistantsClient(model_id=INTEGRATION_TEST_MODEL) as temp_client:
        # Get the assistant ID by triggering assistant creation
        messages = [ChatMessage(role="user", text="Hello")]
        await temp_client.get_response(messages=messages)
        assistant_id = temp_client.assistant_id

        # Now test using the existing assistant
        async with OpenAIAssistantsClient(
            model_id=INTEGRATION_TEST_MODEL, assistant_id=assistant_id
        ) as openai_assistants_client:
            assert isinstance(openai_assistants_client, ChatClientProtocol)
            assert openai_assistants_client.assistant_id == assistant_id

            messages = [ChatMessage(role="user", text="What can you do?")]

            # Test that the client can be used to get a response
            response = await openai_assistants_client.get_response(messages=messages)

            assert response is not None
            assert isinstance(response, ChatResponse)
            assert len(response.text) > 0


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
@pytest.mark.skip(reason="OpenAI file search functionality is currently broken - tracked in GitHub issue")
async def test_file_search() -> None:
    """Test OpenAI Assistants Client response."""
    async with OpenAIAssistantsClient(model_id=INTEGRATION_TEST_MODEL) as openai_assistants_client:
        assert isinstance(openai_assistants_client, ChatClientProtocol)

        messages: list[ChatMessage] = []
        messages.append(ChatMessage(role="user", text="What's the weather like today?"))

        file_id, vector_store = await create_vector_store(openai_assistants_client)
        response = await openai_assistants_client.get_response(
            messages=messages,
            options={
                "tools": [HostedFileSearchTool()],
                "tool_resources": {"file_search": {"vector_store_ids": [vector_store.vector_store_id]}},
            },
        )
        await delete_vector_store(openai_assistants_client, file_id, vector_store.vector_store_id)

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert any(word in response.text.lower() for word in ["sunny", "25", "weather"])


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
@pytest.mark.skip(reason="OpenAI file search functionality is currently broken - tracked in GitHub issue")
async def test_file_search_streaming() -> None:
    """Test OpenAI Assistants Client response."""
    async with OpenAIAssistantsClient(model_id=INTEGRATION_TEST_MODEL) as openai_assistants_client:
        assert isinstance(openai_assistants_client, ChatClientProtocol)

        messages: list[ChatMessage] = []
        messages.append(ChatMessage(role="user", text="What's the weather like today?"))

        file_id, vector_store = await create_vector_store(openai_assistants_client)
        response = openai_assistants_client.get_streaming_response(
            messages=messages,
            options={
                "tools": [HostedFileSearchTool()],
                "tool_resources": {"file_search": {"vector_store_ids": [vector_store.vector_store_id]}},
            },
        )

        assert response is not None
        full_message: str = ""
        async for chunk in response:
            assert chunk is not None
            assert isinstance(chunk, ChatResponseUpdate)
            for content in chunk.contents:
                if content.type == "text" and content.text:
                    full_message += content.text
        await delete_vector_store(openai_assistants_client, file_id, vector_store.vector_store_id)

        assert any(word in full_message.lower() for word in ["sunny", "25", "weather"])


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_assistants_agent_basic_run():
    """Test ChatAgent basic run functionality with OpenAIAssistantsClient."""
    async with ChatAgent(
        chat_client=OpenAIAssistantsClient(model_id=INTEGRATION_TEST_MODEL),
    ) as agent:
        # Run a simple query
        response = await agent.run("Hello! Please respond with 'Hello World' exactly.")

        # Validate response
        assert isinstance(response, AgentResponse)
        assert response.text is not None
        assert len(response.text) > 0
        assert "Hello World" in response.text


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_assistants_agent_basic_run_streaming():
    """Test ChatAgent basic streaming functionality with OpenAIAssistantsClient."""
    async with ChatAgent(
        chat_client=OpenAIAssistantsClient(model_id=INTEGRATION_TEST_MODEL),
    ) as agent:
        # Run streaming query
        full_message: str = ""
        async for chunk in agent.run_stream("Please respond with exactly: 'This is a streaming response test.'"):
            assert chunk is not None
            assert isinstance(chunk, AgentResponseUpdate)
            if chunk.text:
                full_message += chunk.text

        # Validate streaming response
        assert len(full_message) > 0
        assert "streaming response test" in full_message.lower()


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_assistants_agent_thread_persistence():
    """Test ChatAgent thread persistence across runs with OpenAIAssistantsClient."""
    async with ChatAgent(
        chat_client=OpenAIAssistantsClient(model_id=INTEGRATION_TEST_MODEL),
        instructions="You are a helpful assistant with good memory.",
    ) as agent:
        # Create a new thread that will be reused
        thread = agent.get_new_thread()

        # First message - establish context
        first_response = await agent.run(
            "Remember this number: 42. What number did I just tell you to remember?", thread=thread
        )
        assert isinstance(first_response, AgentResponse)
        assert "42" in first_response.text

        # Second message - test conversation memory
        second_response = await agent.run(
            "What number did I tell you to remember in my previous message?", thread=thread
        )
        assert isinstance(second_response, AgentResponse)
        assert "42" in second_response.text

        # Verify thread has been populated with conversation ID
        assert thread.service_thread_id is not None


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_assistants_agent_existing_thread_id():
    """Test ChatAgent with existing thread ID to continue conversations across agent instances."""
    # First, create a conversation and capture the thread ID
    existing_thread_id = None

    async with ChatAgent(
        chat_client=OpenAIAssistantsClient(model_id=INTEGRATION_TEST_MODEL),
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    ) as agent:
        # Start a conversation and get the thread ID
        thread = agent.get_new_thread()
        response1 = await agent.run("What's the weather in Paris?", thread=thread)

        # Validate first response
        assert isinstance(response1, AgentResponse)
        assert response1.text is not None
        assert any(word in response1.text.lower() for word in ["weather", "paris"])

        # The thread ID is set after the first response
        existing_thread_id = thread.service_thread_id
        assert existing_thread_id is not None

    # Now continue with the same thread ID in a new agent instance

    async with ChatAgent(
        chat_client=OpenAIAssistantsClient(thread_id=existing_thread_id),
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    ) as agent:
        # Create a thread with the existing ID
        thread = AgentThread(service_thread_id=existing_thread_id)

        # Ask about the previous conversation
        response2 = await agent.run("What was the last city I asked about?", thread=thread)

        # Validate that the agent remembers the previous conversation
        assert isinstance(response2, AgentResponse)
        assert response2.text is not None
        # Should reference Paris from the previous conversation
        assert "paris" in response2.text.lower()


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_assistants_agent_code_interpreter():
    """Test ChatAgent with code interpreter through OpenAIAssistantsClient."""

    async with ChatAgent(
        chat_client=OpenAIAssistantsClient(model_id=INTEGRATION_TEST_MODEL),
        instructions="You are a helpful assistant that can write and execute Python code.",
        tools=[HostedCodeInterpreterTool()],
    ) as agent:
        # Request code execution
        response = await agent.run("Write Python code to calculate the factorial of 5 and show the result.")

        # Validate response
        assert isinstance(response, AgentResponse)
        assert response.text is not None
        # Factorial of 5 is 120
        assert "120" in response.text or "factorial" in response.text.lower()


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_agent_level_tool_persistence():
    """Test that agent-level tools persist across multiple runs with OpenAI Assistants Client."""

    async with ChatAgent(
        chat_client=OpenAIAssistantsClient(model_id=INTEGRATION_TEST_MODEL),
        instructions="You are a helpful assistant that uses available tools.",
        tools=[get_weather],  # Agent-level tool
    ) as agent:
        # First run - agent-level tool should be available
        first_response = await agent.run("What's the weather like in Chicago?")

        assert isinstance(first_response, AgentResponse)
        assert first_response.text is not None
        # Should use the agent-level weather tool
        assert any(term in first_response.text.lower() for term in ["chicago", "sunny", "72"])

        # Second run - agent-level tool should still be available (persistence test)
        second_response = await agent.run("What's the weather in Miami?")

        assert isinstance(second_response, AgentResponse)
        assert second_response.text is not None
        # Should use the agent-level weather tool again
        assert any(term in second_response.text.lower() for term in ["miami", "sunny", "72"])


# Callable API Key Tests
def test_with_callable_api_key() -> None:
    """Test OpenAIAssistantsClient initialization with callable API key."""

    async def get_api_key() -> str:
        return "test-api-key-123"

    client = OpenAIAssistantsClient(model_id="gpt-4o", api_key=get_api_key)

    # Verify client was created successfully
    assert client.model_id == "gpt-4o"
    # OpenAI SDK now manages callable API keys internally
    assert client.client is not None
