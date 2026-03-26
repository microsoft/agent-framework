# Copyright (c) Microsoft. All rights reserved.

from typing import Annotated
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import (
    SupportsChatGetResponse,
    tool,
)
from agent_framework._settings import SecretString
from agent_framework.azure import AzureOpenAIAssistantsClient
from pydantic import Field


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
    assert client.model == "test_chat_deployment"
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
    assert client.model == azure_openai_unit_test_env["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"]
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

    assert client.model == "test_chat_deployment"
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

    assert dumped_settings["model"] == "test_chat_deployment"
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


def test_azure_assistants_client_entra_id_authentication() -> None:
    """Test credential authentication path with sync credential."""
    mock_credential = MagicMock()
    mock_provider = MagicMock(return_value="token-string")

    with (
        patch("agent_framework_azure_ai._deprecated_azure_openai.load_settings") as mock_load_settings,
        patch(
            "agent_framework_azure_ai._deprecated_azure_openai.resolve_credential_to_token_provider",
            return_value=mock_provider,
        ) as mock_resolve,
        patch("agent_framework_azure_ai._deprecated_azure_openai.AsyncAzureOpenAI") as mock_azure_client,
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
    with patch("agent_framework_azure_ai._deprecated_azure_openai.load_settings") as mock_load_settings:
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
        patch("agent_framework_azure_ai._deprecated_azure_openai.load_settings") as mock_load_settings,
        patch(
            "agent_framework_azure_ai._deprecated_azure_openai.resolve_credential_to_token_provider",
            return_value=mock_provider,
        ),
        patch("agent_framework_azure_ai._deprecated_azure_openai.AsyncAzureOpenAI") as mock_azure_client,
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
        patch("agent_framework_azure_ai._deprecated_azure_openai.load_settings") as mock_load_settings,
        patch("agent_framework_azure_ai._deprecated_azure_openai.AsyncAzureOpenAI") as mock_azure_client,
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
        patch("agent_framework_azure_ai._deprecated_azure_openai.load_settings") as mock_load_settings,
        patch("agent_framework_azure_ai._deprecated_azure_openai.AsyncAzureOpenAI") as mock_azure_client,
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
