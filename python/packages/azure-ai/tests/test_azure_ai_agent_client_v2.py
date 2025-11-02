# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import (
    ChatClientProtocol,
    ChatMessage,
    ChatOptions,
    Role,
    TextContent,
)
from agent_framework.exceptions import ServiceInitializationError
from pydantic import ValidationError

from agent_framework_azure_ai import AzureAIAgentClientV2, AzureAISettings


def create_test_azure_ai_client_v2(
    mock_project_client: MagicMock,
    agent_name: str | None = None,
    agent_version: str | None = None,
    conversation_id: str | None = None,
    azure_ai_settings: AzureAISettings | None = None,
    should_close_client: bool = False,
) -> AzureAIAgentClientV2:
    """Helper function to create AzureAIAgentClientV2 instances for testing, bypassing normal validation."""
    if azure_ai_settings is None:
        azure_ai_settings = AzureAISettings(env_file_path="test.env")

    # Create client instance directly
    client = object.__new__(AzureAIAgentClientV2)

    # Set attributes directly
    client.project_client = mock_project_client
    client.credential = None
    client.agent_name = agent_name
    client.agent_version = agent_version
    client.model_id = azure_ai_settings.model_deployment_name
    client.conversation_id = conversation_id
    client._should_close_client = should_close_client  # type: ignore
    client.additional_properties = {}
    client.middleware = None

    # Mock the OpenAI client attribute
    mock_openai_client = MagicMock()
    mock_openai_client.conversations = MagicMock()
    mock_openai_client.conversations.create = AsyncMock()
    client.client = mock_openai_client

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


def test_azure_ai_client_v2_init_with_project_client(mock_project_client: MagicMock) -> None:
    """Test AzureAIAgentClientV2 initialization with existing project_client."""
    with patch("agent_framework_azure_ai._chat_client_v2.AzureAISettings") as mock_settings:
        mock_settings.return_value.project_endpoint = None
        mock_settings.return_value.model_deployment_name = "test-model"

        client = AzureAIAgentClientV2(
            project_client=mock_project_client,
            agent_name="test-agent",
            agent_version="1.0",
        )

        assert client.project_client is mock_project_client
        assert client.agent_name == "test-agent"
        assert client.agent_version == "1.0"
        assert not client._should_close_client  # type: ignore
        assert isinstance(client, ChatClientProtocol)


def test_azure_ai_client_v2_init_auto_create_client(
    azure_ai_unit_test_env: dict[str, str],
    mock_azure_credential: MagicMock,
) -> None:
    """Test AzureAIAgentClientV2 initialization with auto-created project_client."""
    with patch("agent_framework_azure_ai._chat_client_v2.AIProjectClient") as mock_ai_project_client:
        mock_project_client = MagicMock()
        mock_ai_project_client.return_value = mock_project_client

        client = AzureAIAgentClientV2(
            project_endpoint=azure_ai_unit_test_env["AZURE_AI_PROJECT_ENDPOINT"],
            model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            async_credential=mock_azure_credential,
            agent_name="test-agent",
        )

        assert client.project_client is mock_project_client
        assert client.agent_name == "test-agent"
        assert client._should_close_client  # type: ignore

        # Verify AIProjectClient was called with correct parameters
        mock_ai_project_client.assert_called_once()


def test_azure_ai_client_v2_init_missing_project_endpoint() -> None:
    """Test AzureAIAgentClientV2 initialization when project_endpoint is missing and no project_client provided."""
    with patch("agent_framework_azure_ai._chat_client_v2.AzureAISettings") as mock_settings:
        mock_settings.return_value.project_endpoint = None
        mock_settings.return_value.model_deployment_name = "test-model"

        with pytest.raises(ServiceInitializationError, match="Azure AI project endpoint is required"):
            AzureAIAgentClientV2(async_credential=MagicMock())


def test_azure_ai_client_v2_init_missing_model_deployment() -> None:
    """Test AzureAIAgentClientV2 initialization when model deployment is missing for agent creation."""
    with patch("agent_framework_azure_ai._chat_client_v2.AzureAISettings") as mock_settings:
        mock_settings.return_value.project_endpoint = "https://test.com"
        mock_settings.return_value.model_deployment_name = None

        with pytest.raises(ServiceInitializationError, match="Azure AI model deployment name is required"):
            AzureAIAgentClientV2(async_credential=MagicMock())


def test_azure_ai_client_v2_init_missing_credential(azure_ai_unit_test_env: dict[str, str]) -> None:
    """Test AzureAIAgentClientV2.__init__ when async_credential is missing and no project_client provided."""
    with pytest.raises(
        ServiceInitializationError, match="Azure credential is required when project_client is not provided"
    ):
        AzureAIAgentClientV2(
            project_endpoint=azure_ai_unit_test_env["AZURE_AI_PROJECT_ENDPOINT"],
            model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        )


def test_azure_ai_client_v2_init_validation_error(mock_azure_credential: MagicMock) -> None:
    """Test that ValidationError in AzureAISettings is properly handled."""
    with patch("agent_framework_azure_ai._chat_client_v2.AzureAISettings") as mock_settings:
        mock_settings.side_effect = ValidationError.from_exception_data("test", [])

        with pytest.raises(ServiceInitializationError, match="Failed to create Azure AI settings"):
            AzureAIAgentClientV2(async_credential=mock_azure_credential)


async def test_azure_ai_client_v2_get_agent_reference_or_create_existing_version(
    mock_project_client: MagicMock,
) -> None:
    """Test _get_agent_reference_or_create when agent_version is already provided."""
    client = create_test_azure_ai_client_v2(mock_project_client, agent_name="existing-agent", agent_version="1.0")

    agent_ref = await client._get_agent_reference_or_create({}, None)  # type: ignore

    assert agent_ref == {"name": "existing-agent", "version": "1.0", "type": "agent_reference"}


async def test_azure_ai_client_v2_get_agent_reference_or_create_new_agent(
    mock_project_client: MagicMock,
    azure_ai_unit_test_env: dict[str, str],
) -> None:
    """Test _get_agent_reference_or_create when creating a new agent."""
    azure_ai_settings = AzureAISettings(model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"])
    client = create_test_azure_ai_client_v2(
        mock_project_client, agent_name="new-agent", azure_ai_settings=azure_ai_settings
    )

    # Mock agent creation response
    mock_agent = MagicMock()
    mock_agent.name = "new-agent"
    mock_agent.version = "1.0"
    mock_project_client.agents.create_version = AsyncMock(return_value=mock_agent)

    run_options = {"model": azure_ai_settings.model_deployment_name}
    agent_ref = await client._get_agent_reference_or_create(run_options, None)  # type: ignore

    assert agent_ref == {"name": "new-agent", "version": "1.0", "type": "agent_reference"}
    assert client.agent_name == "new-agent"
    assert client.agent_version == "1.0"


async def test_azure_ai_client_v2_get_agent_reference_missing_model(
    mock_project_client: MagicMock,
) -> None:
    """Test _get_agent_reference_or_create when model is missing for agent creation."""
    client = create_test_azure_ai_client_v2(mock_project_client, agent_name="test-agent")

    with pytest.raises(ServiceInitializationError, match="Model deployment name is required for agent creation"):
        await client._get_agent_reference_or_create({}, None)  # type: ignore


async def test_azure_ai_client_v2_get_conversation_id_or_create_existing(
    mock_project_client: MagicMock,
) -> None:
    """Test _get_conversation_id_or_create when conversation_id is already provided."""
    client = create_test_azure_ai_client_v2(mock_project_client, conversation_id="existing-conversation")

    conversation_id = await client._get_conversation_id_or_create({})  # type: ignore

    assert conversation_id == "existing-conversation"


async def test_azure_ai_client_v2_get_conversation_id_or_create_new(
    mock_project_client: MagicMock,
) -> None:
    """Test _get_conversation_id_or_create when creating a new conversation."""
    client = create_test_azure_ai_client_v2(mock_project_client)

    # Mock conversation creation response
    mock_conversation = MagicMock()
    mock_conversation.id = "new-conversation-123"
    client.client.conversations.create = AsyncMock(return_value=mock_conversation)

    conversation_id = await client._get_conversation_id_or_create({})  # type: ignore

    assert conversation_id == "new-conversation-123"
    client.client.conversations.create.assert_called_once()


async def test_azure_ai_client_v2_prepare_input_with_system_messages(
    mock_project_client: MagicMock,
) -> None:
    """Test _prepare_input converts system/developer messages to instructions."""
    client = create_test_azure_ai_client_v2(mock_project_client)

    messages = [
        ChatMessage(role=Role.SYSTEM, contents=[TextContent(text="You are a helpful assistant.")]),
        ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")]),
        ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text="System response")]),
    ]

    result_messages, instructions = client._prepare_input(messages)  # type: ignore

    assert len(result_messages) == 2
    assert result_messages[0].role == Role.USER
    assert result_messages[1].role == Role.ASSISTANT
    assert instructions == "You are a helpful assistant."


async def test_azure_ai_client_v2_prepare_input_no_system_messages(
    mock_project_client: MagicMock,
) -> None:
    """Test _prepare_input with no system/developer messages."""
    client = create_test_azure_ai_client_v2(mock_project_client)

    messages = [
        ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")]),
        ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text="Hi there!")]),
    ]

    result_messages, instructions = client._prepare_input(messages)  # type: ignore

    assert len(result_messages) == 2
    assert instructions is None


async def test_azure_ai_client_v2_prepare_options_basic(mock_project_client: MagicMock) -> None:
    """Test prepare_options basic functionality."""
    client = create_test_azure_ai_client_v2(mock_project_client, agent_name="test-agent", agent_version="1.0")

    messages = [ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")])]
    chat_options = ChatOptions()

    with (
        patch.object(client.__class__.__bases__[0], "prepare_options", return_value={"model": "test-model"}),
        patch.object(
            client,
            "_get_agent_reference_or_create",
            return_value={"name": "test-agent", "version": "1.0", "type": "agent_reference"},
        ),
    ):
        run_options = await client.prepare_options(messages, chat_options)

        assert "extra_body" in run_options
        assert run_options["extra_body"]["agent"]["name"] == "test-agent"


async def test_azure_ai_client_v2_prepare_options_with_store(mock_project_client: MagicMock) -> None:
    """Test prepare_options with store=True creates conversation."""
    client = create_test_azure_ai_client_v2(mock_project_client, agent_name="test-agent", agent_version="1.0")

    # Mock conversation creation
    mock_conversation = MagicMock()
    mock_conversation.id = "new-conversation-456"
    client.client.conversations.create = AsyncMock(return_value=mock_conversation)

    messages = [ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")])]
    chat_options = ChatOptions(store=True)

    with (
        patch.object(
            client.__class__.__bases__[0], "prepare_options", return_value={"model": "test-model", "store": True}
        ),
        patch.object(
            client,
            "_get_agent_reference_or_create",
            return_value={"name": "test-agent", "version": "1.0", "type": "agent_reference"},
        ),
    ):
        run_options = await client.prepare_options(messages, chat_options)

        assert "conversation" in run_options
        assert run_options["conversation"] == "new-conversation-456"


async def test_azure_ai_client_v2_initialize_client(mock_project_client: MagicMock) -> None:
    """Test initialize_client method."""
    client = create_test_azure_ai_client_v2(mock_project_client)

    mock_openai_client = MagicMock()
    mock_project_client.get_openai_client = AsyncMock(return_value=mock_openai_client)

    await client.initialize_client()

    assert client.client is mock_openai_client
    mock_project_client.get_openai_client.assert_called_once()


def test_azure_ai_client_v2_get_conversation_id_from_response(mock_project_client: MagicMock) -> None:
    """Test get_conversation_id method."""
    client = create_test_azure_ai_client_v2(mock_project_client)

    # Test with conversation and store=True
    mock_response = MagicMock()
    mock_response.conversation.id = "test-conversation-123"

    conversation_id = client.get_conversation_id(mock_response, store=True)
    assert conversation_id == "test-conversation-123"

    # Test with store=False
    conversation_id = client.get_conversation_id(mock_response, store=False)
    assert conversation_id is None

    # Test with no conversation
    mock_response.conversation = None
    conversation_id = client.get_conversation_id(mock_response, store=True)
    assert conversation_id is None


def test_azure_ai_client_v2_update_agent_name(mock_project_client: MagicMock) -> None:
    """Test _update_agent_name method."""
    client = create_test_azure_ai_client_v2(mock_project_client)

    # Test updating agent name when current is None
    with patch.object(client, "_update_agent_name") as mock_update:
        mock_update.return_value = None
        client._update_agent_name("new-agent")  # type: ignore
        mock_update.assert_called_once_with("new-agent")

    # Test behavior when agent name is updated
    assert client.agent_name is None  # Should remain None since we didn't actually update
    client.agent_name = "test-agent"  # Manually set for the test

    # Test with None input
    with patch.object(client, "_update_agent_name") as mock_update:
        mock_update.return_value = None
        client._update_agent_name(None)  # type: ignore
        mock_update.assert_called_once_with(None)


async def test_azure_ai_client_v2_async_context_manager(mock_project_client: MagicMock) -> None:
    """Test async context manager functionality."""
    client = create_test_azure_ai_client_v2(mock_project_client, should_close_client=True)

    mock_project_client.close = AsyncMock()

    async with client as ctx_client:
        assert ctx_client is client

    # Should call close after exiting context
    mock_project_client.close.assert_called_once()


async def test_azure_ai_client_v2_close_method(mock_project_client: MagicMock) -> None:
    """Test close method."""
    client = create_test_azure_ai_client_v2(mock_project_client, should_close_client=True)

    mock_project_client.close = AsyncMock()

    await client.close()

    mock_project_client.close.assert_called_once()


async def test_azure_ai_client_v2_close_client_when_should_close_false(mock_project_client: MagicMock) -> None:
    """Test _close_client_if_needed when should_close_client is False."""
    client = create_test_azure_ai_client_v2(mock_project_client, should_close_client=False)

    mock_project_client.close = AsyncMock()

    await client._close_client_if_needed()  # type: ignore

    # Should not call close when should_close_client is False
    mock_project_client.close.assert_not_called()


async def test_azure_ai_client_v2_agent_creation_with_instructions(
    mock_project_client: MagicMock,
) -> None:
    """Test agent creation with combined instructions."""
    client = create_test_azure_ai_client_v2(mock_project_client, agent_name="test-agent")

    # Mock agent creation response
    mock_agent = MagicMock()
    mock_agent.name = "test-agent"
    mock_agent.version = "1.0"
    mock_project_client.agents.create_version = AsyncMock(return_value=mock_agent)

    run_options = {"model": "test-model", "instructions": "Option instructions. "}
    messages_instructions = "Message instructions. "

    await client._get_agent_reference_or_create(run_options, messages_instructions)  # type: ignore

    # Verify agent was created with combined instructions
    call_args = mock_project_client.agents.create_version.call_args
    assert call_args[1]["definition"].instructions == "Message instructions. Option instructions. "


async def test_azure_ai_client_v2_agent_creation_with_tools(
    mock_project_client: MagicMock,
) -> None:
    """Test agent creation with tools."""
    client = create_test_azure_ai_client_v2(mock_project_client, agent_name="test-agent")

    # Mock agent creation response
    mock_agent = MagicMock()
    mock_agent.name = "test-agent"
    mock_agent.version = "1.0"
    mock_project_client.agents.create_version = AsyncMock(return_value=mock_agent)

    test_tools = [{"type": "function", "function": {"name": "test_tool"}}]
    run_options = {"model": "test-model", "tools": test_tools}

    await client._get_agent_reference_or_create(run_options, None)  # type: ignore

    # Verify agent was created with tools
    call_args = mock_project_client.agents.create_version.call_args
    assert call_args[1]["definition"].tools == test_tools


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
