# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import inspect
import os
import sys
from functools import wraps
from pathlib import Path
from typing import Annotated, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import ChatResponse, Content, Message, SupportsChatGetResponse, tool
from agent_framework._telemetry import get_user_agent
from agent_framework.exceptions import ChatClientException, ChatClientInvalidRequestException
from agent_framework_openai import OpenAIContentFilterException
from azure.ai.projects.models import MCPTool as FoundryMCPTool
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import AzureCliCredential
from openai import BadRequestError
from pydantic import BaseModel
from pytest import param

from agent_framework_foundry import FoundryChatClient, RawFoundryChatClient


class OutputStruct(BaseModel):
    """A structured output for testing purposes."""

    location: str
    weather: str | None = None


@tool(approval_mode="never_require")
async def get_weather(location: Annotated[str, "The location as a city name"]) -> str:
    """Get the current weather in a given location."""
    return f"The current weather in {location} is sunny."


skip_if_foundry_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("FOUNDRY_PROJECT_ENDPOINT", "") in ("", "https://test-project.services.ai.azure.com/")
    or os.getenv("FOUNDRY_MODEL", "") == "",
    reason="No real FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_MODEL provided; skipping integration tests.",
)

_TEST_FOUNDRY_PROJECT_ENDPOINT = "https://test-project.services.ai.azure.com/"
_TEST_FOUNDRY_MODEL = "test-gpt-4o"
_FOUNDRY_CHAT_ENV_VARS = ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL")


@pytest.fixture(autouse=True)
def clear_foundry_chat_settings_env(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Prevent unit tests from inheriting Foundry chat settings from the shell."""

    if request.node.get_closest_marker("integration") is not None:
        return

    for env_var in _FOUNDRY_CHAT_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)


def _with_foundry_debug() -> Any:
    def decorator(func: Any) -> Any:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                debug_message = (
                    "Foundry debug: "
                    f"project_endpoint={os.getenv('FOUNDRY_PROJECT_ENDPOINT', '<unset>')}, "
                    f"model={os.getenv('FOUNDRY_MODEL', '<unset>')}"
                )
                if hasattr(exc, "add_note"):
                    exc.add_note(debug_message)
                elif exc.args:
                    exc.args = (f"{exc.args[0]}\n{debug_message}", *exc.args[1:])
                else:
                    exc.args = (debug_message,)
                raise

        return wrapper

    return decorator


def _make_mock_openai_client() -> MagicMock:
    client = MagicMock()
    client.default_headers = {}
    client.responses = MagicMock()
    client.responses.create = AsyncMock()
    client.responses.parse = AsyncMock()
    client.files = MagicMock()
    client.files.create = AsyncMock()
    client.files.delete = AsyncMock()
    client.vector_stores = MagicMock()
    client.vector_stores.create = AsyncMock()
    client.vector_stores.delete = AsyncMock()
    client.vector_stores.files = MagicMock()
    client.vector_stores.files.create_and_poll = AsyncMock()
    return client


async def create_vector_store(client: FoundryChatClient) -> tuple[str, Content]:
    """Create a vector store with sample documents for testing."""
    file = await client.client.files.create(
        file=("todays_weather.txt", b"The weather today is sunny with a high of 75F."),
        purpose="user_data",
    )
    vector_store = await client.client.vector_stores.create(
        name="knowledge_base",
        expires_after={"anchor": "last_active_at", "days": 1},
    )
    result = await client.client.vector_stores.files.create_and_poll(
        vector_store_id=vector_store.id,
        file_id=file.id,
        poll_interval_ms=1000,
    )
    if result.last_error is not None:
        raise RuntimeError(f"Vector store file processing failed with status: {result.last_error.message}")

    return file.id, Content.from_hosted_vector_store(vector_store_id=vector_store.id)


async def delete_vector_store(client: FoundryChatClient, file_id: str, vector_store_id: str) -> None:
    """Delete the vector store after tests."""
    await client.client.vector_stores.delete(vector_store_id=vector_store_id)
    await client.client.files.delete(file_id=file_id)


def test_init() -> None:
    mock_openai_client = _make_mock_openai_client()
    mock_project_client = MagicMock()
    mock_project_client.get_openai_client.return_value = mock_openai_client

    client = FoundryChatClient(project_client=mock_project_client, model=_TEST_FOUNDRY_MODEL)

    assert client.model == _TEST_FOUNDRY_MODEL
    assert isinstance(client, SupportsChatGetResponse)
    assert client.project_client is mock_project_client


def test_raw_foundry_chat_client_init_uses_explicit_parameters() -> None:
    signature = inspect.signature(RawFoundryChatClient.__init__)

    assert "default_headers" in signature.parameters
    assert "compaction_strategy" in signature.parameters
    assert "tokenizer" in signature.parameters
    assert "additional_properties" in signature.parameters
    assert all(parameter.kind != inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())


def test_foundry_chat_client_init_uses_explicit_parameters() -> None:
    signature = inspect.signature(FoundryChatClient.__init__)

    assert "default_headers" in signature.parameters
    assert "compaction_strategy" in signature.parameters
    assert "tokenizer" in signature.parameters
    assert "additional_properties" in signature.parameters
    assert all(parameter.kind != inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())


def test_init_with_default_header() -> None:
    default_headers = {"X-Unit-Test": "test-guid"}
    mock_openai_client = _make_mock_openai_client()
    project_client = MagicMock()
    project_client.get_openai_client.return_value = mock_openai_client

    client = FoundryChatClient(
        project_client=project_client,
        model=_TEST_FOUNDRY_MODEL,
        default_headers=default_headers,
    )

    assert client.model == _TEST_FOUNDRY_MODEL
    for key, value in default_headers.items():
        assert client.default_headers is not None
        assert key in client.default_headers
        assert client.default_headers[key] == value


def test_init_with_project_endpoint_creates_project_client() -> None:
    credential = MagicMock()
    mock_openai_client = _make_mock_openai_client()
    project_client = MagicMock()
    project_client.get_openai_client.return_value = mock_openai_client

    with patch("agent_framework_foundry._chat_client.AIProjectClient", return_value=project_client) as factory:
        client = FoundryChatClient(
            project_endpoint=_TEST_FOUNDRY_PROJECT_ENDPOINT,
            model=_TEST_FOUNDRY_MODEL,
            credential=credential,
            allow_preview=True,
        )

    assert client.project_client is project_client
    assert client.model == _TEST_FOUNDRY_MODEL
    assert factory.call_args.kwargs["endpoint"] == _TEST_FOUNDRY_PROJECT_ENDPOINT
    assert factory.call_args.kwargs["credential"] is credential
    assert factory.call_args.kwargs["allow_preview"] is True
    assert factory.call_args.kwargs["user_agent"] == get_user_agent()


def test_init_with_empty_model_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FOUNDRY_MODEL", raising=False)
    mock_openai_client = _make_mock_openai_client()
    mock_project_client = MagicMock()
    mock_project_client.get_openai_client.return_value = mock_openai_client

    with pytest.raises(ValueError, match="Model is required"):
        FoundryChatClient(project_client=mock_project_client)


def test_init_with_empty_project_source_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)

    with pytest.raises(ValueError, match="Either 'project_endpoint' or 'project_client' is required"):
        FoundryChatClient(model=_TEST_FOUNDRY_MODEL)


def test_init_with_project_endpoint_requires_credential() -> None:
    with pytest.raises(ValueError, match="Azure credential is required"):
        FoundryChatClient(
            project_endpoint=_TEST_FOUNDRY_PROJECT_ENDPOINT,
            model=_TEST_FOUNDRY_MODEL,
        )


async def test_configure_azure_monitor() -> None:
    mock_openai_client = _make_mock_openai_client()
    project_client = MagicMock()
    project_client.get_openai_client.return_value = mock_openai_client
    project_client.telemetry.get_application_insights_connection_string = AsyncMock(
        return_value="InstrumentationKey=test-key;IngestionEndpoint=https://test.endpoint"
    )
    client = FoundryChatClient(project_client=project_client, model=_TEST_FOUNDRY_MODEL)

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

    project_client.telemetry.get_application_insights_connection_string.assert_called_once()
    mock_configure.assert_called_once()
    call_kwargs = mock_configure.call_args.kwargs
    assert call_kwargs["connection_string"] == "InstrumentationKey=test-key;IngestionEndpoint=https://test.endpoint"
    assert call_kwargs["views"] == []
    assert call_kwargs["resource"] is mock_resource
    mock_enable.assert_called_once_with(enable_sensitive_data=True)


async def test_configure_azure_monitor_resource_not_found() -> None:
    mock_openai_client = _make_mock_openai_client()
    project_client = MagicMock()
    project_client.get_openai_client.return_value = mock_openai_client
    project_client.telemetry.get_application_insights_connection_string = AsyncMock(
        side_effect=ResourceNotFoundError("No Application Insights found")
    )
    client = FoundryChatClient(project_client=project_client, model=_TEST_FOUNDRY_MODEL)

    await client.configure_azure_monitor()

    project_client.telemetry.get_application_insights_connection_string.assert_called_once()


async def test_configure_azure_monitor_import_error() -> None:
    mock_openai_client = _make_mock_openai_client()
    project_client = MagicMock()
    project_client.get_openai_client.return_value = mock_openai_client
    project_client.telemetry.get_application_insights_connection_string = AsyncMock(
        return_value="InstrumentationKey=test-key"
    )
    client = FoundryChatClient(project_client=project_client, model=_TEST_FOUNDRY_MODEL)
    original_import = __import__

    def _import_with_missing_azure_monitor(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "azure.monitor.opentelemetry":
            raise ImportError("No module named 'azure.monitor.opentelemetry'")
        return original_import(name, globals, locals, fromlist, level)

    with (
        patch.dict(sys.modules, {"azure.monitor.opentelemetry": None}),
        patch("builtins.__import__", side_effect=_import_with_missing_azure_monitor),
        pytest.raises(ImportError, match="azure-monitor-opentelemetry is required"),
    ):
        await client.configure_azure_monitor()


async def test_configure_azure_monitor_with_custom_resource() -> None:
    mock_openai_client = _make_mock_openai_client()
    project_client = MagicMock()
    project_client.get_openai_client.return_value = mock_openai_client
    project_client.telemetry.get_application_insights_connection_string = AsyncMock(
        return_value="InstrumentationKey=test-key"
    )
    client = FoundryChatClient(project_client=project_client, model=_TEST_FOUNDRY_MODEL)

    custom_resource = MagicMock()
    mock_configure = MagicMock()

    with (
        patch.dict(
            "sys.modules",
            {"azure.monitor.opentelemetry": MagicMock(configure_azure_monitor=mock_configure)},
        ),
        patch("agent_framework.observability.create_metric_views", return_value=[]),
        patch("agent_framework.observability.create_resource") as mock_create_resource,
        patch("agent_framework.observability.enable_instrumentation"),
    ):
        await client.configure_azure_monitor(resource=custom_resource)

    mock_create_resource.assert_not_called()
    call_kwargs = mock_configure.call_args.kwargs
    assert call_kwargs["resource"] is custom_resource


async def test_get_response_with_invalid_input() -> None:
    mock_openai_client = _make_mock_openai_client()
    project_client = MagicMock()
    project_client.get_openai_client.return_value = mock_openai_client
    client = FoundryChatClient(project_client=project_client, model="test-model")

    with pytest.raises(ChatClientInvalidRequestException, match="Messages are required"):
        await client.get_response(messages=[])


async def test_web_search_tool_with_location() -> None:
    mock_openai_client = _make_mock_openai_client()
    project_client = MagicMock()
    project_client.get_openai_client.return_value = mock_openai_client
    client = FoundryChatClient(project_client=project_client, model="test-model")

    web_search_tool = FoundryChatClient.get_web_search_tool(
        user_location={
            "city": "Seattle",
            "country": "US",
            "region": "WA",
            "timezone": "America/Los_Angeles",
        }
    )

    assert web_search_tool.user_location.city == "Seattle"
    assert web_search_tool.user_location.country == "US"
    _, run_options, _ = await client._prepare_request(
        messages=[Message(role="user", contents=["What's the weather?"])],
        options={"tools": [web_search_tool], "tool_choice": "auto"},
    )

    assert run_options["tools"] == [web_search_tool]
    assert run_options["tool_choice"] == "auto"


async def test_code_interpreter_tool_variations() -> None:
    mock_openai_client = _make_mock_openai_client()
    project_client = MagicMock()
    project_client.get_openai_client.return_value = mock_openai_client
    client = FoundryChatClient(project_client=project_client, model="test-model")

    code_tool = FoundryChatClient.get_code_interpreter_tool()
    assert code_tool.container["type"] == "auto"

    _, run_options, _ = await client._prepare_request(
        messages=[Message("user", ["Run some code"])],
        options={"tools": [code_tool]},
    )

    assert run_options["tools"] == [code_tool]

    code_tool_with_files = FoundryChatClient.get_code_interpreter_tool(file_ids=["file1", "file2"])
    assert code_tool_with_files.container.file_ids == ["file1", "file2"]

    _, run_options, _ = await client._prepare_request(
        messages=[Message(role="user", contents=["Process these files"])],
        options={"tools": [code_tool_with_files]},
    )

    assert run_options["tools"] == [code_tool_with_files]


async def test_hosted_file_search_tool_validation() -> None:
    mock_openai_client = _make_mock_openai_client()
    project_client = MagicMock()
    project_client.get_openai_client.return_value = mock_openai_client
    client = FoundryChatClient(project_client=project_client, model="test-model")

    with pytest.raises(ValueError, match="vector_store_ids"):
        FoundryChatClient.get_file_search_tool(vector_store_ids=[])

    file_search_tool = FoundryChatClient.get_file_search_tool(vector_store_ids=["vs_123"])
    assert file_search_tool.vector_store_ids == ["vs_123"]

    _, run_options, _ = await client._prepare_request(
        messages=[Message("user", ["Test"])],
        options={"tools": [file_search_tool]},
    )

    assert run_options["tools"] == [file_search_tool]


async def test_chat_message_parsing_with_function_calls() -> None:
    mock_openai_client = _make_mock_openai_client()
    project_client = MagicMock()
    project_client.get_openai_client.return_value = mock_openai_client
    client = FoundryChatClient(project_client=project_client, model="test-model")

    function_call = Content.from_function_call(
        call_id="test-call-id",
        name="test_function",
        arguments='{"param": "value"}',
        additional_properties={"fc_id": "test-fc-id"},
    )
    function_result = Content.from_function_result(call_id="test-call-id", result="Function executed successfully")
    messages = [
        Message(role="user", contents=["Call a function"]),
        Message(role="assistant", contents=[function_call]),
        Message(role="tool", contents=[function_result]),
    ]

    prepared_messages = client._prepare_messages_for_openai(messages)

    assert prepared_messages == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Call a function"}],
        },
        {
            "call_id": "test-call-id",
            "id": "fc_test-fc-id",
            "type": "function_call",
            "name": "test_function",
            "arguments": '{"param": "value"}',
        },
        {
            "call_id": "test-call-id",
            "type": "function_call_output",
            "output": "Function executed successfully",
        },
    ]


async def test_content_filter_exception() -> None:
    mock_openai_client = _make_mock_openai_client()
    project_client = MagicMock()
    project_client.get_openai_client.return_value = mock_openai_client
    client = FoundryChatClient(project_client=project_client, model="test-model")

    mock_error = BadRequestError(
        message="Content filter error",
        response=MagicMock(),
        body={"error": {"code": "content_filter", "message": "Content filter error"}},
    )
    mock_error.code = "content_filter"
    client.client.responses.create.side_effect = mock_error

    with pytest.raises(OpenAIContentFilterException) as exc_info:
        await client.get_response(messages=[Message(role="user", contents=["Test message"])])

    assert "content error" in str(exc_info.value)


async def test_response_format_parse_path() -> None:
    mock_openai_client = _make_mock_openai_client()
    project_client = MagicMock()
    project_client.get_openai_client.return_value = mock_openai_client
    client = FoundryChatClient(project_client=project_client, model="test-model")

    mock_parsed_response = MagicMock()
    mock_parsed_response.id = "parsed_response_123"
    mock_parsed_response.text = "Parsed response"
    mock_parsed_response.model = "test-model"
    mock_parsed_response.created_at = 1000000000
    mock_parsed_response.metadata = {}
    mock_parsed_response.output_parsed = None
    mock_parsed_response.usage = None
    mock_parsed_response.finish_reason = None
    mock_parsed_response.conversation = None
    client.client.responses.parse = AsyncMock(return_value=mock_parsed_response)

    response = await client.get_response(
        messages=[Message(role="user", contents=["Test message"])],
        options={"response_format": OutputStruct, "store": True},
    )
    assert response.response_id == "parsed_response_123"
    assert response.conversation_id == "parsed_response_123"
    assert response.model == "test-model"


async def test_response_format_parse_path_with_conversation_id() -> None:
    mock_openai_client = _make_mock_openai_client()
    project_client = MagicMock()
    project_client.get_openai_client.return_value = mock_openai_client
    client = FoundryChatClient(project_client=project_client, model="test-model")

    mock_parsed_response = MagicMock()
    mock_parsed_response.id = "parsed_response_123"
    mock_parsed_response.text = "Parsed response"
    mock_parsed_response.model = "test-model"
    mock_parsed_response.created_at = 1000000000
    mock_parsed_response.metadata = {}
    mock_parsed_response.output_parsed = None
    mock_parsed_response.usage = None
    mock_parsed_response.finish_reason = None
    mock_parsed_response.conversation = MagicMock()
    mock_parsed_response.conversation.id = "conversation_456"
    client.client.responses.parse = AsyncMock(return_value=mock_parsed_response)

    response = await client.get_response(
        messages=[Message(role="user", contents=["Test message"])],
        options={"response_format": OutputStruct, "store": True},
    )
    assert response.response_id == "parsed_response_123"
    assert response.conversation_id == "conversation_456"
    assert response.model == "test-model"


async def test_response_format_dict_parse_path() -> None:
    mock_openai_client = _make_mock_openai_client()
    project_client = MagicMock()
    project_client.get_openai_client.return_value = mock_openai_client
    client = FoundryChatClient(project_client=project_client, model="test-model")
    response_format = {"type": "object", "properties": {"answer": {"type": "string"}}}

    mock_response = MagicMock()
    mock_response.id = "response_123"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000
    mock_response.metadata = {}
    mock_response.output_parsed = None
    mock_response.output = []
    mock_response.usage = None
    mock_response.finish_reason = None
    mock_response.conversation = None
    mock_response.status = "completed"

    mock_message_content = MagicMock()
    mock_message_content.type = "output_text"
    mock_message_content.text = '{"answer": "Parsed"}'
    mock_message_content.annotations = []
    mock_message_content.logprobs = None

    mock_message_item = MagicMock()
    mock_message_item.type = "message"
    mock_message_item.content = [mock_message_content]
    mock_response.output = [mock_message_item]
    client.client.responses.create = AsyncMock(return_value=mock_response)

    response = await client.get_response(
        messages=[Message(role="user", contents=["Test message"])],
        options={"response_format": response_format},
    )

    assert response.response_id == "response_123"
    assert response.value is not None
    assert isinstance(response.value, dict)
    assert response.value["answer"] == "Parsed"


async def test_bad_request_error_non_content_filter() -> None:
    mock_openai_client = _make_mock_openai_client()
    project_client = MagicMock()
    project_client.get_openai_client.return_value = mock_openai_client
    client = FoundryChatClient(project_client=project_client, model="test-model")

    mock_error = BadRequestError(
        message="Invalid request",
        response=MagicMock(),
        body={"error": {"code": "invalid_request", "message": "Invalid request"}},
    )
    mock_error.code = "invalid_request"
    client.client.responses.parse = AsyncMock(side_effect=mock_error)

    with pytest.raises(ChatClientException) as exc_info:
        await client.get_response(
            messages=[Message(role="user", contents=["Test message"])],
            options={"response_format": OutputStruct},
        )

    assert "failed to complete the prompt" in str(exc_info.value)


def test_get_mcp_tool_with_project_connection_id() -> None:
    tool_config = FoundryChatClient.get_mcp_tool(
        name="Docs MCP",
        project_connection_id="conn-123",
        allowed_tools=["search_docs"],
    )

    assert tool_config["project_connection_id"] == "conn-123"
    assert tool_config["allowed_tools"] == ["search_docs"]
    assert tool_config["server_label"] == "Docs_MCP"
    # ``server_url`` should not be fabricated when only a project connection is supplied.
    assert "server_url" not in tool_config


def test_get_mcp_tool_requires_url_or_project_connection_id() -> None:
    """Missing both ``url`` and ``project_connection_id`` is always invalid."""
    with pytest.raises(ValueError, match="url.*project_connection_id"):
        FoundryChatClient.get_mcp_tool(name="x")


def test_prepare_tools_for_openai_strips_extraneous_name_from_foundry_mcp_tool() -> None:
    """Toolbox-returned MCP tools may carry ``name``; Foundry Responses rejects it."""
    project_client = MagicMock()
    project_client.get_openai_client.return_value = _make_mock_openai_client()
    client = FoundryChatClient(project_client=project_client, model="test-model")

    tool = FoundryMCPTool(
        server_label="githubmcp",
        server_url="https://api.githubcopilot.com/mcp",
    )
    tool["project_connection_id"] = "githubmcp"
    tool["name"] = "githubmcp"

    response_tools = client._prepare_tools_for_openai([tool])

    assert len(response_tools) == 1
    prepared = response_tools[0]
    assert prepared["type"] == "mcp"
    assert prepared["server_label"] == "githubmcp"
    assert prepared["project_connection_id"] == "githubmcp"
    assert "name" not in prepared


def test_prepare_tools_for_openai_strips_read_model_fields_from_toolbox_code_interpreter() -> None:
    """Toolbox-returned code interpreter tools may carry read-model-only name/description."""
    project_client = MagicMock()
    project_client.get_openai_client.return_value = _make_mock_openai_client()
    client = FoundryChatClient(project_client=project_client, model="test-model")

    tool = {
        "type": "code_interpreter",
        "name": "code_interpreter_t6bbtm",
        "description": "Toolbox read model description",
        "container": {"file_ids": [], "type": "auto"},
    }

    response_tools = client._prepare_tools_for_openai([tool])

    assert len(response_tools) == 1
    prepared = response_tools[0]
    assert prepared["type"] == "code_interpreter"
    assert prepared["container"] == {"file_ids": [], "type": "auto"}
    assert "name" not in prepared
    assert "description" not in prepared


def test_prepare_tools_for_openai_injects_default_container_for_code_interpreter_dict() -> None:
    """Toolbox-returned code_interpreter without a container must get a default injected.

    The Azure SDK treats ``container`` as optional, but the Responses API rejects
    ``code_interpreter`` entries without one. The sanitizer backfills ``{"type": "auto"}``.
    """
    project_client = MagicMock()
    project_client.get_openai_client.return_value = _make_mock_openai_client()
    client = FoundryChatClient(project_client=project_client, model="test-model")

    tool = {
        "type": "code_interpreter",
        "name": "code_interpreter_t6bbtm",
    }

    response_tools = client._prepare_tools_for_openai([tool])

    assert len(response_tools) == 1
    prepared = response_tools[0]
    assert prepared["type"] == "code_interpreter"
    assert prepared["container"] == {"type": "auto"}
    assert "name" not in prepared


def test_prepare_tools_for_openai_injects_default_container_for_code_interpreter_sdk_instance() -> None:
    """SDK ``CodeInterpreterTool`` instances without a container must also be backfilled.

    Reproduces the toolbox creation path that calls
    ``CodeInterpreterTool(name="code_interpreter")`` without a container.
    """
    from azure.ai.projects.models import CodeInterpreterTool

    project_client = MagicMock()
    project_client.get_openai_client.return_value = _make_mock_openai_client()
    client = FoundryChatClient(project_client=project_client, model="test-model")

    response_tools = client._prepare_tools_for_openai([CodeInterpreterTool(name="code_interpreter")])

    assert len(response_tools) == 1
    prepared = response_tools[0]
    assert prepared["type"] == "code_interpreter"
    assert prepared["container"] == {"type": "auto"}
    assert "name" not in prepared


def test_prepare_tools_for_openai_preserves_existing_code_interpreter_container() -> None:
    """An already-populated container must not be overwritten by the sanitizer."""
    project_client = MagicMock()
    project_client.get_openai_client.return_value = _make_mock_openai_client()
    client = FoundryChatClient(project_client=project_client, model="test-model")

    explicit_container = {"file_ids": ["file_123"], "type": "auto"}
    tool = {"type": "code_interpreter", "container": explicit_container}

    response_tools = client._prepare_tools_for_openai([tool])

    assert response_tools[0]["container"] == explicit_container


def test_prepare_tools_for_openai_rejects_file_search_without_vector_store_ids() -> None:
    """``file_search`` without ``vector_store_ids`` is always invalid — surface a clear error."""
    project_client = MagicMock()
    project_client.get_openai_client.return_value = _make_mock_openai_client()
    client = FoundryChatClient(project_client=project_client, model="test-model")

    with pytest.raises(ValueError, match="vector_store_ids"):
        client._prepare_tools_for_openai([{"type": "file_search", "name": "fs"}])


def test_prepare_tools_for_openai_rejects_mcp_without_server_destination() -> None:
    """``mcp`` with neither ``server_url`` nor ``project_connection_id`` is always invalid."""
    project_client = MagicMock()
    project_client.get_openai_client.return_value = _make_mock_openai_client()
    client = FoundryChatClient(project_client=project_client, model="test-model")

    tool = FoundryMCPTool(server_label="orphan")

    with pytest.raises(ValueError, match="server_url.*project_connection_id"):
        client._prepare_tools_for_openai([tool])


def test_prepare_tools_for_openai_accepts_mcp_with_only_project_connection_id() -> None:
    """MCP tools backed by a Foundry connection (no ``server_url``) must still pass validation."""
    project_client = MagicMock()
    project_client.get_openai_client.return_value = _make_mock_openai_client()
    client = FoundryChatClient(project_client=project_client, model="test-model")

    tool = FoundryMCPTool(server_label="githubmcp")
    tool["project_connection_id"] = "githubmcp"

    response_tools = client._prepare_tools_for_openai([tool])

    assert len(response_tools) == 1
    assert response_tools[0]["project_connection_id"] == "githubmcp"
    assert "server_url" not in response_tools[0]


def test_prepare_tools_for_openai_strips_name_from_non_function_hosted_tool_dicts() -> None:
    """All non-function hosted tool payloads should drop top-level read-model names."""
    project_client = MagicMock()
    project_client.get_openai_client.return_value = _make_mock_openai_client()
    client = FoundryChatClient(project_client=project_client, model="test-model")

    response_tools = client._prepare_tools_for_openai([
        {
            "type": "file_search",
            "name": "file_search_tool_123",
            "description": "toolbox decoration",
            "vector_store_ids": ["vs_123"],
        },
        {
            "type": "web_search",
            "name": "web_search_tool_456",
            "description": "toolbox decoration",
        },
    ])

    assert len(response_tools) == 2
    assert response_tools[0]["type"] == "file_search"
    assert response_tools[0]["vector_store_ids"] == ["vs_123"]
    assert "name" not in response_tools[0]
    assert "description" not in response_tools[0]
    assert response_tools[1]["type"] == "web_search"
    assert "name" not in response_tools[1]
    assert "description" not in response_tools[1]


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_foundry_integration_tests_disabled
@pytest.mark.parametrize(
    "option_name,option_value,needs_validation",
    [
        param("max_tokens", 500, False, id="max_tokens"),
        param("seed", 123, False, id="seed"),
        param("user", "test-user-id", False, id="user"),
        param("metadata", {"test_key": "test_value"}, False, id="metadata"),
        param("tool_choice", "none", True, id="tool_choice_none"),
        param("tools", [get_weather], True, id="tools_function"),
        param("tool_choice", "auto", True, id="tool_choice_auto"),
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
                        },
                        "required": ["location", "conditions"],
                        "additionalProperties": False,
                    },
                },
            },
            True,
            id="response_format_runtime_json_schema",
        ),
    ],
)
@_with_foundry_debug()
async def test_integration_options(
    option_name: str,
    option_value: Any,
    needs_validation: bool,
) -> None:
    client = FoundryChatClient(credential=AzureCliCredential())
    client.function_invocation_configuration["max_iterations"] = 2

    if option_name.startswith("tools") or option_name.startswith("tool_choice"):
        messages = [Message(role="user", contents=["What is the weather in Seattle?"])]
    elif option_name.startswith("response_format"):
        messages = [Message(role="user", contents=["The weather in Seattle is sunny"])]
        messages.append(Message(role="user", contents=["What is the weather in Seattle?"]))
    else:
        messages = [Message(role="user", contents=["Say 'Hello World' briefly."])]

    options: dict[str, Any] = {option_name: option_value}
    if option_name.startswith("tool_choice"):
        options["tools"] = [get_weather]

    response = await client.get_response(messages=messages, options=options, stream=True).get_final_response()

    assert isinstance(response, ChatResponse)
    assert response.text is not None
    assert len(response.text) > 0

    if needs_validation:
        if option_name.startswith("tools") or option_name.startswith("tool_choice"):
            text = response.text.lower()
            assert "sunny" in text or "seattle" in text
        elif option_name.startswith("response_format"):
            if option_value == OutputStruct:
                assert response.value is not None
                assert isinstance(response.value, OutputStruct)
                assert "seattle" in response.value.location.lower()
            else:
                assert response.value is not None
                assert isinstance(response.value, dict)
                assert "location" in response.value


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_foundry_integration_tests_disabled
@_with_foundry_debug()
async def test_integration_web_search() -> None:
    client = FoundryChatClient(credential=AzureCliCredential())

    web_search_tool = FoundryChatClient.get_web_search_tool()
    content = {
        "messages": [
            Message(
                role="user",
                contents=["Who are the main characters of Kpop Demon Hunters? Do a web search to find the answer."],
            )
        ],
        "options": {"tool_choice": "auto", "tools": [web_search_tool]},
    }
    response = await client.get_response(stream=True, **content).get_final_response()

    assert isinstance(response, ChatResponse)
    assert "Rumi" in response.text
    assert "Mira" in response.text
    assert "Zoey" in response.text


@pytest.mark.flaky
@pytest.mark.integration
@pytest.mark.xfail(reason="Azure AI Foundry stopped accepting array-format output in function_call_output ~2026-04-03")
@skip_if_foundry_integration_tests_disabled
@_with_foundry_debug()
async def test_integration_tool_rich_content_image() -> None:
    image_path = Path(__file__).parent.parent / "assets" / "sample_image.jpg"
    image_bytes = image_path.read_bytes()

    @tool(approval_mode="never_require")
    def get_test_image() -> Content:
        return Content.from_data(data=image_bytes, media_type="image/jpeg")

    client = FoundryChatClient(credential=AzureCliCredential())
    client.function_invocation_configuration["max_iterations"] = 2

    messages = [Message(role="user", contents=["Call the get_test_image tool and describe what you see."])]
    options: dict[str, Any] = {"tools": [get_test_image], "tool_choice": "auto"}

    response = await client.get_response(messages=messages, options=options, stream=True).get_final_response()

    assert isinstance(response, ChatResponse)
    assert response.text is not None
    assert len(response.text) > 0
    assert "house" in response.text.lower(), f"Model did not describe the house image. Response: {response.text}"


def test_get_code_interpreter_tool() -> None:
    """Test code interpreter tool creation."""

    tool_obj = RawFoundryChatClient.get_code_interpreter_tool()
    assert tool_obj is not None


def test_get_code_interpreter_tool_with_file_ids() -> None:
    """Test code interpreter tool with file IDs."""

    tool_obj = RawFoundryChatClient.get_code_interpreter_tool(file_ids=["file-abc123"])
    assert tool_obj is not None


def test_get_file_search_tool() -> None:
    """Test file search tool creation."""

    tool_obj = RawFoundryChatClient.get_file_search_tool(vector_store_ids=["vs_abc123"])
    assert tool_obj is not None


def test_get_file_search_tool_requires_vector_store_ids() -> None:
    """Test that empty vector_store_ids raises ValueError."""

    with pytest.raises(ValueError, match="vector_store_ids"):
        RawFoundryChatClient.get_file_search_tool(vector_store_ids=[])


def test_get_web_search_tool() -> None:
    """Test web search tool creation."""

    tool_obj = RawFoundryChatClient.get_web_search_tool()
    assert tool_obj is not None


def test_get_web_search_tool_with_location() -> None:
    """Test web search tool with user location."""

    tool_obj = RawFoundryChatClient.get_web_search_tool(
        user_location={"city": "Seattle", "country": "US"},
        search_context_size="high",
    )
    assert tool_obj is not None


def test_get_image_generation_tool() -> None:
    """Test image generation tool creation."""

    tool_obj = RawFoundryChatClient.get_image_generation_tool()
    assert tool_obj is not None


def test_get_mcp_tool() -> None:
    """Test MCP tool creation."""

    tool_obj = RawFoundryChatClient.get_mcp_tool(
        name="my_mcp",
        url="https://mcp.example.com",
    )
    assert tool_obj is not None


def test_get_mcp_tool_with_connection_id() -> None:
    """Test MCP tool with project connection ID."""

    tool_obj = RawFoundryChatClient.get_mcp_tool(
        name="github_mcp",
        project_connection_id="conn_abc123",
        description="GitHub MCP via Foundry",
    )
    assert tool_obj is not None
