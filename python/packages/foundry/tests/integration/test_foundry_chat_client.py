# Copyright (c) Microsoft. All rights reserved.

from typing import Annotated

from agent_framework import ChatClient, ChatMessage, ChatResponse, ChatResponseUpdate, TextContent
from pydantic import Field

from agent_framework_foundry import FoundryChatClient


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    return f"The weather in {location} is sunny with a high of 25°C."


async def test_foundry_chat_client_get_response() -> None:
    """Test Foundry Chat Client response."""
    async with FoundryChatClient() as foundry_chat_client:
        assert isinstance(foundry_chat_client, ChatClient)

        messages: list[ChatMessage] = []
        messages.append(
            ChatMessage(
                role="user",
                text="The weather in Seattle is currently sunny with a high of 25°C. "
                "It's a beautiful day for outdoor activities.",
            )
        )
        messages.append(ChatMessage(role="user", text="What's the weather like today?"))

        # Test that the client can be used to get a response
        response = await foundry_chat_client.get_response(messages=messages)

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert any(word in response.text.lower() for word in ["sunny", "25"])


async def test_foundry_chat_client_get_response_tools() -> None:
    """Test Foundry Chat Client response with tools."""
    async with FoundryChatClient() as foundry_chat_client:
        assert isinstance(foundry_chat_client, ChatClient)

        messages: list[ChatMessage] = []
        messages.append(ChatMessage(role="user", text="What's the weather like in Seattle?"))

        # Test that the client can be used to get a response
        response = await foundry_chat_client.get_response(
            messages=messages,
            tools=[get_weather],
            tool_choice="auto",
        )

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert any(word in response.text.lower() for word in ["sunny", "25"])


async def test_foundry_chat_client_streaming() -> None:
    """Test Foundry Chat Client streaming response."""
    async with FoundryChatClient() as foundry_chat_client:
        assert isinstance(foundry_chat_client, ChatClient)

        messages: list[ChatMessage] = []
        messages.append(
            ChatMessage(
                role="user",
                text="The weather in Seattle is currently sunny with a high of 25°C. "
                "It's a beautiful day for outdoor activities.",
            )
        )
        messages.append(ChatMessage(role="user", text="What's the weather like today?"))

        # Test that the client can be used to get a response
        response = foundry_chat_client.get_streaming_response(messages=messages)

        full_message: str = ""
        async for chunk in response:
            assert chunk is not None
            assert isinstance(chunk, ChatResponseUpdate)
            for content in chunk.contents:
                if isinstance(content, TextContent) and content.text:
                    full_message += content.text

        assert any(word in full_message.lower() for word in ["sunny", "25"])


async def test_foundry_chat_client_streaming_tools() -> None:
    """Test Foundry Chat Client streaming response with tools."""
    async with FoundryChatClient() as foundry_chat_client:
        assert isinstance(foundry_chat_client, ChatClient)

        messages: list[ChatMessage] = []
        messages.append(ChatMessage(role="user", text="What's the weather like in Seattle?"))

        # Test that the client can be used to get a response
        response = foundry_chat_client.get_streaming_response(
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

        assert any(word in full_message.lower() for word in ["sunny", "25"])
