# Copyright (c) Microsoft. All rights reserved.
# pyright: reportPrivateUsage=false

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import ChatMessage, Context, Role
from agent_framework.exceptions import ServiceInitializationError

from agent_framework_zep import ZepProvider


def test_zep_provider_import() -> None:
    """Test that ZepProvider can be imported."""
    assert ZepProvider is not None


@pytest.fixture
def mock_zep_client() -> AsyncMock:
    """Create a mock AsyncZep client."""
    mock_client = AsyncMock()
    mock_client.thread = AsyncMock()
    mock_client.thread.add_messages = AsyncMock()
    mock_client.thread.get_user_context = AsyncMock()
    mock_client.thread.create = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()
    return mock_client


@pytest.fixture
def sample_messages() -> list[ChatMessage]:
    """Create sample chat messages for testing."""
    return [
        ChatMessage(role=Role.USER, text="Hello, how are you?"),
        ChatMessage(role=Role.ASSISTANT, text="I'm doing well, thank you!"),
        ChatMessage(role=Role.SYSTEM, text="You are a helpful assistant"),
    ]


class TestZepProviderInitialization:
    """Test initialization and configuration of ZepProvider."""

    def test_init_with_thread_id(self, mock_zep_client: AsyncMock) -> None:
        """Test initialization with thread ID provided."""
        provider = ZepProvider(
            user_id="user123",
            thread_id="thread123",
            zep_client=mock_zep_client,
        )
        assert provider.thread_id == "thread123"
        assert provider.zep_client == mock_zep_client

    def test_init_without_thread_id_succeeds(self, mock_zep_client: AsyncMock) -> None:
        """Test that initialization succeeds without thread_id (validation happens during invocation)."""
        provider = ZepProvider(user_id="user123", zep_client=mock_zep_client)
        assert provider.thread_id is None

    def test_init_with_scope_to_per_operation_thread_id(self, mock_zep_client: AsyncMock) -> None:
        """Test initialization with scope_to_per_operation_thread_id enabled."""
        provider = ZepProvider(
            user_id="user123",
            scope_to_per_operation_thread_id=True,
            zep_client=mock_zep_client,
        )
        assert provider.scope_to_per_operation_thread_id is True

    @patch("agent_framework_zep._provider.AsyncZep")
    def test_init_creates_default_client_when_none_provided(self, mock_zep_class: MagicMock) -> None:
        """Test that a default client is created when none is provided."""
        mock_client = AsyncMock()
        mock_zep_class.return_value = mock_client

        provider = ZepProvider(user_id="user123", thread_id="thread123", api_key="test_api_key")

        mock_zep_class.assert_called_once_with(api_key="test_api_key")
        assert provider.zep_client == mock_client
        assert provider._should_close_client is True

    @patch("agent_framework_zep._provider.AsyncZep")
    @patch.dict("os.environ", {"ZEP_API_KEY": "env_api_key"})
    def test_init_uses_env_api_key(self, mock_zep_class: MagicMock) -> None:
        """Test that initialization uses ZEP_API_KEY environment variable."""
        mock_client = AsyncMock()
        mock_zep_class.return_value = mock_client

        provider = ZepProvider(user_id="user123", thread_id="thread123")

        mock_zep_class.assert_called_once_with(api_key="env_api_key")
        assert provider.zep_client == mock_client

    def test_init_without_client_or_api_key_raises_error(self) -> None:
        """Test that initialization without client or API key raises error."""
        with pytest.raises(ServiceInitializationError) as exc_info:
            ZepProvider(user_id="user123", thread_id="thread123")

        assert "Either zep_client or api_key must be provided" in str(exc_info.value)

    def test_init_with_provided_client_should_not_close(self, mock_zep_client: AsyncMock) -> None:
        """Test that provided client should not be closed by provider."""
        provider = ZepProvider(user_id="user123", thread_id="thread123", zep_client=mock_zep_client)
        assert provider._should_close_client is False


class TestZepProviderAsyncContextManager:
    """Test async context manager behavior."""

    async def test_async_context_manager_entry(self, mock_zep_client: AsyncMock) -> None:
        """Test async context manager entry returns self."""
        provider = ZepProvider(user_id="user123", thread_id="thread123", zep_client=mock_zep_client)
        async with provider as ctx:
            assert ctx is provider

    async def test_async_context_manager_exit_closes_client_when_should_close(self) -> None:
        """Test that async context manager closes client when it should."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("agent_framework_zep._provider.AsyncZep", return_value=mock_client):
            provider = ZepProvider(user_id="user123", thread_id="thread123", api_key="test_key")
            assert provider._should_close_client is True

            async with provider:
                pass

            mock_client.__aexit__.assert_called_once()

    async def test_async_context_manager_exit_does_not_close_provided_client(self, mock_zep_client: AsyncMock) -> None:
        """Test that async context manager does not close provided client."""
        provider = ZepProvider(user_id="user123", thread_id="thread123", zep_client=mock_zep_client)
        assert provider._should_close_client is False

        async with provider:
            pass

        mock_zep_client.__aexit__.assert_not_called()


class TestZepProviderThreadMethods:
    """Test thread lifecycle methods."""

    async def test_thread_created_sets_per_operation_thread_id(self, mock_zep_client: AsyncMock) -> None:
        """Test that thread_created sets per-operation thread ID."""
        provider = ZepProvider(user_id="user123", zep_client=mock_zep_client)

        await provider.thread_created("thread123")

        assert provider._per_operation_thread_id == "thread123"

    async def test_thread_created_with_existing_thread_id(self, mock_zep_client: AsyncMock) -> None:
        """Test thread_created when thread ID already exists."""
        provider = ZepProvider(user_id="user123", zep_client=mock_zep_client)
        provider._per_operation_thread_id = "existing_thread"

        await provider.thread_created("thread123")

        # Should not overwrite existing thread ID
        assert provider._per_operation_thread_id == "existing_thread"

    async def test_thread_created_validation_with_scope_enabled(self, mock_zep_client: AsyncMock) -> None:
        """Test thread_created validation when scope_to_per_operation_thread_id is enabled."""
        provider = ZepProvider(
            user_id="user123",
            scope_to_per_operation_thread_id=True,
            zep_client=mock_zep_client,
        )
        provider._per_operation_thread_id = "existing_thread"

        with pytest.raises(ValueError) as exc_info:
            await provider.thread_created("different_thread")

        assert "can only be used with one thread at a time" in str(exc_info.value)

    async def test_thread_created_creates_zep_thread(self, mock_zep_client: AsyncMock) -> None:
        """Test that thread_created creates a Zep thread with user association."""
        provider = ZepProvider(user_id="user123", zep_client=mock_zep_client)

        await provider.thread_created("thread123")

        # Verify Zep thread.create was called with correct parameters
        mock_zep_client.thread.create.assert_called_once_with(
            thread_id="thread123",
            user_id="user123",
        )
        assert "thread123" in provider._created_threads

    async def test_thread_created_handles_existing_thread(self, mock_zep_client: AsyncMock) -> None:
        """Test that thread_created handles already-existing threads gracefully."""
        provider = ZepProvider(user_id="user123", zep_client=mock_zep_client)

        # Simulate thread already exists (Zep raises exception)
        mock_zep_client.thread.create.side_effect = Exception("Thread already exists")

        # Should not raise - gracefully handle existing thread
        await provider.thread_created("thread123")

        assert "thread123" in provider._created_threads

    async def test_thread_created_skips_duplicate_calls(self, mock_zep_client: AsyncMock) -> None:
        """Test that thread_created only creates thread once."""
        provider = ZepProvider(user_id="user123", zep_client=mock_zep_client)

        # First call creates thread
        await provider.thread_created("thread123")
        assert mock_zep_client.thread.create.call_count == 1

        # Second call with same ID should not create again
        await provider.thread_created("thread123")
        assert mock_zep_client.thread.create.call_count == 1  # Still just 1


class TestZepProviderInvoked:
    """Test invoked method (message persistence)."""

    async def test_invoked_fails_without_thread_id(self, mock_zep_client: AsyncMock) -> None:
        """Test that invoked fails when no thread ID is available."""
        provider = ZepProvider(user_id="user123", zep_client=mock_zep_client)
        message = ChatMessage(role=Role.USER, text="Hello!")

        with pytest.raises(ServiceInitializationError) as exc_info:
            await provider.invoked(message)

        assert "Thread ID is required" in str(exc_info.value)

    async def test_invoked_single_message(self, mock_zep_client: AsyncMock) -> None:
        """Test persisting a single message."""
        provider = ZepProvider(user_id="user123", thread_id="thread123", zep_client=mock_zep_client)
        message = ChatMessage(role=Role.USER, text="Hello!")

        await provider.invoked(message)

        mock_zep_client.thread.add_messages.assert_called_once()
        call_args = mock_zep_client.thread.add_messages.call_args
        assert call_args.kwargs["thread_id"] == "thread123"
        messages = call_args.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].content == "Hello!"

    async def test_invoked_multiple_messages(
        self, mock_zep_client: AsyncMock, sample_messages: list[ChatMessage]
    ) -> None:
        """Test persisting multiple messages."""
        provider = ZepProvider(user_id="user123", thread_id="thread123", zep_client=mock_zep_client)

        await provider.invoked(sample_messages)

        mock_zep_client.thread.add_messages.assert_called_once()
        call_args = mock_zep_client.thread.add_messages.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 3
        assert messages[0].role == "user"
        assert messages[0].content == "Hello, how are you?"
        assert messages[1].role == "assistant"
        assert messages[1].content == "I'm doing well, thank you!"
        assert messages[2].role == "system"
        assert messages[2].content == "You are a helpful assistant"

    async def test_invoked_with_request_and_response_messages(self, mock_zep_client: AsyncMock) -> None:
        """Test persisting both request and response messages."""
        provider = ZepProvider(user_id="user123", thread_id="thread123", zep_client=mock_zep_client)
        request_message = ChatMessage(role=Role.USER, text="Hello!")
        response_message = ChatMessage(role=Role.ASSISTANT, text="Hi there!")

        await provider.invoked(request_message, response_message)

        mock_zep_client.thread.add_messages.assert_called_once()
        call_args = mock_zep_client.thread.add_messages.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"

    async def test_invoked_with_scope_to_per_operation_thread_id(
        self, mock_zep_client: AsyncMock, sample_messages: list[ChatMessage]
    ) -> None:
        """Test persisting messages with scope_to_per_operation_thread_id enabled."""
        provider = ZepProvider(
            user_id="user123",
            thread_id="base_thread",
            scope_to_per_operation_thread_id=True,
            zep_client=mock_zep_client,
        )
        await provider.thread_created("operation_thread")

        await provider.invoked(sample_messages)

        call_args = mock_zep_client.thread.add_messages.call_args
        assert call_args.kwargs["thread_id"] == "operation_thread"

    async def test_invoked_without_scope_uses_base_thread_id(
        self, mock_zep_client: AsyncMock, sample_messages: list[ChatMessage]
    ) -> None:
        """Test persisting messages without scope uses base thread_id."""
        provider = ZepProvider(
            user_id="user123",
            thread_id="base_thread",
            scope_to_per_operation_thread_id=False,
            zep_client=mock_zep_client,
        )

        await provider.invoked(sample_messages)

        call_args = mock_zep_client.thread.add_messages.call_args
        assert call_args.kwargs["thread_id"] == "base_thread"

    async def test_invoked_filters_empty_messages(self, mock_zep_client: AsyncMock) -> None:
        """Test that empty or invalid messages are filtered out."""
        provider = ZepProvider(user_id="user123", thread_id="thread123", zep_client=mock_zep_client)
        messages = [
            ChatMessage(role=Role.USER, text=""),  # Empty text
            ChatMessage(role=Role.USER, text="   "),  # Whitespace only
            ChatMessage(role=Role.USER, text="Valid message"),
        ]

        await provider.invoked(messages)

        call_args = mock_zep_client.thread.add_messages.call_args
        zep_messages = call_args.kwargs["messages"]
        # Should only include the valid message
        assert len(zep_messages) == 1
        assert zep_messages[0].content == "Valid message"

    async def test_invoked_skips_when_no_valid_messages(self, mock_zep_client: AsyncMock) -> None:
        """Test that Zep client is not called when no valid messages exist."""
        provider = ZepProvider(user_id="user123", thread_id="thread123", zep_client=mock_zep_client)
        messages = [
            ChatMessage(role=Role.USER, text=""),
            ChatMessage(role=Role.USER, text="   "),
        ]

        await provider.invoked(messages)

        mock_zep_client.thread.add_messages.assert_not_called()

    async def test_invoked_with_message_names(self, mock_zep_client: AsyncMock) -> None:
        """Test persisting messages with names."""
        provider = ZepProvider(user_id="user123", thread_id="thread123", zep_client=mock_zep_client)
        message = ChatMessage(role=Role.USER, text="Hello!", author_name="John")

        await provider.invoked(message)

        call_args = mock_zep_client.thread.add_messages.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0].name == "John"


class TestZepProviderInvoking:
    """Test invoking method (context retrieval)."""

    async def test_invoking_fails_without_thread_id(self, mock_zep_client: AsyncMock) -> None:
        """Test that invoking fails when no thread ID is available."""
        provider = ZepProvider(user_id="user123", zep_client=mock_zep_client)
        message = ChatMessage(role=Role.USER, text="What's the weather?")

        with pytest.raises(ServiceInitializationError) as exc_info:
            await provider.invoking(message)

        assert "Thread ID is required" in str(exc_info.value)

    async def test_invoking_single_message(self, mock_zep_client: AsyncMock) -> None:
        """Test invoking with a single message."""
        provider = ZepProvider(user_id="user123", thread_id="thread123", zep_client=mock_zep_client)
        message = ChatMessage(role=Role.USER, text="What's the weather?")

        # Mock user context response
        mock_context_response = MagicMock()
        mock_context_response.context = "User likes outdoor activities\nUser lives in Seattle"
        mock_zep_client.thread.get_user_context.return_value = mock_context_response

        context = await provider.invoking(message)

        mock_zep_client.thread.get_user_context.assert_called_once()
        call_args = mock_zep_client.thread.get_user_context.call_args
        assert call_args.kwargs["thread_id"] == "thread123"
        assert call_args.kwargs["mode"] == "basic"

        assert isinstance(context, Context)
        assert context.messages is not None
        assert len(context.messages) == 1
        assert context.messages[0].role == Role.SYSTEM
        assert context.messages[0].text == "User likes outdoor activities\nUser lives in Seattle"

    async def test_invoking_with_empty_context(self, mock_zep_client: AsyncMock) -> None:
        """Test invoking when Zep returns empty context."""
        provider = ZepProvider(user_id="user123", thread_id="thread123", zep_client=mock_zep_client)
        message = ChatMessage(role=Role.USER, text="What's the weather?")

        # Mock empty context response
        mock_context_response = MagicMock()
        mock_context_response.context = ""
        mock_zep_client.thread.get_user_context.return_value = mock_context_response

        context = await provider.invoking(message)

        assert isinstance(context, Context)
        assert len(context.messages) == 0

    async def test_invoking_with_none_context(self, mock_zep_client: AsyncMock) -> None:
        """Test invoking when Zep returns None context."""
        provider = ZepProvider(user_id="user123", thread_id="thread123", zep_client=mock_zep_client)
        message = ChatMessage(role=Role.USER, text="What's the weather?")

        # Mock None context response
        mock_context_response = MagicMock()
        mock_context_response.context = None
        mock_zep_client.thread.get_user_context.return_value = mock_context_response

        context = await provider.invoking(message)

        assert isinstance(context, Context)
        assert len(context.messages) == 0

    async def test_invoking_handles_exception_gracefully(self, mock_zep_client: AsyncMock) -> None:
        """Test invoking handles exceptions gracefully (e.g., thread doesn't exist yet)."""
        provider = ZepProvider(user_id="user123", thread_id="thread123", zep_client=mock_zep_client)
        message = ChatMessage(role=Role.USER, text="What's the weather?")

        # Mock exception (e.g., thread not found)
        mock_zep_client.thread.get_user_context.side_effect = Exception("Thread not found")

        context = await provider.invoking(message)

        assert isinstance(context, Context)
        assert len(context.messages) == 0

    async def test_invoking_with_scope_to_per_operation_thread_id(self, mock_zep_client: AsyncMock) -> None:
        """Test invoking with scope_to_per_operation_thread_id enabled."""
        provider = ZepProvider(
            user_id="user123",
            thread_id="base_thread",
            scope_to_per_operation_thread_id=True,
            zep_client=mock_zep_client,
        )
        await provider.thread_created("operation_thread")

        message = ChatMessage(role=Role.USER, text="What's the weather?")

        mock_context_response = MagicMock()
        mock_context_response.context = "Context from operation thread"
        mock_zep_client.thread.get_user_context.return_value = mock_context_response

        context = await provider.invoking(message)

        call_args = mock_zep_client.thread.get_user_context.call_args
        assert call_args.kwargs["thread_id"] == "operation_thread"
        assert context.messages is not None
        assert context.messages[0].text == "Context from operation thread"

    async def test_invoking_with_multiple_messages(self, mock_zep_client: AsyncMock) -> None:
        """Test invoking with multiple messages."""
        provider = ZepProvider(user_id="user123", thread_id="thread123", zep_client=mock_zep_client)
        messages = [
            ChatMessage(role=Role.USER, text="First message"),
            ChatMessage(role=Role.USER, text="Second message"),
        ]

        mock_context_response = MagicMock()
        mock_context_response.context = "Relevant context"
        mock_zep_client.thread.get_user_context.return_value = mock_context_response

        context = await provider.invoking(messages)

        assert isinstance(context, Context)
        assert context.messages is not None
        assert len(context.messages) == 1
