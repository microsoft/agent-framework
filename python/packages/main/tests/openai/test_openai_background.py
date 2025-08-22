# Copyright (c) Microsoft. All rights reserved.

import os
from math import floor
from typing import Annotated

import pytest
from pydantic import BaseModel

from agent_framework import ChatClient, ChatMessage, ChatResponse, ChatResponseUpdate, ResponseStatus, ai_function
from agent_framework.exceptions import ServiceResponseException
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


async def test_openai_responses_client_background_response() -> None:
    """Test OpenAI chat completion responses."""
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClient)

    messages: list[ChatMessage] = []
    messages.append(ChatMessage(role="user", text="The weather in New York is sunny"))
    messages.append(ChatMessage(role="user", text="What is the weather in New York?"))

    # Test that the client can be used to get a response
    response = await openai_responses_client.get_response(
        messages=messages,
        background=True,
        store=True,
    )
    assert response is not None and response.response_id is not None
    assert isinstance(response, ChatResponse)
    assert response.status and response.status != ResponseStatus.COMPLETED

    response = await openai_responses_client.get_response(
        messages=[],  # messages are meaningless here.. do something about that
        long_running_message_id=response.response_id,
        # Uncomment this lines if you want to poll
        # background=True,
    )
    assert "sunny" in response.messages[0].text.lower()


async def test_openai_responses_client_background_structured_response() -> None:
    """Test OpenAI chat completion responses."""
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClient)

    messages: list[ChatMessage] = []
    messages.append(ChatMessage(role="user", text="The weather in New York is sunny"))
    messages.append(ChatMessage(role="user", text="What is the weather in New York?"))

    # Test that the client can be used to get a response
    response = await openai_responses_client.get_response(
        messages=messages,
        background=True,
        store=True,
        response_format=OutputStruct,
    )

    assert response is not None and response.response_id is not None
    assert isinstance(response, ChatResponse)
    assert response.status and response.status != ResponseStatus.COMPLETED

    final_response = await openai_responses_client.get_response(
        messages=[],  # messages are meaningless here.. do something about that
        long_running_message_id=response.response_id,
        # Uncomment this lines if you want to poll
        # background=True,
    )
    output = OutputStruct.model_validate_json(final_response.messages[0].text)
    assert "new york" in output.location.lower()
    assert "sunny" in output.weather.lower()


async def test_openai_responses_client_background_streaming_response() -> None:
    """Test OpenAI chat completion responses."""
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClient)

    messages: list[ChatMessage] = []
    messages.append(ChatMessage(role="user", text="The weather in New York is sunny"))
    messages.append(ChatMessage(role="user", text="What is the weather in New York?"))

    # Test that the client can be used to get a response
    stream = openai_responses_client.get_streaming_response(
        messages=messages,
        background=True,
        store=True,
    )
    conversation_id: str | None = None
    all_messages: list[str] = []
    partial_messages: list[str] = []
    assert stream is not None
    async for response in stream:
        assert isinstance(response, ChatResponseUpdate)
        if response.conversation_id:
            conversation_id = response.conversation_id
        all_messages.append(response.text)

    assert conversation_id is not None
    restart_idx = floor(len(all_messages) / 2)
    stream = openai_responses_client.get_streaming_response(
        messages=[],  # messages are meaningless here.. do something about that
        long_running_conversation_id=conversation_id,
        long_running_sequence_number=restart_idx,
    )
    assert stream is not None
    async for response in stream:
        assert isinstance(response, ChatResponseUpdate)
        partial_messages.append(response.text)

    assert partial_messages == all_messages[restart_idx + 1 :]


async def test_openai_responses_client_background_streaming_structured_response() -> None:
    """Test OpenAI chat completion responses."""
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClient)

    messages: list[ChatMessage] = []
    messages.append(ChatMessage(role="user", text="The weather in New York is sunny"))
    messages.append(ChatMessage(role="user", text="What is the weather in New York?"))

    # Test that the client can be used to get a response
    stream = openai_responses_client.get_streaming_response(
        messages=messages,
        background=True,
        store=True,
        response_format=OutputStruct,
    )
    conversation_id: str | None = None
    all_messages: list[str] = []
    partial_messages: list[str] = []
    assert stream is not None
    async for response in stream:
        assert isinstance(response, ChatResponseUpdate)
        if response.conversation_id:
            conversation_id = response.conversation_id
        # The first response should contain the conversation_id
        assert conversation_id is not None
        all_messages.append(response.text)

    restart_idx = floor(len(all_messages) / 2)
    # Currently broken. See https://github.com/openai/openai-python/issues/2579
    with pytest.raises(ServiceResponseException):
        stream = openai_responses_client.get_streaming_response(
            messages=[],
            long_running_conversation_id=conversation_id,
            long_running_sequence_number=restart_idx,
            response_format=OutputStruct,
        )
        assert stream is not None
        async for response in stream:
            assert isinstance(response, ChatResponseUpdate)
            partial_messages.append(response.text)

        assert partial_messages == all_messages[restart_idx + 1 :]
        output = OutputStruct.model_validate_json("".join(all_messages))
        assert "new york" in output.location.lower()
        assert "sunny" in output.weather.lower()
