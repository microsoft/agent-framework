# Copyright (c) Microsoft. All rights reserved.

import json
import logging
import os
from typing import Annotated, Any
from unittest.mock import MagicMock

import pytest
from azure.identity import AzureCliCredential
from pydantic import BaseModel
from pytest import param

from agent_framework import (
    Agent,
    AgentResponse,
    ChatResponse,
    Content,
    Message,
    SupportsChatGetResponse,
    tool,
)
from agent_framework.azure import AzureOpenAIResponsesClient

skip_if_azure_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("AZURE_OPENAI_ENDPOINT", "") in ("", "https://test-endpoint.com"),
    reason="No real AZURE_OPENAI_ENDPOINT provided; skipping integration tests.",
)

logger = logging.getLogger(__name__)


class OutputStruct(BaseModel):
    """A structured output for testing purposes."""

    location: str
    weather: str


@tool(approval_mode="never_require")
async def get_weather(location: Annotated[str, "The location as a city name"]) -> str:
    """Get the current weather in a given location."""
    # Implementation of the tool to get weather
    return f"The weather in {location} is sunny and 72°F."


async def create_vector_store(client: AzureOpenAIResponsesClient) -> tuple[str, Content]:
    """Create a vector store with sample documents for testing."""
    file = await client.client.files.create(
        file=("todays_weather.txt", b"The weather today is sunny with a high of 75F."), purpose="assistants"
    )
    vector_store = await client.client.vector_stores.create(
        name="knowledge_base",
        expires_after={"anchor": "last_active_at", "days": 1},
    )
    result = await client.client.vector_stores.files.create_and_poll(vector_store_id=vector_store.id, file_id=file.id)
    if result.last_error is not None:
        raise Exception(f"Vector store file processing failed with status: {result.last_error.message}")

    return file.id, Content.from_hosted_vector_store(vector_store_id=vector_store.id)


async def delete_vector_store(client: AzureOpenAIResponsesClient, file_id: str, vector_store_id: str) -> None:
    """Delete the vector store after tests."""

    await client.client.vector_stores.delete(vector_store_id=vector_store_id)
    await client.client.files.delete(file_id=file_id)


def test_init(azure_openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    azure_responses_client = AzureOpenAIResponsesClient(credential=AzureCliCredential())

    assert azure_responses_client.model_id == azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]
    assert isinstance(azure_responses_client, SupportsChatGetResponse)


def test_init_validation_fail() -> None:
    # Test successful initialization
    with pytest.raises(ValueError):
        AzureOpenAIResponsesClient(api_key="34523", deployment_name={"test": "dict"})  # type: ignore


def test_init_model_id_constructor(azure_openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    model_id = "test_model_id"
    azure_responses_client = AzureOpenAIResponsesClient(deployment_name=model_id)

    assert azure_responses_client.model_id == model_id
    assert isinstance(azure_responses_client, SupportsChatGetResponse)


def test_init_with_default_header(azure_openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    # Test successful initialization
    azure_responses_client = AzureOpenAIResponsesClient(
        default_headers=default_headers,
    )

    assert azure_responses_client.model_id == azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]
    assert isinstance(azure_responses_client, SupportsChatGetResponse)

    # Assert that the default header we added is present in the client's default headers
    for key, value in default_headers.items():
        assert key in azure_responses_client.client.default_headers
        assert azure_responses_client.client.default_headers[key] == value


@pytest.mark.parametrize("exclude_list", [["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]], indirect=True)
def test_init_with_empty_model_id(azure_openai_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        AzureOpenAIResponsesClient()


def test_init_with_project_client(azure_openai_unit_test_env: dict[str, str]) -> None:
    """Test initialization with an existing AIProjectClient."""
    from unittest.mock import patch

    from openai import AsyncOpenAI

    # Create a mock AIProjectClient that returns a mock AsyncOpenAI client
    mock_openai_client = MagicMock(spec=AsyncOpenAI)
    mock_openai_client.default_headers = {}

    mock_project_client = MagicMock()
    mock_project_client.get_openai_client.return_value = mock_openai_client

    with patch(
        "agent_framework.azure._responses_client.AzureOpenAIResponsesClient._create_client_from_project",
        return_value=mock_openai_client,
    ):
        azure_responses_client = AzureOpenAIResponsesClient(
            project_client=mock_project_client,
            deployment_name="gpt-4o",
        )

    assert azure_responses_client.model_id == "gpt-4o"
    assert azure_responses_client.client is mock_openai_client
    assert isinstance(azure_responses_client, SupportsChatGetResponse)


def test_init_with_project_endpoint(azure_openai_unit_test_env: dict[str, str]) -> None:
    """Test initialization with a project endpoint and credential."""
    from unittest.mock import patch

    from openai import AsyncOpenAI

    mock_openai_client = MagicMock(spec=AsyncOpenAI)
    mock_openai_client.default_headers = {}

    with patch(
        "agent_framework.azure._responses_client.AzureOpenAIResponsesClient._create_client_from_project",
        return_value=mock_openai_client,
    ):
        azure_responses_client = AzureOpenAIResponsesClient(
            project_endpoint="https://test-project.services.ai.azure.com",
            deployment_name="gpt-4o",
            credential=AzureCliCredential(),
        )

    assert azure_responses_client.model_id == "gpt-4o"
    assert azure_responses_client.client is mock_openai_client
    assert isinstance(azure_responses_client, SupportsChatGetResponse)


def test_create_client_from_project_with_project_client() -> None:
    """Test _create_client_from_project with an existing project client."""
    from openai import AsyncOpenAI

    mock_openai_client = MagicMock(spec=AsyncOpenAI)
    mock_project_client = MagicMock()
    mock_project_client.get_openai_client.return_value = mock_openai_client

    result = AzureOpenAIResponsesClient._create_client_from_project(
        project_client=mock_project_client,
        project_endpoint=None,
        credential=None,
    )

    assert result is mock_openai_client
    mock_project_client.get_openai_client.assert_called_once()


def test_create_client_from_project_with_endpoint() -> None:
    """Test _create_client_from_project with a project endpoint."""
    from unittest.mock import patch

    from openai import AsyncOpenAI

    mock_openai_client = MagicMock(spec=AsyncOpenAI)
    mock_credential = MagicMock()

    with patch("agent_framework.azure._responses_client.AIProjectClient") as MockAIProjectClient:
        mock_instance = MockAIProjectClient.return_value
        mock_instance.get_openai_client.return_value = mock_openai_client

        result = AzureOpenAIResponsesClient._create_client_from_project(
            project_client=None,
            project_endpoint="https://test-project.services.ai.azure.com",
            credential=mock_credential,
        )

    assert result is mock_openai_client
    MockAIProjectClient.assert_called_once()
    mock_instance.get_openai_client.assert_called_once()


def test_create_client_from_project_missing_endpoint() -> None:
    """Test _create_client_from_project raises error when endpoint is missing."""
    with pytest.raises(ValueError, match="project endpoint is required"):
        AzureOpenAIResponsesClient._create_client_from_project(
            project_client=None,
            project_endpoint=None,
            credential=MagicMock(),
        )


def test_create_client_from_project_missing_credential() -> None:
    """Test _create_client_from_project raises error when credential is missing."""
    with pytest.raises(ValueError, match="credential is required"):
        AzureOpenAIResponsesClient._create_client_from_project(
            project_client=None,
            project_endpoint="https://test-project.services.ai.azure.com",
            credential=None,
        )


def test_serialize(azure_openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    settings = {
        "deployment_name": azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        "api_key": azure_openai_unit_test_env["AZURE_OPENAI_API_KEY"],
        "default_headers": default_headers,
    }

    azure_responses_client = AzureOpenAIResponsesClient.from_dict(settings)
    dumped_settings = azure_responses_client.to_dict()
    assert dumped_settings["deployment_name"] == azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]
    assert "api_key" not in dumped_settings
    # Assert that the default header we added is present in the dumped_settings default headers
    for key, value in default_headers.items():
        assert key in dumped_settings["default_headers"]
        assert dumped_settings["default_headers"][key] == value
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]


# region Integration Tests


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
@pytest.mark.parametrize(
    "option_name,option_value,needs_validation",
    [
        # Simple ChatOptions - just verify they don't fail
        param("temperature", 0.7, False, id="temperature"),
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
        # OpenAIResponsesOptions - just verify they don't fail
        param("safety_identifier", "user-hash-abc123", False, id="safety_identifier"),
        param("truncation", "auto", False, id="truncation"),
        param("top_logprobs", 5, False, id="top_logprobs"),
        param("prompt_cache_key", "test-cache-key", False, id="prompt_cache_key"),
        param("max_tool_calls", 3, False, id="max_tool_calls"),
        # Complex options requiring output validation
        param("tools", [get_weather], True, id="tools_function"),
        param("tool_choice", "auto", True, id="tool_choice_auto"),
        param(
            "tool_choice",
            {"mode": "required", "required_function_name": "get_weather"},
            True,
            id="tool_choice_required",
        ),
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
async def test_integration_options(
    option_name: str,
    option_value: Any,
    needs_validation: bool,
) -> None:
    """Parametrized test covering all ChatOptions and OpenAIResponsesOptions.

    Tests both streaming and non-streaming modes for each option to ensure
    they don't cause failures. Options marked with needs_validation also
    check that the feature actually works correctly.
    """
    client = AzureOpenAIResponsesClient(credential=AzureCliCredential())
    # Need at least 2 iterations for tool_choice tests: one to get function call, one to get final response
    client.function_invocation_configuration["max_iterations"] = 2

    for streaming in [False, True]:
        # Prepare test message
        if option_name == "tools" or option_name == "tool_choice":
            # Use weather-related prompt for tool tests
            messages = [Message(role="user", text="What is the weather in Seattle?")]
        elif option_name == "response_format":
            # Use prompt that works well with structured output
            messages = [
                Message(role="user", text="The weather in Seattle is sunny"),
                Message(role="user", text="What is the weather in Seattle?"),
            ]
        else:
            # Generic prompt for simple options
            messages = [Message(role="user", text="Say 'Hello World' briefly.")]

        # Build options dict
        options: dict[str, Any] = {option_name: option_value}

        # Add tools if testing tool_choice to avoid errors
        if option_name == "tool_choice":
            options["tools"] = [get_weather]

        if streaming:
            # Test streaming mode
            response_stream = client.get_response(
                messages=messages,
                stream=True,
                options=options,
            )

            response = await response_stream.get_final_response()
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
            if option_name == "tools" or option_name == "tool_choice":
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
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_integration_web_search() -> None:
    client = AzureOpenAIResponsesClient(credential=AzureCliCredential())

    for streaming in [False, True]:
        content = {
            "messages": [
                Message(
                    role="user",
                    text="Who are the main characters of Kpop Demon Hunters? Do a web search to find the answer.",
                )
            ],
            "options": {
                "tool_choice": "auto",
                "tools": [AzureOpenAIResponsesClient.get_web_search_tool()],
            },
            "stream": streaming,
        }
        if streaming:
            response = await client.get_response(**content).get_final_response()
        else:
            response = await client.get_response(**content)

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert "Rumi" in response.text
        assert "Mira" in response.text
        assert "Zoey" in response.text

        # Test that the client will use the web search tool with location
        content = {
            "messages": [Message(role="user", text="What is the current weather? Do not ask for my current location.")],
            "options": {
                "tool_choice": "auto",
                "tools": [
                    AzureOpenAIResponsesClient.get_web_search_tool(user_location={"country": "US", "city": "Seattle"})
                ],
            },
            "stream": streaming,
        }
        if streaming:
            response = await client.get_response(**content).get_final_response()
        else:
            response = await client.get_response(**content)
        assert response.text is not None


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_integration_client_file_search() -> None:
    """Test Azure responses client with file search tool."""
    azure_responses_client = AzureOpenAIResponsesClient(credential=AzureCliCredential())
    file_id, vector_store = await create_vector_store(azure_responses_client)
    try:
        # Test that the client will use the file search tool
        response = await azure_responses_client.get_response(
            messages=[
                Message(
                    role="user",
                    text="What is the weather today? Do a file search to find the answer.",
                )
            ],
            options={
                "tools": [
                    AzureOpenAIResponsesClient.get_file_search_tool(vector_store_ids=[vector_store.vector_store_id])
                ],
                "tool_choice": "auto",
            },
        )

        assert "sunny" in response.text.lower()
        assert "75" in response.text
    finally:
        await delete_vector_store(azure_responses_client, file_id, vector_store.vector_store_id)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_integration_client_file_search_streaming() -> None:
    """Test Azure responses client with file search tool and streaming."""
    azure_responses_client = AzureOpenAIResponsesClient(credential=AzureCliCredential())
    file_id, vector_store = await create_vector_store(azure_responses_client)
    # Test that the client will use the file search tool
    try:
        response_stream = azure_responses_client.get_response(
            messages=[
                Message(
                    role="user",
                    text="What is the weather today? Do a file search to find the answer.",
                )
            ],
            stream=True,
            options={
                "tools": [
                    AzureOpenAIResponsesClient.get_file_search_tool(vector_store_ids=[vector_store.vector_store_id])
                ],
                "tool_choice": "auto",
            },
        )

        full_response = await response_stream.get_final_response()
        assert "sunny" in full_response.text.lower()
        assert "75" in full_response.text
    finally:
        await delete_vector_store(azure_responses_client, file_id, vector_store.vector_store_id)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_integration_client_agent_hosted_mcp_tool() -> None:
    """Integration test for MCP tool with Azure Response Agent using Microsoft Learn MCP."""
    client = AzureOpenAIResponsesClient(credential=AzureCliCredential())
    response = await client.get_response(
        messages=[Message(role="user", text="How to create an Azure storage account using az cli?")],
        options={
            # this needs to be high enough to handle the full MCP tool response.
            "max_tokens": 5000,
            "tools": AzureOpenAIResponsesClient.get_mcp_tool(
                name="Microsoft Learn MCP",
                url="https://learn.microsoft.com/api/mcp",
            ),
        },
    )
    assert isinstance(response, ChatResponse)
    # MCP server may return empty response intermittently - skip test rather than fail
    if not response.text:
        pytest.skip("MCP server returned empty response - service-side issue")
    # Should contain Azure-related content since it's asking about Azure CLI
    assert any(term in response.text.lower() for term in ["azure", "storage", "account", "cli"])


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_integration_client_agent_hosted_code_interpreter_tool():
    """Test Azure Responses Client agent with code interpreter tool."""
    client = AzureOpenAIResponsesClient(credential=AzureCliCredential())

    response = await client.get_response(
        messages=[Message(role="user", text="Calculate the sum of numbers from 1 to 10 using Python code.")],
        options={
            "tools": [AzureOpenAIResponsesClient.get_code_interpreter_tool()],
        },
    )
    # Should contain calculation result (sum of 1-10 = 55) or code execution content
    contains_relevant_content = any(
        term in response.text.lower() for term in ["55", "sum", "code", "python", "calculate", "10"]
    )
    assert contains_relevant_content or len(response.text.strip()) > 10


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_integration_client_agent_existing_session():
    """Test Azure Responses Client agent with existing session to continue conversations across agent instances."""
    # First conversation - capture the session
    preserved_session = None

    async with Agent(
        client=AzureOpenAIResponsesClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant with good memory.",
    ) as first_agent:
        # Start a conversation and capture the session
        session = first_agent.create_session()
        first_response = await first_agent.run("My hobby is photography. Remember this.", session=session, store=True)

        assert isinstance(first_response, AgentResponse)
        assert first_response.text is not None

        # Preserve the session for reuse
        preserved_session = session

    # Second conversation - reuse the session in a new agent instance
    if preserved_session:
        async with Agent(
            client=AzureOpenAIResponsesClient(credential=AzureCliCredential()),
            instructions="You are a helpful assistant with good memory.",
        ) as second_agent:
            # Reuse the preserved session
            second_response = await second_agent.run("What is my hobby?", session=preserved_session)

            assert isinstance(second_response, AgentResponse)
            assert second_response.text is not None
            assert "photography" in second_response.text.lower()
