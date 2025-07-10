# Copyright (c) Microsoft. All rights reserved.

from agent_framework import ChatClient, ChatMessage, ChatOptions, ChatResponse
from agent_framework.openai import OpenAIChatCompletion


def get_story_text() -> str:
    """Return a sample story text."""
    return (
        "Emily and David, two passionate scientists, met during a research expedition to Antarctica. "
        "Bonded by their love for the natural world and shared curiosity, they uncovered a "
        "groundbreaking phenomenon in glaciology that could potentially reshape our understanding "
        "of climate change."
    )


async def test_openai_chat_completion_response() -> None:
    """Test OpenAI chat completion responses."""
    open_ai_chat_completion = OpenAIChatCompletion(ai_model_id="gpt-4.1-mini")

    assert isinstance(open_ai_chat_completion, ChatClient)

    messages: list[ChatMessage] = []
    messages.append(ChatMessage(role="user", text=get_story_text()))
    messages.append(ChatMessage(role="user", text="who are Emily and David?"))

    # Test that the client can be used to get a response
    response = await open_ai_chat_completion.get_response(messages=messages, chat_options=ChatOptions())

    assert response is not None
    assert isinstance(response, ChatResponse)
    assert "two passionate scientists" in response.text


# TODO(peterychang): Add test using tools to get the story text
