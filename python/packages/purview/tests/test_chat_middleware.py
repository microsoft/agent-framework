# Copyright (c) Microsoft. All rights reserved.
"""Tests for Purview chat middleware."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import ChatContext, ChatMessage, Role
from azure.core.credentials import AccessToken

from agent_framework_purview import PurviewChatPolicyMiddleware, PurviewSettings


@dataclass
class DummyChatClient:
    name: str = "dummy"


class TestPurviewChatPolicyMiddleware:
    @pytest.fixture
    def mock_credential(self) -> AsyncMock:
        credential = AsyncMock()
        credential.get_token = AsyncMock(return_value=AccessToken("fake-token", 9999999999))
        return credential

    @pytest.fixture
    def settings(self) -> PurviewSettings:
        return PurviewSettings(app_name="Test App", tenant_id="test-tenant")

    @pytest.fixture
    def middleware(self, mock_credential: AsyncMock, settings: PurviewSettings) -> PurviewChatPolicyMiddleware:
        return PurviewChatPolicyMiddleware(mock_credential, settings)

    @pytest.fixture
    def chat_context(self) -> ChatContext:
        chat_client = DummyChatClient()
        chat_options = MagicMock()
        chat_options.model = "test-model"
        return ChatContext(
            chat_client=chat_client, messages=[ChatMessage(role=Role.USER, text="Hello")], chat_options=chat_options
        )

    async def test_initialization(self, middleware: PurviewChatPolicyMiddleware) -> None:
        assert middleware._client is not None
        assert middleware._processor is not None

    async def test_allows_clean_prompt(
        self, middleware: PurviewChatPolicyMiddleware, chat_context: ChatContext
    ) -> None:
        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")) as mock_proc:
            next_called = False

            async def mock_next(ctx: ChatContext) -> None:
                nonlocal next_called
                next_called = True

                class Result:
                    def __init__(self):
                        self.messages = [ChatMessage(role=Role.ASSISTANT, text="Hi there")]

                ctx.result = Result()

            await middleware.process(chat_context, mock_next)
            assert next_called
            assert mock_proc.call_count == 2
            assert chat_context.result.messages[0].role == Role.ASSISTANT

    async def test_blocks_prompt(self, middleware: PurviewChatPolicyMiddleware, chat_context: ChatContext) -> None:
        with patch.object(middleware._processor, "process_messages", return_value=(True, "user-123")):

            async def mock_next(ctx: ChatContext) -> None:  # should not run
                raise AssertionError("next should not be called when prompt blocked")

            await middleware.process(chat_context, mock_next)
            assert chat_context.terminate
            assert chat_context.result
            msg = chat_context.result[0]  # type: ignore[index]
            assert msg.role in ("system", Role.SYSTEM)
            assert "blocked" in msg.text.lower()

    async def test_blocks_response(self, middleware: PurviewChatPolicyMiddleware, chat_context: ChatContext) -> None:
        call_state = {"count": 0}

        async def side_effect(messages, activity, user_id=None):
            call_state["count"] += 1
            should_block = call_state["count"] == 2
            return (should_block, "user-123")

        with patch.object(middleware._processor, "process_messages", side_effect=side_effect):

            async def mock_next(ctx: ChatContext) -> None:
                class Result:
                    def __init__(self):
                        self.messages = [ChatMessage(role=Role.ASSISTANT, text="Sensitive output")]  # pragma: no cover

                ctx.result = Result()

            await middleware.process(chat_context, mock_next)
            assert call_state["count"] == 2
            msgs = getattr(chat_context.result, "messages", None) or chat_context.result
            first_msg = msgs[0]
            assert first_msg.role in ("system", Role.SYSTEM)
            assert "blocked" in first_msg.text.lower()

    async def test_streaming_skips_post_check(self, middleware: PurviewChatPolicyMiddleware) -> None:
        chat_client = DummyChatClient()
        chat_options = MagicMock()
        chat_options.model = "test-model"
        streaming_context = ChatContext(
            chat_client=chat_client,
            messages=[ChatMessage(role=Role.USER, text="Hello")],
            chat_options=chat_options,
            is_streaming=True,
        )
        with patch.object(middleware._processor, "process_messages", return_value=False) as mock_proc:

            async def mock_next(ctx: ChatContext) -> None:
                ctx.result = MagicMock()

            await middleware.process(streaming_context, mock_next)
            assert mock_proc.call_count == 1

    async def test_chat_middleware_handles_post_check_exception(
        self, middleware: PurviewChatPolicyMiddleware, chat_context: ChatContext
    ) -> None:
        """Test that exceptions in post-check are logged but don't affect result."""
        call_count = 0

        async def mock_process_messages(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (False, "user-123")  # Pre-check succeeds
            raise Exception("Post-check error")  # Post-check fails

        with patch.object(middleware._processor, "process_messages", side_effect=mock_process_messages):

            async def mock_next(ctx: ChatContext) -> None:
                # Create a mock result with messages attribute
                result = MagicMock()
                result.messages = [ChatMessage(role=Role.ASSISTANT, text="Response")]
                ctx.result = result

            await middleware.process(chat_context, mock_next)

            # Should have been called twice (pre and post)
            assert call_count == 2
            # Result should still be set
            assert chat_context.result is not None
