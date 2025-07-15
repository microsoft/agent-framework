# Copyright (c) Microsoft. All rights reserved.

from agent_framework import ChatClient, ChatMessage, ChatResponse, ChatResponseUpdate, TextContent, ai_function

from agent_framework_azure import AzureChatClient


@ai_function
def get_story_text() -> str:
    """Returns a story about Emily and David."""
    return (
        "Emily and David, two passionate scientists, met during a research expedition to Antarctica. "
        "Bonded by their love for the natural world and shared curiosity, they uncovered a "
        "groundbreaking phenomenon in glaciology that could potentially reshape our understanding "
        "of climate change."
    )


async def test_azure_openai_chat_client_response() -> None:
    """Test Azure OpenAI chat completion responses."""
    azure_chat_client = AzureChatClient(deployment_name="gpt-4o")

    assert isinstance(azure_chat_client, ChatClient)

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
    response = await azure_chat_client.get_response(messages=messages)

    assert response is not None
    assert isinstance(response, ChatResponse)
    assert "scientists" in response.text


async def test_azure_openai_chat_client_response_tools() -> None:
    """Test AzureOpenAI chat completion responses."""
    azure_chat_client = AzureChatClient(deployment_name="gpt-4o")

    assert isinstance(azure_chat_client, ChatClient)

    messages: list[ChatMessage] = []
    messages.append(ChatMessage(role="user", text="who are Emily and David?"))

    # Test that the client can be used to get a response
    response = await azure_chat_client.get_response(
        messages=messages,
        tools=[get_story_text],
        tool_choice="auto",
    )

    assert response is not None
    assert isinstance(response, ChatResponse)
    assert "scientists" in response.text


async def test_azure_openai_chat_client_streaming() -> None:
    """Test Azure OpenAI chat completion responses."""
    azure_chat_client = AzureChatClient(deployment_name="gpt-4o")

    assert isinstance(azure_chat_client, ChatClient)

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
    response = azure_chat_client.get_streaming_response(messages=messages)

    full_message: str = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text

    assert "scientists" in full_message


async def test_azure_openai_chat_client_streaming_tools() -> None:
    """Test AzureOpenAI chat completion responses."""
    azure_chat_client = AzureChatClient(deployment_name="gpt-4o")

    assert isinstance(azure_chat_client, ChatClient)

    messages: list[ChatMessage] = []
    messages.append(ChatMessage(role="user", text="who are Emily and David?"))

    # Test that the client can be used to get a response
    response = azure_chat_client.get_streaming_response(
        messages=messages,
        tools=[get_story_text],
        tool_choice="auto",
    )
    full_message: str = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text

    assert "scientists" in full_message
