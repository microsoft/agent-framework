# Copyright (c) Microsoft. All rights reserved.

import os
from typing import Annotated

import pytest
from pydantic import BaseModel

from agent_framework import ChatClient, ChatMessage, ChatResponse, ChatResponseUpdate, TextContent, ai_function
from agent_framework.exceptions import ServiceInitializationError, ServiceResponseException
from agent_framework.openai import OpenAIResponsesClient

skip_if_openai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("OPENAI_API_KEY", "") in ("", "test-dummy-key"),
    reason="No real OPENAI_API_KEY provided; skipping integration tests."
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


def test_init(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    openai_responses_client = OpenAIResponsesClient()

    assert openai_responses_client.ai_model_id == openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"]
    assert isinstance(openai_responses_client, ChatClient)


def test_init_validation_fail() -> None:
    # Test successful initialization
    with pytest.raises(ServiceInitializationError):
        OpenAIResponsesClient(api_key="34523", ai_model_id={"test": "dict"})  # type: ignore


def test_init_ai_model_id_constructor(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    ai_model_id = "test_model_id"
    openai_responses_client = OpenAIResponsesClient(ai_model_id=ai_model_id)

    assert openai_responses_client.ai_model_id == ai_model_id
    assert isinstance(openai_responses_client, ChatClient)


def test_init_with_default_header(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    # Test successful initialization
    openai_responses_client = OpenAIResponsesClient(
        default_headers=default_headers,
    )

    assert openai_responses_client.ai_model_id == openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"]
    assert isinstance(openai_responses_client, ChatClient)

    # Assert that the default header we added is present in the client's default headers
    for key, value in default_headers.items():
        assert key in openai_responses_client.client.default_headers
        assert openai_responses_client.client.default_headers[key] == value


@pytest.mark.parametrize("exclude_list", [["OPENAI_RESPONSES_MODEL_ID"]], indirect=True)
def test_init_with_empty_model_id(openai_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(ServiceInitializationError):
        OpenAIResponsesClient(
            env_file_path="test.env",
        )


@pytest.mark.parametrize("exclude_list", [["OPENAI_API_KEY"]], indirect=True)
def test_init_with_empty_api_key(openai_unit_test_env: dict[str, str]) -> None:
    ai_model_id = "test_model_id"

    with pytest.raises(ServiceInitializationError):
        OpenAIResponsesClient(
            ai_model_id=ai_model_id,
            env_file_path="test.env",
        )


def test_serialize(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    settings = {
        "ai_model_id": openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"],
        "api_key": openai_unit_test_env["OPENAI_API_KEY"],
        "default_headers": default_headers,
    }

    openai_responses_client = OpenAIResponsesClient.from_dict(settings)
    dumped_settings = openai_responses_client.to_dict()
    assert dumped_settings["ai_model_id"] == openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"]
    assert dumped_settings["api_key"] == openai_unit_test_env["OPENAI_API_KEY"]
    # Assert that the default header we added is present in the dumped_settings default headers
    for key, value in default_headers.items():
        assert key in dumped_settings["default_headers"]
        assert dumped_settings["default_headers"][key] == value
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]


def test_serialize_with_org_id(openai_unit_test_env: dict[str, str]) -> None:
    settings = {
        "ai_model_id": openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"],
        "api_key": openai_unit_test_env["OPENAI_API_KEY"],
        "org_id": openai_unit_test_env["OPENAI_ORG_ID"],
    }

    openai_responses_client = OpenAIResponsesClient.from_dict(settings)
    dumped_settings = openai_responses_client.to_dict()
    assert dumped_settings["ai_model_id"] == openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"]
    assert dumped_settings["api_key"] == openai_unit_test_env["OPENAI_API_KEY"]
    assert dumped_settings["org_id"] == openai_unit_test_env["OPENAI_ORG_ID"]
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_response() -> None:
    """Test OpenAI chat completion responses."""
    openai_responses_client = OpenAIResponsesClient(ai_model_id="gpt-4.1-mini")

    assert isinstance(openai_responses_client, ChatClient)

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
    response = await openai_responses_client.get_response(messages=messages)

    assert response is not None
    assert isinstance(response, ChatResponse)
    assert "scientists" in response.text

    messages.clear()
    messages.append(ChatMessage(role="user", text="The weather in New York is sunny"))
    messages.append(ChatMessage(role="user", text="What is the weather in New York?"))

    # Test that the client can be used to get a response
    response = await openai_responses_client.get_response(
        messages=messages,
        response_format=OutputStruct,
    )

    assert response is not None
    assert isinstance(response, ChatResponse)
    output = OutputStruct.model_validate_json(response.text)
    assert output.location == "New York"
    assert "sunny" in output.weather


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_response_tools() -> None:
    """Test OpenAI chat completion responses."""
    openai_responses_client = OpenAIResponsesClient(ai_model_id="gpt-4o-mini")

    assert isinstance(openai_responses_client, ChatClient)

    messages: list[ChatMessage] = []
    messages.append(ChatMessage(role="user", text="What is the weather in New York?"))

    # Test that the client can be used to get a response
    response = await openai_responses_client.get_response(
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
    response = await openai_responses_client.get_response(
        messages=messages,
        tools=[get_weather],
        tool_choice="auto",
        response_format=OutputStruct,
    )

    assert response is not None
    assert isinstance(response, ChatResponse)
    output = OutputStruct.model_validate_json(response.text)
    assert "Seattle" in output.location
    assert "sunny" in output.weather


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_streaming() -> None:
    """Test Azure OpenAI chat completion responses."""
    openai_responses_client = OpenAIResponsesClient(ai_model_id="gpt-4.1-mini")

    assert isinstance(openai_responses_client, ChatClient)

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
    response = openai_responses_client.get_streaming_response(messages=messages)

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

    # This is currently broken. See https://github.com/openai/openai-python/issues/2305
    with pytest.raises(ServiceResponseException):
        response = openai_responses_client.get_streaming_response(
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
        assert "sunny" in output.weather


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_streaming_tools() -> None:
    """Test OpenAI chat completion responses."""
    openai_responses_client = OpenAIResponsesClient(ai_model_id="gpt-4o-mini")

    assert isinstance(openai_responses_client, ChatClient)

    messages: list[ChatMessage] = [ChatMessage(role="user", text="What is the weather in Seattle?")]

    # Test that the client can be used to get a response
    response = openai_responses_client.get_streaming_response(
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

    # This is currently broken. See https://github.com/openai/openai-python/issues/2305
    with pytest.raises(ServiceResponseException):
        response = openai_responses_client.get_streaming_response(
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
        assert "sunny" in output.weather
