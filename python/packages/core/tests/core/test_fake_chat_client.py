# Copyright (c) Microsoft. All rights reserved.

import pytest

from agent_framework import (
    Agent,
    ChatResponse,
    ChatResponseUpdate,
    FakeChatClient,
    Message,
)


# region Basic functionality


async def test_default_response():
    """FakeChatClient returns a default response when none configured."""
    client = FakeChatClient()
    response = await client.get_response([Message(role="user", contents=["Hi"])])
    assert response.text == "Hello!"
    assert response.messages[0].role == "assistant"


async def test_single_string_response():
    """FakeChatClient returns a configured string response."""
    client = FakeChatClient(responses=["Test response"])
    response = await client.get_response([Message(role="user", contents=["Hi"])])
    assert response.text == "Test response"


async def test_multiple_string_responses():
    """FakeChatClient cycles through multiple responses."""
    client = FakeChatClient(responses=["First", "Second", "Third"])
    r1 = await client.get_response([Message(role="user", contents=["Hi"])])
    r2 = await client.get_response([Message(role="user", contents=["Hi"])])
    r3 = await client.get_response([Message(role="user", contents=["Hi"])])
    assert r1.text == "First"
    assert r2.text == "Second"
    assert r3.text == "Third"


async def test_repeat_last_default():
    """By default, exhausted responses repeat the last one."""
    client = FakeChatClient(responses=["First", "Second"])
    r1 = await client.get_response([Message(role="user", contents=["Hi"])])
    r2 = await client.get_response([Message(role="user", contents=["Hi"])])
    r3 = await client.get_response([Message(role="user", contents=["Hi"])])
    assert r1.text == "First"
    assert r2.text == "Second"
    assert r3.text == "Second"  # Repeats last


async def test_repeat_loop():
    """With repeat='loop', responses cycle from the beginning."""
    client = FakeChatClient(responses=["A", "B"], repeat="loop")
    r1 = await client.get_response([Message(role="user", contents=["Hi"])])
    r2 = await client.get_response([Message(role="user", contents=["Hi"])])
    r3 = await client.get_response([Message(role="user", contents=["Hi"])])
    assert r1.text == "A"
    assert r2.text == "B"
    assert r3.text == "A"  # Loops back


def test_invalid_repeat_mode():
    """Invalid repeat mode raises ValueError."""
    with pytest.raises(ValueError, match="repeat must be"):
        FakeChatClient(repeat="invalid")


def test_empty_responses_raises():
    """Empty responses sequence raises ValueError."""
    with pytest.raises(ValueError, match="responses must not be empty"):
        FakeChatClient(responses=[])


# region Message and ChatResponse inputs


async def test_message_response():
    """FakeChatClient accepts Message objects as responses."""
    msg = Message(role="assistant", contents=["Custom message"])
    client = FakeChatClient(responses=[msg])
    response = await client.get_response([Message(role="user", contents=["Hi"])])
    assert response.text == "Custom message"


async def test_chat_response_input():
    """FakeChatClient accepts ChatResponse objects as responses."""
    chat_resp = ChatResponse(
        messages=[Message(role="assistant", contents=["From ChatResponse"])],
        model="test-model",
        response_id="test-123",
    )
    client = FakeChatClient(responses=[chat_resp])
    response = await client.get_response([Message(role="user", contents=["Hi"])])
    assert response.text == "From ChatResponse"
    assert response.model == "test-model"
    assert response.response_id == "test-123"


# region Streaming


async def test_streaming_response():
    """FakeChatClient streams character-by-character."""
    client = FakeChatClient(responses=["Hi"])
    chunks: list[str] = []
    async for update in client.get_response(
        [Message(role="user", contents=["Hello"])],
        stream=True,
    ):
        if update.text:
            chunks.append(update.text)

    assert chunks == ["H", "i"]


async def test_streaming_with_delay():
    """FakeChatClient respects stream_delay_seconds."""
    client = FakeChatClient(responses=["AB"], stream_delay_seconds=0.05)
    chunks: list[str] = []
    async for update in client.get_response(
        [Message(role="user", contents=["Hello"])],
        stream=True,
    ):
        if update.text:
            chunks.append(update.text)

    assert chunks == ["A", "B"]


async def test_streaming_finalizer_returns_original_response():
    """Streaming finalizer returns the original configured response."""
    client = FakeChatClient(responses=["Hello"])
    stream = client.get_response(
        [Message(role="user", contents=["Hi"])],
        stream=True,
    )
    updates: list[ChatResponseUpdate] = []
    async for update in stream:
        updates.append(update)

    final = await stream.finalize()
    assert final is not None
    assert final.text == "Hello"


# region Call counting


async def test_call_count():
    """FakeChatClient tracks call count."""
    client = FakeChatClient(responses=["Response"])
    assert client.call_count == 0
    await client.get_response([Message(role="user", contents=["Hi"])])
    assert client.call_count == 1
    await client.get_response([Message(role="user", contents=["Hi"])])
    assert client.call_count == 2


async def test_call_count_includes_streaming():
    """Call count increments for streaming calls too."""
    client = FakeChatClient(responses=["Hi"])
    assert client.call_count == 0
    async for _ in client.get_response(
        [Message(role="user", contents=["Hello"])],
        stream=True,
    ):
        pass
    assert client.call_count == 1


# region Integration with Agent


async def test_with_agent():
    """FakeChatClient works with Agent for end-to-end testing."""
    client = FakeChatClient(responses=["I am a test agent."])
    agent = Agent(
        client=client,
        name="TestAgent",
        instructions="You are a test assistant.",
    )
    result = await agent.run("Who are you?")
    assert "test agent" in result.text.lower()


async def test_with_agent_streaming():
    """FakeChatClient works with Agent in streaming mode."""
    client = FakeChatClient(responses=["Streaming response"])
    agent = Agent(
        client=client,
        name="StreamAgent",
    )
    chunks: list[str] = []
    async for chunk in agent.run("Hello", stream=True):
        if chunk.text:
            chunks.append(chunk.text)

    assert "".join(chunks) == "Streaming response"
