# Copyright (c) Microsoft. All rights reserved.

from typing import Annotated

import pytest
from pydantic import BaseModel

from agent_framework import ChatClient, ChatMessage, ChatResponse, ChatResponseUpdate, TextContent, ai_function
from agent_framework.openai import OpenAIResponsesClient


class OutputStruct(BaseModel):
    """A structured output for testing purposes."""

    location: str
    weather: str


@ai_function
async def get_weather(location: Annotated[str, "The location as a city name"]) -> str:
    """Get the current weather in a given location."""
    # Implementation of the tool to get weather
    return f"The current weather in {location} is sunny."


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
    messages.append(ChatMessage(role="user", text="What is the weather in New York?"))

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
    assert output.location == "New York"
    assert "sunny" in output.weather


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
    messages.append(ChatMessage(role="user", text="The weather in New York is sunny"))
    messages.append(ChatMessage(role="user", text="What is the weather in New York?"))

    # This is currently broken. See https://github.com/openai/openai-python/issues/2305
    with pytest.raises(AttributeError):
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
        assert output.location == "New York"
        assert "sunny" in output.weather


async def test_openai_responses_client_streaming_tools() -> None:
    """Test AzureOpenAI chat completion responses."""
    openai_responses_client = OpenAIResponsesClient(ai_model_id="gpt-4o-mini")

    assert isinstance(openai_responses_client, ChatClient)

    messages: list[ChatMessage] = [ChatMessage(role="user", text="What is the weather in New York?")]

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
    messages.append(ChatMessage(role="user", text="What is the weather in New York?"))

    # This is currently broken. See https://github.com/openai/openai-python/issues/2305
    with pytest.raises(AttributeError):
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
        assert output.location == "New York"
        assert "sunny" in output.weather
