# Copyright (c) Microsoft. All rights reserved.
"""Tests for Purview chat middleware."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import (
    ChatContext,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    MiddlewareTermination,
    ResponseStream,
)
from azure.core.credentials import AccessToken

from agent_framework_purview import PurviewChatPolicyMiddleware, PurviewSettings
from agent_framework_purview._models import Activity


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
        client = DummyChatClient()
        chat_options = MagicMock()
        chat_options.model = "test-model"
        return ChatContext(
            client=cast(Any, client), messages=[Message(role="user", contents=["Hello"])], options=chat_options
        )

    async def test_initialization(self, middleware: PurviewChatPolicyMiddleware) -> None:
        assert middleware._client is not None
        assert middleware._processor is not None

    async def test_allows_clean_prompt(
        self, middleware: PurviewChatPolicyMiddleware, chat_context: ChatContext
    ) -> None:
        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")) as mock_proc:
            next_called = False

            async def mock_next() -> None:
                nonlocal next_called
                next_called = True

                chat_context.result = ChatResponse(messages=[Message(role="assistant", contents=["Hi there"])])

            await middleware.process(chat_context, mock_next)
            assert next_called
            assert mock_proc.call_count == 2
            result = cast(ChatResponse[Any], chat_context.result)
            assert result.messages[0].role == "assistant"

    async def test_blocks_prompt(self, middleware: PurviewChatPolicyMiddleware, chat_context: ChatContext) -> None:
        with patch.object(middleware._processor, "process_messages", return_value=(True, "user-123")):

            async def mock_next() -> None:  # should not run
                raise AssertionError("next should not be called when prompt blocked")

            with pytest.raises(MiddlewareTermination):
                await middleware.process(chat_context, mock_next)
            assert chat_context.result
            assert hasattr(chat_context.result, "messages")
            result = cast(ChatResponse[Any], chat_context.result)
            msg = result.messages[0]
            assert msg.role in ("system", "system")
            assert "blocked" in msg.text.lower()

    async def test_blocks_response(self, middleware: PurviewChatPolicyMiddleware, chat_context: ChatContext) -> None:
        call_state = {"count": 0}

        async def side_effect(messages, activity, session_id=None, user_id=None):
            call_state["count"] += 1
            should_block = call_state["count"] == 2
            return (should_block, "user-123")

        with patch.object(middleware._processor, "process_messages", side_effect=side_effect):

            async def mock_next() -> None:
                chat_context.result = ChatResponse(messages=[Message(role="assistant", contents=["Sensitive output"])])

            await middleware.process(chat_context, mock_next)
            assert call_state["count"] == 2
            result = cast(ChatResponse[Any], chat_context.result)
            msgs = result.messages
            first_msg = msgs[0]
            assert first_msg.role in ("system", "system")
            assert "blocked" in first_msg.text.lower()

    async def test_streaming_response_is_evaluated_and_blocked(self, middleware: PurviewChatPolicyMiddleware) -> None:
        """Streamed content is evaluated in full and replaced when policy blocks it."""
        client = DummyChatClient()
        chat_options = MagicMock()
        chat_options.model = "test-model"
        streaming_context = ChatContext(
            client=cast(Any, client),
            messages=[Message(role="user", contents=["Hello"])],
            options=chat_options,
            stream=True,
        )

        async def updates() -> AsyncIterator[ChatResponseUpdate]:
            yield ChatResponseUpdate(role="assistant", contents=[Content.from_text(text="confidential")])

        with patch.object(
            middleware._processor,
            "process_messages",
            side_effect=[(False, "user-123"), (True, "user-123")],
        ) as mock_proc:

            async def mock_next() -> None:
                streaming_context.result = cast(Any, ResponseStream(updates(), finalizer=ChatResponse.from_updates))

            await middleware.process(streaming_context, mock_next)
            released = [update async for update in cast(Any, streaming_context.result)]

        assert mock_proc.call_count == 2
        assert mock_proc.call_args_list[1][0][1] == Activity.DOWNLOAD_TEXT
        released_text = "".join(update.text for update in released)
        assert "confidential" not in released_text
        assert "blocked" in released_text.lower()

    async def test_streaming_response_passes_when_allowed(self, middleware: PurviewChatPolicyMiddleware) -> None:
        """Allowed streamed content is released unchanged, reusing the prompt-phase identity."""
        client = DummyChatClient()
        chat_options = MagicMock()
        chat_options.model = "test-model"
        streaming_context = ChatContext(
            client=cast(Any, client),
            messages=[Message(role="user", contents=["Hello"])],
            options=chat_options,
            stream=True,
        )

        async def updates() -> AsyncIterator[ChatResponseUpdate]:
            yield ChatResponseUpdate(role="assistant", contents=[Content.from_text(text="all ")])
            yield ChatResponseUpdate(role="assistant", contents=[Content.from_text(text="clear")])

        with patch.object(
            middleware._processor,
            "process_messages",
            side_effect=[(False, "user-123"), (False, "user-123")],
        ) as mock_proc:

            async def mock_next() -> None:
                streaming_context.result = cast(Any, ResponseStream(updates(), finalizer=ChatResponse.from_updates))

            await middleware.process(streaming_context, mock_next)
            released = [update async for update in cast(Any, streaming_context.result)]

        assert mock_proc.call_count == 2
        assert mock_proc.call_args_list[1].kwargs["user_id"] == "user-123"
        assert "".join(update.text for update in released) == "all clear"

    async def test_streaming_releases_the_evaluated_content_not_the_buffered_updates(
        self, middleware: PurviewChatPolicyMiddleware
    ) -> None:
        """The released updates come from the response that was evaluated, not from the buffer."""
        client = DummyChatClient()
        chat_options = MagicMock()
        chat_options.model = "test-model"
        streaming_context = ChatContext(
            client=cast(Any, client),
            messages=[Message(role="user", contents=["Hello"])],
            options=chat_options,
            stream=True,
        )

        async def updates() -> AsyncIterator[ChatResponseUpdate]:
            yield ChatResponseUpdate(role="assistant", contents=[Content.from_text(text="confidential")])

        def diverging_finalizer(_updates: Any) -> ChatResponse[Any]:
            return ChatResponse(messages=[Message(role="assistant", contents=[Content.from_text(text="benign")])])

        with patch.object(
            middleware._processor,
            "process_messages",
            side_effect=[(False, "user-123"), (False, "user-123")],
        ):

            async def mock_next() -> None:
                streaming_context.result = cast(Any, ResponseStream(updates(), finalizer=diverging_finalizer))

            await middleware.process(streaming_context, mock_next)
            released = [update async for update in cast(Any, streaming_context.result)]

        released_text = "".join(update.text for update in released)
        assert released_text == "benign"
        assert "confidential" not in released_text

    async def test_streaming_preserves_response_level_metadata(self, middleware: PurviewChatPolicyMiddleware) -> None:
        """Metadata carried by the response survives the buffered stream."""
        client = DummyChatClient()
        chat_options = MagicMock()
        chat_options.model = "test-model"
        streaming_context = ChatContext(
            client=cast(Any, client),
            messages=[Message(role="user", contents=["Hello"])],
            options=chat_options,
            stream=True,
        )

        async def updates() -> AsyncIterator[ChatResponseUpdate]:
            yield ChatResponseUpdate(role="assistant", contents=[Content.from_text(text="all clear")])

        def finalizer(_updates: Any) -> ChatResponse[Any]:
            return ChatResponse(
                messages=[Message(role="assistant", contents=[Content.from_text(text="all clear")])],
                response_id="resp-1",
                conversation_id="conv-1",
                model="model-1",
                continuation_token=cast(Any, {"token": "token-1"}),
                additional_properties={"custom": "value"},
            )

        with patch.object(
            middleware._processor,
            "process_messages",
            side_effect=[(False, "user-123"), (False, "user-123")],
        ):

            async def mock_next() -> None:
                streaming_context.result = cast(Any, ResponseStream(updates(), finalizer=finalizer))

            await middleware.process(streaming_context, mock_next)
            released = [update async for update in cast(Any, streaming_context.result)]

        assert released[-1].response_id == "resp-1"
        assert released[-1].conversation_id == "conv-1"
        assert released[-1].model == "model-1"
        assert released[-1].continuation_token == {"token": "token-1"}
        assert released[-1].additional_properties is not None
        assert released[-1].additional_properties["custom"] == "value"

    async def test_streaming_closes_the_inner_stream_when_never_pulled(
        self, middleware: PurviewChatPolicyMiddleware
    ) -> None:
        """Abandoning the gated stream before the first pull still releases the inner stream."""
        client = DummyChatClient()
        chat_options = MagicMock()
        chat_options.model = "test-model"
        streaming_context = ChatContext(
            client=cast(Any, client),
            messages=[Message(role="user", contents=["Hello"])],
            options=chat_options,
            stream=True,
        )
        closed = False

        async def updates() -> AsyncIterator[ChatResponseUpdate]:
            yield ChatResponseUpdate(role="assistant", contents=[Content.from_text(text="all clear")])

        def _mark_closed() -> None:
            nonlocal closed
            closed = True

        with patch.object(
            middleware._processor,
            "process_messages",
            side_effect=[(False, "user-123"), (False, "user-123")],
        ):

            async def mock_next() -> None:
                inner = ResponseStream(updates(), finalizer=ChatResponse.from_updates)
                inner.with_cleanup_hook(_mark_closed)
                streaming_context.result = cast(Any, inner)

            await middleware.process(streaming_context, mock_next)
            await cast(Any, streaming_context.result).close()

        assert closed is True

    async def test_chat_middleware_handles_post_check_exception(
        self, middleware: PurviewChatPolicyMiddleware, chat_context: ChatContext
    ) -> None:
        """Test that exceptions in post-check are logged but don't affect result when ignore_exceptions=True."""
        # Set ignore_exceptions to True to test exception suppression
        middleware._settings["ignore_exceptions"] = True

        call_count = 0

        async def mock_process_messages(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (False, "user-123")  # Pre-check succeeds
            raise Exception("Post-check error")  # Post-check fails

        with patch.object(middleware._processor, "process_messages", side_effect=mock_process_messages):

            async def mock_next() -> None:
                result = MagicMock()
                result.messages = [Message(role="assistant", contents=["Response"])]
                chat_context.result = result

            await middleware.process(chat_context, mock_next)

            # Should have been called twice (pre and post)
            assert call_count == 2
            # Result should still be set
            assert chat_context.result is not None

    async def test_chat_middleware_uses_consistent_user_id(
        self, middleware: PurviewChatPolicyMiddleware, chat_context: ChatContext
    ) -> None:
        """Test that the same user_id from pre-check is used in post-check."""
        captured_user_ids: list[str | None] = []

        async def mock_process_messages(messages, activity, session_id=None, user_id=None):
            captured_user_ids.append(user_id)
            return (False, "resolved-user-123")

        with patch.object(middleware._processor, "process_messages", side_effect=mock_process_messages):

            async def mock_next() -> None:
                result = MagicMock()
                result.messages = [Message(role="assistant", contents=["Response"])]
                chat_context.result = result

            await middleware.process(chat_context, mock_next)

            # Should have been called twice
            assert len(captured_user_ids) == 2
            # First call should have None (no user_id provided yet)
            assert captured_user_ids[0] is None
            # Second call should have the resolved user_id from first call
            assert captured_user_ids[1] == "resolved-user-123"

    async def test_chat_middleware_handles_payment_required_pre_check(self, mock_credential: AsyncMock) -> None:
        """Test that 402 in pre-check is handled based on settings."""
        from agent_framework_purview._exceptions import PurviewPaymentRequiredError

        # Test with ignore_payment_required=False
        settings = PurviewSettings(app_name="Test App", ignore_payment_required=False)
        middleware = PurviewChatPolicyMiddleware(mock_credential, settings)

        client = DummyChatClient()
        chat_options = MagicMock()
        chat_options.model = "test-model"
        context = ChatContext(
            client=cast(Any, client), messages=[Message(role="user", contents=["Hello"])], options=chat_options
        )

        async def mock_process_messages(*args, **kwargs):
            raise PurviewPaymentRequiredError("Payment required")

        with patch.object(middleware._processor, "process_messages", side_effect=mock_process_messages):

            async def mock_next() -> None:
                raise AssertionError("next should not be called")

            # Should raise the exception
            with pytest.raises(PurviewPaymentRequiredError):
                await middleware.process(context, mock_next)

    async def test_chat_middleware_handles_payment_required_post_check(self, mock_credential: AsyncMock) -> None:
        """Test that 402 in post-check is raised when ignore_payment_required=False."""
        from agent_framework_purview._exceptions import PurviewPaymentRequiredError

        settings = PurviewSettings(app_name="Test App", ignore_payment_required=False)
        middleware = PurviewChatPolicyMiddleware(mock_credential, settings)

        client = DummyChatClient()
        chat_options = MagicMock()
        chat_options.model = "test-model"
        context = ChatContext(
            client=cast(Any, client), messages=[Message(role="user", contents=["Hello"])], options=chat_options
        )

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (False, "user-123")
            raise PurviewPaymentRequiredError("Payment required")

        with patch.object(middleware._processor, "process_messages", side_effect=side_effect):

            async def mock_next() -> None:
                result = MagicMock()
                result.messages = [Message(role="assistant", contents=["OK"])]
                context.result = result

            with pytest.raises(PurviewPaymentRequiredError):
                await middleware.process(context, mock_next)

    async def test_chat_middleware_ignores_payment_required_when_configured(self, mock_credential: AsyncMock) -> None:
        """Test that 402 is ignored when ignore_payment_required=True."""
        from agent_framework_purview._exceptions import PurviewPaymentRequiredError

        settings = PurviewSettings(app_name="Test App", ignore_payment_required=True)
        middleware = PurviewChatPolicyMiddleware(mock_credential, settings)

        client = DummyChatClient()
        chat_options = MagicMock()
        chat_options.model = "test-model"
        context = ChatContext(
            client=cast(Any, client), messages=[Message(role="user", contents=["Hello"])], options=chat_options
        )

        async def mock_process_messages(*args, **kwargs):
            raise PurviewPaymentRequiredError("Payment required")

        with patch.object(middleware._processor, "process_messages", side_effect=mock_process_messages):

            async def mock_next() -> None:
                result = MagicMock()
                result.messages = [Message(role="assistant", contents=["Response"])]
                context.result = result

            # Should not raise, just log
            await middleware.process(context, mock_next)
            # Next should have been called
            assert context.result is not None

    async def test_chat_middleware_result_without_messages_attribute_is_not_silently_allowed(
        self, middleware: PurviewChatPolicyMiddleware, chat_context: ChatContext
    ) -> None:
        """A result shape that cannot be evaluated surfaces an error rather than passing unchecked."""
        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")):

            async def mock_next() -> None:
                # Set result to something without messages attribute
                chat_context.result = cast(Any, "Some string result")

            with pytest.raises(AttributeError):
                await middleware.process(chat_context, mock_next)

    async def test_chat_middleware_result_without_messages_attribute_tolerated_when_ignoring_exceptions(
        self, middleware: PurviewChatPolicyMiddleware, chat_context: ChatContext
    ) -> None:
        """With ignore_exceptions enabled, an unevaluatable result is logged and left unchanged."""
        middleware._settings["ignore_exceptions"] = True

        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")):

            async def mock_next() -> None:
                chat_context.result = cast(Any, "Some string result")

            await middleware.process(chat_context, mock_next)

            assert chat_context.result == "Some string result"

    async def test_chat_middleware_with_ignore_exceptions(self, mock_credential: AsyncMock) -> None:
        """Test that middleware respects ignore_exceptions setting."""
        settings = PurviewSettings(app_name="Test App", ignore_exceptions=True)
        middleware = PurviewChatPolicyMiddleware(mock_credential, settings)

        client = DummyChatClient()
        chat_options = MagicMock()
        chat_options.model = "test-model"
        context = ChatContext(
            client=cast(Any, client), messages=[Message(role="user", contents=["Hello"])], options=chat_options
        )

        async def mock_process_messages(*args, **kwargs):
            raise ValueError("Some error")

        with patch.object(middleware._processor, "process_messages", side_effect=mock_process_messages):

            async def mock_next() -> None:
                result = MagicMock()
                result.messages = [Message(role="assistant", contents=["Response"])]
                context.result = result

            # Should not raise, just log
            await middleware.process(context, mock_next)
            # Next should have been called
            assert context.result is not None

    async def test_chat_middleware_raises_on_pre_check_exception_when_ignore_exceptions_false(
        self, mock_credential: AsyncMock
    ) -> None:
        """Test that exceptions are propagated by default when ignore_exceptions=False."""
        settings = PurviewSettings(app_name="Test App", ignore_exceptions=False)
        middleware = PurviewChatPolicyMiddleware(mock_credential, settings)

        client = DummyChatClient()
        chat_options = MagicMock()
        chat_options.model = "test-model"
        context = ChatContext(
            client=cast(Any, client), messages=[Message(role="user", contents=["Hello"])], options=chat_options
        )

        with patch.object(middleware._processor, "process_messages", side_effect=ValueError("boom")):

            async def mock_next() -> None:
                raise AssertionError("next should not be called")

            with pytest.raises(ValueError, match="boom"):
                await middleware.process(context, mock_next)

    async def test_chat_middleware_raises_on_post_check_exception_when_ignore_exceptions_false(
        self, mock_credential: AsyncMock
    ) -> None:
        """Test that post-check exceptions are propagated by default."""
        settings = PurviewSettings(app_name="Test App", ignore_exceptions=False)
        middleware = PurviewChatPolicyMiddleware(mock_credential, settings)

        client = DummyChatClient()
        chat_options = MagicMock()
        chat_options.model = "test-model"
        context = ChatContext(
            client=cast(Any, client), messages=[Message(role="user", contents=["Hello"])], options=chat_options
        )

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (False, "user-123")
            raise ValueError("post")

        with patch.object(middleware._processor, "process_messages", side_effect=side_effect):

            async def mock_next() -> None:
                result = MagicMock()
                result.messages = [Message(role="assistant", contents=["OK"])]
                context.result = result

            with pytest.raises(ValueError, match="post"):
                await middleware.process(context, mock_next)

    async def test_chat_middleware_uses_conversation_id_from_options(
        self, middleware: PurviewChatPolicyMiddleware
    ) -> None:
        """Test that session_id is extracted from context.options['conversation_id']."""
        chat_client = DummyChatClient()
        messages = [Message(role="user", contents=["Hello"])]
        options = {"conversation_id": "conv-123", "model": "test-model"}
        context = ChatContext(client=cast(Any, chat_client), messages=messages, options=options)

        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")) as mock_proc:

            async def mock_next() -> None:
                result = MagicMock()
                result.messages = [Message(role="assistant", contents=["Hi"])]
                context.result = result

            await middleware.process(context, mock_next)

            # Verify session_id is passed to both pre-check and post-check
            assert mock_proc.call_count == 2
            mock_proc.assert_any_call(messages, Activity.UPLOAD_TEXT, session_id="conv-123")

    async def test_chat_middleware_passes_none_session_id_when_options_missing(
        self, middleware: PurviewChatPolicyMiddleware
    ) -> None:
        """Test that session_id is None when options don't contain conversation_id."""
        chat_client = DummyChatClient()
        messages = [Message(role="user", contents=["Hello"])]
        context = ChatContext(client=cast(Any, chat_client), messages=messages, options=None)

        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")) as mock_proc:

            async def mock_next() -> None:
                result = MagicMock()
                result.messages = [Message(role="assistant", contents=["Hi"])]
                context.result = result

            await middleware.process(context, mock_next)

            # Verify session_id=None is passed
            mock_proc.assert_any_call(messages, Activity.UPLOAD_TEXT, session_id=None)

    async def test_chat_middleware_session_id_used_in_post_check(self, middleware: PurviewChatPolicyMiddleware) -> None:
        """Test that session_id is passed to post-check process_messages call."""
        chat_client = DummyChatClient()
        messages = [Message(role="user", contents=["Hello"])]
        options = {"conversation_id": "conv-999"}
        context = ChatContext(client=cast(Any, chat_client), messages=messages, options=options)

        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")) as mock_proc:

            async def mock_next() -> None:
                result = MagicMock()
                result.messages = [Message(role="assistant", contents=["Response"])]
                context.result = result

            await middleware.process(context, mock_next)

            # Verify both calls include session_id
            assert mock_proc.call_count == 2
            # Check post-check call includes session_id
            post_check_call = mock_proc.call_args_list[1]
            assert post_check_call[1]["session_id"] == "conv-999"
