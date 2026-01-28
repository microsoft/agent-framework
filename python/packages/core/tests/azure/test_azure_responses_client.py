# Copyright (c) Microsoft. All rights reserved.

import json
import os
from typing import Annotated, Any

import pytest
from azure.identity import AzureCliCredential
from pydantic import BaseModel
from pytest import param

from agent_framework import (
    AgentResponse,
    ChatAgent,
    ChatClientProtocol,
    ChatMessage,
    ChatResponse,
    Content,
    HostedCodeInterpreterTool,
    HostedFileSearchTool,
    HostedMCPTool,
    HostedWebSearchTool,
    tool,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.exceptions import ServiceInitializationError

skip_if_azure_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("AZURE_OPENAI_ENDPOINT", "") in ("", "https://test-endpoint.com"),
    reason="No real AZURE_OPENAI_ENDPOINT provided; skipping integration tests."
    if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    else "Integration tests are disabled.",
)


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
    assert isinstance(azure_responses_client, ChatClientProtocol)


def test_init_validation_fail() -> None:
    # Test successful initialization
    with pytest.raises(ServiceInitializationError):
        AzureOpenAIResponsesClient(api_key="34523", deployment_name={"test": "dict"})  # type: ignore


def test_init_model_id_constructor(azure_openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    model_id = "test_model_id"
    azure_responses_client = AzureOpenAIResponsesClient(deployment_name=model_id)

    assert azure_responses_client.model_id == model_id
    assert isinstance(azure_responses_client, ChatClientProtocol)


def test_init_with_default_header(azure_openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    # Test successful initialization
    azure_responses_client = AzureOpenAIResponsesClient(
        default_headers=default_headers,
    )

    assert azure_responses_client.model_id == azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]
    assert isinstance(azure_responses_client, ChatClientProtocol)

    # Assert that the default header we added is present in the client's default headers
    for key, value in default_headers.items():
        assert key in azure_responses_client.client.default_headers
        assert azure_responses_client.client.default_headers[key] == value


@pytest.mark.parametrize("exclude_list", [["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]], indirect=True)
def test_init_with_empty_model_id(azure_openai_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(ServiceInitializationError):
        AzureOpenAIResponsesClient(
            env_file_path="test.env",
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
    # to ensure toolmode required does not endlessly loop
    client.function_invocation_configuration.max_iterations = 1

    for streaming in [False, True]:
        # Prepare test message
        if option_name == "tools" or option_name == "tool_choice":
            # Use weather-related prompt for tool tests
            messages = [ChatMessage(role="user", text="What is the weather in Seattle?")]
        elif option_name == "response_format":
            # Use prompt that works well with structured output
            messages = [ChatMessage(role="user", text="The weather in Seattle is sunny")]
            messages.append(ChatMessage(role="user", text="What is the weather in Seattle?"))
        else:
            # Generic prompt for simple options
            messages = [ChatMessage(role="user", text="Say 'Hello World' briefly.")]

        # Build options dict
        options: dict[str, Any] = {option_name: option_value}

        # Add tools if testing tool_choice to avoid errors
        if option_name == "tool_choice":
            options["tools"] = [get_weather]

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
@skip_if_azure_integration_tests_disabled
async def test_integration_web_search() -> None:
    client = AzureOpenAIResponsesClient(credential=AzureCliCredential())

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
@skip_if_azure_integration_tests_disabled
async def test_integration_client_file_search() -> None:
    """Test Azure responses client with file search tool."""
    azure_responses_client = AzureOpenAIResponsesClient(credential=AzureCliCredential())
    file_id, vector_store = await create_vector_store(azure_responses_client)
    try:
        # Test that the client will use the file search tool
        response = await azure_responses_client.get_response(
            messages=[
                ChatMessage(
                    role="user",
                    text="What is the weather today? Do a file search to find the answer.",
                )
            ],
            options={"tools": [HostedFileSearchTool(inputs=vector_store)], "tool_choice": "auto"},
        )

        assert "sunny" in response.text.lower()
        assert "75" in response.text
    finally:
        await delete_vector_store(azure_responses_client, file_id, vector_store.vector_store_id)


@pytest.mark.flaky
@skip_if_azure_integration_tests_disabled
async def test_integration_client_file_search_streaming() -> None:
    """Test Azure responses client with file search tool and streaming."""
    azure_responses_client = AzureOpenAIResponsesClient(credential=AzureCliCredential())
    file_id, vector_store = await create_vector_store(azure_responses_client)
    # Test that the client will use the file search tool
    try:
        response = azure_responses_client.get_streaming_response(
            messages=[
                ChatMessage(
                    role="user",
                    text="What is the weather today? Do a file search to find the answer.",
                )
            ],
            options={"tools": [HostedFileSearchTool(inputs=vector_store)], "tool_choice": "auto"},
        )

        assert response is not None
        full_response = await ChatResponse.from_chat_response_generator(response)
        assert "sunny" in full_response.text.lower()
        assert "75" in full_response.text
    finally:
        await delete_vector_store(azure_responses_client, file_id, vector_store.vector_store_id)


@pytest.mark.flaky
@skip_if_azure_integration_tests_disabled
async def test_integration_client_agent_hosted_mcp_tool() -> None:
    """Integration test for HostedMCPTool with Azure Response Agent using Microsoft Learn MCP."""
    client = AzureOpenAIResponsesClient(credential=AzureCliCredential())
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
@skip_if_azure_integration_tests_disabled
async def test_integration_client_agent_hosted_code_interpreter_tool():
    """Test Azure Responses Client agent with HostedCodeInterpreterTool through AzureOpenAIResponsesClient."""
    client = AzureOpenAIResponsesClient(credential=AzureCliCredential())

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
@skip_if_azure_integration_tests_disabled
async def test_integration_client_agent_existing_thread():
    """Test Azure Responses Client agent with existing thread to continue conversations across agent instances."""
    # First conversation - capture the thread
    preserved_thread = None

    async with ChatAgent(
        chat_client=AzureOpenAIResponsesClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant with good memory.",
    ) as first_agent:
        # Start a conversation and capture the thread
        thread = first_agent.get_new_thread()
        first_response = await first_agent.run("My hobby is photography. Remember this.", thread=thread, store=True)

        assert isinstance(first_response, AgentResponse)
        assert first_response.text is not None

        # Preserve the thread for reuse
        preserved_thread = thread

    # Second conversation - reuse the thread in a new agent instance
    if preserved_thread:
        async with ChatAgent(
            chat_client=AzureOpenAIResponsesClient(credential=AzureCliCredential()),
            instructions="You are a helpful assistant with good memory.",
        ) as second_agent:
            # Reuse the preserved thread
            second_response = await second_agent.run("What is my hobby?", thread=preserved_thread)

            assert isinstance(second_response, AgentResponse)
            assert second_response.text is not None
            assert "photography" in second_response.text.lower()
