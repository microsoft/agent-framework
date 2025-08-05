# Copyright (c) Microsoft. All rights reserved.

import os
from typing import Annotated
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_framework import (
    ChatClient,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    TextContent,
)
from agent_framework.exceptions import ServiceInitializationError
from pydantic import Field

from agent_framework_azure import AzureAssistantsClient

skip_if_azure_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("AZURE_OPENAI_ENDPOINT", "") in ("", "https://test-endpoint.com"),
    reason="No real AZURE_OPENAI_ENDPOINT provided; skipping integration tests."
    if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    else "Integration tests are disabled.",
)


def create_test_azure_assistants_client(
    mock_async_azure_openai: MagicMock,
    deployment_name: str | None = None,
    assistant_id: str | None = None,
    assistant_name: str | None = None,
    thread_id: str | None = None,
    should_delete_assistant: bool = False,
) -> AzureAssistantsClient:
    """Helper function to create AzureAssistantsClient instances for testing, bypassing Pydantic validation."""
    return AzureAssistantsClient.model_construct(
        ai_model_id=deployment_name or "test_chat_deployment",
        assistant_id=assistant_id,
        assistant_name=assistant_name,
        thread_id=thread_id,
        api_key="test-api-key",
        endpoint="https://test-endpoint.com",
        client=mock_async_azure_openai,
        _should_delete_assistant=should_delete_assistant,
    )


@pytest.fixture
def mock_async_azure_openai() -> MagicMock:
    """Mock AsyncAzureOpenAI client."""
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

    # Mock beta.threads.messages
    mock_client.beta.threads.messages.create = AsyncMock()
    mock_client.beta.threads.messages.list = AsyncMock(return_value=MagicMock(data=[]))

    return mock_client


def test_azure_assistants_client_init_with_client(mock_async_azure_openai: MagicMock) -> None:
    """Test AzureAssistantsClient initialization with existing client."""
    chat_client = create_test_azure_assistants_client(
        mock_async_azure_openai,
        deployment_name="test_chat_deployment",
        assistant_id="existing-assistant-id",
        thread_id="test-thread-id",
    )

    assert chat_client.client is mock_async_azure_openai
    assert chat_client.ai_model_id == "test_chat_deployment"
    assert chat_client.assistant_id == "existing-assistant-id"
    assert chat_client.thread_id == "test-thread-id"
    assert not chat_client._should_delete_assistant  # type: ignore
    assert isinstance(chat_client, ChatClient)


def test_azure_assistants_client_init_auto_create_client(
    azure_openai_unit_test_env: dict[str, str],
    mock_async_azure_openai: MagicMock,
) -> None:
    """Test AzureAssistantsClient initialization with auto-created client."""
    chat_client = AzureAssistantsClient.model_construct(
        ai_model_id=azure_openai_unit_test_env["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"],
        assistant_id=None,
        assistant_name="TestAssistant",
        thread_id=None,
        api_key=azure_openai_unit_test_env["AZURE_OPENAI_API_KEY"],
        endpoint=azure_openai_unit_test_env["AZURE_OPENAI_ENDPOINT"],
        client=mock_async_azure_openai,
        _should_delete_assistant=False,
    )

    assert chat_client.client is mock_async_azure_openai
    assert chat_client.ai_model_id == azure_openai_unit_test_env["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"]
    assert chat_client.assistant_id is None
    assert chat_client.assistant_name == "TestAssistant"
    assert not chat_client._should_delete_assistant  # type: ignore


def test_azure_assistants_client_init_validation_fail() -> None:
    """Test AzureAssistantsClient initialization with validation failure."""
    with pytest.raises(ServiceInitializationError):
        # Force failure by providing invalid deployment name type - this should cause validation to fail
        AzureAssistantsClient(deployment_name=123, api_key="valid-key")  # type: ignore


@pytest.mark.parametrize("exclude_list", [["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"]], indirect=True)
def test_azure_assistants_client_init_missing_deployment_name(azure_openai_unit_test_env: dict[str, str]) -> None:
    """Test AzureAssistantsClient initialization with missing deployment name."""
    with pytest.raises(ServiceInitializationError):
        AzureAssistantsClient(
            api_key=azure_openai_unit_test_env.get("AZURE_OPENAI_API_KEY", "test-key"), env_file_path="nonexistent.env"
        )


def test_azure_assistants_client_init_with_default_headers(azure_openai_unit_test_env: dict[str, str]) -> None:
    """Test AzureAssistantsClient initialization with default headers."""
    default_headers = {"X-Unit-Test": "test-guid"}

    chat_client = AzureAssistantsClient(
        deployment_name="test_chat_deployment",
        api_key=azure_openai_unit_test_env["AZURE_OPENAI_API_KEY"],
        endpoint=azure_openai_unit_test_env["AZURE_OPENAI_ENDPOINT"],
        default_headers=default_headers,
    )

    assert chat_client.ai_model_id == "test_chat_deployment"
    assert isinstance(chat_client, ChatClient)

    # Assert that the default header we added is present in the client's default headers
    for key, value in default_headers.items():
        assert key in chat_client.client.default_headers
        assert chat_client.client.default_headers[key] == value


async def test_azure_assistants_client_get_assistant_id_or_create_existing_assistant(
    mock_async_azure_openai: MagicMock,
) -> None:
    """Test _get_assistant_id_or_create when assistant_id is already provided."""
    chat_client = create_test_azure_assistants_client(mock_async_azure_openai, assistant_id="existing-assistant-id")

    assistant_id = await chat_client._get_assistant_id_or_create()  # type: ignore

    assert assistant_id == "existing-assistant-id"
    assert not chat_client._should_delete_assistant  # type: ignore
    mock_async_azure_openai.beta.assistants.create.assert_not_called()


async def test_azure_assistants_client_get_assistant_id_or_create_create_new(
    mock_async_azure_openai: MagicMock,
) -> None:
    """Test _get_assistant_id_or_create when creating a new assistant."""
    chat_client = create_test_azure_assistants_client(
        mock_async_azure_openai, deployment_name="test_chat_deployment", assistant_name="TestAssistant"
    )

    assistant_id = await chat_client._get_assistant_id_or_create()  # type: ignore

    assert assistant_id == "test-assistant-id"
    assert chat_client._should_delete_assistant  # type: ignore
    mock_async_azure_openai.beta.assistants.create.assert_called_once()


async def test_azure_assistants_client_aclose_should_not_delete(
    mock_async_azure_openai: MagicMock,
) -> None:
    """Test close when assistant should not be deleted."""
    chat_client = create_test_azure_assistants_client(
        mock_async_azure_openai, assistant_id="assistant-to-keep", should_delete_assistant=False
    )

    await chat_client.close()  # type: ignore

    # Verify assistant deletion was not called
    mock_async_azure_openai.beta.assistants.delete.assert_not_called()
    assert not chat_client._should_delete_assistant  # type: ignore


async def test_azure_assistants_client_aclose_should_delete(mock_async_azure_openai: MagicMock) -> None:
    """Test close method calls cleanup."""
    chat_client = create_test_azure_assistants_client(
        mock_async_azure_openai, assistant_id="assistant-to-delete", should_delete_assistant=True
    )

    await chat_client.close()

    # Verify assistant deletion was called
    mock_async_azure_openai.beta.assistants.delete.assert_called_once_with("assistant-to-delete")
    assert not chat_client._should_delete_assistant  # type: ignore


async def test_azure_assistants_client_async_context_manager(mock_async_azure_openai: MagicMock) -> None:
    """Test async context manager functionality."""
    chat_client = create_test_azure_assistants_client(
        mock_async_azure_openai, assistant_id="assistant-to-delete", should_delete_assistant=True
    )

    # Test context manager
    async with chat_client:
        pass  # Just test that we can enter and exit

    # Verify cleanup was called on exit
    mock_async_azure_openai.beta.assistants.delete.assert_called_once_with("assistant-to-delete")


def test_azure_assistants_client_serialize(azure_openai_unit_test_env: dict[str, str]) -> None:
    """Test serialization of AzureAssistantsClient."""
    default_headers = {"X-Unit-Test": "test-guid"}

    # Test basic initialization and to_dict
    chat_client = AzureAssistantsClient(
        deployment_name="test_chat_deployment",
        assistant_id="test-assistant-id",
        assistant_name="TestAssistant",
        thread_id="test-thread-id",
        api_key=azure_openai_unit_test_env["AZURE_OPENAI_API_KEY"],
        endpoint=azure_openai_unit_test_env["AZURE_OPENAI_ENDPOINT"],
        default_headers=default_headers,
    )

    dumped_settings = chat_client.to_dict()

    assert dumped_settings["ai_model_id"] == "test_chat_deployment"
    assert dumped_settings["assistant_id"] == "test-assistant-id"
    assert dumped_settings["assistant_name"] == "TestAssistant"
    assert dumped_settings["thread_id"] == "test-thread-id"
    assert dumped_settings["api_key"] == azure_openai_unit_test_env["AZURE_OPENAI_API_KEY"]

    # Assert that the default header we added is present in the dumped_settings default headers
    for key, value in default_headers.items():
        assert key in dumped_settings["default_headers"]
        assert dumped_settings["default_headers"][key] == value
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    return f"The weather in {location} is sunny with a high of 25°C."


@skip_if_azure_integration_tests_disabled
async def test_azure_assistants_client_get_response() -> None:
    """Test Azure Assistants Client response."""
    async with AzureAssistantsClient() as azure_assistants_client:
        assert isinstance(azure_assistants_client, ChatClient)

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
        response = await azure_assistants_client.get_response(messages=messages)

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert any(word in response.text.lower() for word in ["sunny", "25", "weather", "seattle"])


@skip_if_azure_integration_tests_disabled
async def test_azure_assistants_client_get_response_tools() -> None:
    """Test Azure Assistants Client response with tools."""
    async with AzureAssistantsClient() as azure_assistants_client:
        assert isinstance(azure_assistants_client, ChatClient)

        messages: list[ChatMessage] = []
        messages.append(ChatMessage(role="user", text="What's the weather like in Seattle?"))

        # Test that the client can be used to get a response
        response = await azure_assistants_client.get_response(
            messages=messages,
            tools=[get_weather],
            tool_choice="auto",
        )

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert any(word in response.text.lower() for word in ["sunny", "25", "weather"])


@skip_if_azure_integration_tests_disabled
async def test_azure_assistants_client_streaming() -> None:
    """Test Azure Assistants Client streaming response."""
    async with AzureAssistantsClient() as azure_assistants_client:
        assert isinstance(azure_assistants_client, ChatClient)

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
        response = azure_assistants_client.get_streaming_response(messages=messages)

        full_message: str = ""
        async for chunk in response:
            assert chunk is not None
            assert isinstance(chunk, ChatResponseUpdate)
            for content in chunk.contents:
                if isinstance(content, TextContent) and content.text:
                    full_message += content.text

        assert any(word in full_message.lower() for word in ["sunny", "25", "weather", "seattle"])


@skip_if_azure_integration_tests_disabled
async def test_azure_assistants_client_streaming_tools() -> None:
    """Test Azure Assistants Client streaming response with tools."""
    async with AzureAssistantsClient() as azure_assistants_client:
        assert isinstance(azure_assistants_client, ChatClient)

        messages: list[ChatMessage] = []
        messages.append(ChatMessage(role="user", text="What's the weather like in Seattle?"))

        # Test that the client can be used to get a response
        response = azure_assistants_client.get_streaming_response(
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

        assert any(word in full_message.lower() for word in ["sunny", "25", "weather"])


@skip_if_azure_integration_tests_disabled
async def test_azure_assistants_client_with_existing_assistant() -> None:
    """Test Azure Assistants Client with existing assistant ID."""
    # First create an assistant to use in the test
    async with AzureAssistantsClient() as temp_client:
        # Get the assistant ID by triggering assistant creation
        messages = [ChatMessage(role="user", text="Hello")]
        await temp_client.get_response(messages=messages)
        assistant_id = temp_client.assistant_id

        # Now test using the existing assistant
        async with AzureAssistantsClient(assistant_id=assistant_id) as azure_assistants_client:
            assert isinstance(azure_assistants_client, ChatClient)
            assert azure_assistants_client.assistant_id == assistant_id

            messages = [ChatMessage(role="user", text="What can you do?")]

            # Test that the client can be used to get a response
            response = await azure_assistants_client.get_response(messages=messages)

            assert response is not None
            assert isinstance(response, ChatResponse)
            assert len(response.text) > 0
