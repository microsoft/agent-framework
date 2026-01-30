# Copyright (c) Microsoft. All rights reserved.


from unittest.mock import patch

from agent_framework import (
    BaseChatClient,
    ChatClientProtocol,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    Role,
)
from agent_framework._clients import _filter_internal_kwargs
from agent_framework._types import prepend_instructions_to_messages


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


async def test_chat_client_instructions_handling(chat_client_base: ChatClientProtocol):
    instructions = "You are a helpful assistant."
    with patch.object(
        chat_client_base,
        "_inner_get_response",
    ) as mock_inner_get_response:
        await chat_client_base.get_response("hello", options={"instructions": instructions})
        mock_inner_get_response.assert_called_once()
        _, kwargs = mock_inner_get_response.call_args
        messages = kwargs.get("messages", [])
        assert len(messages) == 1
        assert messages[0].role == Role.USER
        assert messages[0].text == "hello"

        appended_messages = prepend_instructions_to_messages(
            [ChatMessage(role=Role.USER, text="hello")],
            instructions,
        )
        assert len(appended_messages) == 2
        assert appended_messages[0].role == Role.SYSTEM
        assert appended_messages[0].text == "You are a helpful assistant."
        assert appended_messages[1].role == Role.USER
        assert appended_messages[1].text == "hello"


# region Internal kwargs filtering tests


class TestFilterInternalKwargs:
    """Tests for _filter_internal_kwargs function."""

    def test_filters_underscore_prefixed_kwargs(self):
        """Kwargs starting with underscore should be filtered out."""
        kwargs = {
            "_function_middleware_pipeline": object(),
            "_chat_middleware_pipeline": object(),
            "_internal": "value",
            "normal_kwarg": "kept",
        }
        result = _filter_internal_kwargs(kwargs)
        assert "_function_middleware_pipeline" not in result
        assert "_chat_middleware_pipeline" not in result
        assert "_internal" not in result
        assert result["normal_kwarg"] == "kept"

    def test_filters_thread_kwarg(self):
        """The 'thread' kwarg should be filtered out."""
        kwargs = {"thread": object(), "other": "value"}
        result = _filter_internal_kwargs(kwargs)
        assert "thread" not in result
        assert result["other"] == "value"

    def test_filters_middleware_kwarg(self):
        """The 'middleware' kwarg should be filtered out."""
        kwargs = {"middleware": [object()], "other": "value"}
        result = _filter_internal_kwargs(kwargs)
        assert "middleware" not in result
        assert result["other"] == "value"

    def test_preserves_conversation_id(self):
        """The 'conversation_id' kwarg should NOT be filtered (used by Azure AI)."""
        kwargs = {"conversation_id": "test-id", "other": "value"}
        result = _filter_internal_kwargs(kwargs)
        assert result["conversation_id"] == "test-id"
        assert result["other"] == "value"

    def test_preserves_other_kwargs(self):
        """Regular kwargs should be preserved."""
        kwargs = {
            "temperature": 0.7,
            "max_tokens": 100,
            "custom_param": "value",
        }
        result = _filter_internal_kwargs(kwargs)
        assert result == kwargs

    def test_filters_multiple_internal_kwargs(self):
        """Multiple internal kwargs should all be filtered."""
        kwargs = {
            "_function_middleware_pipeline": object(),
            "thread": object(),
            "middleware": [object()],
            "temperature": 0.7,
            "conversation_id": "test-id",
        }
        result = _filter_internal_kwargs(kwargs)
        assert "_function_middleware_pipeline" not in result
        assert "thread" not in result
        assert "middleware" not in result
        assert result["temperature"] == 0.7
        assert result["conversation_id"] == "test-id"

    def test_empty_kwargs(self):
        """Empty kwargs should return empty dict."""
        result = _filter_internal_kwargs({})
        assert result == {}


async def test_get_response_filters_internal_kwargs(chat_client_base: ChatClientProtocol):
    """Verify that get_response filters internal kwargs before calling _inner_get_response."""
    with patch.object(chat_client_base, "_inner_get_response") as mock_inner:
        mock_inner.return_value = ChatResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="response")])

        # Call with internal kwargs that should be filtered
        # Note: _function_middleware_pipeline is handled by the @use_function_invocation decorator,
        # not the base class filtering, so we don't test it here.
        await chat_client_base.get_response(
            "hello",
            thread=object(),
            middleware=[object()],
            _custom_internal="filtered",  # Underscore-prefixed should be filtered
            conversation_id="test-id",  # Should NOT be filtered
            custom_param="value",  # Should NOT be filtered
        )

        mock_inner.assert_called_once()
        _, kwargs = mock_inner.call_args

        # Internal kwargs should be filtered
        assert "thread" not in kwargs
        assert "middleware" not in kwargs
        assert "_custom_internal" not in kwargs

        # These should be preserved
        assert kwargs["conversation_id"] == "test-id"
        assert kwargs["custom_param"] == "value"


async def test_get_streaming_response_filters_internal_kwargs(chat_client_base: ChatClientProtocol):
    """Verify that get_streaming_response filters internal kwargs before calling _inner_get_streaming_response."""
    with patch.object(chat_client_base, "_inner_get_streaming_response") as mock_inner:

        async def mock_generator(*args, **kwargs):
            yield ChatResponseUpdate(text="response")

        mock_inner.return_value = mock_generator()

        # Call with internal kwargs that should be filtered
        # Note: _function_middleware_pipeline is handled by the @use_function_invocation decorator,
        # not the base class filtering, so we don't test it here.
        async for _ in chat_client_base.get_streaming_response(
            "hello",
            thread=object(),
            middleware=[object()],
            _custom_internal="filtered",  # Underscore-prefixed should be filtered
            conversation_id="test-id",  # Should NOT be filtered
            custom_param="value",  # Should NOT be filtered
        ):
            pass

        mock_inner.assert_called_once()
        _, kwargs = mock_inner.call_args

        # Internal kwargs should be filtered
        assert "thread" not in kwargs
        assert "middleware" not in kwargs
        assert "_custom_internal" not in kwargs

        # These should be preserved
        assert kwargs["conversation_id"] == "test-id"
        assert kwargs["custom_param"] == "value"


# endregion
