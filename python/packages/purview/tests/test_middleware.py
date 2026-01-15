# Copyright (c) Microsoft. All rights reserved.

"""Tests for Purview middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import AgentResponse, AgentRunContext, ChatMessage, Role
from azure.core.credentials import AccessToken

from agent_framework_purview import PurviewPolicyMiddleware, PurviewSettings


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
        context = AgentRunContext(agent=mock_agent, messages=[ChatMessage(role=Role.USER, text="Hello, how are you?")])

        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")):
            next_called = False

            async def mock_next(ctx: AgentRunContext) -> None:
                nonlocal next_called
                next_called = True
                ctx.result = AgentResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="I'm good, thanks!")])

            await middleware.process(context, mock_next)

            assert next_called
            assert context.result is not None
            assert not context.terminate

    async def test_middleware_blocks_prompt_on_policy_violation(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test middleware blocks prompt that violates policy."""
        context = AgentRunContext(
            agent=mock_agent, messages=[ChatMessage(role=Role.USER, text="Sensitive information")]
        )

        with patch.object(middleware._processor, "process_messages", return_value=(True, "user-123")):
            next_called = False

            async def mock_next(ctx: AgentRunContext) -> None:
                nonlocal next_called
                next_called = True

            await middleware.process(context, mock_next)

            assert not next_called
            assert context.result is not None
            assert context.terminate
            assert len(context.result.messages) == 1
            assert context.result.messages[0].role == Role.SYSTEM
            assert "blocked by policy" in context.result.messages[0].text.lower()

    async def test_middleware_checks_response(self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock) -> None:
        """Test middleware checks agent response for policy violations."""
        context = AgentRunContext(agent=mock_agent, messages=[ChatMessage(role=Role.USER, text="Hello")])

        call_count = 0

        async def mock_process_messages(messages, activity, user_id=None):
            nonlocal call_count
            call_count += 1
            should_block = call_count != 1
            return (should_block, "user-123")

        with patch.object(middleware._processor, "process_messages", side_effect=mock_process_messages):

            async def mock_next(ctx: AgentRunContext) -> None:
                ctx.result = AgentResponse(
                    messages=[ChatMessage(role=Role.ASSISTANT, text="Here's some sensitive information")]
                )

            await middleware.process(context, mock_next)

            assert call_count == 2
            assert context.result is not None
            assert len(context.result.messages) == 1
            assert context.result.messages[0].role == Role.SYSTEM
            assert "blocked by policy" in context.result.messages[0].text.lower()

    async def test_middleware_handles_result_without_messages(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test middleware handles result that doesn't have messages attribute."""
        # Set ignore_exceptions to True so AttributeError is caught and logged
        middleware._settings.ignore_exceptions = True

        context = AgentRunContext(agent=mock_agent, messages=[ChatMessage(role=Role.USER, text="Hello")])

        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")):

            async def mock_next(ctx: AgentRunContext) -> None:
                ctx.result = "Some non-standard result"

            await middleware.process(context, mock_next)

            assert context.result == "Some non-standard result"

    async def test_middleware_processor_receives_correct_activity(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test middleware passes correct activity type to processor."""
        from agent_framework_purview._models import Activity

        context = AgentRunContext(agent=mock_agent, messages=[ChatMessage(role=Role.USER, text="Test")])

        with patch.object(middleware._processor, "process_messages", return_value=(False, "user-123")) as mock_process:

            async def mock_next(ctx: AgentRunContext) -> None:
                ctx.result = AgentResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="Response")])

            await middleware.process(context, mock_next)

            assert mock_process.call_count == 2
            for call in mock_process.call_args_list:
                assert call[0][1] == Activity.UPLOAD_TEXT

    async def test_middleware_handles_pre_check_exception(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test that exceptions in pre-check are logged but don't stop processing when ignore_exceptions=True."""
        # Set ignore_exceptions to True
        middleware._settings.ignore_exceptions = True

        context = AgentRunContext(agent=mock_agent, messages=[ChatMessage(role=Role.USER, text="Test")])

        with patch.object(
            middleware._processor, "process_messages", side_effect=Exception("Pre-check error")
        ) as mock_process:

            async def mock_next(ctx: AgentRunContext) -> None:
                ctx.result = AgentResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="Response")])

            await middleware.process(context, mock_next)

            # Should have been called twice (pre-check raises, then post-check also raises)
            assert mock_process.call_count == 2
            # Context should not be terminated
            assert not context.terminate
            # Result should be set by mock_next
            assert context.result is not None

    async def test_middleware_handles_post_check_exception(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test that exceptions in post-check are logged but don't affect result when ignore_exceptions=True."""
        # Set ignore_exceptions to True
        middleware._settings.ignore_exceptions = True

        context = AgentRunContext(agent=mock_agent, messages=[ChatMessage(role=Role.USER, text="Test")])

        call_count = 0

        async def mock_process_messages(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (False, "user-123")  # Pre-check succeeds
            raise Exception("Post-check error")  # Post-check fails

        with patch.object(middleware._processor, "process_messages", side_effect=mock_process_messages):

            async def mock_next(ctx: AgentRunContext) -> None:
                ctx.result = AgentResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="Response")])

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
        context = AgentRunContext(agent=mock_agent, messages=[ChatMessage(role=Role.USER, text="Test")])

        # Mock processor to raise an exception
        async def mock_process_messages(*args, **kwargs):
            raise ValueError("Test error")

        with patch.object(middleware._processor, "process_messages", side_effect=mock_process_messages):

            async def mock_next(ctx):
                ctx.result = AgentResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="Response")])

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
        context = AgentRunContext(agent=mock_agent, messages=[ChatMessage(role=Role.USER, text="Test")])

        # Mock processor to raise an exception
        async def mock_process_messages(*args, **kwargs):
            raise ValueError("Test error")

        with patch.object(middleware._processor, "process_messages", side_effect=mock_process_messages):

            async def mock_next(ctx):
                pass

            # Should raise the exception
            with pytest.raises(ValueError, match="Test error"):
                await middleware.process(context, mock_next)
