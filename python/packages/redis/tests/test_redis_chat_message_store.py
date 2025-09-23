# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import ChatMessage, Role, TextContent

from agent_framework_redis import RedisChatMessageStore


class TestRedisChatMessageStore:
    """Unit tests for RedisChatMessageStore using mocked Redis client.

    These tests use mocked Redis operations to verify the logic and behavior
    of the RedisChatMessageStore without requiring a real Redis server.
    """

    @pytest.fixture
    def sample_messages(self):
        """Sample chat messages for testing."""
        return [
            ChatMessage(role=Role.USER, text="Hello", message_id="msg1"),
            ChatMessage(role=Role.ASSISTANT, text="Hi there!", message_id="msg2"),
            ChatMessage(role=Role.USER, text="How are you?", message_id="msg3"),
        ]

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client with all required methods."""
        client = MagicMock()
        # Core list operations
        client.lrange = AsyncMock(return_value=[])
        client.llen = AsyncMock(return_value=0)
        client.lindex = AsyncMock(return_value=None)
        client.lset = AsyncMock(return_value=True)
        client.lrem = AsyncMock(return_value=0)
        client.lpop = AsyncMock(return_value=None)
        client.rpop = AsyncMock(return_value=None)
        client.ltrim = AsyncMock(return_value=True)
        client.delete = AsyncMock(return_value=1)

        # Pipeline operations
        mock_pipeline = AsyncMock()
        mock_pipeline.rpush = AsyncMock()
        mock_pipeline.execute = AsyncMock()
        client.pipeline.return_value.__aenter__.return_value = mock_pipeline

        return client

    @pytest.fixture
    def redis_store(self, mock_redis_client):
        """Redis chat message store with mocked client."""
        with patch("agent_framework_redis._chat_message_store.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            store = RedisChatMessageStore(redis_url="redis://localhost:6379", thread_id="test_thread_123")
            store._redis_client = mock_redis_client
            return store

    def test_init_with_thread_id(self):
        """Test initialization with explicit thread ID."""
        thread_id = "user123_session456"
        with patch("agent_framework_redis._chat_message_store.redis.from_url"):
            store = RedisChatMessageStore(redis_url="redis://localhost:6379", thread_id=thread_id)

        assert store.thread_id == thread_id
        assert store.redis_url == "redis://localhost:6379"
        assert store.key_prefix == "chat_messages"
        assert store.redis_key == f"chat_messages:{thread_id}"

    def test_init_auto_generate_thread_id(self):
        """Test initialization with auto-generated thread ID."""
        with patch("agent_framework_redis._chat_message_store.redis.from_url"):
            store = RedisChatMessageStore(redis_url="redis://localhost:6379")

        assert store.thread_id is not None
        assert store.thread_id.startswith("thread_")
        assert len(store.thread_id) > 10  # Should be a UUID

    def test_init_with_custom_prefix(self):
        """Test initialization with custom key prefix."""
        with patch("agent_framework_redis._chat_message_store.redis.from_url"):
            store = RedisChatMessageStore(
                redis_url="redis://localhost:6379", thread_id="test123", key_prefix="custom_messages"
            )

        assert store.redis_key == "custom_messages:test123"

    def test_init_with_max_messages(self):
        """Test initialization with message limit."""
        with patch("agent_framework_redis._chat_message_store.redis.from_url"):
            store = RedisChatMessageStore(redis_url="redis://localhost:6379", thread_id="test123", max_messages=100)

        assert store.max_messages == 100

    def test_init_with_redis_url_required(self):
        """Test that redis_url is required for initialization."""
        with pytest.raises(ValueError, match="redis_url is required for Redis connection"):
            # Should raise an exception since redis_url is required
            RedisChatMessageStore(thread_id="test123")

    def test_init_with_initial_messages(self, sample_messages):
        """Test initialization with initial messages."""
        with patch("agent_framework_redis._chat_message_store.redis.from_url"):
            store = RedisChatMessageStore(
                redis_url="redis://localhost:6379", thread_id="test123", messages=sample_messages
            )

        assert store._initial_messages == sample_messages

    async def test_add_messages_single(self, redis_store, mock_redis_client, sample_messages):
        """Test adding a single message using pipeline operations."""
        message = sample_messages[0]

        await redis_store.add_messages([message])

        # Verify pipeline operations were called
        mock_redis_client.pipeline.assert_called_with(transaction=True)

        # Get the pipeline mock and verify it was used correctly
        pipeline_mock = mock_redis_client.pipeline.return_value.__aenter__.return_value
        pipeline_mock.rpush.assert_called()
        pipeline_mock.execute.assert_called()

    async def test_add_messages_multiple(self, redis_store, mock_redis_client, sample_messages):
        """Test adding multiple messages using pipeline operations."""
        await redis_store.add_messages(sample_messages)

        # Verify pipeline operations
        mock_redis_client.pipeline.assert_called_with(transaction=True)

        # Verify rpush was called for each message
        pipeline_mock = mock_redis_client.pipeline.return_value.__aenter__.return_value
        assert pipeline_mock.rpush.call_count == len(sample_messages)

    async def test_add_messages_with_max_limit(self, mock_redis_client):
        """Test adding messages with max limit triggers trimming."""
        with patch("agent_framework_redis._chat_message_store.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client

            # Mock llen to return count that exceeds limit after adding
            mock_redis_client.llen.return_value = 5

            store = RedisChatMessageStore(redis_url="redis://localhost:6379", thread_id="test123", max_messages=3)
            store._redis_client = mock_redis_client

            message = ChatMessage(role=Role.USER, text="Test")
            await store.add_messages([message])

            # Should trim after adding to keep only last 3 messages
            mock_redis_client.ltrim.assert_called_once_with("chat_messages:test123", -3, -1)

    async def test_list_messages_empty(self, redis_store, mock_redis_client):
        """Test listing messages when store is empty."""
        mock_redis_client.lrange.return_value = []

        messages = await redis_store.list_messages()

        assert messages == []
        mock_redis_client.lrange.assert_called_once_with("chat_messages:test_thread_123", 0, -1)

    async def test_list_messages_with_data(self, redis_store, mock_redis_client, sample_messages):
        """Test listing messages with data in Redis."""
        # Create proper serialized messages using the actual serialization method
        test_messages = [
            ChatMessage(role=Role.USER, text="Hello", message_id="msg1"),
            ChatMessage(role=Role.ASSISTANT, text="Hi there!", message_id="msg2"),
        ]
        serialized_messages = [redis_store._serialize_message(msg) for msg in test_messages]
        mock_redis_client.lrange.return_value = serialized_messages

        messages = await redis_store.list_messages()

        assert len(messages) == 2
        assert messages[0].role == Role.USER
        assert messages[0].text == "Hello"
        assert messages[1].role == Role.ASSISTANT
        assert messages[1].text == "Hi there!"

    async def test_list_messages_with_initial_messages(self, sample_messages):
        """Test that initial messages are added to Redis and retrieved correctly."""
        with patch("agent_framework_redis._chat_message_store.redis.from_url") as mock_from_url:
            mock_redis_client = MagicMock()
            mock_redis_client.llen = AsyncMock(return_value=0)  # Redis key is empty
            mock_redis_client.lrange = AsyncMock(return_value=[])

            # Mock pipeline for adding initial messages
            mock_pipeline = AsyncMock()
            mock_pipeline.rpush = AsyncMock()
            mock_pipeline.execute = AsyncMock()
            mock_redis_client.pipeline.return_value.__aenter__.return_value = mock_pipeline

            mock_from_url.return_value = mock_redis_client

            store = RedisChatMessageStore(
                redis_url="redis://localhost:6379",
                thread_id="test123",
                messages=sample_messages[:1],  # One initial message
            )
            store._redis_client = mock_redis_client

            # Mock Redis to return the initial message after it's added
            initial_message_json = store._serialize_message(sample_messages[0])
            mock_redis_client.lrange.return_value = [initial_message_json]

            messages = await store.list_messages()

            assert len(messages) == 1
            assert messages[0].text == "Hello"
            # Verify initial message was added to Redis via pipeline
            mock_pipeline.rpush.assert_called()

    async def test_initial_messages_not_added_if_key_exists(self, sample_messages):
        """Test that initial messages are not added if Redis key already has data."""
        with patch("agent_framework_redis._chat_message_store.redis.from_url") as mock_from_url:
            mock_redis_client = MagicMock()
            mock_redis_client.llen = AsyncMock(return_value=5)  # Key already has messages
            mock_redis_client.lrange = AsyncMock(return_value=[])

            # Pipeline should not be called since key already exists
            mock_pipeline = AsyncMock()
            mock_pipeline.rpush = AsyncMock()
            mock_pipeline.execute = AsyncMock()
            mock_redis_client.pipeline.return_value.__aenter__.return_value = mock_pipeline

            mock_from_url.return_value = mock_redis_client

            store = RedisChatMessageStore(
                redis_url="redis://localhost:6379",
                thread_id="test123",
                messages=sample_messages[:1],  # One initial message
            )
            store._redis_client = mock_redis_client

            await store.list_messages()

            # Should check length but not add messages since key exists
            mock_redis_client.llen.assert_called()
            mock_pipeline.rpush.assert_not_called()

    async def test_serialize_state(self, redis_store):
        """Test state serialization."""
        state = await redis_store.serialize_state()

        expected_state = {
            "thread_id": "test_thread_123",
            "redis_url": "redis://localhost:6379",
            "key_prefix": "chat_messages",
            "max_messages": None,
        }

        assert state == expected_state

    async def test_deserialize_state(self, redis_store):
        """Test state deserialization."""
        serialized_state = {
            "thread_id": "restored_thread_456",
            "redis_url": "redis://localhost:6380",
            "key_prefix": "restored_messages",
            "max_messages": 50,
        }

        await redis_store.deserialize_state(serialized_state)

        assert redis_store.thread_id == "restored_thread_456"
        assert redis_store.redis_url == "redis://localhost:6380"
        assert redis_store.key_prefix == "restored_messages"
        assert redis_store.max_messages == 50

    async def test_deserialize_state_empty(self, redis_store):
        """Test deserializing empty state doesn't change anything."""
        original_thread_id = redis_store.thread_id

        await redis_store.deserialize_state(None)

        assert redis_store.thread_id == original_thread_id

    async def test_clear_messages(self, redis_store, mock_redis_client):
        """Test clearing all messages."""
        await redis_store.clear()

        mock_redis_client.delete.assert_called_once_with("chat_messages:test_thread_123")

    async def test_message_serialization_roundtrip(self, sample_messages):
        """Test message serialization and deserialization roundtrip."""
        with patch("agent_framework_redis._chat_message_store.redis.from_url"):
            store = RedisChatMessageStore(redis_url="redis://localhost:6379", thread_id="test123")

        message = sample_messages[0]

        # Test serialization
        serialized = store._serialize_message(message)
        assert isinstance(serialized, str)

        # Test deserialization
        deserialized = store._deserialize_message(serialized)
        assert deserialized.role == message.role
        assert deserialized.text == message.text
        assert deserialized.message_id == message.message_id

    async def test_message_serialization_with_complex_content(self):
        """Test serialization of messages with complex content."""
        with patch("agent_framework_redis._chat_message_store.redis.from_url"):
            store = RedisChatMessageStore(redis_url="redis://localhost:6379", thread_id="test123")

        # Message with multiple content types
        message = ChatMessage(
            role=Role.ASSISTANT,
            contents=[TextContent(text="Hello"), TextContent(text="World")],
            author_name="TestBot",
            message_id="complex_msg",
            additional_properties={"metadata": "test"},
        )

        serialized = store._serialize_message(message)
        deserialized = store._deserialize_message(serialized)

        assert deserialized.role == Role.ASSISTANT
        assert deserialized.text == "Hello World"
        assert deserialized.author_name == "TestBot"
        assert deserialized.message_id == "complex_msg"
        assert deserialized.additional_properties == {"metadata": "test"}

    async def test_redis_connection_error_handling(self):
        """Test handling Redis connection errors in add_messages."""
        with patch("agent_framework_redis._chat_message_store.redis.from_url") as mock_from_url:
            mock_client = MagicMock()

            # Mock pipeline to raise exception during execution
            mock_pipeline = AsyncMock()
            mock_pipeline.rpush = AsyncMock()
            mock_pipeline.execute = AsyncMock(side_effect=Exception("Connection failed"))
            mock_client.pipeline.return_value.__aenter__.return_value = mock_pipeline

            mock_from_url.return_value = mock_client

            store = RedisChatMessageStore(redis_url="redis://localhost:6379", thread_id="test123")
            store._redis_client = mock_client

            message = ChatMessage(role=Role.USER, text="Test")

            # Should propagate Redis connection errors
            with pytest.raises(Exception, match="Connection failed"):
                await store.add_messages([message])

    async def test_getitem(self, redis_store, mock_redis_client, sample_messages):
        """Test getitem method using Redis LINDEX."""
        # Mock LINDEX to return specific messages
        serialized_msg0 = redis_store._serialize_message(sample_messages[0])
        serialized_msg1 = redis_store._serialize_message(sample_messages[1])

        def mock_lindex(key, index):
            if index == 0:
                return serialized_msg0
            if index == -1 or index == 1:
                return serialized_msg1
            return None

        mock_redis_client.lindex = AsyncMock(side_effect=mock_lindex)

        # Test positive index
        message = await redis_store.getitem(0)
        assert message.text == "Hello"

        # Test negative index
        message = await redis_store.getitem(-1)
        assert message.text == "Hi there!"

    async def test_getitem_index_error(self, redis_store, mock_redis_client):
        """Test getitem raises IndexError for invalid index."""
        mock_redis_client.lindex = AsyncMock(return_value=None)

        with pytest.raises(IndexError):
            await redis_store.getitem(0)

    async def test_setitem(self, redis_store, mock_redis_client, sample_messages):
        """Test setitem method using Redis LSET."""
        mock_redis_client.llen.return_value = 2
        mock_redis_client.lset = AsyncMock()

        new_message = ChatMessage(role=Role.USER, text="Updated message")
        await redis_store.setitem(0, new_message)

        mock_redis_client.lset.assert_called_once()
        call_args = mock_redis_client.lset.call_args
        assert call_args[0][0] == "chat_messages:test_thread_123"
        assert call_args[0][1] == 0

    async def test_setitem_index_error(self, redis_store, mock_redis_client):
        """Test setitem raises IndexError for invalid index."""
        mock_redis_client.llen.return_value = 0

        new_message = ChatMessage(role=Role.USER, text="Test")
        with pytest.raises(IndexError):
            await redis_store.setitem(0, new_message)

    async def test_append(self, redis_store, mock_redis_client):
        """Test append method delegates to add_messages."""
        message = ChatMessage(role=Role.USER, text="Appended message")
        await redis_store.append(message)

        # Should call pipeline operations via add_messages
        mock_redis_client.pipeline.assert_called_with(transaction=True)

        # Verify the message was added via pipeline
        pipeline_mock = mock_redis_client.pipeline.return_value.__aenter__.return_value
        pipeline_mock.rpush.assert_called()
        pipeline_mock.execute.assert_called()

    async def test_count(self, redis_store, mock_redis_client):
        """Test count method."""
        mock_redis_client.llen.return_value = 5

        count = await redis_store.count()

        assert count == 5
        mock_redis_client.llen.assert_called_with("chat_messages:test_thread_123")

    async def test_len_method(self, redis_store, mock_redis_client):
        """Test async __len__ method."""
        mock_redis_client.llen.return_value = 3

        length = await redis_store.__len__()

        assert length == 3
        mock_redis_client.llen.assert_called_with("chat_messages:test_thread_123")

    def test_bool_method(self, redis_store):
        """Test __bool__ method always returns True."""
        # Store should always be truthy
        assert bool(redis_store) is True
        assert redis_store.__bool__() is True

        # Should work in if statements (this is what Agent Framework uses)
        if redis_store:
            assert True  # Should reach this
        else:
            raise AssertionError("Store should be truthy")

    async def test_index_found(self, redis_store, mock_redis_client, sample_messages):
        """Test index method when message is found using Redis LINDEX."""
        mock_redis_client.llen.return_value = 2

        # Mock LINDEX to return messages at each position
        serialized_msg0 = redis_store._serialize_message(sample_messages[0])
        serialized_msg1 = redis_store._serialize_message(sample_messages[1])

        def mock_lindex(key, index):
            if index == 0:
                return serialized_msg0
            if index == 1:
                return serialized_msg1
            return None

        mock_redis_client.lindex = AsyncMock(side_effect=mock_lindex)

        index = await redis_store.index(sample_messages[1])
        assert index == 1

        # Should have called lindex twice (index 0, then index 1)
        assert mock_redis_client.lindex.call_count == 2

    async def test_index_not_found(self, redis_store, mock_redis_client, sample_messages):
        """Test index method when message is not found."""
        mock_redis_client.llen.return_value = 1
        mock_redis_client.lindex = AsyncMock(return_value="different_message")

        with pytest.raises(ValueError, match="ChatMessage not found in store"):
            await redis_store.index(sample_messages[0])

    async def test_remove(self, redis_store, mock_redis_client, sample_messages):
        """Test remove method using Redis LREM."""
        mock_redis_client.lrem = AsyncMock(return_value=1)  # 1 element removed

        await redis_store.remove(sample_messages[0])

        # Should use LREM to remove the message
        expected_serialized = redis_store._serialize_message(sample_messages[0])
        mock_redis_client.lrem.assert_called_once_with("chat_messages:test_thread_123", 1, expected_serialized)

    async def test_remove_not_found(self, redis_store, mock_redis_client, sample_messages):
        """Test remove method when message is not found."""
        mock_redis_client.lrem = AsyncMock(return_value=0)  # 0 elements removed

        with pytest.raises(ValueError, match="ChatMessage not found in store"):
            await redis_store.remove(sample_messages[0])

    async def test_extend(self, redis_store, mock_redis_client, sample_messages):
        """Test extend method delegates to add_messages."""
        await redis_store.extend(sample_messages[:2])

        # Should call pipeline operations via add_messages
        mock_redis_client.pipeline.assert_called_with(transaction=True)

        # Verify rpush was called for each message
        pipeline_mock = mock_redis_client.pipeline.return_value.__aenter__.return_value
        assert pipeline_mock.rpush.call_count >= 2
