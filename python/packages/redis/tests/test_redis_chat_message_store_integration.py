# Copyright (c) Microsoft. All rights reserved.

from uuid import uuid4

import pytest
from agent_framework import ChatMessage, Role, TextContent

from agent_framework_redis import RedisChatMessageStore


class TestRedisChatMessageStoreIntegration:
    """Comprehensive integration tests for RedisChatMessageStore with real Redis.

    These tests require a running Redis server and test each method of the
    RedisChatMessageStore class to ensure proper functionality with real Redis operations.
    """

    @pytest.fixture
    async def redis_store(self):
        """Create a Redis store for integration testing with cleanup."""
        import redis.asyncio as redis

        # Check if Redis is available
        try:
            test_client = redis.from_url("redis://localhost:6379", decode_responses=True)
            await test_client.ping()
            await test_client.aclose()
        except Exception:
            pytest.skip("Redis server not available for integration tests")

        # Create store with unique thread ID for test isolation
        thread_id = f"integration_test_{uuid4()}"
        store = RedisChatMessageStore(redis_url="redis://localhost:6379", thread_id=thread_id)

        yield store

        # Cleanup after test
        try:
            await store.clear()
            await store._redis_client.aclose()
        except Exception:
            pass  # Ignore cleanup errors

    @pytest.fixture
    def sample_messages(self):
        """Sample messages for testing."""
        return [
            ChatMessage(role=Role.USER, text="Hello", message_id="msg1", author_name="Alice"),
            ChatMessage(role=Role.ASSISTANT, text="Hi there!", message_id="msg2", author_name="Bot"),
            ChatMessage(role=Role.USER, text="How are you?", message_id="msg3", author_name="Alice"),
            ChatMessage(role=Role.ASSISTANT, text="I'm doing well!", message_id="msg4", author_name="Bot"),
        ]

    # ============================================================================
    # Core Protocol Methods Integration Tests
    # ============================================================================

    async def test_add_messages_integration(self, redis_store, sample_messages):
        """Test add_messages with real Redis."""
        # Initially empty
        initial_messages = await redis_store.list_messages()
        assert len(initial_messages) == 0

        # Add single message
        await redis_store.add_messages([sample_messages[0]])
        messages = await redis_store.list_messages()
        assert len(messages) == 1
        assert messages[0].text == "Hello"
        assert messages[0].message_id == "msg1"

        # Add multiple messages
        await redis_store.add_messages(sample_messages[1:3])
        messages = await redis_store.list_messages()
        assert len(messages) == 3
        assert messages[1].text == "Hi there!"
        assert messages[2].text == "How are you?"

    async def test_list_messages_integration(self, redis_store, sample_messages):
        """Test list_messages with real Redis."""
        # Add messages first
        await redis_store.add_messages(sample_messages)

        # Retrieve messages
        messages = await redis_store.list_messages()

        # Verify order and content
        assert len(messages) == 4
        assert messages[0].text == "Hello"
        assert messages[1].text == "Hi there!"
        assert messages[2].text == "How are you?"
        assert messages[3].text == "I'm doing well!"

        # Verify all properties are preserved
        assert messages[0].role == Role.USER
        assert messages[1].role == Role.ASSISTANT
        assert messages[0].author_name == "Alice"
        assert messages[1].author_name == "Bot"

    async def test_serialize_deserialize_state_integration(self, sample_messages):
        """Test state serialization and deserialization with real Redis."""
        # Create initial store
        thread_id = f"serialize_test_{uuid4()}"
        store1 = RedisChatMessageStore(
            redis_url="redis://localhost:6379", thread_id=thread_id, key_prefix="test_messages", max_messages=50
        )

        # Add some messages
        await store1.add_messages(sample_messages[:2])

        # Serialize state
        serialized_state = await store1.serialize_state()
        await store1._redis_client.aclose()

        # Create new store and deserialize
        store2 = RedisChatMessageStore(redis_url="redis://localhost:6379")
        await store2.deserialize_state(serialized_state)

        # Verify configuration was restored
        assert store2.thread_id == thread_id
        assert store2.key_prefix == "test_messages"
        assert store2.max_messages == 50

        # Verify messages are still accessible
        messages = await store2.list_messages()
        assert len(messages) == 2
        assert messages[0].text == "Hello"
        assert messages[1].text == "Hi there!"

        # Cleanup
        await store2.clear()
        await store2._redis_client.aclose()

    async def test_clear_integration(self, redis_store, sample_messages):
        """Test clear method with real Redis."""
        # Add messages
        await redis_store.add_messages(sample_messages)

        # Verify messages exist
        messages = await redis_store.list_messages()
        assert len(messages) == 4

        # Clear all messages
        await redis_store.clear()

        # Verify messages are gone
        messages = await redis_store.list_messages()
        assert len(messages) == 0

    # ============================================================================
    # List-like Convenience Methods Integration Tests
    # ============================================================================

    async def test_len_integration(self, redis_store, sample_messages):
        """Test async __len__ method with real Redis."""
        # Initially empty
        count = await redis_store.__len__()
        assert count == 0

        # Add messages one by one and check count
        for i, message in enumerate(sample_messages, 1):
            await redis_store.add_messages([message])
            count = await redis_store.__len__()
            assert count == i

    async def test_getitem_integration(self, redis_store, sample_messages):
        """Test getitem method with real Redis."""
        # Add messages
        await redis_store.add_messages(sample_messages)

        # Test positive indices
        message0 = await redis_store.getitem(0)
        assert message0.text == "Hello"

        message2 = await redis_store.getitem(2)
        assert message2.text == "How are you?"

        # Test negative indices
        last_message = await redis_store.getitem(-1)
        assert last_message.text == "I'm doing well!"

        second_last = await redis_store.getitem(-2)
        assert second_last.text == "How are you?"

    async def test_getitem_index_error_integration(self, redis_store):
        """Test getitem with invalid indices."""
        # Empty store
        with pytest.raises(IndexError):
            await redis_store.getitem(0)

        # Add one message
        await redis_store.add_messages([ChatMessage(role=Role.USER, text="Test")])

        # Test out of range indices
        with pytest.raises(IndexError):
            await redis_store.getitem(5)

        with pytest.raises(IndexError):
            await redis_store.getitem(-5)

    async def test_setitem_integration(self, redis_store, sample_messages):
        """Test setitem method with real Redis."""
        # Add initial messages
        await redis_store.add_messages(sample_messages[:3])

        # Update message at index 1
        new_message = ChatMessage(role=Role.ASSISTANT, text="Updated response!", message_id="updated")
        await redis_store.setitem(1, new_message)

        # Verify update
        messages = await redis_store.list_messages()
        assert len(messages) == 3  # Same count
        assert messages[0].text == "Hello"  # Unchanged
        assert messages[1].text == "Updated response!"  # Changed
        assert messages[1].message_id == "updated"
        assert messages[2].text == "How are you?"  # Unchanged

    async def test_append_integration(self, redis_store, sample_messages):
        """Test append method with real Redis."""
        # Start empty
        count = await redis_store.__len__()
        assert count == 0

        # Append messages one by one
        for i, message in enumerate(sample_messages):
            await redis_store.append(message)

            # Verify count increases
            count = await redis_store.__len__()
            assert count == i + 1

            # Verify message is at the end
            last_message = await redis_store.getitem(-1)
            assert last_message.text == message.text

    async def test_count_integration(self, redis_store, sample_messages):
        """Test count method with real Redis."""
        # Test empty store
        count = await redis_store.count()
        assert count == 0

        # Add messages and verify count
        await redis_store.add_messages(sample_messages[:2])
        count = await redis_store.count()
        assert count == 2

        # Add more messages
        await redis_store.add_messages(sample_messages[2:])
        count = await redis_store.count()
        assert count == 4

    async def test_index_integration(self, redis_store, sample_messages):
        """Test index method with real Redis."""
        # Add messages
        await redis_store.add_messages(sample_messages)

        # Find indices of messages
        index0 = await redis_store.index(sample_messages[0])
        assert index0 == 0

        index2 = await redis_store.index(sample_messages[2])
        assert index2 == 2

        # Test message not found
        non_existent = ChatMessage(role=Role.USER, text="Not in store")
        with pytest.raises(ValueError, match="ChatMessage not found in store"):
            await redis_store.index(non_existent)

    async def test_remove_integration(self, redis_store, sample_messages):
        """Test remove method with real Redis."""
        # Add messages
        await redis_store.add_messages(sample_messages)
        initial_count = await redis_store.__len__()
        assert initial_count == 4

        # Remove first message
        await redis_store.remove(sample_messages[0])

        # Verify removal
        count = await redis_store.__len__()
        assert count == 3

        messages = await redis_store.list_messages()
        assert messages[0].text == "Hi there!"  # First message is now the second original
        assert messages[1].text == "How are you?"
        assert messages[2].text == "I'm doing well!"

        # Remove middle message
        await redis_store.remove(sample_messages[2])  # "How are you?"

        # Verify removal
        count = await redis_store.__len__()
        assert count == 2

        messages = await redis_store.list_messages()
        assert messages[0].text == "Hi there!"
        assert messages[1].text == "I'm doing well!"

    async def test_remove_not_found_integration(self, redis_store, sample_messages):
        """Test remove method with message not in store."""
        await redis_store.add_messages(sample_messages[:2])

        # Try to remove message that's not in store
        non_existent = ChatMessage(role=Role.USER, text="Not in store")
        with pytest.raises(ValueError, match="ChatMessage not found in store"):
            await redis_store.remove(non_existent)

    async def test_extend_integration(self, redis_store, sample_messages):
        """Test extend method with real Redis."""
        # Start with one message
        await redis_store.add_messages([sample_messages[0]])

        # Extend with remaining messages
        await redis_store.extend(sample_messages[1:])

        # Verify all messages are present
        messages = await redis_store.list_messages()
        assert len(messages) == 4
        for i, expected in enumerate(sample_messages):
            assert messages[i].text == expected.text
            assert messages[i].message_id == expected.message_id

    # ============================================================================
    # Advanced Integration Tests
    # ============================================================================

    async def test_initial_messages_integration(self, sample_messages):
        """Test store initialization with initial messages."""
        thread_id = f"initial_test_{uuid4()}"

        # Create store with initial messages
        store = RedisChatMessageStore(
            redis_url="redis://localhost:6379",
            thread_id=thread_id,
            messages=sample_messages[:2],  # First 2 messages as initial
        )

        # Initial messages should be added to Redis on first access
        messages = await store.list_messages()
        assert len(messages) == 2
        assert messages[0].text == "Hello"
        assert messages[1].text == "Hi there!"

        # Add more messages
        await store.add_messages(sample_messages[2:])

        # Verify all messages are present
        all_messages = await store.list_messages()
        assert len(all_messages) == 4

        # Cleanup
        await store.clear()
        await store._redis_client.aclose()

    async def test_max_messages_trimming_integration(self, sample_messages):
        """Test automatic message trimming with max_messages."""
        thread_id = f"trim_test_{uuid4()}"

        # Create store with small message limit
        store = RedisChatMessageStore(
            redis_url="redis://localhost:6379",
            thread_id=thread_id,
            max_messages=2,  # Keep only 2 most recent messages
        )

        # Add messages one by one
        for i, message in enumerate(sample_messages):
            await store.add_messages([message])

            messages = await store.list_messages()
            expected_count = min(i + 1, 2)  # Should never exceed 2
            assert len(messages) == expected_count

        # Final check - should have only last 2 messages
        final_messages = await store.list_messages()
        assert len(final_messages) == 2
        assert final_messages[0].text == "How are you?"  # 3rd message
        assert final_messages[1].text == "I'm doing well!"  # 4th message

        # Cleanup
        await store.clear()
        await store._redis_client.aclose()

    async def test_thread_isolation_integration(self, sample_messages):
        """Test that different thread IDs create isolated conversations."""
        thread_id1 = f"isolation_test_1_{uuid4()}"
        thread_id2 = f"isolation_test_2_{uuid4()}"

        # Create two stores with different thread IDs
        store1 = RedisChatMessageStore(redis_url="redis://localhost:6379", thread_id=thread_id1)
        store2 = RedisChatMessageStore(redis_url="redis://localhost:6379", thread_id=thread_id2)

        # Add different messages to each store
        await store1.add_messages(sample_messages[:2])
        await store2.add_messages(sample_messages[2:])

        # Verify isolation
        messages1 = await store1.list_messages()
        messages2 = await store2.list_messages()

        assert len(messages1) == 2
        assert len(messages2) == 2
        assert messages1[0].text == "Hello"
        assert messages2[0].text == "How are you?"

        # Cleanup both stores
        await store1.clear()
        await store2.clear()
        await store1._redis_client.aclose()
        await store2._redis_client.aclose()

    async def test_persistence_across_instances_integration(self, sample_messages):
        """Test that messages persist across different store instances."""
        thread_id = f"persistence_test_{uuid4()}"

        # Create first store instance and add messages
        store1 = RedisChatMessageStore(redis_url="redis://localhost:6379", thread_id=thread_id)
        await store1.add_messages(sample_messages[:2])
        await store1._redis_client.aclose()

        # Create second store instance with same thread ID
        store2 = RedisChatMessageStore(redis_url="redis://localhost:6379", thread_id=thread_id)

        # Should see messages from first instance
        messages = await store2.list_messages()
        assert len(messages) == 2
        assert messages[0].text == "Hello"
        assert messages[1].text == "Hi there!"

        # Add more messages with second instance
        await store2.add_messages(sample_messages[2:])

        # Create third instance to verify persistence
        store3 = RedisChatMessageStore(redis_url="redis://localhost:6379", thread_id=thread_id)

        # Should see all messages
        all_messages = await store3.list_messages()
        assert len(all_messages) == 4

        # Cleanup
        await store3.clear()
        await store2._redis_client.aclose()
        await store3._redis_client.aclose()

    async def test_concurrent_access_integration(self, sample_messages):
        """Test concurrent access from multiple store instances."""
        import asyncio

        thread_id = f"concurrent_test_{uuid4()}"

        # Create multiple store instances for same thread
        stores = [RedisChatMessageStore(redis_url="redis://localhost:6379", thread_id=thread_id) for _ in range(3)]

        # Concurrently add messages from different stores
        async def add_message(store, message):
            await store.add_messages([message])

        # Add messages concurrently
        tasks = [add_message(stores[i % 3], sample_messages[i]) for i in range(len(sample_messages))]
        await asyncio.gather(*tasks)

        # Verify all messages were added
        final_messages = await stores[0].list_messages()
        assert len(final_messages) == 4

        # Cleanup
        await stores[0].clear()
        for store in stores:
            await store._redis_client.aclose()

    async def test_complex_message_content_integration(self, redis_store):
        """Test with complex ChatMessage content."""
        # Create message with multiple content types
        complex_message = ChatMessage(
            role=Role.ASSISTANT,
            contents=[TextContent(text="Here's some text"), TextContent(text="And more text")],
            author_name="ComplexBot",
            message_id="complex_001",
            additional_properties={"metadata": "test_data", "priority": "high"},
        )

        # Add and retrieve
        await redis_store.add_messages([complex_message])
        retrieved_messages = await redis_store.list_messages()

        # Verify complex content is preserved
        retrieved = retrieved_messages[0]
        assert retrieved.role == Role.ASSISTANT
        assert retrieved.text == "Here's some text And more text"  # Combined text
        assert retrieved.author_name == "ComplexBot"
        assert retrieved.message_id == "complex_001"
        assert retrieved.additional_properties == {"metadata": "test_data", "priority": "high"}

    async def test_large_conversation_integration(self, redis_store):
        """Test performance with larger conversation."""
        # Create many messages
        large_conversation = [
            ChatMessage(
                role=Role.USER if i % 2 == 0 else Role.ASSISTANT, text=f"Message number {i}", message_id=f"msg_{i:03d}"
            )
            for i in range(100)
        ]

        # Add in batches
        batch_size = 10
        for i in range(0, len(large_conversation), batch_size):
            batch = large_conversation[i : i + batch_size]
            await redis_store.add_messages(batch)

        # Verify all messages are stored
        count = await redis_store.__len__()
        assert count == 100

        # Verify order is preserved
        messages = await redis_store.list_messages()
        assert messages[0].text == "Message number 0"
        assert messages[50].text == "Message number 50"
        assert messages[99].text == "Message number 99"

        # Test efficient access to specific messages
        message_50 = await redis_store.getitem(50)
        assert message_50.text == "Message number 50"
