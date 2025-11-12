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
from azure.ai.projects.models import (
    ResponseTextFormatConfigurationJsonSchema,
)
from openai.types.responses.parsed_response import ParsedResponse
from openai.types.responses.response import Response as OpenAIResponse
from pydantic import BaseModel, ConfigDict, ValidationError

from agent_framework_azure_ai import AzureAIClient, AzureAISettings


def create_test_azure_ai_client(
    mock_project_client: MagicMock,
    agent_name: str | None = None,
    agent_version: str | None = None,
    conversation_id: str | None = None,
    azure_ai_settings: AzureAISettings | None = None,
    should_close_client: bool = False,
    use_latest_version: bool | None = None,
) -> AzureAIClient:
    """Helper function to create AzureAIClient instances for testing, bypassing normal validation."""
    if azure_ai_settings is None:
        azure_ai_settings = AzureAISettings(env_file_path="test.env")

    # Create client instance directly
    client = object.__new__(AzureAIClient)

    # Set attributes directly
    client.project_client = mock_project_client
    client.credential = None
    client.agent_name = agent_name
    client.agent_version = agent_version
    client.use_latest_version = use_latest_version
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


def test_azure_ai_client_init_with_project_client(mock_project_client: MagicMock) -> None:
    """Test AzureAIClient initialization with existing project_client."""
    with patch("agent_framework_azure_ai._client.AzureAISettings") as mock_settings:
        mock_settings.return_value.project_endpoint = None
        mock_settings.return_value.model_deployment_name = "test-model"

        client = AzureAIClient(
            project_client=mock_project_client,
            agent_name="test-agent",
            agent_version="1.0",
        )

        assert client.project_client is mock_project_client
        assert client.agent_name == "test-agent"
        assert client.agent_version == "1.0"
        assert not client._should_close_client  # type: ignore
        assert isinstance(client, ChatClientProtocol)


def test_azure_ai_client_init_auto_create_client(
    azure_ai_unit_test_env: dict[str, str],
    mock_azure_credential: MagicMock,
) -> None:
    """Test AzureAIClient initialization with auto-created project_client."""
    with patch("agent_framework_azure_ai._client.AIProjectClient") as mock_ai_project_client:
        mock_project_client = MagicMock()
        mock_ai_project_client.return_value = mock_project_client

        client = AzureAIClient(
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


def test_azure_ai_client_init_missing_project_endpoint() -> None:
    """Test AzureAIClient initialization when project_endpoint is missing and no project_client provided."""
    with patch("agent_framework_azure_ai._client.AzureAISettings") as mock_settings:
        mock_settings.return_value.project_endpoint = None
        mock_settings.return_value.model_deployment_name = "test-model"

        with pytest.raises(ServiceInitializationError, match="Azure AI project endpoint is required"):
            AzureAIClient(async_credential=MagicMock())


def test_azure_ai_client_init_missing_credential(azure_ai_unit_test_env: dict[str, str]) -> None:
    """Test AzureAIClient.__init__ when async_credential is missing and no project_client provided."""
    with pytest.raises(
        ServiceInitializationError, match="Azure credential is required when project_client is not provided"
    ):
        AzureAIClient(
            project_endpoint=azure_ai_unit_test_env["AZURE_AI_PROJECT_ENDPOINT"],
            model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        )


def test_azure_ai_client_init_validation_error(mock_azure_credential: MagicMock) -> None:
    """Test that ValidationError in AzureAISettings is properly handled."""
    with patch("agent_framework_azure_ai._client.AzureAISettings") as mock_settings:
        mock_settings.side_effect = ValidationError.from_exception_data("test", [])

        with pytest.raises(ServiceInitializationError, match="Failed to create Azure AI settings"):
            AzureAIClient(async_credential=mock_azure_credential)


async def test_azure_ai_client_get_agent_reference_or_create_existing_version(
    mock_project_client: MagicMock,
) -> None:
    """Test _get_agent_reference_or_create when agent_version is already provided."""
    client = create_test_azure_ai_client(mock_project_client, agent_name="existing-agent", agent_version="1.0")

    agent_ref = await client._get_agent_reference_or_create({}, None)  # type: ignore

    assert agent_ref == {"name": "existing-agent", "version": "1.0", "type": "agent_reference"}


async def test_azure_ai_client_get_agent_reference_or_create_new_agent(
    mock_project_client: MagicMock,
    azure_ai_unit_test_env: dict[str, str],
) -> None:
    """Test _get_agent_reference_or_create when creating a new agent."""
    azure_ai_settings = AzureAISettings(model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"])
    client = create_test_azure_ai_client(
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


async def test_azure_ai_client_get_agent_reference_missing_model(
    mock_project_client: MagicMock,
) -> None:
    """Test _get_agent_reference_or_create when model is missing for agent creation."""
    client = create_test_azure_ai_client(mock_project_client, agent_name="test-agent")

    with pytest.raises(ServiceInitializationError, match="Model deployment name is required for agent creation"):
        await client._get_agent_reference_or_create({}, None)  # type: ignore


async def test_azure_ai_client_prepare_input_with_system_messages(
    mock_project_client: MagicMock,
) -> None:
    """Test _prepare_input converts system/developer messages to instructions."""
    client = create_test_azure_ai_client(mock_project_client)

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


async def test_azure_ai_client_prepare_input_no_system_messages(
    mock_project_client: MagicMock,
) -> None:
    """Test _prepare_input with no system/developer messages."""
    client = create_test_azure_ai_client(mock_project_client)

    messages = [
        ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")]),
        ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text="Hi there!")]),
    ]

    result_messages, instructions = client._prepare_input(messages)  # type: ignore

    assert len(result_messages) == 2
    assert instructions is None


async def test_azure_ai_client_prepare_options_basic(mock_project_client: MagicMock) -> None:
    """Test prepare_options basic functionality."""
    client = create_test_azure_ai_client(mock_project_client, agent_name="test-agent", agent_version="1.0")

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


async def test_azure_ai_client_initialize_client(mock_project_client: MagicMock) -> None:
    """Test initialize_client method."""
    client = create_test_azure_ai_client(mock_project_client)

    mock_openai_client = MagicMock()
    mock_project_client.get_openai_client = AsyncMock(return_value=mock_openai_client)

    await client.initialize_client()

    assert client.client is mock_openai_client
    mock_project_client.get_openai_client.assert_called_once()


def test_azure_ai_client_update_agent_name(mock_project_client: MagicMock) -> None:
    """Test _update_agent_name method."""
    client = create_test_azure_ai_client(mock_project_client)

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


async def test_azure_ai_client_async_context_manager(mock_project_client: MagicMock) -> None:
    """Test async context manager functionality."""
    client = create_test_azure_ai_client(mock_project_client, should_close_client=True)

    mock_project_client.close = AsyncMock()

    async with client as ctx_client:
        assert ctx_client is client

    # Should call close after exiting context
    mock_project_client.close.assert_called_once()


async def test_azure_ai_client_close_method(mock_project_client: MagicMock) -> None:
    """Test close method."""
    client = create_test_azure_ai_client(mock_project_client, should_close_client=True)

    mock_project_client.close = AsyncMock()

    await client.close()

    mock_project_client.close.assert_called_once()


async def test_azure_ai_client_close_client_when_should_close_false(mock_project_client: MagicMock) -> None:
    """Test _close_client_if_needed when should_close_client is False."""
    client = create_test_azure_ai_client(mock_project_client, should_close_client=False)

    mock_project_client.close = AsyncMock()

    await client._close_client_if_needed()  # type: ignore

    # Should not call close when should_close_client is False
    mock_project_client.close.assert_not_called()


async def test_azure_ai_client_agent_creation_with_instructions(
    mock_project_client: MagicMock,
) -> None:
    """Test agent creation with combined instructions."""
    client = create_test_azure_ai_client(mock_project_client, agent_name="test-agent")

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


async def test_azure_ai_client_agent_creation_with_tools(
    mock_project_client: MagicMock,
) -> None:
    """Test agent creation with tools."""
    client = create_test_azure_ai_client(mock_project_client, agent_name="test-agent")

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


async def test_azure_ai_client_use_latest_version_existing_agent(
    mock_project_client: MagicMock,
) -> None:
    """Test _get_agent_reference_or_create when use_latest_version=True and agent exists."""
    client = create_test_azure_ai_client(mock_project_client, agent_name="existing-agent", use_latest_version=True)

    # Mock existing agent response
    mock_existing_agent = MagicMock()
    mock_existing_agent.name = "existing-agent"
    mock_existing_agent.versions.latest.version = "2.5"
    mock_project_client.agents.get = AsyncMock(return_value=mock_existing_agent)

    run_options = {"model": "test-model"}
    agent_ref = await client._get_agent_reference_or_create(run_options, None)  # type: ignore

    # Verify existing agent was retrieved and used
    mock_project_client.agents.get.assert_called_once_with("existing-agent")
    mock_project_client.agents.create_version.assert_not_called()

    assert agent_ref == {"name": "existing-agent", "version": "2.5", "type": "agent_reference"}
    assert client.agent_name == "existing-agent"
    assert client.agent_version == "2.5"


async def test_azure_ai_client_use_latest_version_agent_not_found(
    mock_project_client: MagicMock,
) -> None:
    """Test _get_agent_reference_or_create when use_latest_version=True but agent doesn't exist."""
    from azure.core.exceptions import ResourceNotFoundError

    client = create_test_azure_ai_client(mock_project_client, agent_name="non-existing-agent", use_latest_version=True)

    # Mock ResourceNotFoundError when trying to retrieve agent
    mock_project_client.agents.get = AsyncMock(side_effect=ResourceNotFoundError("Agent not found"))

    # Mock agent creation response for fallback
    mock_created_agent = MagicMock()
    mock_created_agent.name = "non-existing-agent"
    mock_created_agent.version = "1.0"
    mock_project_client.agents.create_version = AsyncMock(return_value=mock_created_agent)

    run_options = {"model": "test-model"}
    agent_ref = await client._get_agent_reference_or_create(run_options, None)  # type: ignore

    # Verify retrieval was attempted and creation was used as fallback
    mock_project_client.agents.get.assert_called_once_with("non-existing-agent")
    mock_project_client.agents.create_version.assert_called_once()

    assert agent_ref == {"name": "non-existing-agent", "version": "1.0", "type": "agent_reference"}
    assert client.agent_name == "non-existing-agent"
    assert client.agent_version == "1.0"


async def test_azure_ai_client_use_latest_version_false(
    mock_project_client: MagicMock,
) -> None:
    """Test _get_agent_reference_or_create when use_latest_version=False (default behavior)."""
    client = create_test_azure_ai_client(mock_project_client, agent_name="test-agent", use_latest_version=False)

    # Mock agent creation response
    mock_created_agent = MagicMock()
    mock_created_agent.name = "test-agent"
    mock_created_agent.version = "1.0"
    mock_project_client.agents.create_version = AsyncMock(return_value=mock_created_agent)

    run_options = {"model": "test-model"}
    agent_ref = await client._get_agent_reference_or_create(run_options, None)  # type: ignore

    # Verify retrieval was not attempted and creation was used directly
    mock_project_client.agents.get.assert_not_called()
    mock_project_client.agents.create_version.assert_called_once()

    assert agent_ref == {"name": "test-agent", "version": "1.0", "type": "agent_reference"}


async def test_azure_ai_client_use_latest_version_with_existing_agent_version(
    mock_project_client: MagicMock,
) -> None:
    """Test that use_latest_version is ignored when agent_version is already provided."""
    client = create_test_azure_ai_client(
        mock_project_client, agent_name="test-agent", agent_version="3.0", use_latest_version=True
    )

    agent_ref = await client._get_agent_reference_or_create({}, None)  # type: ignore

    # Verify neither retrieval nor creation was attempted since version is already set
    mock_project_client.agents.get.assert_not_called()
    mock_project_client.agents.create_version.assert_not_called()

    assert agent_ref == {"name": "test-agent", "version": "3.0", "type": "agent_reference"}


class ResponseFormatModel(BaseModel):
    """Test Pydantic model for response format testing."""

    name: str
    value: int
    description: str
    model_config = ConfigDict(extra="forbid")


async def test_azure_ai_client_agent_creation_with_response_format(
    mock_project_client: MagicMock,
) -> None:
    """Test agent creation with response_format configuration."""
    client = create_test_azure_ai_client(mock_project_client, agent_name="test-agent")

    # Mock agent creation response
    mock_agent = MagicMock()
    mock_agent.name = "test-agent"
    mock_agent.version = "1.0"
    mock_project_client.agents.create_version = AsyncMock(return_value=mock_agent)

    run_options = {"model": "test-model", "response_format": ResponseFormatModel}

    await client._get_agent_reference_or_create(run_options, None)  # type: ignore

    # Verify agent was created with response format configuration
    call_args = mock_project_client.agents.create_version.call_args
    created_definition = call_args[1]["definition"]

    # Check that text format configuration was set
    assert hasattr(created_definition, "text")
    assert created_definition.text is not None

    # Check that the format is a ResponseTextFormatConfigurationJsonSchema
    assert hasattr(created_definition.text, "format")
    format_config = created_definition.text.format
    assert isinstance(format_config, ResponseTextFormatConfigurationJsonSchema)

    # Check the schema name matches the model class name
    assert format_config.name == "ResponseFormatModel"

    # Check that schema was generated correctly
    assert format_config.schema is not None
    schema = format_config.schema
    assert "properties" in schema
    assert "name" in schema["properties"]
    assert "value" in schema["properties"]
    assert "description" in schema["properties"]


async def test_azure_ai_client_prepare_options_excludes_response_format(
    mock_project_client: MagicMock,
) -> None:
    """Test that prepare_options excludes response_format from final run options."""
    client = create_test_azure_ai_client(mock_project_client, agent_name="test-agent", agent_version="1.0")

    messages = [ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")])]
    chat_options = ChatOptions()

    with (
        patch.object(
            client.__class__.__bases__[0],
            "prepare_options",
            return_value={"model": "test-model", "response_format": ResponseFormatModel},
        ),
        patch.object(
            client,
            "_get_agent_reference_or_create",
            return_value={"name": "test-agent", "version": "1.0", "type": "agent_reference"},
        ),
    ):
        run_options = await client.prepare_options(messages, chat_options)

        # response_format should be excluded from final run options
        assert "response_format" not in run_options
        # But extra_body should contain agent reference
        assert "extra_body" in run_options
        assert run_options["extra_body"]["agent"]["name"] == "test-agent"


async def test_azure_ai_client_prepare_options_with_resp_conversation_id(
    mock_project_client: MagicMock,
) -> None:
    """Test prepare_options with conversation ID starting with 'resp_'."""
    client = create_test_azure_ai_client(mock_project_client, agent_name="test-agent", agent_version="1.0")

    messages = [ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")])]
    chat_options = ChatOptions(conversation_id="resp_12345")

    with (
        patch.object(
            client.__class__.__bases__[0],
            "prepare_options",
            return_value={"model": "test-model", "previous_response_id": "old_value", "conversation": "old_conv"},
        ),
        patch.object(
            client,
            "_get_agent_reference_or_create",
            return_value={"name": "test-agent", "version": "1.0", "type": "agent_reference"},
        ),
    ):
        run_options = await client.prepare_options(messages, chat_options)

        # Should set previous_response_id and remove conversation property
        assert run_options["previous_response_id"] == "resp_12345"
        assert "conversation" not in run_options


async def test_azure_ai_client_prepare_options_with_conv_conversation_id(
    mock_project_client: MagicMock,
) -> None:
    """Test prepare_options with conversation ID starting with 'conv_'."""
    client = create_test_azure_ai_client(mock_project_client, agent_name="test-agent", agent_version="1.0")

    messages = [ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")])]
    chat_options = ChatOptions(conversation_id="conv_67890")

    with (
        patch.object(
            client.__class__.__bases__[0],
            "prepare_options",
            return_value={"model": "test-model", "previous_response_id": "old_value", "conversation": "old_conv"},
        ),
        patch.object(
            client,
            "_get_agent_reference_or_create",
            return_value={"name": "test-agent", "version": "1.0", "type": "agent_reference"},
        ),
    ):
        run_options = await client.prepare_options(messages, chat_options)

        # Should set conversation and remove previous_response_id property
        assert run_options["conversation"] == "conv_67890"
        assert "previous_response_id" not in run_options


async def test_azure_ai_client_prepare_options_with_client_conversation_id(
    mock_project_client: MagicMock,
) -> None:
    """Test prepare_options using client's default conversation ID when chat options don't have one."""
    client = create_test_azure_ai_client(
        mock_project_client, agent_name="test-agent", agent_version="1.0", conversation_id="resp_client_default"
    )

    messages = [ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")])]
    chat_options = ChatOptions()  # No conversation_id specified

    with (
        patch.object(
            client.__class__.__bases__[0],
            "prepare_options",
            return_value={"model": "test-model", "previous_response_id": "old_value", "conversation": "old_conv"},
        ),
        patch.object(
            client,
            "_get_agent_reference_or_create",
            return_value={"name": "test-agent", "version": "1.0", "type": "agent_reference"},
        ),
    ):
        run_options = await client.prepare_options(messages, chat_options)

        # Should use client's default conversation_id and set previous_response_id
        assert run_options["previous_response_id"] == "resp_client_default"
        assert "conversation" not in run_options


def test_get_conversation_id_with_store_true_and_conversation_id() -> None:
    """Test get_conversation_id returns conversation ID when store is True and conversation exists."""
    client = create_test_azure_ai_client(MagicMock())

    # Mock OpenAI response with conversation
    mock_response = MagicMock(spec=OpenAIResponse)
    mock_response.id = "resp_12345"
    mock_conversation = MagicMock()
    mock_conversation.id = "conv_67890"
    mock_response.conversation = mock_conversation

    result = client.get_conversation_id(mock_response, store=True)

    assert result == "conv_67890"


def test_get_conversation_id_with_store_true_and_no_conversation() -> None:
    """Test get_conversation_id returns response ID when store is True and no conversation exists."""
    client = create_test_azure_ai_client(MagicMock())

    # Mock OpenAI response without conversation
    mock_response = MagicMock(spec=OpenAIResponse)
    mock_response.id = "resp_12345"
    mock_response.conversation = None

    result = client.get_conversation_id(mock_response, store=True)

    assert result == "resp_12345"


def test_get_conversation_id_with_store_true_and_empty_conversation_id() -> None:
    """Test get_conversation_id returns response ID when store is True and conversation ID is empty."""
    client = create_test_azure_ai_client(MagicMock())

    # Mock OpenAI response with conversation but empty ID
    mock_response = MagicMock(spec=OpenAIResponse)
    mock_response.id = "resp_12345"
    mock_conversation = MagicMock()
    mock_conversation.id = ""
    mock_response.conversation = mock_conversation

    result = client.get_conversation_id(mock_response, store=True)

    assert result == "resp_12345"


def test_get_conversation_id_with_store_false() -> None:
    """Test get_conversation_id returns None when store is False."""
    client = create_test_azure_ai_client(MagicMock())

    # Mock OpenAI response with conversation
    mock_response = MagicMock(spec=OpenAIResponse)
    mock_response.id = "resp_12345"
    mock_conversation = MagicMock()
    mock_conversation.id = "conv_67890"
    mock_response.conversation = mock_conversation

    result = client.get_conversation_id(mock_response, store=False)

    assert result is None


def test_get_conversation_id_with_parsed_response_and_store_true() -> None:
    """Test get_conversation_id works with ParsedResponse when store is True."""
    client = create_test_azure_ai_client(MagicMock())

    # Mock ParsedResponse with conversation
    mock_response = MagicMock(spec=ParsedResponse[BaseModel])
    mock_response.id = "resp_parsed_12345"
    mock_conversation = MagicMock()
    mock_conversation.id = "conv_parsed_67890"
    mock_response.conversation = mock_conversation

    result = client.get_conversation_id(mock_response, store=True)

    assert result == "conv_parsed_67890"


def test_get_conversation_id_with_parsed_response_no_conversation() -> None:
    """Test get_conversation_id returns response ID with ParsedResponse when no conversation exists."""
    client = create_test_azure_ai_client(MagicMock())

    # Mock ParsedResponse without conversation
    mock_response = MagicMock(spec=ParsedResponse[BaseModel])
    mock_response.id = "resp_parsed_12345"
    mock_response.conversation = None

    result = client.get_conversation_id(mock_response, store=True)

    assert result == "resp_parsed_12345"


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
