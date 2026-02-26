# Copyright (c) Microsoft. All rights reserved.

"""Tests for Purview middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import AgentContext, AgentResponse, AgentSession, Message, MiddlewareTermination
from azure.core.credentials import AccessToken

from agent_framework_purview import PurviewPolicyMiddleware, PurviewSettings
from agent_framework_purview._models import Activity


class TestPurviewPolicyMiddleware:
    """Test PurviewPolicyMiddleware functionality."""

    @pytest.fixture
    def mock_credential(self) -> AsyncMock:
        """Create a mock async credential."""
        credential = AsyncMock()
        credential.get_token = AsyncMock(return_value=AccessToken("fake-token", 9999999999))
        return credential

    @pytest.fixture
    def settings(self) -> PurviewSettings:
        """Create test settings."""
        return PurviewSettings(app_name="Test App", tenant_id="test-tenant")

    @pytest.fixture
    def middleware(self, mock_credential: AsyncMock, settings: PurviewSettings) -> PurviewPolicyMiddleware:
        """Create PurviewPolicyMiddleware instance."""
        return PurviewPolicyMiddleware(mock_credential, settings)

    @pytest.fixture
    def mock_agent(self) -> MagicMock:
        """Create a mock agent."""
        agent = MagicMock()
        agent.name = "test-agent"
        return agent

    def test_middleware_initialization(self, mock_credential: AsyncMock, settings: PurviewSettings) -> None:
        """Test PurviewPolicyMiddleware initialization."""
        middleware = PurviewPolicyMiddleware(mock_credential, settings)

        assert middleware._client is not None
        assert middleware._processor is not None

    async def test_middleware_allows_clean_prompt(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test middleware allows prompt that passes policy check."""
        context = AgentContext(agent=mock_agent, messages=[Message(role="user", text="Hello, how are you?")])

        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")):
            next_called = False

            async def mock_next() -> None:
                nonlocal next_called
                next_called = True
                context.result = AgentResponse(messages=[Message(role="assistant", text="I'm good, thanks!")])

            await middleware.process(context, mock_next)

            assert next_called
            assert context.result is not None

    async def test_middleware_blocks_prompt_on_policy_violation(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test middleware blocks prompt that violates policy."""
        context = AgentContext(agent=mock_agent, messages=[Message(role="user", text="Sensitive information")])

        with patch.object(middleware._processor, "process_messages", return_value=(True, "user-123")):
            next_called = False

            async def mock_next() -> None:
                nonlocal next_called
                next_called = True

            with pytest.raises(MiddlewareTermination):
                await middleware.process(context, mock_next)

            assert not next_called
            assert context.result is not None
            assert len(context.result.messages) == 1
            assert context.result.messages[0].role == "system"
            assert "blocked by policy" in context.result.messages[0].text.lower()

    async def test_middleware_checks_response(self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock) -> None:
        """Test middleware checks agent response for policy violations."""
        context = AgentContext(agent=mock_agent, messages=[Message(role="user", text="Hello")])

        call_count = 0

        async def mock_process_messages(messages, activity, session_id=None, user_id=None):
            nonlocal call_count
            call_count += 1
            should_block = call_count != 1
            return (should_block, "user-123")

        with patch.object(middleware._processor, "process_messages", side_effect=mock_process_messages):

            async def mock_next() -> None:
                context.result = AgentResponse(
                    messages=[Message(role="assistant", text="Here's some sensitive information")]
                )

            await middleware.process(context, mock_next)

            assert call_count == 2
            assert context.result is not None
            assert len(context.result.messages) == 1
            assert context.result.messages[0].role == "system"
            assert "blocked by policy" in context.result.messages[0].text.lower()

    async def test_middleware_handles_result_without_messages(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test middleware handles result that doesn't have messages attribute."""
        # Set ignore_exceptions to True so AttributeError is caught and logged
        middleware._settings["ignore_exceptions"] = True

        context = AgentContext(agent=mock_agent, messages=[Message(role="user", text="Hello")])

        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")):

            async def mock_next() -> None:
                context.result = "Some non-standard result"

            await middleware.process(context, mock_next)

            assert context.result == "Some non-standard result"

    async def test_middleware_processor_receives_correct_activity(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test middleware passes correct activity type to processor."""
        from agent_framework_purview._models import Activity

        context = AgentContext(agent=mock_agent, messages=[Message(role="user", text="Test")])

        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")) as mock_process:

            async def mock_next() -> None:
                context.result = AgentResponse(messages=[Message(role="assistant", text="Response")])

            await middleware.process(context, mock_next)

            assert mock_process.call_count == 2
            # First call (pre-check) should be UPLOAD_TEXT for user prompt
            assert mock_process.call_args_list[0][0][1] == Activity.UPLOAD_TEXT
            # Second call (post-check) should be DOWNLOAD_TEXT for agent response
            assert mock_process.call_args_list[1][0][1] == Activity.DOWNLOAD_TEXT

    async def test_middleware_streaming_skips_post_check(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test that streaming results skip post-check evaluation."""
        context = AgentContext(agent=mock_agent, messages=[Message(role="user", text="Hello")])
        context.stream = True

        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")) as mock_proc:

            async def mock_next() -> None:
                context.result = AgentResponse(messages=[Message(role="assistant", text="streaming")])

            await middleware.process(context, mock_next)

        assert mock_proc.call_count == 1

    async def test_middleware_payment_required_in_pre_check_raises_by_default(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test that 402 in pre-check is raised when ignore_payment_required=False."""
        from agent_framework_purview._exceptions import PurviewPaymentRequiredError

        context = AgentContext(agent=mock_agent, messages=[Message(role="user", text="Hello")])

        with patch.object(
            middleware._processor,
            "process_messages",
            side_effect=PurviewPaymentRequiredError("Payment required"),
        ):

            async def mock_next() -> None:
                raise AssertionError("next should not be called")

            with pytest.raises(PurviewPaymentRequiredError):
                await middleware.process(context, mock_next)

    async def test_middleware_payment_required_in_post_check_raises_by_default(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test that 402 in post-check is raised when ignore_payment_required=False."""
        from agent_framework_purview._exceptions import PurviewPaymentRequiredError

        context = AgentContext(agent=mock_agent, messages=[Message(role="user", text="Hello")])

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (False, "user-123")
            raise PurviewPaymentRequiredError("Payment required")

        with patch.object(middleware._processor, "process_messages", side_effect=side_effect):

            async def mock_next() -> None:
                context.result = AgentResponse(messages=[Message(role="assistant", text="OK")])

            with pytest.raises(PurviewPaymentRequiredError):
                await middleware.process(context, mock_next)

    async def test_middleware_post_check_exception_raises_when_ignore_exceptions_false(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test that post-check exceptions are propagated when ignore_exceptions=False."""
        middleware._settings["ignore_exceptions"] = False

        context = AgentContext(agent=mock_agent, messages=[Message(role="user", text="Hello")])

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (False, "user-123")
            raise ValueError("Post-check blew up")

        with patch.object(middleware._processor, "process_messages", side_effect=side_effect):

            async def mock_next() -> None:
                context.result = AgentResponse(messages=[Message(role="assistant", text="OK")])

            with pytest.raises(ValueError, match="Post-check blew up"):
                await middleware.process(context, mock_next)

    async def test_middleware_handles_pre_check_exception(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test that exceptions in pre-check are logged but don't stop processing when ignore_exceptions=True."""
        # Set ignore_exceptions to True
        middleware._settings["ignore_exceptions"] = True

        context = AgentContext(agent=mock_agent, messages=[Message(role="user", text="Test")])

        with patch.object(
            middleware._processor, "process_messages", side_effect=Exception("Pre-check error")
        ) as mock_process:

            async def mock_next() -> None:
                context.result = AgentResponse(messages=[Message(role="assistant", text="Response")])

            await middleware.process(context, mock_next)

            # Should have been called twice (pre-check raises, then post-check also raises)
            assert mock_process.call_count == 2
            # Result should be set by mock_next
            assert context.result is not None

    async def test_middleware_handles_post_check_exception(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test that exceptions in post-check are logged but don't affect result when ignore_exceptions=True."""
        # Set ignore_exceptions to True
        middleware._settings["ignore_exceptions"] = True

        context = AgentContext(agent=mock_agent, messages=[Message(role="user", text="Test")])

        call_count = 0

        async def mock_process_messages(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (False, "user-123")  # Pre-check succeeds
            raise Exception("Post-check error")  # Post-check fails

        with patch.object(middleware._processor, "process_messages", side_effect=mock_process_messages):

            async def mock_next() -> None:
                context.result = AgentResponse(messages=[Message(role="assistant", text="Response")])

            await middleware.process(context, mock_next)

            # Should have been called twice (pre and post)
            assert call_count == 2
            # Result should still be set
            assert context.result is not None
            assert hasattr(context.result, "messages")

    async def test_middleware_with_ignore_exceptions_true(self, mock_credential: AsyncMock) -> None:
        """Test that middleware logs but doesn't throw when ignore_exceptions is True."""
        settings = PurviewSettings(app_name="Test App", ignore_exceptions=True)
        middleware = PurviewPolicyMiddleware(mock_credential, settings)

        mock_agent = MagicMock()
        mock_agent.name = "test-agent"
        context = AgentContext(agent=mock_agent, messages=[Message(role="user", text="Test")])

        # Mock processor to raise an exception
        async def mock_process_messages(*args, **kwargs):
            raise ValueError("Test error")

        with patch.object(middleware._processor, "process_messages", side_effect=mock_process_messages):

            async def mock_next():
                context.result = AgentResponse(messages=[Message(role="assistant", text="Response")])

            # Should not raise, just log
            await middleware.process(context, mock_next)

            # Result should be set because next was called despite the error
            assert context.result is not None

    async def test_middleware_with_ignore_exceptions_false(self, mock_credential: AsyncMock) -> None:
        """Test that middleware throws exceptions when ignore_exceptions is False."""
        settings = PurviewSettings(app_name="Test App", ignore_exceptions=False)
        middleware = PurviewPolicyMiddleware(mock_credential, settings)

        mock_agent = MagicMock()
        mock_agent.name = "test-agent"
        context = AgentContext(agent=mock_agent, messages=[Message(role="user", text="Test")])

        # Mock processor to raise an exception
        async def mock_process_messages(*args, **kwargs):
            raise ValueError("Test error")

        with patch.object(middleware._processor, "process_messages", side_effect=mock_process_messages):

            async def mock_next():
                pass

            # Should raise the exception
            with pytest.raises(ValueError, match="Test error"):
                await middleware.process(context, mock_next)

    async def test_middleware_uses_session_service_session_id_as_session_id(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test that session_id is extracted from session.service_session_id."""
        session = AgentSession(service_session_id="thread-123")
        context = AgentContext(agent=mock_agent, messages=[Message(role="user", text="Hello")], session=session)

        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")) as mock_proc:

            async def mock_next() -> None:
                context.result = AgentResponse(messages=[Message(role="assistant", text="Hi")])

            await middleware.process(context, mock_next)

            # Verify session_id is passed to both pre-check and post-check
            assert mock_proc.call_count == 2
            mock_proc.assert_any_call(context.messages, Activity.UPLOAD_TEXT, session_id="thread-123")

    async def test_middleware_uses_message_conversation_id_as_session_id(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test that session_id is extracted from message.additional_properties['conversation_id']."""
        messages = [Message(role="user", text="Hello", additional_properties={"conversation_id": "conv-456"})]
        context = AgentContext(agent=mock_agent, messages=messages)

        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")) as mock_proc:

            async def mock_next() -> None:
                context.result = AgentResponse(messages=[Message(role="assistant", text="Hi")])

            await middleware.process(context, mock_next)

            # Verify session_id is passed to both pre-check and post-check
            assert mock_proc.call_count == 2
            mock_proc.assert_any_call(messages, Activity.UPLOAD_TEXT, session_id="conv-456")

    async def test_middleware_session_id_takes_precedence_over_message_conversation_id(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test that session.service_session_id takes precedence over message conversation_id."""
        session = AgentSession(service_session_id="thread-789")
        messages = [Message(role="user", text="Hello", additional_properties={"conversation_id": "conv-456"})]
        context = AgentContext(agent=mock_agent, messages=messages, session=session)

        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")) as mock_proc:

            async def mock_next() -> None:
                context.result = AgentResponse(messages=[Message(role="assistant", text="Hi")])

            await middleware.process(context, mock_next)

            # Verify session ID is used, not message conversation_id
            mock_proc.assert_any_call(messages, Activity.UPLOAD_TEXT, session_id="thread-789")

    async def test_middleware_passes_none_session_id_when_not_available(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test that session_id is None when no session or conversation_id is available."""
        context = AgentContext(agent=mock_agent, messages=[Message(role="user", text="Hello")])

        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")) as mock_proc:

            async def mock_next() -> None:
                context.result = AgentResponse(messages=[Message(role="assistant", text="Hi")])

            await middleware.process(context, mock_next)

            # Verify session_id=None is passed
            mock_proc.assert_any_call(context.messages, Activity.UPLOAD_TEXT, session_id=None)

    async def test_middleware_session_id_used_in_post_check(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test that session_id is passed to post-check process_messages call."""
        session = AgentSession(service_session_id="thread-999")
        context = AgentContext(agent=mock_agent, messages=[Message(role="user", text="Hello")], session=session)

        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")) as mock_proc:

            async def mock_next() -> None:
                context.result = AgentResponse(messages=[Message(role="assistant", text="Response")])

            await middleware.process(context, mock_next)

            # Verify both calls include session_id
            assert mock_proc.call_count == 2
            # Check post-check call includes session_id
            post_check_call = mock_proc.call_args_list[1]
            assert post_check_call[1]["session_id"] == "thread-999"
