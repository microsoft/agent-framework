# Copyright (c) Microsoft. All rights reserved.

"""Tests for performance fixes: context memory leak and item lookup optimization."""

import pytest

from agent_framework_devui._conversations import InMemoryConversationStore
from agent_framework_devui._mapper import MessageMapper
from agent_framework_devui.models._openai_custom import AgentFrameworkRequest


class TestContextMemoryLeak:
    """Test that context memory leak is fixed."""

    def test_context_cleanup_after_aggregation(self):
        """Verify contexts are cleaned up after aggregation."""
        mapper = MessageMapper(max_contexts=10)

        # Create multiple requests
        requests = [AgentFrameworkRequest(model="test_agent", input="test message", stream=True) for _ in range(5)]

        # Create contexts for each request
        for request in requests:
            mapper._get_or_create_context(request)

        # Verify contexts created
        assert len(mapper._conversion_contexts) == 5

        # Simulate aggregation cleanup for first 3 requests
        import asyncio

        async def cleanup_requests():
            for request in requests[:3]:
                # Call aggregate_to_response which should cleanup
                await mapper.aggregate_to_response([], request)

        asyncio.run(cleanup_requests())

        # Verify first 3 contexts were cleaned up
        assert len(mapper._conversion_contexts) == 2, "Contexts should be cleaned up after aggregation"

    def test_lru_eviction_at_capacity(self):
        """Verify LRU eviction works when at max capacity."""
        mapper = MessageMapper(max_contexts=3)

        # Create 5 requests (more than max)
        requests = [AgentFrameworkRequest(model="test_agent", input=f"message {i}", stream=True) for i in range(5)]

        # Create contexts for all requests
        for request in requests:
            mapper._get_or_create_context(request)

        # Should only have 3 contexts (oldest 2 evicted)
        assert len(mapper._conversion_contexts) == 3, "Should only keep max_contexts"

    def test_lru_move_to_end_on_access(self):
        """Verify accessing a context moves it to end (LRU)."""
        mapper = MessageMapper(max_contexts=3)

        # Create 3 requests
        req1 = AgentFrameworkRequest(model="test_agent", input="msg1", stream=True)
        req2 = AgentFrameworkRequest(model="test_agent", input="msg2", stream=True)
        req3 = AgentFrameworkRequest(model="test_agent", input="msg3", stream=True)

        # Create contexts
        mapper._get_or_create_context(req1)
        mapper._get_or_create_context(req2)
        mapper._get_or_create_context(req3)

        # Access req1 again (should move to end)
        mapper._get_or_create_context(req1)

        # Add one more (should evict req2, not req1)
        req4 = AgentFrameworkRequest(model="test_agent", input="msg4", stream=True)
        mapper._get_or_create_context(req4)

        # Verify req1 still exists (was moved to end)
        assert id(req1) in mapper._conversion_contexts
        # Verify req2 was evicted (was oldest)
        assert id(req2) not in mapper._conversion_contexts


class TestItemLookupOptimization:
    """Test that item lookup optimization works correctly."""

    @pytest.mark.asyncio
    async def test_item_index_created_on_conversation_create(self):
        """Verify item index is initialized when conversation is created."""
        store = InMemoryConversationStore()

        conv = store.create_conversation()

        assert conv.id in store._item_index
        assert isinstance(store._item_index[conv.id], dict)
        assert len(store._item_index[conv.id]) == 0

    @pytest.mark.asyncio
    async def test_item_index_populated_on_add_items(self):
        """Verify items are added to index when added to conversation."""
        store = InMemoryConversationStore()

        conv = store.create_conversation()

        # Add items
        items = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Hello"}]}]

        added_items = await store.add_items(conv.id, items)

        # Verify index populated
        assert len(store._item_index[conv.id]) == 1
        assert added_items[0].id in store._item_index[conv.id]

    @pytest.mark.asyncio
    async def test_get_item_uses_index_o1_lookup(self):
        """Verify get_item uses index for O(1) lookup."""
        store = InMemoryConversationStore()

        conv = store.create_conversation()

        # Add 100 items
        items = [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": f"Message {i}"}]}
            for i in range(100)
        ]

        added_items = await store.add_items(conv.id, items)

        # Get item from middle (would be slow with linear search)
        target_item = added_items[50]

        # Should use index for O(1) lookup
        retrieved_item = store.get_item(conv.id, target_item.id)

        assert retrieved_item is not None
        assert retrieved_item.id == target_item.id

    @pytest.mark.asyncio
    async def test_item_index_cleaned_up_on_delete(self):
        """Verify item index is cleaned up when conversation is deleted."""
        store = InMemoryConversationStore()

        conv = store.create_conversation()

        # Add items
        items = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Hello"}]}]
        await store.add_items(conv.id, items)

        # Verify index exists
        assert conv.id in store._item_index

        # Delete conversation
        store.delete_conversation(conv.id)

        # Verify index cleaned up
        assert conv.id not in store._item_index

    @pytest.mark.asyncio
    async def test_get_item_returns_none_for_missing_conversation(self):
        """Verify get_item returns None for non-existent conversation."""
        store = InMemoryConversationStore()

        item = store.get_item("nonexistent_conv", "nonexistent_item")

        assert item is None

    @pytest.mark.asyncio
    async def test_get_item_returns_none_for_missing_item(self):
        """Verify get_item returns None for non-existent item."""
        store = InMemoryConversationStore()

        conv = store.create_conversation()

        item = store.get_item(conv.id, "nonexistent_item")

        assert item is None
