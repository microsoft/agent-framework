# Copyright (c) Microsoft. All rights reserved.
# pyright: reportPrivateUsage=false

from unittest.mock import AsyncMock, patch

import pytest
from agent_framework import ChatMessage, Context, Role
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.mem0 import Mem0Provider


def test_mem0_provider_import() -> None:
    """Test that Mem0Provider can be imported."""
    assert Mem0Provider is not None


@pytest.fixture
def mock_mem0_client() -> AsyncMock:
    """Create a mock Mem0 AsyncMemoryClient."""
    from mem0 import AsyncMemoryClient

    mock_client = AsyncMock(spec=AsyncMemoryClient)
    mock_client.add = AsyncMock()
    mock_client.search = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()
    mock_client.async_client = AsyncMock()
    mock_client.async_client.aclose = AsyncMock()
    return mock_client


@pytest.fixture
def sample_messages() -> list[ChatMessage]:
    """Create sample chat messages for testing."""
    return [
        ChatMessage(role=Role.USER, text="Hello, how are you?"),
        ChatMessage(role=Role.ASSISTANT, text="I'm doing well, thank you!"),
        ChatMessage(role=Role.SYSTEM, text="You are a helpful assistant"),
    ]


class TestMem0ProviderInitialization:
    """Test initialization and configuration of Mem0Provider."""

    def test_init_with_all_ids(self, mock_mem0_client: AsyncMock) -> None:
        """Test initialization with all IDs provided."""
        provider = Mem0Provider(
            user_id="user123",
            agent_id="agent123",
            application_id="app123",
            thread_id="thread123",
            mem0_client=mock_mem0_client,
        )
        assert provider.user_id == "user123"
        assert provider.agent_id == "agent123"
        assert provider.application_id == "app123"
        assert provider.thread_id == "thread123"

    def test_init_without_filters_succeeds(self, mock_mem0_client: AsyncMock) -> None:
        """Test that initialization succeeds even without filters (validation happens during invocation)."""
        provider = Mem0Provider(mem0_client=mock_mem0_client)
        assert provider.user_id is None
        assert provider.agent_id is None
        assert provider.application_id is None
        assert provider.thread_id is None

    def test_init_with_custom_context_prompt(self, mock_mem0_client: AsyncMock) -> None:
        """Test initialization with custom context prompt."""
        custom_prompt = "## Custom Memories\nConsider these memories:"
        provider = Mem0Provider(user_id="user123", context_prompt=custom_prompt, mem0_client=mock_mem0_client)
        assert provider.context_prompt == custom_prompt

    def test_init_with_scope_to_per_operation_thread_id(self, mock_mem0_client: AsyncMock) -> None:
        """Test initialization with scope_to_per_operation_thread_id enabled."""
        provider = Mem0Provider(
            user_id="user123",
            scope_to_per_operation_thread_id=True,
            mem0_client=mock_mem0_client,
        )
        assert provider.scope_to_per_operation_thread_id is True

    @patch("agent_framework_mem0._provider.AsyncMemoryClient")
    def test_init_creates_default_client_when_none_provided(self, mock_memory_client_class: AsyncMock) -> None:
        """Test that a default client is created when none is provided."""
        from mem0 import AsyncMemoryClient

        mock_client = AsyncMock(spec=AsyncMemoryClient)
        mock_memory_client_class.return_value = mock_client

        provider = Mem0Provider(user_id="user123", api_key="test_api_key")

        mock_memory_client_class.assert_called_once_with(api_key="test_api_key")
        assert provider.mem0_client == mock_client
        assert provider._should_close_client is True

    def test_init_with_provided_client_should_not_close(self, mock_mem0_client: AsyncMock) -> None:
        """Test that provided client should not be closed by provider."""
        provider = Mem0Provider(user_id="user123", mem0_client=mock_mem0_client)
        assert provider._should_close_client is False


class TestMem0ProviderAsyncContextManager:
    """Test async context manager behavior."""

    async def test_async_context_manager_entry(self, mock_mem0_client: AsyncMock) -> None:
        """Test async context manager entry returns self."""
        provider = Mem0Provider(user_id="user123", mem0_client=mock_mem0_client)
        async with provider as ctx:
            assert ctx is provider

    async def test_async_context_manager_exit_closes_client_when_should_close(self) -> None:
        """Test that async context manager closes client when it should."""
        from mem0 import AsyncMemoryClient

        mock_client = AsyncMock(spec=AsyncMemoryClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.async_client = AsyncMock()
        mock_client.async_client.aclose = AsyncMock()

        with patch("agent_framework_mem0._provider.AsyncMemoryClient", return_value=mock_client):
            provider = Mem0Provider(user_id="user123", api_key="test_key")
            assert provider._should_close_client is True

            async with provider:
                pass

            mock_client.__aexit__.assert_called_once()

    async def test_async_context_manager_exit_does_not_close_provided_client(self, mock_mem0_client: AsyncMock) -> None:
        """Test that async context manager does not close provided client."""
        provider = Mem0Provider(user_id="user123", mem0_client=mock_mem0_client)
        assert provider._should_close_client is False

        async with provider:
            pass

        mock_mem0_client.__aexit__.assert_not_called()


class TestMem0ProviderThreadMethods:
    """Test thread lifecycle methods."""

    async def test_thread_created_sets_per_operation_thread_id(self, mock_mem0_client: AsyncMock) -> None:
        """Test that thread_created sets per-operation thread ID."""
        provider = Mem0Provider(user_id="user123", mem0_client=mock_mem0_client)

        await provider.thread_created("thread123")

        assert provider._per_operation_thread_id == "thread123"

    async def test_thread_created_with_existing_thread_id(self, mock_mem0_client: AsyncMock) -> None:
        """Test thread_created when thread ID already exists."""
        provider = Mem0Provider(user_id="user123", mem0_client=mock_mem0_client)
        provider._per_operation_thread_id = "existing_thread"

        await provider.thread_created("thread123")

        # Should not overwrite existing thread ID
        assert provider._per_operation_thread_id == "existing_thread"

    async def test_thread_created_validation_with_scope_enabled(self, mock_mem0_client: AsyncMock) -> None:
        """Test thread_created validation when scope_to_per_operation_thread_id is enabled."""
        provider = Mem0Provider(
            user_id="user123",
            scope_to_per_operation_thread_id=True,
            mem0_client=mock_mem0_client,
        )
        provider._per_operation_thread_id = "existing_thread"

        with pytest.raises(ValueError) as exc_info:
            await provider.thread_created("different_thread")

        assert "can only be used with one thread at a time" in str(exc_info.value)

    async def test_messages_adding_sets_per_operation_thread_id(self, mock_mem0_client: AsyncMock) -> None:
        """Test that invoked sets per-operation thread ID."""
        provider = Mem0Provider(user_id="user123", mem0_client=mock_mem0_client)

        await provider.thread_created("thread123")

        assert provider._per_operation_thread_id == "thread123"


class TestMem0ProviderMessagesAdding:
    """Test invoked method."""

    async def test_messages_adding_fails_without_filters(self, mock_mem0_client: AsyncMock) -> None:
        """Test that invoked fails when no filters are provided."""
        provider = Mem0Provider(mem0_client=mock_mem0_client)
        message = ChatMessage(role=Role.USER, text="Hello!")

        with pytest.raises(ServiceInitializationError) as exc_info:
            await provider.invoked(message)

        assert "At least one of the filters" in str(exc_info.value)

    async def test_messages_adding_single_message(self, mock_mem0_client: AsyncMock) -> None:
        """Test adding a single message."""
        provider = Mem0Provider(user_id="user123", mem0_client=mock_mem0_client)
        message = ChatMessage(role=Role.USER, text="Hello!")

        await provider.invoked(message)

        mock_mem0_client.add.assert_called_once()
        call_args = mock_mem0_client.add.call_args
        assert call_args.kwargs["messages"] == [{"role": "user", "content": "Hello!"}]
        assert call_args.kwargs["user_id"] == "user123"

    async def test_messages_adding_multiple_messages(
        self, mock_mem0_client: AsyncMock, sample_messages: list[ChatMessage]
    ) -> None:
        """Test adding multiple messages."""
        provider = Mem0Provider(user_id="user123", mem0_client=mock_mem0_client)

        await provider.invoked(sample_messages)

        mock_mem0_client.add.assert_called_once()
        call_args = mock_mem0_client.add.call_args
        expected_messages = [
            {"role": "user", "content": "Hello, how are you?"},
            {"role": "assistant", "content": "I'm doing well, thank you!"},
            {"role": "system", "content": "You are a helpful assistant"},
        ]
        assert call_args.kwargs["messages"] == expected_messages

    async def test_messages_adding_with_agent_id(
        self, mock_mem0_client: AsyncMock, sample_messages: list[ChatMessage]
    ) -> None:
        """Test adding messages with agent_id."""
        provider = Mem0Provider(agent_id="agent123", mem0_client=mock_mem0_client)

        await provider.invoked(sample_messages)

        call_args = mock_mem0_client.add.call_args
        assert call_args.kwargs["agent_id"] == "agent123"
        assert call_args.kwargs["user_id"] is None

    async def test_messages_adding_with_application_id(
        self, mock_mem0_client: AsyncMock, sample_messages: list[ChatMessage]
    ) -> None:
        """Test adding messages with application_id in metadata."""
        provider = Mem0Provider(user_id="user123", application_id="app123", mem0_client=mock_mem0_client)

        await provider.invoked(sample_messages)

        call_args = mock_mem0_client.add.call_args
        assert call_args.kwargs["metadata"] == {"application_id": "app123"}

    async def test_messages_adding_with_scope_to_per_operation_thread_id(
        self, mock_mem0_client: AsyncMock, sample_messages: list[ChatMessage]
    ) -> None:
        """Test adding messages with scope_to_per_operation_thread_id enabled."""
        provider = Mem0Provider(
            user_id="user123",
            thread_id="base_thread",
            scope_to_per_operation_thread_id=True,
            mem0_client=mock_mem0_client,
        )
        provider._per_operation_thread_id = "operation_thread"

        await provider.thread_created(thread_id="operation_thread")
        await provider.invoked(sample_messages)

        call_args = mock_mem0_client.add.call_args
        assert call_args.kwargs["run_id"] == "operation_thread"

    async def test_messages_adding_without_scope_uses_base_thread_id(
        self, mock_mem0_client: AsyncMock, sample_messages: list[ChatMessage]
    ) -> None:
        """Test adding messages without scope uses base thread_id."""
        provider = Mem0Provider(
            user_id="user123",
            thread_id="base_thread",
            scope_to_per_operation_thread_id=False,
            mem0_client=mock_mem0_client,
        )

        await provider.invoked(sample_messages)

        call_args = mock_mem0_client.add.call_args
        assert call_args.kwargs["run_id"] == "base_thread"

    async def test_messages_adding_filters_empty_messages(self, mock_mem0_client: AsyncMock) -> None:
        """Test that empty or invalid messages are filtered out."""
        provider = Mem0Provider(user_id="user123", mem0_client=mock_mem0_client)
        messages = [
            ChatMessage(role=Role.USER, text=""),  # Empty text
            ChatMessage(role=Role.USER, text="   "),  # Whitespace only
            ChatMessage(role=Role.USER, text="Valid message"),
        ]

        await provider.invoked(messages)

        call_args = mock_mem0_client.add.call_args
        # Should only include the valid message
        assert call_args.kwargs["messages"] == [{"role": "user", "content": "Valid message"}]

    async def test_messages_adding_skips_when_no_valid_messages(self, mock_mem0_client: AsyncMock) -> None:
        """Test that mem0 client is not called when no valid messages exist."""
        provider = Mem0Provider(user_id="user123", mem0_client=mock_mem0_client)
        messages = [
            ChatMessage(role=Role.USER, text=""),
            ChatMessage(role=Role.USER, text="   "),
        ]

        await provider.invoked(messages)

        mock_mem0_client.add.assert_not_called()


class TestMem0ProviderModelInvoking:
    """Test invoking method."""

    async def test_model_invoking_fails_without_filters(self, mock_mem0_client: AsyncMock) -> None:
        """Test that invoking fails when no filters are provided."""
        provider = Mem0Provider(mem0_client=mock_mem0_client)
        message = ChatMessage(role=Role.USER, text="What's the weather?")

        with pytest.raises(ServiceInitializationError) as exc_info:
            await provider.invoking(message)

        assert "At least one of the filters" in str(exc_info.value)

    async def test_model_invoking_single_message(self, mock_mem0_client: AsyncMock) -> None:
        """Test invoking with a single message."""
        provider = Mem0Provider(user_id="user123", mem0_client=mock_mem0_client)
        message = ChatMessage(role=Role.USER, text="What's the weather?")

        # Mock search results
        mock_mem0_client.search.return_value = [
            {"memory": "User likes outdoor activities"},
            {"memory": "User lives in Seattle"},
        ]

        context = await provider.invoking(message)

        mock_mem0_client.search.assert_called_once()
        call_args = mock_mem0_client.search.call_args
        assert call_args.kwargs["query"] == "What's the weather?"
        assert call_args.kwargs["user_id"] == "user123"

        assert isinstance(context, Context)
        expected_instructions = (
            "## Memories\nConsider the following memories when answering user questions:\n"
            "User likes outdoor activities\nUser lives in Seattle"
        )

        assert context.messages
        assert context.messages[0].text == expected_instructions

    async def test_model_invoking_multiple_messages(
        self, mock_mem0_client: AsyncMock, sample_messages: list[ChatMessage]
    ) -> None:
        """Test invoking with multiple messages."""
        provider = Mem0Provider(user_id="user123", mem0_client=mock_mem0_client)

        mock_mem0_client.search.return_value = [{"memory": "Previous conversation context"}]

        await provider.invoking(sample_messages)

        call_args = mock_mem0_client.search.call_args
        expected_query = "Hello, how are you?\nI'm doing well, thank you!\nYou are a helpful assistant"
        assert call_args.kwargs["query"] == expected_query

    async def test_model_invoking_with_agent_id(self, mock_mem0_client: AsyncMock) -> None:
        """Test invoking with agent_id."""
        provider = Mem0Provider(agent_id="agent123", mem0_client=mock_mem0_client)
        message = ChatMessage(role=Role.USER, text="Hello")

        mock_mem0_client.search.return_value = []

        await provider.invoking(message)

        call_args = mock_mem0_client.search.call_args
        assert call_args.kwargs["agent_id"] == "agent123"
        assert call_args.kwargs["user_id"] is None

    async def test_model_invoking_with_scope_to_per_operation_thread_id(self, mock_mem0_client: AsyncMock) -> None:
        """Test invoking with scope_to_per_operation_thread_id enabled."""
        provider = Mem0Provider(
            user_id="user123",
            thread_id="base_thread",
            scope_to_per_operation_thread_id=True,
            mem0_client=mock_mem0_client,
        )
        provider._per_operation_thread_id = "operation_thread"
        message = ChatMessage(role=Role.USER, text="Hello")

        mock_mem0_client.search.return_value = []

        await provider.invoking(message)

        call_args = mock_mem0_client.search.call_args
        assert call_args.kwargs["run_id"] == "operation_thread"

    async def test_model_invoking_no_memories_returns_none_instructions(self, mock_mem0_client: AsyncMock) -> None:
        """Test that no memories returns context with None instructions."""
        provider = Mem0Provider(user_id="user123", mem0_client=mock_mem0_client)
        message = ChatMessage(role=Role.USER, text="Hello")

        mock_mem0_client.search.return_value = []

        context = await provider.invoking(message)

        assert isinstance(context, Context)
        assert not context.messages

    async def test_model_invoking_function_approval_response_returns_none_instructions(
        self, mock_mem0_client: AsyncMock
    ) -> None:
        """Test invoking with function approval response content messages returns context with None instructions."""
        from agent_framework import FunctionApprovalResponseContent, FunctionCallContent

        provider = Mem0Provider(user_id="user123", mem0_client=mock_mem0_client)
        function_call = FunctionCallContent(call_id="1", name="test_func", arguments='{"arg1": "value1"}')
        message = ChatMessage(
            role=Role.USER,
            contents=[
                FunctionApprovalResponseContent(
                    id="approval_1",
                    function_call=function_call,
                    approved=True,
                )
            ],
        )

        mock_mem0_client.search.return_value = []

        context = await provider.invoking(message)

        assert isinstance(context, Context)
        assert not context.messages

    async def test_model_invoking_filters_empty_message_text(self, mock_mem0_client: AsyncMock) -> None:
        """Test that empty message text is filtered out from query."""
        provider = Mem0Provider(user_id="user123", mem0_client=mock_mem0_client)
        messages = [
            ChatMessage(role=Role.USER, text=""),
            ChatMessage(role=Role.USER, text="Valid message"),
            ChatMessage(role=Role.USER, text="   "),
        ]

        mock_mem0_client.search.return_value = []

        await provider.invoking(messages)

        call_args = mock_mem0_client.search.call_args
        assert call_args.kwargs["query"] == "Valid message"

    async def test_model_invoking_custom_context_prompt(self, mock_mem0_client: AsyncMock) -> None:
        """Test invoking with custom context prompt."""
        custom_prompt = "## Custom Context\nRemember these details:"
        provider = Mem0Provider(
            user_id="user123",
            context_prompt=custom_prompt,
            mem0_client=mock_mem0_client,
        )
        message = ChatMessage(role=Role.USER, text="Hello")

        mock_mem0_client.search.return_value = [{"memory": "Test memory"}]

        context = await provider.invoking(message)

        expected_instructions = "## Custom Context\nRemember these details:\nTest memory"
        assert context.messages
        assert context.messages[0].text == expected_instructions


class TestMem0ProviderValidation:
    """Test validation methods."""

    def test_validate_per_operation_thread_id_success(self, mock_mem0_client: AsyncMock) -> None:
        """Test successful validation of per-operation thread ID."""
        provider = Mem0Provider(
            user_id="user123",
            scope_to_per_operation_thread_id=True,
            mem0_client=mock_mem0_client,
        )
        provider._per_operation_thread_id = "thread123"

        # Should not raise exception for same thread ID
        provider._validate_per_operation_thread_id("thread123")

        # Should not raise exception for None
        provider._validate_per_operation_thread_id(None)

    def test_validate_per_operation_thread_id_failure(self, mock_mem0_client: AsyncMock) -> None:
        """Test validation failure for conflicting thread IDs."""
        provider = Mem0Provider(
            user_id="user123",
            scope_to_per_operation_thread_id=True,
            mem0_client=mock_mem0_client,
        )
        provider._per_operation_thread_id = "thread123"

        with pytest.raises(ValueError) as exc_info:
            provider._validate_per_operation_thread_id("different_thread")

        assert "can only be used with one thread at a time" in str(exc_info.value)

    def test_validate_per_operation_thread_id_disabled_scope(self, mock_mem0_client: AsyncMock) -> None:
        """Test that validation is skipped when scope is disabled."""
        provider = Mem0Provider(
            user_id="user123",
            scope_to_per_operation_thread_id=False,
            mem0_client=mock_mem0_client,
        )
        provider._per_operation_thread_id = "thread123"

        # Should not raise exception even with different thread ID
        provider._validate_per_operation_thread_id("different_thread")
