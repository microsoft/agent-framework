# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import MagicMock

import pytest
from agent_framework import ChatClient, ChatMessage, ChatOptions, ChatRole
from agent_framework.exceptions import ServiceInitializationError

from agent_framework_foundry import FoundryChatClient, FoundrySettings


def create_test_foundry_chat_client(
    mock_ai_project_client: MagicMock,
    agent_id: str | None = None,
    thread_id: str | None = None,
    foundry_settings: FoundrySettings | None = None,
    should_delete_agent: bool = False,
) -> FoundryChatClient:
    """Helper function to create FoundryChatClient instances for testing, bypassing Pydantic validation."""
    if foundry_settings is None:
        foundry_settings = FoundrySettings()

    return FoundryChatClient.model_construct(
        client=mock_ai_project_client,
        agent_id=agent_id,
        thread_id=thread_id,
        _should_delete_agent=should_delete_agent,
        _foundry_settings=foundry_settings,
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
    )

    assert chat_client.client is mock_ai_project_client
    assert chat_client.agent_id is None
    assert not chat_client._should_delete_agent  # type: ignore


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


async def test_foundry_chat_client_get_agent_id_or_create_missing_model(
    mock_ai_project_client: MagicMock,
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


def test_foundry_chat_client_convert_function_results_to_tool_output(mock_ai_project_client: MagicMock) -> None:
    """Test _convert_function_results_to_tool_output method."""
    from agent_framework import FunctionResultContent

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
