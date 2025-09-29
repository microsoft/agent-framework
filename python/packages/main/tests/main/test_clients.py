# Copyright (c) Microsoft. All rights reserved.

import sys

from agent_framework import (
    BaseChatClient,
    ChatClientProtocol,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    FunctionCallContent,
    FunctionResultContent,
    Role,
    TextContent,
    ai_function,
)

if sys.version_info >= (3, 12):
    pass  # type: ignore
else:
    pass  # type: ignore[import]


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


async def test_base_client_with_function_calling(chat_client_base: ChatClientProtocol):
    exec_counter = 0

    @ai_function(name="test_function")
    def ai_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="test_function", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]
    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[ai_func])
    assert exec_counter == 1
    assert len(response.messages) == 3
    assert response.messages[0].role == Role.ASSISTANT
    assert isinstance(response.messages[0].contents[0], FunctionCallContent)
    assert response.messages[0].contents[0].name == "test_function"
    assert response.messages[0].contents[0].arguments == '{"arg1": "value1"}'
    assert response.messages[0].contents[0].call_id == "1"
    assert response.messages[1].role == Role.TOOL
    assert isinstance(response.messages[1].contents[0], FunctionResultContent)
    assert response.messages[1].contents[0].call_id == "1"
    assert response.messages[1].contents[0].result == "Processed value1"
    assert response.messages[2].role == Role.ASSISTANT
    assert response.messages[2].text == "done"


async def test_base_client_with_function_calling_resets(chat_client_base: ChatClientProtocol):
    exec_counter = 0

    @ai_function(name="test_function")
    def ai_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="test_function", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="2", name="test_function", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]
    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[ai_func])
    assert exec_counter == 2
    assert len(response.messages) == 5
    assert response.messages[0].role == Role.ASSISTANT
    assert response.messages[1].role == Role.TOOL
    assert response.messages[2].role == Role.ASSISTANT
    assert response.messages[3].role == Role.TOOL
    assert response.messages[4].role == Role.ASSISTANT
    assert isinstance(response.messages[0].contents[0], FunctionCallContent)
    assert isinstance(response.messages[1].contents[0], FunctionResultContent)
    assert isinstance(response.messages[2].contents[0], FunctionCallContent)
    assert isinstance(response.messages[3].contents[0], FunctionResultContent)


async def test_base_client_with_streaming_function_calling(chat_client_base: ChatClientProtocol):
    exec_counter = 0

    @ai_function(name="test_function")
    def ai_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="1", name="test_function", arguments='{"arg1":')],
                role="assistant",
            ),
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="1", name="test_function", arguments='"value1"}')],
                role="assistant",
            ),
        ],
        [
            ChatResponseUpdate(
                contents=[TextContent(text="Processed value1")],
                role="assistant",
            )
        ],
    ]
    updates = []
    async for update in chat_client_base.get_streaming_response("hello", tool_choice="auto", tools=[ai_func]):
        updates.append(update)
    assert len(updates) == 4  # two updates with the function call, the function result and the final text
    assert updates[0].contents[0].call_id == "1"
    assert updates[1].contents[0].call_id == "1"
    assert updates[2].contents[0].call_id == "1"
    assert updates[3].text == "Processed value1"
    assert exec_counter == 1
