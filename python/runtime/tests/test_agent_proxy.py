# Copyright (c) Microsoft. All rights reserved.

"""Tests for the AgentProxy and AgentProxyThread classes."""

import os

# Import framework types for testing
import sys
import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, Mock

import pytest
from agent_runtime.agent_proxy import AgentProxy, AgentProxyThread
from agent_runtime.agent_actor import (
    ActorId,
    ActorMessageType,
    ActorResponseMessage,
    RequestStatus,
)
from agent_runtime.runtime import (
    ActorResponseHandle,
    ActorClient,
)

sys.path.append(os.path.join(os.path.dirname(__file__), "../../packages/main"))

from agent_framework import AgentRunResponse, AgentRunResponseUpdate, AgentThread, ChatMessage, ChatRole  # type: ignore


class TestAgentProxyThread:
    """Tests for AgentProxyThread constructor and validation."""

    def test_constructor_default_creates_valid_id(self):
        """Verifies that the default constructor creates a valid thread ID."""
        thread = AgentProxyThread()

        assert thread.id is not None
        assert len(thread.id) > 0
        # Should be a valid hex string (UUID without hyphens)
        assert all(c in "0123456789abcdefABCDEF" for c in thread.id)

    def test_constructor_with_valid_id_sets_correctly(self):
        """Verifies that constructor with valid ID sets it correctly."""
        custom_id = "test_thread_123"
        thread = AgentProxyThread(custom_id)

        assert thread.id == custom_id

    @pytest.mark.parametrize("valid_id", [
        "abc123",
        "test-thread_456",
        "thread.with.dots",
        "thread~with~tildes",
        "123456789abcdef"
    ])
    def test_constructor_accepts_valid_ids(self, valid_id):
        """Verifies that constructor accepts various valid ID formats."""
        thread = AgentProxyThread(valid_id)
        assert thread.id == valid_id

    @pytest.mark.parametrize("invalid_id", [
        "invalid thread id!",
        "thread@with@symbols",
        "thread with spaces",
        "thread#hash",
        ""
    ])
    def test_constructor_rejects_invalid_ids(self, invalid_id):
        """Verifies that constructor rejects invalid ID formats."""
        with pytest.raises(ValueError, match="Thread ID .* is not valid"):
            AgentProxyThread(invalid_id)

    def test_create_id_generates_unique_ids(self):
        """Verifies that _create_id generates unique IDs."""
        ids = [AgentProxyThread._create_id() for _ in range(10)]

        # All IDs should be unique
        assert len(set(ids)) == 10
        # All should be valid hex strings
        for id_val in ids:
            assert all(c in "0123456789abcdefABCDEF" for c in id_val)

    def test_multiple_instances_have_unique_ids(self):
        """Verifies that multiple instances have unique IDs."""
        threads = [AgentProxyThread() for _ in range(5)]
        thread_ids = [t.id for t in threads]

        # All IDs should be unique
        assert len(set(thread_ids)) == 5


class TestAgentProxyConstructor:
    """Tests for AgentProxy constructor validation."""

    def test_constructor_with_valid_name_and_client(self):
        """Verifies that constructor works with valid name and client."""
        mock_client = Mock(spec=ActorClient)
        proxy = AgentProxy("test_agent", mock_client)

        assert proxy.name == "test_agent"
        assert proxy.id == "test_agent"
        assert proxy.display_name == "test_agent"
        assert proxy.description is None

    @pytest.mark.parametrize("valid_name", [
        "agent",
        " ",
        "特殊字符",
        "    a",
        "my-agent_123"
    ])
    def test_constructor_accepts_various_valid_names(self, valid_name):
        """Verifies that constructor accepts various valid agent names."""
        mock_client = Mock(spec=ActorClient)
        proxy = AgentProxy(valid_name, mock_client)

        assert proxy.name == valid_name

    def test_constructor_rejects_empty_name(self):
        """Verifies that constructor rejects empty name."""
        mock_client = Mock(spec=ActorClient)

        with pytest.raises(ValueError, match="Agent name cannot be empty"):
            AgentProxy("", mock_client)

    def test_constructor_rejects_none_client(self):
        """Verifies that constructor rejects None client."""
        with pytest.raises(ValueError, match="Client cannot be None"):
            AgentProxy("test_agent", None)


class TestAgentProxyThreadManagement:
    """Tests for AgentProxy thread management methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=ActorClient)
        self.proxy = AgentProxy("test_agent", self.mock_client)

    def test_get_new_thread_returns_agent_proxy_thread(self):
        """Verifies that GetNewThread returns an AgentProxyThread instance."""
        thread = self.proxy.get_new_thread()

        assert thread is not None
        assert isinstance(thread, AgentProxyThread)

    def test_get_new_thread_multiple_calls_return_distinct_instances(self):
        """Verifies that consecutive calls return distinct instances."""
        thread1 = self.proxy.get_new_thread()
        thread2 = self.proxy.get_new_thread()

        assert thread1 is not thread2
        assert thread1.id != thread2.id

    def test_get_thread_with_id_returns_correct_thread(self):
        """Verifies that GetThread returns thread with specified ID."""
        custom_id = "custom_thread_123"
        thread = self.proxy.get_thread(custom_id)

        assert isinstance(thread, AgentProxyThread)
        assert thread.id == custom_id

    def test_get_new_thread_creates_unique_threads(self):
        """Verifies that multiple calls create threads with unique IDs."""
        threads = [self.proxy.get_new_thread() for _ in range(10)]
        thread_ids = [t.id for t in threads]

        assert len(set(thread_ids)) == 10  # All unique


class TestAgentProxyMessageNormalization:
    """Tests for message normalization functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=ActorClient)
        self.proxy = AgentProxy("test_agent", self.mock_client)

    def test_normalize_messages_string_input(self):
        """Test normalization of string input."""
        result = self.proxy._normalize_messages("Hello world")

        assert len(result) == 1
        assert isinstance(result[0], ChatMessage)
        assert result[0].role == ChatRole.USER
        assert result[0].text == "Hello world"

    def test_normalize_messages_chat_message_input(self):
        """Test normalization of ChatMessage input."""
        original_msg = ChatMessage(role=ChatRole.ASSISTANT, text="Response")
        result = self.proxy._normalize_messages(original_msg)

        assert len(result) == 1
        assert result[0] is original_msg

    def test_normalize_messages_list_of_strings(self):
        """Test normalization of list of strings."""
        result = self.proxy._normalize_messages(["Hello", "World"])

        assert len(result) == 2
        assert all(isinstance(msg, ChatMessage) for msg in result)
        assert all(msg.role == ChatRole.USER for msg in result)
        assert result[0].text == "Hello"
        assert result[1].text == "World"

    def test_normalize_messages_mixed_list(self):
        """Test normalization of mixed list (strings and ChatMessages)."""
        chat_msg = ChatMessage(role=ChatRole.ASSISTANT, text="Response")
        result = self.proxy._normalize_messages(["Hello", chat_msg])

        assert len(result) == 2
        assert result[0].role == ChatRole.USER
        assert result[0].text == "Hello"
        assert result[1] is chat_msg

    def test_normalize_messages_invalid_type_raises_error(self):
        """Test that invalid message types raise ValueError."""
        with pytest.raises(ValueError, match="Unexpected messages type"):
            self.proxy._normalize_messages(123)

    def test_normalize_messages_invalid_list_item_raises_error(self):
        """Test that invalid items in list raise ValueError."""
        with pytest.raises(ValueError, match="Unexpected message type"):
            self.proxy._normalize_messages(["Valid", 123])


class MockActorResponseHandle(ActorResponseHandle):
    """Mock implementation of ActorResponseHandle for testing."""

    def __init__(self, response: ActorResponseMessage = None, updates: list = None):
        self._response = response
        self._updates = updates or []

    async def get_response(self) -> ActorResponseMessage:
        if self._response is None:
            raise ValueError("No response configured")
        return self._response

    async def watch_updates(self) -> AsyncIterator[ActorResponseMessage]:
        for update in self._updates:
            yield update


class TestAgentProxyRunAsync:
    """Tests for AgentProxy RunAsync functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=ActorClient)
        self.proxy = AgentProxy("test_agent", self.mock_client)
        self.thread = AgentProxyThread("thread123")
        self.messages = [ChatMessage(role=ChatRole.USER, text="Hello")]

    @pytest.mark.asyncio
    async def test_run_async_completed_status_returns_response(self):
        """Verifies that RunAsync returns deserialized response when status is Completed."""
        # Arrange
        response_data = {"messages": []}
        mock_response = ActorResponseMessage(
            message_id="msg1",
            message_type=ActorMessageType.RESPONSE,
            status=RequestStatus.COMPLETED,
            data=response_data
        )
        mock_handle = MockActorResponseHandle(response=mock_response)
        self.mock_client.send_request = AsyncMock(return_value=mock_handle)

        # Act
        result = await self.proxy.run(self.messages, thread=self.thread)

        # Assert
        assert isinstance(result, AgentRunResponse)
        assert result.messages == []

    @pytest.mark.asyncio
    async def test_run_async_failed_status_raises_exception(self):
        """Verifies that RunAsync raises RuntimeError when status is Failed."""
        # Arrange
        mock_response = ActorResponseMessage(
            message_id="msg1",
            message_type=ActorMessageType.RESPONSE,
            status=RequestStatus.FAILED,
            data="Error message"
        )
        mock_handle = MockActorResponseHandle(response=mock_response)
        self.mock_client.send_request = AsyncMock(return_value=mock_handle)

        # Act & Assert
        with pytest.raises(RuntimeError, match="The agent run request failed: Error message"):
            await self.proxy.run(self.messages, thread=self.thread)

    @pytest.mark.asyncio
    async def test_run_async_pending_status_raises_exception(self):
        """Verifies that RunAsync raises RuntimeError when status is Pending."""
        # Arrange
        mock_response = ActorResponseMessage(
            message_id="msg1",
            message_type=ActorMessageType.RESPONSE,
            status=RequestStatus.PENDING,
            data={}
        )
        mock_handle = MockActorResponseHandle(response=mock_response)
        self.mock_client.send_request = AsyncMock(return_value=mock_handle)

        # Act & Assert
        with pytest.raises(RuntimeError, match="The agent run request is still pending"):
            await self.proxy.run(self.messages, thread=self.thread)

    @pytest.mark.asyncio
    async def test_run_async_not_found_status_raises_exception(self):
        """Verifies that RunAsync raises RuntimeError for unsupported status."""
        # Arrange
        mock_response = ActorResponseMessage(
            message_id="msg1",
            message_type=ActorMessageType.RESPONSE,
            status=RequestStatus.NOT_FOUND,
            data={}
        )
        mock_handle = MockActorResponseHandle(response=mock_response)
        self.mock_client.send_request = AsyncMock(return_value=mock_handle)

        # Act & Assert
        with pytest.raises(RuntimeError, match="unsupported status"):
            await self.proxy.run(self.messages, thread=self.thread)

    @pytest.mark.asyncio
    async def test_run_async_none_messages_raises_exception(self):
        """Verifies that RunAsync raises ValueError for None messages."""
        with pytest.raises(ValueError, match="Messages cannot be None"):
            await self.proxy.run(None, thread=self.thread)

    @pytest.mark.asyncio
    async def test_run_async_invalid_thread_type_raises_exception(self):
        """Verifies that RunAsync raises TypeError for invalid thread type."""
        invalid_thread = Mock(spec=AgentThread)

        with pytest.raises(TypeError, match="must be an instance of AgentProxyThread"):
            await self.proxy.run(self.messages, thread=invalid_thread)

    @pytest.mark.asyncio
    async def test_run_async_none_thread_creates_new_thread(self):
        """Verifies that RunAsync creates new thread ID when thread is None."""
        # Arrange
        response_data = {"messages": []}
        mock_response = ActorResponseMessage(
            message_id="msg1",
            message_type=ActorMessageType.RESPONSE,
            status=RequestStatus.COMPLETED,
            data=response_data
        )
        mock_handle = MockActorResponseHandle(response=mock_response)
        self.mock_client.send_request = AsyncMock(return_value=mock_handle)

        # Act
        result = await self.proxy.run(self.messages, thread=None)

        # Assert
        assert isinstance(result, AgentRunResponse)
        # Verify that send_request was called with a valid ActorId
        self.mock_client.send_request.assert_called_once()
        call_args = self.mock_client.send_request.call_args
        actor_id = call_args[1]["actor_id"]
        assert isinstance(actor_id, ActorId)
        assert actor_id.type_name == "test_agent"
        assert actor_id.instance_id is not None

    @pytest.mark.asyncio
    async def test_run_async_uses_message_id_from_last_message(self):
        """Verifies that RunAsync uses message ID from the last message."""
        # Arrange
        expected_message_id = "custom-msg-id"
        messages_with_id = [
            ChatMessage(role=ChatRole.USER, text="First"),
            ChatMessage(role=ChatRole.USER, text="Last", message_id=expected_message_id)
        ]

        response_data = {"messages": []}
        mock_response = ActorResponseMessage(
            message_id="msg1",
            message_type=ActorMessageType.RESPONSE,
            status=RequestStatus.COMPLETED,
            data=response_data
        )
        mock_handle = MockActorResponseHandle(response=mock_response)
        self.mock_client.send_request = AsyncMock(return_value=mock_handle)

        # Act
        await self.proxy.run(messages_with_id, thread=self.thread)

        # Assert
        call_args = self.mock_client.send_request.call_args
        assert call_args[1]["message_id"] == expected_message_id


class TestAgentProxyRunStreaming:
    """Tests for AgentProxy RunStreaming functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=ActorClient)
        self.proxy = AgentProxy("test_agent", self.mock_client)
        self.thread = AgentProxyThread("thread123")
        self.messages = [ChatMessage(role=ChatRole.USER, text="Hello")]

    @pytest.mark.asyncio
    async def test_run_streaming_none_messages_raises_exception(self):
        """Verifies that run_streaming raises ValueError for None messages."""
        with pytest.raises(ValueError, match="Messages cannot be None"):
            async for _ in self.proxy.run_streaming(None, thread=self.thread):
                pass

    @pytest.mark.asyncio
    async def test_run_streaming_invalid_thread_type_raises_exception(self):
        """Verifies that run_streaming raises TypeError for invalid thread type."""
        invalid_thread = Mock(spec=AgentThread)

        with pytest.raises(TypeError, match="must be an instance of AgentProxyThread"):
            async for _ in self.proxy.run_streaming(self.messages, thread=invalid_thread):
                pass

    @pytest.mark.asyncio
    async def test_run_streaming_pending_status_yields_updates(self):
        """Verifies that run_streaming yields updates for pending status."""
        # Arrange
        update_data = {
            "progress": {
                "contents": [],
                "role": ChatRole.ASSISTANT
            }
        }
        pending_update = ActorResponseMessage(
            message_id="msg1",
            message_type=ActorMessageType.RESPONSE,
            status=RequestStatus.PENDING,
            data=update_data
        )

        mock_handle = MockActorResponseHandle(updates=[pending_update])
        self.mock_client.send_request = AsyncMock(return_value=mock_handle)

        # Act
        updates = []
        async for update in self.proxy.run_streaming(self.messages, thread=self.thread):
            updates.append(update)

        # Assert
        assert len(updates) == 1
        assert isinstance(updates[0], AgentRunResponseUpdate)

    @pytest.mark.asyncio
    async def test_run_streaming_completed_status_stops_enumeration(self):
        """Verifies that run_streaming stops on completed status."""
        # Arrange
        completed_update = ActorResponseMessage(
            message_id="msg1",
            message_type=ActorMessageType.RESPONSE,
            status=RequestStatus.COMPLETED,
            data={}
        )

        mock_handle = MockActorResponseHandle(updates=[completed_update])
        self.mock_client.send_request = AsyncMock(return_value=mock_handle)

        # Act
        updates = []
        async for update in self.proxy.run_streaming(self.messages, thread=self.thread):
            updates.append(update)

        # Assert
        assert len(updates) == 0  # Should not yield anything for completed

    @pytest.mark.asyncio
    async def test_run_streaming_failed_status_raises_exception(self):
        """Verifies that run_streaming raises RuntimeError for failed status."""
        # Arrange
        failed_update = ActorResponseMessage(
            message_id="msg1",
            message_type=ActorMessageType.RESPONSE,
            status=RequestStatus.FAILED,
            data="Error occurred"
        )

        mock_handle = MockActorResponseHandle(updates=[failed_update])
        self.mock_client.send_request = AsyncMock(return_value=mock_handle)

        # Act & Assert
        with pytest.raises(RuntimeError, match="The agent run request failed"):
            async for _update in self.proxy.run_streaming(self.messages, thread=self.thread):
                pass


class TestAgentProxyActorIntegration:
    """Tests for AgentProxy integration with actor system."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=ActorClient)
        self.proxy = AgentProxy("test_agent", self.mock_client)

    @pytest.mark.asyncio
    async def test_run_core_constructs_correct_actor_id(self):
        """Verifies that _run_core constructs correct ActorId."""
        # Arrange
        messages = [ChatMessage(role=ChatRole.USER, text="Hello")]
        thread_id = "test_thread_123"

        mock_handle = Mock(spec=ActorResponseHandle)
        self.mock_client.send_request = AsyncMock(return_value=mock_handle)

        # Act
        await self.proxy._run_core(messages, thread_id)

        # Assert
        call_args = self.mock_client.send_request.call_args
        actor_id = call_args[1]["actor_id"]

        assert isinstance(actor_id, ActorId)
        assert actor_id.type_name == "test_agent"
        assert actor_id.instance_id == thread_id

    @pytest.mark.asyncio
    async def test_run_core_sends_correct_method_and_params(self):
        """Verifies that _run_core sends correct method and params."""
        # Arrange
        messages = [ChatMessage(role=ChatRole.USER, text="Hello")]
        thread_id = "test_thread_123"

        mock_handle = Mock(spec=ActorResponseHandle)
        self.mock_client.send_request = AsyncMock(return_value=mock_handle)

        # Act
        await self.proxy._run_core(messages, thread_id)

        # Assert
        call_args = self.mock_client.send_request.call_args

        assert call_args[1]["method"] == "run"
        assert "params" in call_args[1]
        params = call_args[1]["params"]
        assert "messages" in params
        assert len(params["messages"]) == 1

    @pytest.mark.asyncio
    async def test_run_core_generates_message_id_when_none_provided(self):
        """Verifies that _run_core generates message ID when messages have none."""
        # Arrange
        messages = [ChatMessage(role=ChatRole.USER, text="Hello")]  # No message_id
        thread_id = "test_thread_123"

        mock_handle = Mock(spec=ActorResponseHandle)
        self.mock_client.send_request = AsyncMock(return_value=mock_handle)

        # Act
        await self.proxy._run_core(messages, thread_id)

        # Assert
        call_args = self.mock_client.send_request.call_args
        message_id = call_args[1]["message_id"]

        assert message_id is not None
        # Should be a valid UUID
        assert uuid.UUID(message_id)
