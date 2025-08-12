# Copyright (c) Microsoft. All rights reserved.

import os
from typing import Annotated

import pytest
from agent_framework import ChatClient, ChatMessage, ChatResponse, ChatResponseUpdate, TextContent, ai_function
from agent_framework.azure import AzureResponsesClient
from agent_framework.exceptions import ServiceInitializationError
from azure.identity import DefaultAzureCredential
from pydantic import BaseModel

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


@ai_function
async def get_weather(location: Annotated[str, "The location as a city name"]) -> str:
    """Get the current weather in a given location."""
    # Implementation of the tool to get weather
    return f"The current weather in {location} is sunny."


def test_init(azure_openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    azure_responses_client = AzureResponsesClient()

    assert azure_responses_client.ai_model_id == azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]
    assert isinstance(azure_responses_client, ChatClient)


def test_init_validation_fail() -> None:
    # Test successful initialization
    with pytest.raises(ServiceInitializationError):
        AzureResponsesClient(api_key="34523", deployment_name={"test": "dict"})  # type: ignore


def test_init_ai_model_id_constructor(azure_openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    ai_model_id = "test_model_id"
    azure_responses_client = AzureResponsesClient(deployment_name=ai_model_id)

    assert azure_responses_client.ai_model_id == ai_model_id
    assert isinstance(azure_responses_client, ChatClient)


def test_init_with_default_header(azure_openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    # Test successful initialization
    azure_responses_client = AzureResponsesClient(
        default_headers=default_headers,
    )

    assert azure_responses_client.ai_model_id == azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]
    assert isinstance(azure_responses_client, ChatClient)

    # Assert that the default header we added is present in the client's default headers
    for key, value in default_headers.items():
        assert key in azure_responses_client.client.default_headers
        assert azure_responses_client.client.default_headers[key] == value


@pytest.mark.parametrize("exclude_list", [["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]], indirect=True)
def test_init_with_empty_model_id(azure_openai_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(ServiceInitializationError):
        AzureResponsesClient(
            env_file_path="test.env",
        )


def test_serialize(azure_openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    settings = {
        "ai_model_id": azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        "api_key": azure_openai_unit_test_env["AZURE_OPENAI_API_KEY"],
        "default_headers": default_headers,
    }

    azure_responses_client = AzureResponsesClient.from_dict(settings)
    dumped_settings = azure_responses_client.to_dict()
    assert dumped_settings["ai_model_id"] == azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]
    assert dumped_settings["api_key"] == azure_openai_unit_test_env["AZURE_OPENAI_API_KEY"]
    # Assert that the default header we added is present in the dumped_settings default headers
    for key, value in default_headers.items():
        assert key in dumped_settings["default_headers"]
        assert dumped_settings["default_headers"][key] == value
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]


@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_response() -> None:
    """Test azure responses client responses."""
    azure_responses_client = AzureResponsesClient(ad_credential=DefaultAzureCredential())

    assert isinstance(azure_responses_client, ChatClient)

    messages: list[ChatMessage] = []
    messages.append(
        ChatMessage(
            role="user",
            text="Emily and David, two passionate scientists, met during a research expedition to Antarctica. "
            "Bonded by their love for the natural world and shared curiosity, they uncovered a "
            "groundbreaking phenomenon in glaciology that could potentially reshape our understanding "
            "of climate change.",
        )
    )
    messages.append(ChatMessage(role="user", text="who are Emily and David?"))

    # Test that the client can be used to get a response
    response = await azure_responses_client.get_response(messages=messages)

    assert response is not None
    assert isinstance(response, ChatResponse)
    assert "scientists" in response.text

    messages.clear()
    messages.append(ChatMessage(role="user", text="The weather in New York is sunny"))
    messages.append(ChatMessage(role="user", text="What is the weather in New York?"))

    # Test that the client can be used to get a response
    response = await azure_responses_client.get_response(
        messages=messages,
        response_format=OutputStruct,
    )

    assert response is not None
    assert isinstance(response, ChatResponse)
    output = OutputStruct.model_validate_json(response.text)
    assert output.location == "New York"
    assert "sunny" in output.weather.lower()


@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_response_tools() -> None:
    """Test azure responses client tools."""
    azure_responses_client = AzureResponsesClient(ad_credential=DefaultAzureCredential())

    assert isinstance(azure_responses_client, ChatClient)

    messages: list[ChatMessage] = []
    messages.append(ChatMessage(role="user", text="What is the weather in New York?"))

    # Test that the client can be used to get a response
    response = await azure_responses_client.get_response(
        messages=messages,
        tools=[get_weather],
        tool_choice="auto",
    )

    assert response is not None
    assert isinstance(response, ChatResponse)
    assert "sunny" in response.text

    messages.clear()
    messages.append(ChatMessage(role="user", text="What is the weather in Seattle?"))

    # Test that the client can be used to get a response
    response = await azure_responses_client.get_response(
        messages=messages,
        tools=[get_weather],
        tool_choice="auto",
        response_format=OutputStruct,
    )

    assert response is not None
    assert isinstance(response, ChatResponse)
    output = OutputStruct.model_validate_json(response.text)
    assert "Seattle" in output.location
    assert "sunny" in output.weather.lower()


@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_streaming() -> None:
    """Test Azure azure responses client streaming responses."""
    azure_responses_client = AzureResponsesClient(ad_credential=DefaultAzureCredential())

    assert isinstance(azure_responses_client, ChatClient)

    messages: list[ChatMessage] = []
    messages.append(
        ChatMessage(
            role="user",
            text="Emily and David, two passionate scientists, met during a research expedition to Antarctica. "
            "Bonded by their love for the natural world and shared curiosity, they uncovered a "
            "groundbreaking phenomenon in glaciology that could potentially reshape our understanding "
            "of climate change.",
        )
    )
    messages.append(ChatMessage(role="user", text="who are Emily and David?"))

    # Test that the client can be used to get a response
    response = azure_responses_client.get_streaming_response(messages=messages)

    full_message: str = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text

    assert "scientists" in full_message

    messages.clear()
    messages.append(ChatMessage(role="user", text="The weather in Seattle is sunny"))
    messages.append(ChatMessage(role="user", text="What is the weather in Seattle?"))

    response = azure_responses_client.get_streaming_response(
        messages=messages,
        response_format=OutputStruct,
    )
    full_message = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text

    output = OutputStruct.model_validate_json(full_message)
    assert "Seattle" in output.location
    assert "sunny" in output.weather.lower()


@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_streaming_tools() -> None:
    """Test azure responses client streaming tools."""
    azure_responses_client = AzureResponsesClient(ad_credential=DefaultAzureCredential())

    assert isinstance(azure_responses_client, ChatClient)

    messages: list[ChatMessage] = [ChatMessage(role="user", text="What is the weather in Seattle?")]

    # Test that the client can be used to get a response
    response = azure_responses_client.get_streaming_response(
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

    assert "sunny" in full_message

    messages.clear()
    messages.append(ChatMessage(role="user", text="What is the weather in Seattle?"))

    response = azure_responses_client.get_streaming_response(
        messages=messages,
        tools=[get_weather],
        tool_choice="auto",
        response_format=OutputStruct,
    )
    full_message = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text

    output = OutputStruct.model_validate_json(full_message)
    assert "Seattle" in output.location
    assert "sunny" in output.weather.lower()
