# Copyright (c) Microsoft. All rights reserved.

"""Tests for Purview middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import AgentRunContext, AgentRunResponse, ChatMessage, Role
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
        return PurviewSettings(app_name="Test App", tenant_id="test-tenant", default_user_id="test-user")

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
        # Create context with clean message
        context = AgentRunContext(agent=mock_agent, messages=[ChatMessage(role=Role.USER, text="Hello, how are you?")])

        # Mock processor to allow content
        with patch.object(middleware._processor, "process_messages", return_value=False):
            # Mock the next handler
            next_called = False

            async def mock_next(ctx: AgentRunContext) -> None:
                nonlocal next_called
                next_called = True
                ctx.result = AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="I'm good, thanks!")])

            await middleware.process(context, mock_next)

            assert next_called
            assert context.result is not None
            assert not context.terminate

    async def test_middleware_blocks_prompt_on_policy_violation(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test middleware blocks prompt that violates policy."""
        # Create context with message that should be blocked
        context = AgentRunContext(
            agent=mock_agent, messages=[ChatMessage(role=Role.USER, text="Sensitive information")]
        )

        # Mock processor to block content
        with patch.object(middleware._processor, "process_messages", return_value=True):
            # Mock the next handler (should not be called)
            next_called = False

            async def mock_next(ctx: AgentRunContext) -> None:
                nonlocal next_called
                next_called = True

            await middleware.process(context, mock_next)

            assert not next_called  # Next should not be called
            assert context.result is not None
            assert context.terminate
            assert len(context.result.messages) == 1
            assert context.result.messages[0].role == Role.SYSTEM
            assert "blocked by policy" in context.result.messages[0].text.lower()

    async def test_middleware_checks_response(self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock) -> None:
        """Test middleware checks agent response for policy violations."""
        # Create context with clean prompt
        context = AgentRunContext(agent=mock_agent, messages=[ChatMessage(role=Role.USER, text="Hello")])

        # Mock processor to allow prompt but block response
        call_count = 0

        async def mock_process_messages(messages, activity):
            nonlocal call_count
            call_count += 1
            # First call (prompt) - allow, second call (response) - block
            return call_count != 1

        with patch.object(middleware._processor, "process_messages", side_effect=mock_process_messages):

            async def mock_next(ctx: AgentRunContext) -> None:
                ctx.result = AgentRunResponse(
                    messages=[ChatMessage(role=Role.ASSISTANT, text="Here's some sensitive information")]
                )

            await middleware.process(context, mock_next)

            assert call_count == 2  # Should be called twice (prompt + response)
            assert context.result is not None
            assert len(context.result.messages) == 1
            assert context.result.messages[0].role == Role.SYSTEM
            assert "blocked by policy" in context.result.messages[0].text.lower()

    async def test_middleware_allows_clean_response(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test middleware allows response that passes policy check."""
        # Create context with clean prompt
        context = AgentRunContext(agent=mock_agent, messages=[ChatMessage(role=Role.USER, text="Hello")])

        # Mock processor to allow both prompt and response
        with patch.object(middleware._processor, "process_messages", return_value=False):

            async def mock_next(ctx: AgentRunContext) -> None:
                ctx.result = AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="Hi there!")])

            original_response_text = "Hi there!"
            await middleware.process(context, mock_next)

            assert context.result is not None
            assert len(context.result.messages) == 1
            assert context.result.messages[0].text == original_response_text

    async def test_middleware_handles_result_without_messages(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test middleware handles result that doesn't have messages attribute."""
        context = AgentRunContext(agent=mock_agent, messages=[ChatMessage(role=Role.USER, text="Hello")])

        # Mock processor to allow prompt
        with patch.object(middleware._processor, "process_messages", return_value=False):

            async def mock_next(ctx: AgentRunContext) -> None:
                # Set result to something without messages attribute
                ctx.result = "Some non-standard result"

            await middleware.process(context, mock_next)

            # Should not crash, and result should be preserved
            assert context.result == "Some non-standard result"

    async def test_middleware_with_empty_messages(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test middleware handles empty message list."""
        context = AgentRunContext(agent=mock_agent, messages=[])

        # Mock processor
        with patch.object(middleware._processor, "process_messages", return_value=False):
            next_called = False

            async def mock_next(ctx: AgentRunContext) -> None:
                nonlocal next_called
                next_called = True
                ctx.result = AgentRunResponse(messages=[])

            await middleware.process(context, mock_next)

            assert next_called

    async def test_middleware_with_multiple_messages(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test middleware processes multiple messages."""
        context = AgentRunContext(
            agent=mock_agent,
            messages=[
                ChatMessage(role=Role.USER, text="First message"),
                ChatMessage(role=Role.ASSISTANT, text="First response"),
                ChatMessage(role=Role.USER, text="Second message"),
            ],
        )

        # Mock processor to allow all messages
        with patch.object(middleware._processor, "process_messages", return_value=False) as mock_process:

            async def mock_next(ctx: AgentRunContext) -> None:
                ctx.result = AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="Second response")])

            await middleware.process(context, mock_next)

            # Should be called twice: once for prompt, once for response
            assert mock_process.call_count == 2

    async def test_middleware_integration_flow(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test complete middleware flow from prompt to response."""
        # Simulate a complete conversation flow
        context = AgentRunContext(
            agent=mock_agent,
            messages=[
                ChatMessage(role=Role.USER, text="What's the weather?"),
            ],
        )

        # Mock processor to allow everything
        with patch.object(middleware._processor, "process_messages", return_value=False):

            async def mock_next(ctx: AgentRunContext) -> None:
                # Simulate agent processing
                ctx.result = AgentRunResponse(
                    messages=[
                        ChatMessage(role=Role.ASSISTANT, text="The weather is sunny!"),
                    ]
                )

            await middleware.process(context, mock_next)

            # Verify the flow completed successfully
            assert context.result is not None
            assert isinstance(context.result, AgentRunResponse)
            assert len(context.result.messages) == 1
            assert context.result.messages[0].role == Role.ASSISTANT
            assert "sunny" in context.result.messages[0].text

    async def test_middleware_preserves_context_terminate_flag(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test middleware preserves terminate flag from next handler."""
        context = AgentRunContext(agent=mock_agent, messages=[ChatMessage(role=Role.USER, text="Hello")])

        with patch.object(middleware._processor, "process_messages", return_value=False):

            async def mock_next(ctx: AgentRunContext) -> None:
                ctx.result = AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="Goodbye")])
                ctx.terminate = True  # Agent wants to terminate

            await middleware.process(context, mock_next)

            # Terminate flag should be preserved
            assert context.terminate

    async def test_middleware_with_sync_credential(self, settings: PurviewSettings) -> None:
        """Test middleware can be initialized with sync credential."""
        sync_credential = MagicMock()
        sync_credential.get_token = MagicMock(return_value=AccessToken("sync-token", 9999999999))

        middleware = PurviewPolicyMiddleware(sync_credential, settings)

        assert middleware._client is not None
        assert middleware._processor is not None

    async def test_middleware_processor_receives_correct_activity(
        self, middleware: PurviewPolicyMiddleware, mock_agent: MagicMock
    ) -> None:
        """Test middleware passes correct activity type to processor."""
        from agent_framework_purview._models import Activity

        context = AgentRunContext(agent=mock_agent, messages=[ChatMessage(role=Role.USER, text="Test")])

        with patch.object(middleware._processor, "process_messages", return_value=False) as mock_process:

            async def mock_next(ctx: AgentRunContext) -> None:
                ctx.result = AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="Response")])

            await middleware.process(context, mock_next)

            # Check that process_messages was called with UPLOAD_TEXT activity
            assert mock_process.call_count == 2
            # Both calls should use UPLOAD_TEXT activity
            for call in mock_process.call_args_list:
                assert call[0][1] == Activity.UPLOAD_TEXT  # Second argument is activity
