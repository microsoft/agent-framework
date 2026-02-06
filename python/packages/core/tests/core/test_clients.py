# Copyright (c) Microsoft. All rights reserved.


from unittest.mock import patch

from agent_framework import (
    BaseChatClient,
    ChatClientProtocol,
    ChatMessage,
    ChatResponse,
)


def test_chat_client_type(chat_client: ChatClientProtocol):
    assert isinstance(chat_client, ChatClientProtocol)


async def test_chat_client_get_response(chat_client: ChatClientProtocol):
    response = await chat_client.get_response(ChatMessage(role="user", text="Hello"))
    assert response.text == "test response"
    assert response.messages[0].role == "assistant"


async def test_chat_client_get_response_streaming(chat_client: ChatClientProtocol):
    async for update in chat_client.get_response(ChatMessage(role="user", text="Hello"), stream=True):
        assert update.text == "test streaming response " or update.text == "another update"
        assert update.role == "assistant"


def test_base_client(chat_client_base: ChatClientProtocol):
    assert isinstance(chat_client_base, BaseChatClient)
    assert isinstance(chat_client_base, ChatClientProtocol)


async def test_base_client_get_response(chat_client_base: ChatClientProtocol):
    response = await chat_client_base.get_response(ChatMessage(role="user", text="Hello"))
    assert response.messages[0].role == "assistant"
    assert response.messages[0].text == "test response - Hello"


async def test_base_client_get_response_streaming(chat_client_base: ChatClientProtocol):
    async for update in chat_client_base.get_response(ChatMessage(role="user", text="Hello"), stream=True):
        assert update.text == "update - Hello" or update.text == "another update"


async def test_chat_client_instructions_handling(chat_client_base: ChatClientProtocol):
    instructions = "You are a helpful assistant."

    async def fake_inner_get_response(**kwargs):
        return ChatResponse(messages=[ChatMessage(role="assistant", text="ok")])

    with patch.object(
        chat_client_base,
        "_inner_get_response",
        side_effect=fake_inner_get_response,
    ) as mock_inner_get_response:
        await chat_client_base.get_response("hello", options={"instructions": instructions})
        mock_inner_get_response.assert_called_once()
        _, kwargs = mock_inner_get_response.call_args
        messages = kwargs.get("messages", [])
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].text == "hello"

        from agent_framework._types import prepend_instructions_to_messages

        appended_messages = prepend_instructions_to_messages(
            [ChatMessage(role="user", text="hello")],
            instructions,
        )
        assert len(appended_messages) == 2
        assert appended_messages[0].role == "system"
        assert appended_messages[0].text == "You are a helpful assistant."
        assert appended_messages[1].role == "user"
        assert appended_messages[1].text == "hello"
