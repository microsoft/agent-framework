# Copyright (c) Microsoft. All rights reserved.

import json
import os
import sys
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from agent_framework import (
    AgentResponse,
    ChatAgent,
    ChatClientProtocol,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    Content,
    HostedCodeInterpreterTool,
    HostedFileSearchTool,
    HostedMCPTool,
    HostedWebSearchTool,
    Role,
    tool,
)
from agent_framework.exceptions import ServiceInitializationError
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    ApproximateLocation,
    CodeInterpreterTool,
    CodeInterpreterToolAuto,
    FileSearchTool,
    MCPTool,
    ResponseTextFormatConfigurationJsonSchema,
    WebSearchPreviewTool,
)
from azure.core.exceptions import ResourceNotFoundError
from azure.identity.aio import AzureCliCredential
from openai.types.responses.parsed_response import ParsedResponse
from openai.types.responses.response import Response as OpenAIResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pytest import fixture, param

from agent_framework_azure_ai import AzureAIClient, AzureAISettings
from agent_framework_azure_ai._shared import from_azure_ai_tools

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


@asynccontextmanager
async def temporary_chat_client(agent_name: str) -> AsyncIterator[AzureAIClient]:
    """Async context manager that creates an Azure AI agent and yields an `AzureAIClient`.

    The underlying agent version is cleaned up automatically after use.
    Tests can construct their own `ChatAgent` instances from the yielded client.
    """
    endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        chat_client = AzureAIClient(
            project_client=project_client,
            agent_name=agent_name,
        )
        try:
            yield chat_client
        finally:
            await project_client.agents.delete(agent_name=agent_name)


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
    client.agent_description = None
    client.use_latest_version = use_latest_version
    client.model_id = azure_ai_settings.model_deployment_name
    client.conversation_id = conversation_id
    client._is_application_endpoint = False  # type: ignore
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


def test_init_with_project_client(mock_project_client: MagicMock) -> None:
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


def test_init_auto_create_client(
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
            credential=mock_azure_credential,
            agent_name="test-agent",
        )

        assert client.project_client is mock_project_client
        assert client.agent_name == "test-agent"
        assert client._should_close_client  # type: ignore

        # Verify AIProjectClient was called with correct parameters
        mock_ai_project_client.assert_called_once()


def test_init_missing_project_endpoint() -> None:
    """Test AzureAIClient initialization when project_endpoint is missing and no project_client provided."""
    with patch("agent_framework_azure_ai._client.AzureAISettings") as mock_settings:
        mock_settings.return_value.project_endpoint = None
        mock_settings.return_value.model_deployment_name = "test-model"

        with pytest.raises(ServiceInitializationError, match="Azure AI project endpoint is required"):
            AzureAIClient(credential=MagicMock())


def test_init_missing_credential(azure_ai_unit_test_env: dict[str, str]) -> None:
    """Test AzureAIClient.__init__ when credential is missing and no project_client provided."""
    with pytest.raises(
        ServiceInitializationError, match="Azure credential is required when project_client is not provided"
    ):
        AzureAIClient(
            project_endpoint=azure_ai_unit_test_env["AZURE_AI_PROJECT_ENDPOINT"],
            model_deployment_name=azure_ai_unit_test_env["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        )


def test_init_validation_error(mock_azure_credential: MagicMock) -> None:
    """Test that ValidationError in AzureAISettings is properly handled."""
    with patch("agent_framework_azure_ai._client.AzureAISettings") as mock_settings:
        mock_settings.side_effect = ValidationError.from_exception_data("test", [])

        with pytest.raises(ServiceInitializationError, match="Failed to create Azure AI settings"):
            AzureAIClient(credential=mock_azure_credential)


async def test_get_agent_reference_or_create_existing_version(
    mock_project_client: MagicMock,
) -> None:
    """Test _get_agent_reference_or_create when agent_version is already provided."""
    client = create_test_azure_ai_client(mock_project_client, agent_name="existing-agent", agent_version="1.0")

    agent_ref = await client._get_agent_reference_or_create({}, None)  # type: ignore

    assert agent_ref == {"name": "existing-agent", "version": "1.0", "type": "agent_reference"}


async def test_get_agent_reference_or_create_missing_agent_name(
    mock_project_client: MagicMock,
) -> None:
    """Test _get_agent_reference_or_create raises when agent_name is missing."""
    client = create_test_azure_ai_client(mock_project_client, agent_name=None)

    with pytest.raises(ServiceInitializationError, match="Agent name is required"):
        await client._get_agent_reference_or_create({}, None)  # type: ignore


async def test_get_agent_reference_or_create_new_agent(
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


async def test_get_agent_reference_missing_model(
    mock_project_client: MagicMock,
) -> None:
    """Test _get_agent_reference_or_create when model is missing for agent creation."""
    client = create_test_azure_ai_client(mock_project_client, agent_name="test-agent")

    with pytest.raises(ServiceInitializationError, match="Model deployment name is required for agent creation"):
        await client._get_agent_reference_or_create({}, None)  # type: ignore


async def test_prepare_messages_for_azure_ai_with_system_messages(
    mock_project_client: MagicMock,
) -> None:
    """Test _prepare_messages_for_azure_ai converts system/developer messages to instructions."""
    client = create_test_azure_ai_client(mock_project_client)

    messages = [
        ChatMessage(role=Role.SYSTEM, contents=[Content.from_text(text="You are a helpful assistant.")]),
        ChatMessage(role=Role.USER, contents=[Content.from_text(text="Hello")]),
        ChatMessage(role=Role.ASSISTANT, contents=[Content.from_text(text="System response")]),
    ]

    result_messages, instructions = client._prepare_messages_for_azure_ai(messages)  # type: ignore

    assert len(result_messages) == 2
    assert result_messages[0].role == Role.USER
    assert result_messages[1].role == Role.ASSISTANT
    assert instructions == "You are a helpful assistant."


async def test_prepare_messages_for_azure_ai_no_system_messages(
    mock_project_client: MagicMock,
) -> None:
    """Test _prepare_messages_for_azure_ai with no system/developer messages."""
    client = create_test_azure_ai_client(mock_project_client)

    messages = [
        ChatMessage(role=Role.USER, contents=[Content.from_text(text="Hello")]),
        ChatMessage(role=Role.ASSISTANT, contents=[Content.from_text(text="Hi there!")]),
    ]

    result_messages, instructions = client._prepare_messages_for_azure_ai(messages)  # type: ignore

    assert len(result_messages) == 2
    assert instructions is None


def test_transform_input_for_azure_ai(mock_project_client: MagicMock) -> None:
    """Test _transform_input_for_azure_ai adds required fields for Azure AI schema.

    WORKAROUND TEST: Azure AI Projects API requires 'type' at item level and
    'annotations' in output_text content items, which OpenAI's Responses API does not require.
    See: https://github.com/Azure/azure-sdk-for-python/issues/44493
    See: https://github.com/microsoft/agent-framework/issues/2926
    """
    client = create_test_azure_ai_client(mock_project_client)

    # Input in OpenAI Responses API format (what agent-framework generates)
    openai_format_input = [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Hello"},
            ],
        },
        {
            "role": "assistant",
            "content": [
                {"type": "output_text", "text": "Hi there!"},
            ],
        },
    ]

    result = client._transform_input_for_azure_ai(openai_format_input)  # type: ignore

    # Verify 'type': 'message' added at item level
    assert result[0]["type"] == "message"
    assert result[1]["type"] == "message"

    # Verify 'annotations' added ONLY to output_text (assistant) content, NOT input_text (user)
    assert result[0]["content"][0]["type"] == "input_text"  # user content type preserved
    assert "annotations" not in result[0]["content"][0]  # user message - no annotations
    assert result[1]["content"][0]["type"] == "output_text"  # assistant content type preserved
    assert result[1]["content"][0]["annotations"] == []  # assistant message - has annotations

    # Verify original fields preserved
    assert result[0]["role"] == "user"
    assert result[0]["content"][0]["text"] == "Hello"
    assert result[1]["role"] == "assistant"
    assert result[1]["content"][0]["text"] == "Hi there!"


def test_transform_input_preserves_existing_fields(mock_project_client: MagicMock) -> None:
    """Test _transform_input_for_azure_ai preserves existing type and annotations."""
    client = create_test_azure_ai_client(mock_project_client)

    # Input that already has the fields (shouldn't duplicate)
    input_with_fields = [
        {
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "output_text", "text": "Hello", "annotations": [{"some": "annotation"}]},
            ],
        },
    ]

    result = client._transform_input_for_azure_ai(input_with_fields)  # type: ignore

    # Should preserve existing values, not overwrite
    assert result[0]["type"] == "message"
    assert result[0]["content"][0]["annotations"] == [{"some": "annotation"}]


def test_transform_input_handles_non_dict_content(mock_project_client: MagicMock) -> None:
    """Test _transform_input_for_azure_ai handles non-dict content items."""
    client = create_test_azure_ai_client(mock_project_client)

    # Input with string content (edge case)
    input_with_string_content = [
        {
            "role": "user",
            "content": ["plain string content"],
        },
    ]

    result = client._transform_input_for_azure_ai(input_with_string_content)  # type: ignore

    # Should add 'type': 'message' at item level even with non-dict content
    assert result[0]["type"] == "message"
    # Non-dict content items should be preserved without modification
    assert result[0]["content"] == ["plain string content"]


async def test_prepare_options_basic(mock_project_client: MagicMock) -> None:
    """Test prepare_options basic functionality."""
    client = create_test_azure_ai_client(mock_project_client, agent_name="test-agent", agent_version="1.0")

    messages = [ChatMessage(role=Role.USER, contents=[Content.from_text(text="Hello")])]

    with (
        patch.object(client.__class__.__bases__[0], "_prepare_options", return_value={"model": "test-model"}),
        patch.object(
            client,
            "_get_agent_reference_or_create",
            return_value={"name": "test-agent", "version": "1.0", "type": "agent_reference"},
        ),
    ):
        run_options = await client._prepare_options(messages, {})

        assert "extra_body" in run_options
        assert run_options["extra_body"]["agent"]["name"] == "test-agent"


@pytest.mark.parametrize(
    "endpoint,expects_agent",
    [
        ("https://example.com/api/projects/my-project/applications/my-application/protocols", False),
        ("https://example.com/api/projects/my-project", True),
    ],
)
async def test_prepare_options_with_application_endpoint(
    mock_azure_credential: MagicMock, endpoint: str, expects_agent: bool
) -> None:
    client = AzureAIClient(
        project_endpoint=endpoint,
        model_deployment_name="test-model",
        credential=mock_azure_credential,
        agent_name="test-agent",
        agent_version="1",
    )

    messages = [ChatMessage(role=Role.USER, contents=[Content.from_text(text="Hello")])]

    with (
        patch.object(client.__class__.__bases__[0], "_prepare_options", return_value={"model": "test-model"}),
        patch.object(
            client,
            "_get_agent_reference_or_create",
            return_value={"name": "test-agent", "version": "1", "type": "agent_reference"},
        ),
    ):
        run_options = await client._prepare_options(messages, {})

    if expects_agent:
        assert "extra_body" in run_options
        assert run_options["extra_body"]["agent"]["name"] == "test-agent"
    else:
        assert "extra_body" not in run_options


@pytest.mark.parametrize(
    "endpoint,expects_agent",
    [
        ("https://example.com/api/projects/my-project/applications/my-application/protocols", False),
        ("https://example.com/api/projects/my-project", True),
    ],
)
async def test_prepare_options_with_application_project_client(
    mock_project_client: MagicMock, endpoint: str, expects_agent: bool
) -> None:
    mock_project_client._config = MagicMock()
    mock_project_client._config.endpoint = endpoint

    client = AzureAIClient(
        project_client=mock_project_client,
        model_deployment_name="test-model",
        agent_name="test-agent",
        agent_version="1",
    )

    messages = [ChatMessage(role=Role.USER, contents=[Content.from_text(text="Hello")])]

    with (
        patch.object(client.__class__.__bases__[0], "_prepare_options", return_value={"model": "test-model"}),
        patch.object(
            client,
            "_get_agent_reference_or_create",
            return_value={"name": "test-agent", "version": "1", "type": "agent_reference"},
        ),
    ):
        run_options = await client._prepare_options(messages, {})

    if expects_agent:
        assert "extra_body" in run_options
        assert run_options["extra_body"]["agent"]["name"] == "test-agent"
    else:
        assert "extra_body" not in run_options


async def test_initialize_client(mock_project_client: MagicMock) -> None:
    """Test _initialize_client method."""
    client = create_test_azure_ai_client(mock_project_client)

    mock_openai_client = MagicMock()
    mock_project_client.get_openai_client = MagicMock(return_value=mock_openai_client)

    await client._initialize_client()

    assert client.client is mock_openai_client
    mock_project_client.get_openai_client.assert_called_once()


def test_update_agent_name_and_description(mock_project_client: MagicMock) -> None:
    """Test _update_agent_name_and_description method."""
    client = create_test_azure_ai_client(mock_project_client)

    # Test updating agent name when current is None
    with patch.object(client, "_update_agent_name_and_description") as mock_update:
        mock_update.return_value = None
        client._update_agent_name_and_description("new-agent")  # type: ignore
        mock_update.assert_called_once_with("new-agent")

    # Test behavior when agent name is updated
    assert client.agent_name is None  # Should remain None since we didn't actually update
    client.agent_name = "test-agent"  # Manually set for the test

    # Test with None input
    with patch.object(client, "_update_agent_name_and_description") as mock_update:
        mock_update.return_value = None
        client._update_agent_name_and_description(None)  # type: ignore
        mock_update.assert_called_once_with(None)


async def test_async_context_manager(mock_project_client: MagicMock) -> None:
    """Test async context manager functionality."""
    client = create_test_azure_ai_client(mock_project_client, should_close_client=True)

    mock_project_client.close = AsyncMock()

    async with client as ctx_client:
        assert ctx_client is client

    # Should call close after exiting context
    mock_project_client.close.assert_called_once()


async def test_close_method(mock_project_client: MagicMock) -> None:
    """Test close method."""
    client = create_test_azure_ai_client(mock_project_client, should_close_client=True)

    mock_project_client.close = AsyncMock()

    await client.close()

    mock_project_client.close.assert_called_once()


async def test_close_client_when_should_close_false(mock_project_client: MagicMock) -> None:
    """Test _close_client_if_needed when should_close_client is False."""
    client = create_test_azure_ai_client(mock_project_client, should_close_client=False)

    mock_project_client.close = AsyncMock()

    await client._close_client_if_needed()  # type: ignore

    # Should not call close when should_close_client is False
    mock_project_client.close.assert_not_called()


async def test_configure_azure_monitor_success(mock_project_client: MagicMock) -> None:
    """Test configure_azure_monitor successfully configures Azure Monitor."""
    client = create_test_azure_ai_client(mock_project_client)

    # Mock the telemetry connection string retrieval
    mock_project_client.telemetry.get_application_insights_connection_string = AsyncMock(
        return_value="InstrumentationKey=test-key;IngestionEndpoint=https://test.endpoint"
    )

    mock_configure = MagicMock()
    mock_views = MagicMock(return_value=[])
    mock_resource = MagicMock()
    mock_enable = MagicMock()

    with (
        patch.dict(
            "sys.modules",
            {"azure.monitor.opentelemetry": MagicMock(configure_azure_monitor=mock_configure)},
        ),
        patch("agent_framework.observability.create_metric_views", mock_views),
        patch("agent_framework.observability.create_resource", return_value=mock_resource),
        patch("agent_framework.observability.enable_instrumentation", mock_enable),
    ):
        await client.configure_azure_monitor(enable_sensitive_data=True)

        # Verify connection string was retrieved
        mock_project_client.telemetry.get_application_insights_connection_string.assert_called_once()

        # Verify Azure Monitor was configured
        mock_configure.assert_called_once()
        call_kwargs = mock_configure.call_args[1]
        assert call_kwargs["connection_string"] == "InstrumentationKey=test-key;IngestionEndpoint=https://test.endpoint"

        # Verify instrumentation was enabled with sensitive data flag
        mock_enable.assert_called_once_with(enable_sensitive_data=True)


async def test_configure_azure_monitor_resource_not_found(mock_project_client: MagicMock) -> None:
    """Test configure_azure_monitor handles ResourceNotFoundError gracefully."""
    client = create_test_azure_ai_client(mock_project_client)

    # Mock the telemetry to raise ResourceNotFoundError
    mock_project_client.telemetry.get_application_insights_connection_string = AsyncMock(
        side_effect=ResourceNotFoundError("No Application Insights found")
    )

    # Should not raise, just log warning and return
    await client.configure_azure_monitor()

    # Verify connection string retrieval was attempted
    mock_project_client.telemetry.get_application_insights_connection_string.assert_called_once()


async def test_configure_azure_monitor_import_error(mock_project_client: MagicMock) -> None:
    """Test configure_azure_monitor raises ImportError when azure-monitor-opentelemetry is not installed."""
    client = create_test_azure_ai_client(mock_project_client)

    # Mock the telemetry connection string retrieval
    mock_project_client.telemetry.get_application_insights_connection_string = AsyncMock(
        return_value="InstrumentationKey=test-key"
    )

    # Mock the import to fail
    with (
        patch.dict(sys.modules, {"azure.monitor.opentelemetry": None}),
        patch("builtins.__import__", side_effect=ImportError("No module named 'azure.monitor.opentelemetry'")),
        pytest.raises(ImportError, match="azure-monitor-opentelemetry is required"),
    ):
        await client.configure_azure_monitor()


async def test_configure_azure_monitor_with_custom_resource(mock_project_client: MagicMock) -> None:
    """Test configure_azure_monitor uses custom resource when provided."""
    client = create_test_azure_ai_client(mock_project_client)

    mock_project_client.telemetry.get_application_insights_connection_string = AsyncMock(
        return_value="InstrumentationKey=test-key"
    )

    custom_resource = MagicMock()
    mock_configure = MagicMock()

    with (
        patch.dict(
            "sys.modules",
            {"azure.monitor.opentelemetry": MagicMock(configure_azure_monitor=mock_configure)},
        ),
        patch("agent_framework.observability.create_metric_views") as mock_views,
        patch("agent_framework.observability.create_resource") as mock_create_resource,
        patch("agent_framework.observability.enable_instrumentation"),
    ):
        mock_views.return_value = []

        await client.configure_azure_monitor(resource=custom_resource)

        # Verify custom resource was used, not create_resource
        mock_create_resource.assert_not_called()
        call_kwargs = mock_configure.call_args[1]
        assert call_kwargs["resource"] is custom_resource


async def test_agent_creation_with_instructions(
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


async def test_agent_creation_with_additional_args(
    mock_project_client: MagicMock,
) -> None:
    """Test agent creation with additional arguments."""
    client = create_test_azure_ai_client(mock_project_client, agent_name="test-agent")

    # Mock agent creation response
    mock_agent = MagicMock()
    mock_agent.name = "test-agent"
    mock_agent.version = "1.0"
    mock_project_client.agents.create_version = AsyncMock(return_value=mock_agent)

    run_options = {"model": "test-model", "temperature": 0.9, "top_p": 0.8}
    messages_instructions = "Message instructions. "

    await client._get_agent_reference_or_create(run_options, messages_instructions)  # type: ignore

    # Verify agent was created with provided arguments
    call_args = mock_project_client.agents.create_version.call_args
    definition = call_args[1]["definition"]
    assert definition.temperature == 0.9
    assert definition.top_p == 0.8


async def test_agent_creation_with_tools(
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


async def test_use_latest_version_existing_agent(
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


async def test_use_latest_version_agent_not_found(
    mock_project_client: MagicMock,
) -> None:
    """Test _get_agent_reference_or_create when use_latest_version=True but agent doesn't exist."""
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


async def test_use_latest_version_false(
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


async def test_use_latest_version_with_existing_agent_version(
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


async def test_agent_creation_with_response_format(
    mock_project_client: MagicMock,
) -> None:
    """Test agent creation with response_format configuration."""
    client = create_test_azure_ai_client(mock_project_client, agent_name="test-agent")

    # Mock agent creation response
    mock_agent = MagicMock()
    mock_agent.name = "test-agent"
    mock_agent.version = "1.0"
    mock_project_client.agents.create_version = AsyncMock(return_value=mock_agent)

    run_options = {"model": "test-model"}
    chat_options = {"response_format": ResponseFormatModel}

    await client._get_agent_reference_or_create(run_options, None, chat_options)  # type: ignore

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
    assert "additionalProperties" in schema


async def test_agent_creation_with_mapping_response_format(
    mock_project_client: MagicMock,
) -> None:
    """Test agent creation when response_format is provided as a mapping."""
    client = create_test_azure_ai_client(mock_project_client, agent_name="test-agent")

    mock_agent = MagicMock()
    mock_agent.name = "test-agent"
    mock_agent.version = "1.0"
    mock_project_client.agents.create_version = AsyncMock(return_value=mock_agent)

    runtime_schema = {
        "title": "WeatherDigest",
        "type": "object",
        "properties": {
            "location": {"type": "string"},
            "conditions": {"type": "string"},
            "temperature_c": {"type": "number"},
            "advisory": {"type": "string"},
        },
        "required": ["location", "conditions", "temperature_c", "advisory"],
        "additionalProperties": False,
    }

    run_options = {"model": "test-model"}
    response_format_mapping = {
        "type": "json_schema",
        "json_schema": {
            "name": runtime_schema["title"],
            "strict": True,
            "schema": runtime_schema,
        },
    }
    chat_options = {"response_format": response_format_mapping}

    await client._get_agent_reference_or_create(run_options, None, chat_options)

    call_args = mock_project_client.agents.create_version.call_args
    created_definition = call_args[1]["definition"]

    assert hasattr(created_definition, "text")
    assert created_definition.text is not None
    format_config = created_definition.text.format
    assert isinstance(format_config, ResponseTextFormatConfigurationJsonSchema)
    assert format_config.name == runtime_schema["title"]
    assert format_config.schema == runtime_schema
    assert format_config.strict is True


async def test_prepare_options_excludes_response_format(
    mock_project_client: MagicMock,
) -> None:
    """Test that prepare_options excludes response_format, text, and text_format from final run options."""
    client = create_test_azure_ai_client(mock_project_client, agent_name="test-agent", agent_version="1.0")

    messages = [ChatMessage(role=Role.USER, contents=[Content.from_text(text="Hello")])]
    chat_options: ChatOptions = {}

    with (
        patch.object(
            client.__class__.__bases__[0],
            "_prepare_options",
            return_value={
                "model": "test-model",
                "response_format": ResponseFormatModel,
                "text": {"format": {"type": "json_schema", "name": "test"}},
                "text_format": ResponseFormatModel,
            },
        ),
        patch.object(
            client,
            "_get_agent_reference_or_create",
            return_value={"name": "test-agent", "version": "1.0", "type": "agent_reference"},
        ),
    ):
        run_options = await client._prepare_options(messages, chat_options)

        # response_format, text, and text_format should be excluded from final run options
        # because they are configured at agent level, not request level
        assert "response_format" not in run_options
        assert "text" not in run_options
        assert "text_format" not in run_options
        # But extra_body should contain agent reference
        assert "extra_body" in run_options
        assert run_options["extra_body"]["agent"]["name"] == "test-agent"


def test_get_conversation_id_with_store_true_and_conversation_id() -> None:
    """Test _get_conversation_id returns conversation ID when store is True and conversation exists."""
    client = create_test_azure_ai_client(MagicMock())

    # Mock OpenAI response with conversation
    mock_response = MagicMock(spec=OpenAIResponse)
    mock_response.id = "resp_12345"
    mock_conversation = MagicMock()
    mock_conversation.id = "conv_67890"
    mock_response.conversation = mock_conversation

    result = client._get_conversation_id(mock_response, store=True)

    assert result == "conv_67890"


def test_get_conversation_id_with_store_true_and_no_conversation() -> None:
    """Test _get_conversation_id returns response ID when store is True and no conversation exists."""
    client = create_test_azure_ai_client(MagicMock())

    # Mock OpenAI response without conversation
    mock_response = MagicMock(spec=OpenAIResponse)
    mock_response.id = "resp_12345"
    mock_response.conversation = None

    result = client._get_conversation_id(mock_response, store=True)

    assert result == "resp_12345"


def test_get_conversation_id_with_store_true_and_empty_conversation_id() -> None:
    """Test _get_conversation_id returns response ID when store is True and conversation ID is empty."""
    client = create_test_azure_ai_client(MagicMock())

    # Mock OpenAI response with conversation but empty ID
    mock_response = MagicMock(spec=OpenAIResponse)
    mock_response.id = "resp_12345"
    mock_conversation = MagicMock()
    mock_conversation.id = ""
    mock_response.conversation = mock_conversation

    result = client._get_conversation_id(mock_response, store=True)

    assert result == "resp_12345"


def test_get_conversation_id_with_store_false() -> None:
    """Test _get_conversation_id returns None when store is False."""
    client = create_test_azure_ai_client(MagicMock())

    # Mock OpenAI response with conversation
    mock_response = MagicMock(spec=OpenAIResponse)
    mock_response.id = "resp_12345"
    mock_conversation = MagicMock()
    mock_conversation.id = "conv_67890"
    mock_response.conversation = mock_conversation

    result = client._get_conversation_id(mock_response, store=False)

    assert result is None


def test_get_conversation_id_with_parsed_response_and_store_true() -> None:
    """Test _get_conversation_id works with ParsedResponse when store is True."""
    client = create_test_azure_ai_client(MagicMock())

    # Mock ParsedResponse with conversation
    mock_response = MagicMock(spec=ParsedResponse[BaseModel])
    mock_response.id = "resp_parsed_12345"
    mock_conversation = MagicMock()
    mock_conversation.id = "conv_parsed_67890"
    mock_response.conversation = mock_conversation

    result = client._get_conversation_id(mock_response, store=True)

    assert result == "conv_parsed_67890"


def test_get_conversation_id_with_parsed_response_no_conversation() -> None:
    """Test _get_conversation_id returns response ID with ParsedResponse when no conversation exists."""
    client = create_test_azure_ai_client(MagicMock())

    # Mock ParsedResponse without conversation
    mock_response = MagicMock(spec=ParsedResponse[BaseModel])
    mock_response.id = "resp_parsed_12345"
    mock_response.conversation = None

    result = client._get_conversation_id(mock_response, store=True)

    assert result == "resp_parsed_12345"


def test_prepare_mcp_tool_basic() -> None:
    """Test _prepare_mcp_tool with basic HostedMCPTool."""
    mcp_tool = HostedMCPTool(
        name="Test MCP Server",
        url="https://example.com/mcp",
    )

    result = AzureAIClient._prepare_mcp_tool(mcp_tool)  # type: ignore

    assert result["server_label"] == "Test_MCP_Server"
    assert result["server_url"] == "https://example.com/mcp"


def test_prepare_mcp_tool_with_description() -> None:
    """Test _prepare_mcp_tool with description."""
    mcp_tool = HostedMCPTool(
        name="Test MCP",
        url="https://example.com/mcp",
        description="A test MCP server",
    )

    result = AzureAIClient._prepare_mcp_tool(mcp_tool)  # type: ignore

    assert result["server_description"] == "A test MCP server"


def test_prepare_mcp_tool_with_project_connection_id() -> None:
    """Test _prepare_mcp_tool with project_connection_id in additional_properties."""
    mcp_tool = HostedMCPTool(
        name="Test MCP",
        url="https://example.com/mcp",
        additional_properties={"project_connection_id": "conn-123"},
    )

    result = AzureAIClient._prepare_mcp_tool(mcp_tool)  # type: ignore

    assert result["project_connection_id"] == "conn-123"
    assert "headers" not in result  # headers should not be set when project_connection_id is present


def test_prepare_mcp_tool_with_headers() -> None:
    """Test _prepare_mcp_tool with headers (no project_connection_id)."""
    mcp_tool = HostedMCPTool(
        name="Test MCP",
        url="https://example.com/mcp",
        headers={"Authorization": "Bearer token123"},
    )

    result = AzureAIClient._prepare_mcp_tool(mcp_tool)  # type: ignore

    assert result["headers"] == {"Authorization": "Bearer token123"}


def test_prepare_mcp_tool_with_allowed_tools() -> None:
    """Test _prepare_mcp_tool with allowed_tools."""
    mcp_tool = HostedMCPTool(
        name="Test MCP",
        url="https://example.com/mcp",
        allowed_tools=["tool1", "tool2"],
    )

    result = AzureAIClient._prepare_mcp_tool(mcp_tool)  # type: ignore

    assert set(result["allowed_tools"]) == {"tool1", "tool2"}


def test_prepare_mcp_tool_with_approval_mode_always_require() -> None:
    """Test _prepare_mcp_tool with string approval_mode 'always_require'."""
    mcp_tool = HostedMCPTool(
        name="Test MCP",
        url="https://example.com/mcp",
        approval_mode="always_require",
    )

    result = AzureAIClient._prepare_mcp_tool(mcp_tool)  # type: ignore

    assert result["require_approval"] == "always"


def test_prepare_mcp_tool_with_approval_mode_never_require() -> None:
    """Test _prepare_mcp_tool with string approval_mode 'never_require'."""
    mcp_tool = HostedMCPTool(
        name="Test MCP",
        url="https://example.com/mcp",
        approval_mode="never_require",
    )

    result = AzureAIClient._prepare_mcp_tool(mcp_tool)  # type: ignore

    assert result["require_approval"] == "never"


def test_prepare_mcp_tool_with_dict_approval_mode_always() -> None:
    """Test _prepare_mcp_tool with dict approval_mode containing always_require_approval."""
    mcp_tool = HostedMCPTool(
        name="Test MCP",
        url="https://example.com/mcp",
        approval_mode={"always_require_approval": {"dangerous_tool", "risky_tool"}},
    )

    result = AzureAIClient._prepare_mcp_tool(mcp_tool)  # type: ignore

    assert "require_approval" in result
    assert "always" in result["require_approval"]
    assert set(result["require_approval"]["always"]["tool_names"]) == {"dangerous_tool", "risky_tool"}


def test_prepare_mcp_tool_with_dict_approval_mode_never() -> None:
    """Test _prepare_mcp_tool with dict approval_mode containing never_require_approval."""
    mcp_tool = HostedMCPTool(
        name="Test MCP",
        url="https://example.com/mcp",
        approval_mode={"never_require_approval": {"safe_tool"}},
    )

    result = AzureAIClient._prepare_mcp_tool(mcp_tool)  # type: ignore

    assert "require_approval" in result
    assert "never" in result["require_approval"]
    assert set(result["require_approval"]["never"]["tool_names"]) == {"safe_tool"}


def test_from_azure_ai_tools() -> None:
    """Test from_azure_ai_tools."""
    # Test MCP tool
    mcp_tool = MCPTool(server_label="test_server", server_url="http://localhost:8080")
    parsed_tools = from_azure_ai_tools([mcp_tool])
    assert len(parsed_tools) == 1
    assert isinstance(parsed_tools[0], HostedMCPTool)
    assert parsed_tools[0].name == "test server"
    assert str(parsed_tools[0].url).rstrip("/") == "http://localhost:8080"

    # Test Code Interpreter tool
    ci_tool = CodeInterpreterTool(container=CodeInterpreterToolAuto(file_ids=["file-1"]))
    parsed_tools = from_azure_ai_tools([ci_tool])
    assert len(parsed_tools) == 1
    assert isinstance(parsed_tools[0], HostedCodeInterpreterTool)
    assert parsed_tools[0].inputs is not None
    assert len(parsed_tools[0].inputs) == 1

    tool_input = parsed_tools[0].inputs[0]

    assert tool_input and tool_input.type == "hosted_file" and tool_input.file_id == "file-1"

    # Test File Search tool
    fs_tool = FileSearchTool(vector_store_ids=["vs-1"], max_num_results=5)
    parsed_tools = from_azure_ai_tools([fs_tool])
    assert len(parsed_tools) == 1
    assert isinstance(parsed_tools[0], HostedFileSearchTool)
    assert parsed_tools[0].inputs is not None
    assert len(parsed_tools[0].inputs) == 1

    tool_input = parsed_tools[0].inputs[0]

    assert tool_input and tool_input.type == "hosted_vector_store" and tool_input.vector_store_id == "vs-1"
    assert parsed_tools[0].max_results == 5

    # Test Web Search tool
    ws_tool = WebSearchPreviewTool(
        user_location=ApproximateLocation(city="Seattle", country="US", region="WA", timezone="PST")
    )
    parsed_tools = from_azure_ai_tools([ws_tool])
    assert len(parsed_tools) == 1
    assert isinstance(parsed_tools[0], HostedWebSearchTool)
    assert parsed_tools[0].additional_properties

    user_location = parsed_tools[0].additional_properties["user_location"]

    assert user_location["city"] == "Seattle"
    assert user_location["country"] == "US"
    assert user_location["region"] == "WA"
    assert user_location["timezone"] == "PST"


# region Integration Tests


@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    return f"The weather in {location} is sunny with a high of 25°C."


class OutputStruct(BaseModel):
    """A structured output for testing purposes."""

    location: str
    weather: str


@fixture
async def client() -> AsyncGenerator[AzureAIClient, None]:
    """Create a client to test with."""
    agent_name = f"test-agent-{uuid4()}"
    endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        client = AzureAIClient(
            project_client=project_client,
            agent_name=agent_name,
        )
        try:
            assert client.function_invocation_configuration
            client.function_invocation_configuration.max_iterations = 1
            yield client
        finally:
            await project_client.agents.delete(agent_name=agent_name)


@pytest.mark.flaky
@skip_if_azure_ai_integration_tests_disabled
@pytest.mark.parametrize(
    "option_name,option_value,needs_validation",
    [
        # Simple ChatOptions - just verify they don't fail
        param("top_p", 0.9, False, id="top_p"),
        param("max_tokens", 500, False, id="max_tokens"),
        param("seed", 123, False, id="seed"),
        param("user", "test-user-id", False, id="user"),
        param("metadata", {"test_key": "test_value"}, False, id="metadata"),
        param("frequency_penalty", 0.5, False, id="frequency_penalty"),
        param("presence_penalty", 0.3, False, id="presence_penalty"),
        param("stop", ["END"], False, id="stop"),
        param("allow_multiple_tool_calls", True, False, id="allow_multiple_tool_calls"),
        param("tool_choice", "none", True, id="tool_choice_none"),
        param("tool_choice", "auto", True, id="tool_choice_auto"),
        param("tool_choice", "required", True, id="tool_choice_required_any"),
        param(
            "tool_choice",
            {"mode": "required", "required_function_name": "get_weather"},
            True,
            id="tool_choice_required",
        ),
        # OpenAIResponsesOptions - just verify they don't fail
        param("safety_identifier", "user-hash-abc123", False, id="safety_identifier"),
        param("truncation", "auto", False, id="truncation"),
        param("top_logprobs", 5, False, id="top_logprobs"),
        param("prompt_cache_key", "test-cache-key", False, id="prompt_cache_key"),
        param("max_tool_calls", 3, False, id="max_tool_calls"),
    ],
)
async def test_integration_options(
    option_name: str,
    option_value: Any,
    needs_validation: bool,
    client: AzureAIClient,
) -> None:
    """Parametrized test covering options that can be set at runtime for a Foundry Agent.

    Tests both streaming and non-streaming modes for each option to ensure
    they don't cause failures. Options marked with needs_validation also
    check that the feature actually works correctly.

    This test reuses a single agent.
    """
    # Prepare test message
    if option_name.startswith("tool_choice"):
        # Use weather-related prompt for tool tests
        messages = [ChatMessage(role="user", text="What is the weather in Seattle?")]
    else:
        # Generic prompt for simple options
        messages = [ChatMessage(role="user", text="Say 'Hello World' briefly.")]

    # Build options dict
    options: dict[str, Any] = {option_name: option_value, "tools": [get_weather]}

    for streaming in [False, True]:
        if streaming:
            # Test streaming mode
            response_gen = client.get_streaming_response(
                messages=messages,
                options=options,
            )

            output_format = option_value if option_name == "response_format" else None
            response = await ChatResponse.from_chat_response_generator(response_gen, output_format_type=output_format)
        else:
            # Test non-streaming mode
            response = await client.get_response(
                messages=messages,
                options=options,
            )

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert response.text is not None, f"No text in response for option '{option_name}'"
        assert len(response.text) > 0, f"Empty response for option '{option_name}'"

        # Validate based on option type
        if needs_validation:
            if option_name.startswith("tool_choice"):
                # Should have called the weather function
                text = response.text.lower()
                assert "sunny" in text or "seattle" in text, f"Tool not invoked for {option_name}"
            elif option_name == "response_format":
                if option_value == OutputStruct:
                    # Should have structured output
                    assert response.value is not None, "No structured output"
                    assert isinstance(response.value, OutputStruct)
                    assert "seattle" in response.value.location.lower()
                else:
                    # Runtime JSON schema
                    assert response.value is None, "No structured output, can't parse any json."
                    response_value = json.loads(response.text)
                    assert isinstance(response_value, dict)
                    assert "location" in response_value
                    assert "seattle" in response_value["location"].lower()


@pytest.mark.flaky
@skip_if_azure_ai_integration_tests_disabled
@pytest.mark.parametrize(
    "option_name,option_value,needs_validation",
    [
        param("temperature", 0.7, False, id="temperature"),
        # Complex options requiring output validation
        param("response_format", OutputStruct, True, id="response_format_pydantic"),
        param(
            "response_format",
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "WeatherDigest",
                    "strict": True,
                    "schema": {
                        "title": "WeatherDigest",
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"},
                            "conditions": {"type": "string"},
                            "temperature_c": {"type": "number"},
                            "advisory": {"type": "string"},
                        },
                        "required": ["location", "conditions", "temperature_c", "advisory"],
                        "additionalProperties": False,
                    },
                },
            },
            True,
            id="response_format_runtime_json_schema",
        ),
    ],
)
async def test_integration_agent_options(
    option_name: str,
    option_value: Any,
    needs_validation: bool,
) -> None:
    """Test Foundry agent level options in both streaming and non-streaming modes.

    Tests both streaming and non-streaming modes for each option to ensure
    they don't cause failures. Options marked with needs_validation also
    check that the feature actually works correctly.

    This test create a new client and uses it for both streaming and non-streaming tests.
    """
    async with temporary_chat_client(agent_name=f"test-agent-{option_name.replace('_', '-')}-{uuid4()}") as client:
        for streaming in [False, True]:
            # Prepare test message
            if option_name.startswith("response_format"):
                # Use prompt that works well with structured output
                messages = [ChatMessage(role="user", text="The weather in Seattle is sunny")]
                messages.append(ChatMessage(role="user", text="What is the weather in Seattle?"))
            else:
                # Generic prompt for simple options
                messages = [ChatMessage(role="user", text="Say 'Hello World' briefly.")]

            # Build options dict
            options = {option_name: option_value}

            if streaming:
                # Test streaming mode
                response_gen = client.get_streaming_response(
                    messages=messages,
                    options=options,
                )

                output_format = option_value if option_name.startswith("response_format") else None
                response = await ChatResponse.from_chat_response_generator(
                    response_gen, output_format_type=output_format
                )
            else:
                # Test non-streaming mode
                response = await client.get_response(
                    messages=messages,
                    options=options,
                )

            assert response is not None
            assert isinstance(response, ChatResponse)
            assert response.text is not None, f"No text in response for option '{option_name}'"
            assert len(response.text) > 0, f"Empty response for option '{option_name}'"

            # Validate based on option type
            if needs_validation and option_name.startswith("response_format"):
                if option_value == OutputStruct:
                    # Should have structured output
                    assert response.value is not None, "No structured output"
                    assert isinstance(response.value, OutputStruct)
                    assert "seattle" in response.value.location.lower()
                else:
                    # Runtime JSON schema
                    assert response.value is None, "No structured output, can't parse any json."
                    response_value = json.loads(response.text)
                    assert isinstance(response_value, dict)
                    assert "location" in response_value
                    assert "seattle" in response_value["location"].lower()


@pytest.mark.flaky
@skip_if_azure_ai_integration_tests_disabled
async def test_integration_web_search() -> None:
    async with temporary_chat_client(agent_name="af-int-test-web-search") as client:
        for streaming in [False, True]:
            content = {
                "messages": "Who are the main characters of Kpop Demon Hunters? Do a web search to find the answer.",
                "options": {
                    "tool_choice": "auto",
                    "tools": [HostedWebSearchTool()],
                },
            }
            if streaming:
                response = await ChatResponse.from_chat_response_generator(client.get_streaming_response(**content))
            else:
                response = await client.get_response(**content)

            assert response is not None
            assert isinstance(response, ChatResponse)
            assert "Rumi" in response.text
            assert "Mira" in response.text
            assert "Zoey" in response.text

            # Test that the client will use the web search tool with location
            additional_properties = {
                "user_location": {
                    "country": "US",
                    "city": "Seattle",
                }
            }
            content = {
                "messages": "What is the current weather? Do not ask for my current location.",
                "options": {
                    "tool_choice": "auto",
                    "tools": [HostedWebSearchTool(additional_properties=additional_properties)],
                },
            }
            if streaming:
                response = await ChatResponse.from_chat_response_generator(client.get_streaming_response(**content))
            else:
                response = await client.get_response(**content)
            assert response.text is not None


@pytest.mark.flaky
@skip_if_azure_ai_integration_tests_disabled
async def test_integration_agent_hosted_mcp_tool() -> None:
    """Integration test for HostedMCPTool with Azure Response Agent using Microsoft Learn MCP."""
    async with temporary_chat_client(agent_name="af-int-test-mcp") as client:
        response = await client.get_response(
            "How to create an Azure storage account using az cli?",
            options={
                # this needs to be high enough to handle the full MCP tool response.
                "max_tokens": 5000,
                "tools": HostedMCPTool(
                    name="Microsoft Learn MCP",
                    url="https://learn.microsoft.com/api/mcp",
                    description="A Microsoft Learn MCP server for documentation questions",
                    approval_mode="never_require",
                ),
            },
        )
        assert isinstance(response, ChatResponse)
        assert response.text
        # Should contain Azure-related content since it's asking about Azure CLI
        assert any(term in response.text.lower() for term in ["azure", "storage", "account", "cli"])


@pytest.mark.flaky
@skip_if_azure_ai_integration_tests_disabled
async def test_integration_agent_hosted_code_interpreter_tool():
    """Test Azure Responses Client agent with HostedCodeInterpreterTool through AzureAIClient."""
    async with temporary_chat_client(agent_name="af-int-test-code-interpreter") as client:
        response = await client.get_response(
            "Calculate the sum of numbers from 1 to 10 using Python code.",
            options={
                "tools": [HostedCodeInterpreterTool()],
            },
        )
        # Should contain calculation result (sum of 1-10 = 55) or code execution content
        contains_relevant_content = any(
            term in response.text.lower() for term in ["55", "sum", "code", "python", "calculate", "10"]
        )
        assert contains_relevant_content or len(response.text.strip()) > 10


@pytest.mark.flaky
@skip_if_azure_ai_integration_tests_disabled
async def test_integration_agent_existing_thread():
    """Test Azure Responses Client agent with existing thread to continue conversations across agent instances."""
    # First conversation - capture the thread
    preserved_thread = None

    async with (
        temporary_chat_client(agent_name="af-int-test-existing-thread") as client,
        ChatAgent(
            chat_client=client,
            instructions="You are a helpful assistant with good memory.",
        ) as first_agent,
    ):
        # Start a conversation and capture the thread
        thread = first_agent.get_new_thread()
        first_response = await first_agent.run("My hobby is photography. Remember this.", thread=thread, store=True)

        assert isinstance(first_response, AgentResponse)
        assert first_response.text is not None

        # Preserve the thread for reuse
        preserved_thread = thread

    # Second conversation - reuse the thread in a new agent instance
    if preserved_thread:
        async with (
            temporary_chat_client(agent_name="af-int-test-existing-thread-2") as client,
            ChatAgent(
                chat_client=client,
                instructions="You are a helpful assistant with good memory.",
            ) as second_agent,
        ):
            # Reuse the preserved thread
            second_response = await second_agent.run("What is my hobby?", thread=preserved_thread)

            assert isinstance(second_response, AgentResponse)
            assert second_response.text is not None
            assert "photography" in second_response.text.lower()
