# Copyright (c) Microsoft. All rights reserved.

import os
from typing import Annotated
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from azure.identity import AzureCliCredential
from pydantic import Field

from agent_framework import (
    Agent,
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    ChatResponse,
    ChatResponseUpdate,
    Message,
    SupportsChatGetResponse,
    tool,
)
from agent_framework._settings import SecretString
from agent_framework.azure import AzureOpenAIAssistantsClient

skip_if_azure_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("AZURE_OPENAI_ENDPOINT", "") in ("", "https://test-endpoint.com"),
    reason="No real AZURE_OPENAI_ENDPOINT provided; skipping integration tests.",
)


def create_test_azure_assistants_client(
    mock_async_azure_openai: MagicMock,
    deployment_name: str | None = None,
    assistant_id: str | None = None,
    assistant_name: str | None = None,
    thread_id: str | None = None,
    should_delete_assistant: bool = False,
) -> AzureOpenAIAssistantsClient:
    """Helper function to create AzureOpenAIAssistantsClient instances for testing."""
    client = AzureOpenAIAssistantsClient(
        deployment_name=deployment_name or "test_chat_deployment",
        assistant_id=assistant_id,
        assistant_name=assistant_name,
        thread_id=thread_id,
        api_key="test-api-key",
        endpoint="https://test-endpoint.com",
        async_client=mock_async_azure_openai,
    )
    # Set the _should_delete_assistant flag directly if needed
    if should_delete_assistant:
        object.__setattr__(client, "_should_delete_assistant", True)
    return client


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
    """Test AzureOpenAIAssistantsClient initialization with existing client."""
    client = create_test_azure_assistants_client(
        mock_async_azure_openai,
        deployment_name="test_chat_deployment",
        assistant_id="existing-assistant-id",
        thread_id="test-thread-id",
    )

    assert client.client is mock_async_azure_openai
    assert client.model_id == "test_chat_deployment"
    assert client.assistant_id == "existing-assistant-id"
    assert client.thread_id == "test-thread-id"
    assert not client._should_delete_assistant  # type: ignore
    assert isinstance(client, SupportsChatGetResponse)


def test_azure_assistants_client_init_auto_create_client(
    azure_openai_unit_test_env: dict[str, str],
    mock_async_azure_openai: MagicMock,
) -> None:
    """Test AzureOpenAIAssistantsClient initialization with auto-created client."""
    client = AzureOpenAIAssistantsClient(
        deployment_name=azure_openai_unit_test_env["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"],
        assistant_name="TestAssistant",
        api_key=azure_openai_unit_test_env["AZURE_OPENAI_API_KEY"],
        endpoint=azure_openai_unit_test_env["AZURE_OPENAI_ENDPOINT"],
        async_client=mock_async_azure_openai,
    )

    assert client.client is mock_async_azure_openai
    assert client.model_id == azure_openai_unit_test_env["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"]
    assert client.assistant_id is None
    assert client.assistant_name == "TestAssistant"
    assert not client._should_delete_assistant  # type: ignore


def test_azure_assistants_client_init_validation_fail() -> None:
    """Test AzureOpenAIAssistantsClient initialization with validation failure."""
    with pytest.raises(ValueError):
        # Force failure by providing invalid deployment name type - this should cause validation to fail
        AzureOpenAIAssistantsClient(deployment_name=123, api_key="valid-key")  # type: ignore


@pytest.mark.parametrize("exclude_list", [["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"]], indirect=True)
def test_azure_assistants_client_init_missing_deployment_name(azure_openai_unit_test_env: dict[str, str]) -> None:
    """Test AzureOpenAIAssistantsClient initialization with missing deployment name."""
    with pytest.raises(ValueError):
        AzureOpenAIAssistantsClient(api_key=azure_openai_unit_test_env.get("AZURE_OPENAI_API_KEY", "test-key"))


def test_azure_assistants_client_init_with_default_headers(azure_openai_unit_test_env: dict[str, str]) -> None:
    """Test AzureOpenAIAssistantsClient initialization with default headers."""
    default_headers = {"X-Unit-Test": "test-guid"}

    client = AzureOpenAIAssistantsClient(
        deployment_name="test_chat_deployment",
        api_key=azure_openai_unit_test_env["AZURE_OPENAI_API_KEY"],
        endpoint=azure_openai_unit_test_env["AZURE_OPENAI_ENDPOINT"],
        default_headers=default_headers,
    )

    assert client.model_id == "test_chat_deployment"
    assert isinstance(client, SupportsChatGetResponse)

    # Assert that the default header we added is present in the client's default headers
    for key, value in default_headers.items():
        assert key in client.client.default_headers
        assert client.client.default_headers[key] == value


async def test_azure_assistants_client_get_assistant_id_or_create_existing_assistant(
    mock_async_azure_openai: MagicMock,
) -> None:
    """Test _get_assistant_id_or_create when assistant_id is already provided."""
    client = create_test_azure_assistants_client(mock_async_azure_openai, assistant_id="existing-assistant-id")

    assistant_id = await client._get_assistant_id_or_create()  # type: ignore

    assert assistant_id == "existing-assistant-id"
    assert not client._should_delete_assistant  # type: ignore
    mock_async_azure_openai.beta.assistants.create.assert_not_called()


async def test_azure_assistants_client_get_assistant_id_or_create_create_new(
    mock_async_azure_openai: MagicMock,
) -> None:
    """Test _get_assistant_id_or_create when creating a new assistant."""
    client = create_test_azure_assistants_client(
        mock_async_azure_openai, deployment_name="test_chat_deployment", assistant_name="TestAssistant"
    )

    assistant_id = await client._get_assistant_id_or_create()  # type: ignore

    assert assistant_id == "test-assistant-id"
    assert client._should_delete_assistant  # type: ignore
    mock_async_azure_openai.beta.assistants.create.assert_called_once()


async def test_azure_assistants_client_aclose_should_not_delete(
    mock_async_azure_openai: MagicMock,
) -> None:
    """Test close when assistant should not be deleted."""
    client = create_test_azure_assistants_client(
        mock_async_azure_openai, assistant_id="assistant-to-keep", should_delete_assistant=False
    )

    await client.close()  # type: ignore

    # Verify assistant deletion was not called
    mock_async_azure_openai.beta.assistants.delete.assert_not_called()
    assert not client._should_delete_assistant  # type: ignore


async def test_azure_assistants_client_aclose_should_delete(mock_async_azure_openai: MagicMock) -> None:
    """Test close method calls cleanup."""
    client = create_test_azure_assistants_client(
        mock_async_azure_openai, assistant_id="assistant-to-delete", should_delete_assistant=True
    )

    await client.close()

    # Verify assistant deletion was called
    mock_async_azure_openai.beta.assistants.delete.assert_called_once_with("assistant-to-delete")
    assert not client._should_delete_assistant  # type: ignore


async def test_azure_assistants_client_async_context_manager(mock_async_azure_openai: MagicMock) -> None:
    """Test async context manager functionality."""
    client = create_test_azure_assistants_client(
        mock_async_azure_openai, assistant_id="assistant-to-delete", should_delete_assistant=True
    )

    # Test context manager
    async with client:
        pass  # Just test that we can enter and exit

    # Verify cleanup was called on exit
    mock_async_azure_openai.beta.assistants.delete.assert_called_once_with("assistant-to-delete")


def test_azure_assistants_client_serialize(azure_openai_unit_test_env: dict[str, str]) -> None:
    """Test serialization of AzureOpenAIAssistantsClient."""
    default_headers = {"X-Unit-Test": "test-guid"}

    # Test basic initialization and to_dict
    client = AzureOpenAIAssistantsClient(
        deployment_name="test_chat_deployment",
        assistant_id="test-assistant-id",
        assistant_name="TestAssistant",
        thread_id="test-thread-id",
        api_key=azure_openai_unit_test_env["AZURE_OPENAI_API_KEY"],
        endpoint=azure_openai_unit_test_env["AZURE_OPENAI_ENDPOINT"],
        default_headers=default_headers,
    )

    dumped_settings = client.to_dict()

    assert dumped_settings["model_id"] == "test_chat_deployment"
    assert dumped_settings["assistant_id"] == "test-assistant-id"
    assert dumped_settings["assistant_name"] == "TestAssistant"
    assert dumped_settings["thread_id"] == "test-thread-id"

    # Assert that the default header we added is present in the dumped_settings default headers
    for key, value in default_headers.items():
        assert key in dumped_settings["default_headers"]
        assert dumped_settings["default_headers"][key] == value
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]


@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    return f"The weather in {location} is sunny with a high of 25°C."


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_azure_assistants_client_get_response() -> None:
    """Test Azure Assistants Client response."""
    async with AzureOpenAIAssistantsClient(credential=AzureCliCredential()) as azure_assistants_client:
        assert isinstance(azure_assistants_client, SupportsChatGetResponse)

        messages: list[Message] = []
        messages.append(
            Message(
                role="user",
                text="The weather in Seattle is currently sunny with a high of 25°C. "
                "It's a beautiful day for outdoor activities.",
            )
        )
        messages.append(Message(role="user", text="What's the weather like today?"))

        # Test that the client can be used to get a response
        response = await azure_assistants_client.get_response(messages=messages)

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert any(word in response.text.lower() for word in ["sunny", "25", "weather", "seattle"])


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_azure_assistants_client_get_response_tools() -> None:
    """Test Azure Assistants Client response with tools."""
    async with AzureOpenAIAssistantsClient(credential=AzureCliCredential()) as azure_assistants_client:
        assert isinstance(azure_assistants_client, SupportsChatGetResponse)

        messages: list[Message] = []
        messages.append(Message(role="user", text="What's the weather like in Seattle?"))

        # Test that the client can be used to get a response
        response = await azure_assistants_client.get_response(
            messages=messages,
            options={"tools": [get_weather], "tool_choice": "auto"},
        )

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert any(word in response.text.lower() for word in ["sunny", "25", "weather"])


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_azure_assistants_client_streaming() -> None:
    """Test Azure Assistants Client streaming response."""
    async with AzureOpenAIAssistantsClient(credential=AzureCliCredential()) as azure_assistants_client:
        assert isinstance(azure_assistants_client, SupportsChatGetResponse)

        messages: list[Message] = []
        messages.append(
            Message(
                role="user",
                text="The weather in Seattle is currently sunny with a high of 25°C. "
                "It's a beautiful day for outdoor activities.",
            )
        )
        messages.append(Message(role="user", text="What's the weather like today?"))

        # Test that the client can be used to get a response
        response = azure_assistants_client.get_response(messages=messages, stream=True)

        full_message: str = ""
        async for chunk in response:
            assert chunk is not None
            assert isinstance(chunk, ChatResponseUpdate)
            for content in chunk.contents:
                if content.type == "text" and content.text:
                    full_message += content.text

        assert any(word in full_message.lower() for word in ["sunny", "25", "weather", "seattle"])


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_azure_assistants_client_streaming_tools() -> None:
    """Test Azure Assistants Client streaming response with tools."""
    async with AzureOpenAIAssistantsClient(credential=AzureCliCredential()) as azure_assistants_client:
        assert isinstance(azure_assistants_client, SupportsChatGetResponse)

        messages: list[Message] = []
        messages.append(Message(role="user", text="What's the weather like in Seattle?"))

        # Test that the client can be used to get a response
        response = azure_assistants_client.get_response(
            messages=messages,
            options={"tools": [get_weather], "tool_choice": "auto"},
            stream=True,
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
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_azure_assistants_client_with_existing_assistant() -> None:
    """Test Azure Assistants Client with existing assistant ID."""
    # First create an assistant to use in the test
    async with AzureOpenAIAssistantsClient(credential=AzureCliCredential()) as temp_client:
        # Get the assistant ID by triggering assistant creation
        messages = [Message(role="user", text="Hello")]
        await temp_client.get_response(messages=messages)
        assistant_id = temp_client.assistant_id

        # Now test using the existing assistant
        async with AzureOpenAIAssistantsClient(
            assistant_id=assistant_id, credential=AzureCliCredential()
        ) as azure_assistants_client:
            assert isinstance(azure_assistants_client, SupportsChatGetResponse)
            assert azure_assistants_client.assistant_id == assistant_id

            messages = [Message(role="user", text="What can you do?")]

            # Test that the client can be used to get a response
            response = await azure_assistants_client.get_response(messages=messages)

            assert response is not None
            assert isinstance(response, ChatResponse)
            assert len(response.text) > 0


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_azure_assistants_agent_basic_run():
    """Test Agent basic run functionality with AzureOpenAIAssistantsClient."""
    async with Agent(
        client=AzureOpenAIAssistantsClient(credential=AzureCliCredential()),
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
@skip_if_azure_integration_tests_disabled
async def test_azure_assistants_agent_basic_run_streaming():
    """Test Agent basic streaming functionality with AzureOpenAIAssistantsClient."""
    async with Agent(
        client=AzureOpenAIAssistantsClient(credential=AzureCliCredential()),
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
@skip_if_azure_integration_tests_disabled
async def test_azure_assistants_agent_session_persistence():
    """Test Agent session persistence across runs with AzureOpenAIAssistantsClient."""
    async with Agent(
        client=AzureOpenAIAssistantsClient(credential=AzureCliCredential()),
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

        # Verify session has been populated with conversation ID
        assert session.service_session_id is not None


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_azure_assistants_agent_existing_session_id():
    """Test Agent with existing session ID to continue conversations across agent instances."""
    # First, create a conversation and capture the session ID
    existing_session_id = None

    async with Agent(
        client=AzureOpenAIAssistantsClient(credential=AzureCliCredential()),
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    ) as agent:
        # Start a conversation and get the session ID
        session = agent.create_session()
        response1 = await agent.run("What's the weather in Paris?", session=session)

        # Validate first response
        assert isinstance(response1, AgentResponse)
        assert response1.text is not None
        assert any(word in response1.text.lower() for word in ["weather", "paris"])

        # The session ID is set after the first response
        existing_session_id = session.service_session_id
        assert existing_session_id is not None

    # Now continue with the same session ID in a new agent instance

    async with Agent(
        client=AzureOpenAIAssistantsClient(thread_id=existing_session_id, credential=AzureCliCredential()),
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    ) as agent:
        # Create a session with the existing ID
        session = AgentSession(service_session_id=existing_session_id)

        # Ask about the previous conversation
        response2 = await agent.run("What was the last city I asked about?", session=session)

        # Validate that the agent remembers the previous conversation
        assert isinstance(response2, AgentResponse)
        assert response2.text is not None
        # Should reference Paris from the previous conversation
        assert "paris" in response2.text.lower()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_azure_assistants_agent_code_interpreter():
    """Test Agent with code interpreter through AzureOpenAIAssistantsClient."""

    async with Agent(
        client=AzureOpenAIAssistantsClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant that can write and execute Python code.",
        tools=[AzureOpenAIAssistantsClient.get_code_interpreter_tool()],
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
@skip_if_azure_integration_tests_disabled
async def test_azure_assistants_client_agent_level_tool_persistence():
    """Test that agent-level tools persist across multiple runs with Azure Assistants Client."""

    async with Agent(
        client=AzureOpenAIAssistantsClient(credential=AzureCliCredential()),
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


def test_azure_assistants_client_entra_id_authentication() -> None:
    """Test credential authentication path with sync credential."""
    mock_credential = MagicMock()
    mock_provider = MagicMock(return_value="token-string")

    with (
        patch("agent_framework.azure._assistants_client.load_settings") as mock_load_settings,
        patch(
            "agent_framework.azure._assistants_client.resolve_credential_to_token_provider",
            return_value=mock_provider,
        ) as mock_resolve,
        patch("agent_framework.azure._assistants_client.AsyncAzureOpenAI") as mock_azure_client,
        patch("agent_framework.openai.OpenAIAssistantsClient.__init__", return_value=None),
    ):
        mock_load_settings.return_value = {
            "chat_deployment_name": "test-deployment",
            "responses_deployment_name": None,
            "api_key": None,
            "token_endpoint": "https://cognitiveservices.azure.com/.default",
            "api_version": "2024-05-01-preview",
            "endpoint": "https://test-endpoint.openai.azure.com",
            "base_url": None,
        }

        client = AzureOpenAIAssistantsClient(
            deployment_name="test-deployment",
            endpoint="https://test-endpoint.openai.azure.com",
            credential=mock_credential,
            token_endpoint="https://cognitiveservices.azure.com/.default",
        )

        # Verify credential was resolved to a token provider
        mock_resolve.assert_called_once_with(mock_credential, "https://cognitiveservices.azure.com/.default")

        # Verify client was created with the token provider
        mock_azure_client.assert_called_once()
        call_args = mock_azure_client.call_args[1]
        assert call_args["azure_ad_token_provider"] is mock_provider

        assert client is not None
        assert isinstance(client, AzureOpenAIAssistantsClient)


def test_azure_assistants_client_no_authentication_error() -> None:
    """Test authentication validation error when no auth provided."""
    with patch("agent_framework.azure._assistants_client.load_settings") as mock_load_settings:
        mock_load_settings.return_value = {
            "chat_deployment_name": "test-deployment",
            "responses_deployment_name": None,
            "api_key": None,
            "token_endpoint": None,
            "api_version": "2024-05-01-preview",
            "endpoint": "https://test-endpoint.openai.azure.com",
            "base_url": None,
        }

        # Test missing authentication raises error
        with pytest.raises(ValueError, match="api_key, credential, or a client"):
            AzureOpenAIAssistantsClient(
                deployment_name="test-deployment",
                endpoint="https://test-endpoint.openai.azure.com",
                # No authentication provided at all
            )


def test_azure_assistants_client_callable_credential() -> None:
    """Test callable token provider as credential."""
    mock_provider = MagicMock(return_value="my-token")

    with (
        patch("agent_framework.azure._assistants_client.load_settings") as mock_load_settings,
        patch(
            "agent_framework.azure._assistants_client.resolve_credential_to_token_provider",
            return_value=mock_provider,
        ),
        patch("agent_framework.azure._assistants_client.AsyncAzureOpenAI") as mock_azure_client,
        patch("agent_framework.openai.OpenAIAssistantsClient.__init__", return_value=None),
    ):
        mock_load_settings.return_value = {
            "chat_deployment_name": "test-deployment",
            "responses_deployment_name": None,
            "api_key": None,
            "token_endpoint": "https://cognitiveservices.azure.com/.default",
            "api_version": "2024-05-01-preview",
            "endpoint": "https://test-endpoint.openai.azure.com",
            "base_url": None,
        }

        client = AzureOpenAIAssistantsClient(
            deployment_name="test-deployment",
            endpoint="https://test-endpoint.openai.azure.com",
            credential=mock_provider,
            token_endpoint="https://cognitiveservices.azure.com/.default",
        )

        # Verify client was created with the token provider
        mock_azure_client.assert_called_once()
        call_args = mock_azure_client.call_args[1]
        assert call_args["azure_ad_token_provider"] is mock_provider

        assert client is not None
        assert isinstance(client, AzureOpenAIAssistantsClient)


def test_azure_assistants_client_base_url_configuration() -> None:
    """Test base_url client parameter path."""
    with (
        patch("agent_framework.azure._assistants_client.load_settings") as mock_load_settings,
        patch("agent_framework.azure._assistants_client.AsyncAzureOpenAI") as mock_azure_client,
        patch("agent_framework.openai.OpenAIAssistantsClient.__init__", return_value=None),
    ):
        mock_load_settings.return_value = {
            "chat_deployment_name": "test-deployment",
            "responses_deployment_name": None,
            "api_key": SecretString("test-api-key"),
            "token_endpoint": None,
            "api_version": "2024-05-01-preview",
            "endpoint": None,
            "base_url": "https://custom-base-url.com",
        }

        client = AzureOpenAIAssistantsClient(
            deployment_name="test-deployment", api_key="test-api-key", base_url="https://custom-base-url.com"
        )

        # base_url path
        mock_azure_client.assert_called_once()
        call_args = mock_azure_client.call_args[1]
        assert call_args["base_url"] == "https://custom-base-url.com"
        assert "azure_endpoint" not in call_args

        assert client is not None
        assert isinstance(client, AzureOpenAIAssistantsClient)


def test_azure_assistants_client_azure_endpoint_configuration() -> None:
    """Test azure_endpoint client parameter path."""
    with (
        patch("agent_framework.azure._assistants_client.load_settings") as mock_load_settings,
        patch("agent_framework.azure._assistants_client.AsyncAzureOpenAI") as mock_azure_client,
        patch("agent_framework.openai.OpenAIAssistantsClient.__init__", return_value=None),
    ):
        mock_load_settings.return_value = {
            "chat_deployment_name": "test-deployment",
            "responses_deployment_name": None,
            "api_key": SecretString("test-api-key"),
            "token_endpoint": None,
            "api_version": "2024-05-01-preview",
            "endpoint": "https://test-endpoint.openai.azure.com",
            "base_url": None,
        }

        client = AzureOpenAIAssistantsClient(
            deployment_name="test-deployment",
            api_key="test-api-key",
            endpoint="https://test-endpoint.openai.azure.com",
        )

        # azure_endpoint path
        mock_azure_client.assert_called_once()
        call_args = mock_azure_client.call_args[1]
        assert call_args["azure_endpoint"] == "https://test-endpoint.openai.azure.com"
        assert "base_url" not in call_args

        assert client is not None
        assert isinstance(client, AzureOpenAIAssistantsClient)
