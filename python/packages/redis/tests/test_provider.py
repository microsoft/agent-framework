# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from agent_framework import ChatMessage, Context, Role, TextContent
from agent_framework.redis import RedisProvider


def test_redis_provider_import() -> None:
    """Ensure RedisProvider can be imported from agent_framework.redis aggregator."""
    assert RedisProvider is not None


@pytest.fixture
def sample_messages() -> list[ChatMessage]:
    return [
        ChatMessage(role=Role.USER, text="Hello, how are you?"),
        ChatMessage(role=Role.ASSISTANT, text="I'm doing well, thank you!"),
        ChatMessage(role=Role.SYSTEM, text="You are a helpful assistant"),
    ]


class TestRedisProviderInitialization:
    @patch("agent_framework_redis._provider.Redis")
    @patch("agent_framework_redis._provider.SemanticMessageHistory")
    @patch("agent_framework_redis._provider.HFTextVectorizer")
    def test_init_semantic(
        self,
        mock_vectorizer_cls: MagicMock,
        mock_sem_hist_cls: MagicMock,
        mock_redis_cls: MagicMock,
    ) -> None:
        mock_redis_cls.from_url.return_value = MagicMock()
        provider = RedisProvider(sequential=False)
        assert provider.sequential is False
        mock_vectorizer_cls.assert_called_once()
        mock_sem_hist_cls.assert_called_once()

    @patch("agent_framework_redis._provider.Redis")
    @patch("agent_framework_redis._provider.MessageHistory")
    def test_init_sequential(self, mock_hist_cls: MagicMock, mock_redis_cls: MagicMock) -> None:
        mock_redis_cls.from_url.return_value = MagicMock()
        provider = RedisProvider(sequential=True)
        assert provider.sequential is True
        mock_hist_cls.assert_called_once()


class TestRedisProviderAsyncContext:
    @patch("agent_framework_redis._provider.Redis")
    @patch("agent_framework_redis._provider.MessageHistory")
    async def test_async_context_manager(self, mock_hist_cls: MagicMock, mock_redis_cls: MagicMock) -> None:
        mock_redis_cls.from_url.return_value = MagicMock()
        mock_hist_cls.return_value = MagicMock()
        provider = RedisProvider(sequential=True)
        async with provider as ctx:
            assert ctx is provider


class TestMessagesAdding:
    @patch("agent_framework_redis._provider.Redis")
    @patch("agent_framework_redis._provider.MessageHistory")
    async def test_single_message(self, mock_hist_cls: MagicMock, mock_redis_cls: MagicMock) -> None:
        mock_redis_cls.from_url.return_value = MagicMock()
        hist = MagicMock()
        mock_hist_cls.return_value = hist

        provider = RedisProvider(sequential=True)
        msg = ChatMessage(role=Role.USER, text="Hello!")

        await provider.messages_adding("thread123", msg)

        hist.add_message.assert_called_once()
        call = hist.add_message.call_args
        assert call.args or call.kwargs  # ensure called with some payload

    @patch("agent_framework_redis._provider.Redis")
    @patch("agent_framework_redis._provider.MessageHistory")
    async def test_multiple_messages(
        self, mock_hist_cls: MagicMock, mock_redis_cls: MagicMock, sample_messages: list[ChatMessage]
    ) -> None:
        mock_redis_cls.from_url.return_value = MagicMock()
        hist = MagicMock()
        mock_hist_cls.return_value = hist

        provider = RedisProvider(sequential=True)
        await provider.messages_adding("thread123", sample_messages)

        # Should add at least once
        assert hist.add_message.call_count == 3

    @patch("agent_framework_redis._provider.Redis")
    @patch("agent_framework_redis._provider.MessageHistory")
    async def test_filters_empty_text(self, mock_hist_cls: MagicMock, mock_redis_cls: MagicMock) -> None:
        mock_redis_cls.from_url.return_value = MagicMock()
        hist = MagicMock()
        mock_hist_cls.return_value = hist

        provider = RedisProvider(sequential=True)
        messages = [
            ChatMessage(role=Role.USER, text=""),
            ChatMessage(role=Role.USER, text="   "),
            ChatMessage(role=Role.USER, text="Valid message"),
        ]

        await provider.messages_adding("thread123", messages)

        assert hist.add_message.call_count == 1

    @patch("agent_framework_redis._provider.Redis")
    @patch("agent_framework_redis._provider.MessageHistory")
    async def test_skips_non_user_assistant_system_roles(
        self, mock_hist_cls: MagicMock, mock_redis_cls: MagicMock
    ) -> None:
        mock_redis_cls.from_url.return_value = MagicMock()
        hist = MagicMock()
        mock_hist_cls.return_value = hist

        provider = RedisProvider(sequential=True)
        messages = [
            ChatMessage(role=Role.TOOL, text="tool output"),
            ChatMessage(role=Role.USER, text="include me"),
        ]

        await provider.messages_adding("thread123", messages)

        # Only USER message should be added
        assert hist.add_message.call_count == 1


class TestModelInvoking:
    @patch("agent_framework_redis._provider.Redis")
    @patch("agent_framework_redis._provider.MessageHistory")
    async def test_sequential_returns_context(self, mock_hist_cls: MagicMock, mock_redis_cls: MagicMock) -> None:
        mock_redis_cls.from_url.return_value = MagicMock()
        hist = MagicMock()
        hist.get_recent.return_value = [
            {"content": "User likes outdoor activities", "metadata": {}},
            {"content": "User lives in Seattle", "metadata": {}},
        ]
        mock_hist_cls.return_value = hist

        provider = RedisProvider(sequential=True)
        msg = ChatMessage(role=Role.USER, text="What's the weather?")
        ctx: Context = await provider.model_invoking(msg)

        assert isinstance(ctx, Context)
        assert ctx.contents
        assert isinstance(ctx.contents[0], TextContent)
        assert "Memories" in ctx.contents[0].text
        assert "User likes outdoor activities" in ctx.contents[0].text

    @patch("agent_framework_redis._provider.Redis")
    @patch("agent_framework_redis._provider.SemanticMessageHistory")
    @patch("agent_framework_redis._provider.HFTextVectorizer")
    async def test_semantic_returns_context(
        self,
        mock_vec_cls: MagicMock,
        mock_sem_hist_cls: MagicMock,
        mock_redis_cls: MagicMock,
    ) -> None:
        mock_redis_cls.from_url.return_value = MagicMock()
        sem_hist = MagicMock()
        sem_hist.get_relevant.return_value = [
            {"content": "Prefers metric units", "metadata": {}},
        ]
        mock_sem_hist_cls.return_value = sem_hist

        provider = RedisProvider(sequential=False)
        msg = ChatMessage(role=Role.USER, text="weather in NYC")
        ctx: Context = await provider.model_invoking(msg)

        assert ctx.contents and isinstance(ctx.contents[0], TextContent)
        assert "Prefers metric units" in ctx.contents[0].text

    @patch("agent_framework_redis._provider.Redis")
    @patch("agent_framework_redis._provider.SemanticMessageHistory")
    @patch("agent_framework_redis._provider.HFTextVectorizer")
    async def test_semantic_no_results_returns_empty_context(
        self,
        mock_vec_cls: MagicMock,
        mock_sem_hist_cls: MagicMock,
        mock_redis_cls: MagicMock,
    ) -> None:
        mock_redis_cls.from_url.return_value = MagicMock()
        sem_hist = MagicMock()
        sem_hist.get_relevant.return_value = []
        mock_sem_hist_cls.return_value = sem_hist

        provider = RedisProvider(sequential=False)
        ctx = await provider.model_invoking(ChatMessage(role=Role.USER, text="hi"))

        assert isinstance(ctx, Context)
        assert not ctx.contents

    @patch("agent_framework_redis._provider.deserialize", side_effect=Exception("boom"))
    @patch("agent_framework_redis._provider.Redis")
    @patch("agent_framework_redis._provider.MessageHistory")
    async def test_deserialize_failure_falls_back_to_string(
        self,
        mock_hist_cls: MagicMock,
        mock_redis_cls: MagicMock,
        _mock_deserialize: MagicMock,
    ) -> None:
        mock_redis_cls.from_url.return_value = MagicMock()
        hist = MagicMock()
        hist.get_recent.return_value = [
            {"content": "raw_text", "metadata": "not a json"},
        ]
        mock_hist_cls.return_value = hist

        provider = RedisProvider(sequential=True)
        ctx = await provider.model_invoking(ChatMessage(role=Role.USER, text="q"))
        assert ctx.contents and "raw_text" in ctx.contents[0].text

    @patch("agent_framework_redis._provider.Redis")
    @patch("agent_framework_redis._provider.SemanticMessageHistory")
    @patch("agent_framework_redis._provider.HFTextVectorizer")
    async def test_semantic_called_with_empty_prompt(
        self,
        mock_vec_cls: MagicMock,
        mock_sem_hist_cls: MagicMock,
        mock_redis_cls: MagicMock,
    ) -> None:
        mock_redis_cls.from_url.return_value = MagicMock()
        sem_hist = MagicMock()
        sem_hist.get_relevant.return_value = []
        mock_sem_hist_cls.return_value = sem_hist

        provider = RedisProvider(sequential=False)
        await provider.model_invoking([])
        # Prompt should be empty string when no messages
        kwargs = sem_hist.get_relevant.call_args.kwargs
        assert kwargs["prompt"] == ""


class TestConvenienceAPI:
    @patch("agent_framework_redis._provider.Redis")
    @patch("agent_framework_redis._provider.MessageHistory")
    async def test_add_and_clear(self, mock_hist_cls: MagicMock, mock_redis_cls: MagicMock) -> None:
        mock_redis_cls.from_url.return_value = MagicMock()
        hist = MagicMock()
        mock_hist_cls.return_value = hist

        provider = RedisProvider(sequential=True)
        await provider.add(text="remember this")
        hist.add_message.assert_called_once()

        await provider.clear()
        hist.clear.assert_called_once()

    @patch("agent_framework_redis._provider.Redis")
    @patch("agent_framework_redis._provider.MessageHistory")
    async def test_close(self, mock_hist_cls: MagicMock, mock_redis_cls: MagicMock) -> None:
        mock_redis_cls.from_url.return_value = MagicMock()
        hist = MagicMock()
        mock_hist_cls.return_value = hist

        provider = RedisProvider(sequential=True)
        await provider.close()
        hist.delete.assert_called_once()

    @patch("agent_framework_redis._provider.Redis")
    @patch("agent_framework_redis._provider.MessageHistory")
    async def test_add_with_role_override_in_metadata(
        self, mock_hist_cls: MagicMock, mock_redis_cls: MagicMock
    ) -> None:
        mock_redis_cls.from_url.return_value = MagicMock()
        hist = MagicMock()
        mock_hist_cls.return_value = hist

        provider = RedisProvider(sequential=True)
        await provider.add(text="note", metadata={"role": "assistant", "extra": 1})
        payload: dict[str, Any] = hist.add_message.call_args.args[0]
        assert payload["role"] == "assistant"

    @patch("agent_framework_redis._provider.Redis")
    @patch("agent_framework_redis._provider.SemanticMessageHistory")
    @patch("agent_framework_redis._provider.HFTextVectorizer")
    async def test_query_semantic_and_sequential_parameters(
        self,
        mock_vec_cls: MagicMock,
        mock_sem_hist_cls: MagicMock,
        mock_redis_cls: MagicMock,
    ) -> None:
        mock_redis_cls.from_url.return_value = MagicMock()
        sem_hist = MagicMock()
        mock_sem_hist_cls.return_value = sem_hist

        provider = RedisProvider(sequential=False)
        await provider.query("q", top_k=5, distance_threshold=0.5)
        kwargs = sem_hist.get_relevant.call_args.kwargs
        assert kwargs["top_k"] == 5
        assert kwargs["distance_threshold"] == 0.5

        # Sequential override
        msg_hist = MagicMock()
        with (
            patch("agent_framework_redis._provider.MessageHistory", return_value=msg_hist),
            patch.object(provider, "sequential", True),
        ):
            await provider.query("q", sequential=True, top_k=7)
            msg_hist.get_recent.assert_not_called()  # provider has semantic history.
            # method uses internal helper
        # Instead, internal helper still routes to existing _message_history.
        # Validate helper got called by switching impl
        with patch.object(provider, "_message_history", msg_hist):
            await provider.query("q", sequential=True, top_k=7)
            msg_hist.get_recent.assert_called_once()
