# Copyright (c) Microsoft. All rights reserved.


from agent_framework import (
    BaseChatClient,
    ChatClientProtocol,
    ChatMessage,
    Role,
)


def test_chat_client_type(chat_client: ChatClientProtocol):
    assert isinstance(chat_client, ChatClientProtocol)


async def test_chat_client_get_response(chat_client: ChatClientProtocol):
    response = await chat_client.get_response(ChatMessage(role="user", text="Hello"))
    assert response.text == "test response"
    assert response.messages[0].role == Role.ASSISTANT


async def test_chat_client_get_streaming_response(chat_client: ChatClientProtocol):
    async for update in chat_client.get_streaming_response(ChatMessage(role="user", text="Hello")):
        assert update.text == "test streaming response " or update.text == "another update"
        assert update.role == Role.ASSISTANT


def test_base_client(chat_client_base: ChatClientProtocol):
    assert isinstance(chat_client_base, BaseChatClient)
    assert isinstance(chat_client_base, ChatClientProtocol)


async def test_base_client_get_response(chat_client_base: ChatClientProtocol):
    response = await chat_client_base.get_response(ChatMessage(role="user", text="Hello"))
    assert response.messages[0].role == Role.ASSISTANT
    assert response.messages[0].text == "test response - Hello"


async def test_base_client_get_streaming_response(chat_client_base: ChatClientProtocol):
    async for update in chat_client_base.get_streaming_response(ChatMessage(role="user", text="Hello")):
        assert update.text == "update - Hello" or update.text == "another update"
