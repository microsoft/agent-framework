# Copyright (c) Microsoft. All rights reserved.


from unittest.mock import patch

from agent_framework import (
    BaseChatClient,
    ChatResponse,
    Message,
    SupportsChatGetResponse,
    SupportsCodeInterpreterTool,
    SupportsFileSearchTool,
    SupportsImageGenerationTool,
    SupportsMCPTool,
    SupportsWebSearchTool,
)


def test_chat_client_type(client: SupportsChatGetResponse):
    assert isinstance(client, SupportsChatGetResponse)


async def test_chat_client_get_response(client: SupportsChatGetResponse):
    response = await client.get_response([Message(role="user", text="Hello")])
    assert response.text == "test response"
    assert response.messages[0].role == "assistant"


async def test_chat_client_get_response_streaming(client: SupportsChatGetResponse):
    async for update in client.get_response([Message(role="user", text="Hello")], stream=True):
        assert update.text == "test streaming response " or update.text == "another update"
        assert update.role == "assistant"


def test_base_client(chat_client_base: SupportsChatGetResponse):
    assert isinstance(chat_client_base, BaseChatClient)
    assert isinstance(chat_client_base, SupportsChatGetResponse)


async def test_base_client_get_response(chat_client_base: SupportsChatGetResponse):
    response = await chat_client_base.get_response([Message(role="user", text="Hello")])
    assert response.messages[0].role == "assistant"
    assert response.messages[0].text == "test response - Hello"


async def test_base_client_get_response_streaming(chat_client_base: SupportsChatGetResponse):
    async for update in chat_client_base.get_response([Message(role="user", text="Hello")], stream=True):
        assert update.text == "update - Hello" or update.text == "another update"


async def test_chat_client_instructions_handling(chat_client_base: SupportsChatGetResponse):
    instructions = "You are a helpful assistant."

    async def fake_inner_get_response(**kwargs):
        return ChatResponse(messages=[Message(role="assistant", text="ok")])

    with patch.object(
        chat_client_base,
        "_inner_get_response",
        side_effect=fake_inner_get_response,
    ) as mock_inner_get_response:
        await chat_client_base.get_response(
            [Message(role="user", text="hello")], options={"instructions": instructions}
        )
        mock_inner_get_response.assert_called_once()
        _, kwargs = mock_inner_get_response.call_args
        messages = kwargs.get("messages", [])
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].text == "hello"

        from agent_framework._types import prepend_instructions_to_messages

        appended_messages = prepend_instructions_to_messages(
            [Message(role="user", text="hello")],
            instructions,
        )
        assert len(appended_messages) == 2
        assert appended_messages[0].role == "system"
        assert appended_messages[0].text == "You are a helpful assistant."
        assert appended_messages[1].role == "user"
        assert appended_messages[1].text == "hello"


# region Tool Support Protocol Tests


def test_openai_responses_client_supports_all_tool_protocols():
    """Test that OpenAIResponsesClient supports all hosted tool protocols."""
    from agent_framework.openai import OpenAIResponsesClient

    assert isinstance(OpenAIResponsesClient, SupportsCodeInterpreterTool)
    assert isinstance(OpenAIResponsesClient, SupportsWebSearchTool)
    assert isinstance(OpenAIResponsesClient, SupportsImageGenerationTool)
    assert isinstance(OpenAIResponsesClient, SupportsMCPTool)
    assert isinstance(OpenAIResponsesClient, SupportsFileSearchTool)


def test_openai_chat_client_supports_web_search_only():
    """Test that OpenAIChatClient only supports web search tool."""
    from agent_framework.openai import OpenAIChatClient

    assert not isinstance(OpenAIChatClient, SupportsCodeInterpreterTool)
    assert isinstance(OpenAIChatClient, SupportsWebSearchTool)
    assert not isinstance(OpenAIChatClient, SupportsImageGenerationTool)
    assert not isinstance(OpenAIChatClient, SupportsMCPTool)
    assert not isinstance(OpenAIChatClient, SupportsFileSearchTool)


def test_openai_assistants_client_supports_code_interpreter_and_file_search():
    """Test that OpenAIAssistantsClient supports code interpreter and file search."""
    from agent_framework.openai import OpenAIAssistantsClient

    assert isinstance(OpenAIAssistantsClient, SupportsCodeInterpreterTool)
    assert not isinstance(OpenAIAssistantsClient, SupportsWebSearchTool)
    assert not isinstance(OpenAIAssistantsClient, SupportsImageGenerationTool)
    assert not isinstance(OpenAIAssistantsClient, SupportsMCPTool)
    assert isinstance(OpenAIAssistantsClient, SupportsFileSearchTool)


def test_protocol_isinstance_with_client_instance():
    """Test that protocol isinstance works with client instances."""
    from agent_framework.openai import OpenAIResponsesClient

    # Create mock client instance (won't connect to API)
    client = OpenAIResponsesClient.__new__(OpenAIResponsesClient)

    assert isinstance(client, SupportsCodeInterpreterTool)
    assert isinstance(client, SupportsWebSearchTool)


def test_protocol_tool_methods_return_dict():
    """Test that static tool methods return dict[str, Any]."""
    from agent_framework.openai import OpenAIResponsesClient

    code_tool = OpenAIResponsesClient.get_code_interpreter_tool()
    assert isinstance(code_tool, dict)
    assert code_tool.get("type") == "code_interpreter"

    web_tool = OpenAIResponsesClient.get_web_search_tool()
    assert isinstance(web_tool, dict)
    assert web_tool.get("type") == "web_search"


# endregion
