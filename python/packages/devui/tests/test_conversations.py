# Copyright (c) Microsoft. All rights reserved.

"""Tests for conversation store implementation."""

from typing import cast

import pytest
from openai.types.conversations import InputFileContent, InputImageContent, InputTextContent

from agent_framework_devui._conversations import InMemoryConversationStore


@pytest.mark.asyncio
async def test_create_conversation():
    """Test creating a conversation."""
    store = InMemoryConversationStore()

    conversation = store.create_conversation(metadata={"agent_id": "test_agent"})

    assert conversation.id.startswith("conv_")
    assert conversation.object == "conversation"
    assert conversation.metadata == {"agent_id": "test_agent"}


@pytest.mark.asyncio
async def test_get_conversation():
    """Test retrieving a conversation."""
    store = InMemoryConversationStore()

    # Create conversation
    created = store.create_conversation(metadata={"agent_id": "test_agent"})

    # Retrieve it
    retrieved = store.get_conversation(created.id)

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.metadata == {"agent_id": "test_agent"}


@pytest.mark.asyncio
async def test_get_conversation_not_found():
    """Test retrieving non-existent conversation."""
    store = InMemoryConversationStore()

    conversation = store.get_conversation("conv_nonexistent")

    assert conversation is None


@pytest.mark.asyncio
async def test_update_conversation():
    """Test updating conversation metadata."""
    store = InMemoryConversationStore()

    # Create conversation
    created = store.create_conversation(metadata={"agent_id": "test_agent"})

    # Update metadata
    updated = store.update_conversation(created.id, metadata={"agent_id": "new_agent", "session_id": "sess_123"})

    assert updated.id == created.id
    assert updated.metadata == {"agent_id": "new_agent", "session_id": "sess_123"}


@pytest.mark.asyncio
async def test_delete_conversation():
    """Test deleting a conversation."""
    store = InMemoryConversationStore()

    # Create conversation
    created = store.create_conversation(metadata={"agent_id": "test_agent"})

    # Delete it
    result = store.delete_conversation(created.id)

    assert result.id == created.id
    assert result.deleted is True
    assert result.object == "conversation.deleted"

    # Verify it's gone
    assert store.get_conversation(created.id) is None


@pytest.mark.asyncio
async def test_get_thread():
    """Test getting underlying AgentThread."""
    store = InMemoryConversationStore()

    # Create conversation
    conversation = store.create_conversation(metadata={"agent_id": "test_agent"})

    # Get thread
    thread = store.get_thread(conversation.id)

    assert thread is not None
    # AgentThread should have message_store
    assert hasattr(thread, "message_store")


@pytest.mark.asyncio
async def test_get_thread_not_found():
    """Test getting thread for non-existent conversation."""
    store = InMemoryConversationStore()

    thread = store.get_thread("conv_nonexistent")

    assert thread is None


@pytest.mark.asyncio
async def test_list_conversations_by_metadata():
    """Test filtering conversations by metadata."""
    store = InMemoryConversationStore()

    # Create multiple conversations
    _conv1 = store.create_conversation(metadata={"agent_id": "agent1"})
    _conv2 = store.create_conversation(metadata={"agent_id": "agent2"})
    conv3 = store.create_conversation(metadata={"agent_id": "agent1", "session_id": "sess_1"})

    # Filter by agent_id
    results = store.list_conversations_by_metadata({"agent_id": "agent1"})

    assert len(results) == 2
    assert all(cast(dict[str, str], c.metadata).get("agent_id") == "agent1" for c in results if c.metadata)

    # Filter by agent_id and session_id
    results = store.list_conversations_by_metadata({"agent_id": "agent1", "session_id": "sess_1"})

    assert len(results) == 1
    assert results[0].id == conv3.id


@pytest.mark.asyncio
async def test_add_items():
    """Test adding items to conversation."""
    store = InMemoryConversationStore()

    # Create conversation
    conversation = store.create_conversation(metadata={"agent_id": "test_agent"})

    # Add items
    items = [{"role": "user", "content": [{"type": "text", "text": "Hello"}]}]

    conv_items = await store.add_items(conversation.id, items=items)

    assert len(conv_items) == 1
    # Message is a ConversationItem type - check standard OpenAI fields
    assert conv_items[0].type == "message"
    assert conv_items[0].role == "user"
    assert conv_items[0].status == "completed"
    assert len(conv_items[0].content) == 1
    assert conv_items[0].content[0].type == "text"
    text_content = cast(InputTextContent, conv_items[0].content[0])
    assert text_content.text == "Hello"


@pytest.mark.asyncio
async def test_list_items():
    """Test listing conversation items."""
    store = InMemoryConversationStore()

    # Create conversation
    conversation = store.create_conversation(metadata={"agent_id": "test_agent"})

    # Add items
    items = [
        {"role": "user", "content": [{"type": "text", "text": "Hello"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Hi there"}]},
    ]
    await store.add_items(conversation.id, items=items)

    # List items
    retrieved_items, has_more = await store.list_items(conversation.id)

    assert len(retrieved_items) >= 2  # At least the items we added
    assert has_more is False


@pytest.mark.asyncio
async def test_list_items_pagination():
    """Test pagination when listing items."""
    store = InMemoryConversationStore()

    # Create conversation
    conversation = store.create_conversation(metadata={"agent_id": "test_agent"})

    # Add multiple items
    items = [{"role": "user", "content": [{"type": "text", "text": f"Message {i}"}]} for i in range(5)]
    await store.add_items(conversation.id, items=items)

    # List with limit
    retrieved_items, has_more = await store.list_items(conversation.id, limit=3)

    assert len(retrieved_items) == 3
    assert has_more is True


@pytest.mark.asyncio
async def test_list_items_converts_function_calls():
    """Test that list_items properly converts function calls to ResponseFunctionToolCallItem."""
    from agent_framework import ChatMessage, ChatMessageStore, Role

    store = InMemoryConversationStore()

    # Create conversation
    conversation = store.create_conversation(metadata={"agent_id": "test_agent"})

    # Get the underlying thread and set up message store
    thread = store.get_thread(conversation.id)
    assert thread is not None

    # Initialize message store if not present
    if thread.message_store is None:
        thread.message_store = ChatMessageStore()

    # Simulate messages from agent execution with function calls
    messages = [
        ChatMessage(role=Role.USER, contents=[{"type": "text", "text": "What's the weather in SF?"}]),
        ChatMessage(
            role=Role.ASSISTANT,
            contents=[
                {
                    "type": "function_call",
                    "name": "get_weather",
                    "arguments": '{"city": "San Francisco"}',
                    "call_id": "call_test123",
                }
            ],
        ),
        ChatMessage(
            role=Role.TOOL,
            contents=[
                {
                    "type": "function_result",
                    "call_id": "call_test123",
                    "output": '{"temperature": 65, "condition": "sunny"}',
                }
            ],
        ),
        ChatMessage(role=Role.ASSISTANT, contents=[{"type": "text", "text": "The weather is sunny, 65°F"}]),
    ]

    # Add messages to thread
    await thread.on_new_messages(messages)

    # List conversation items
    items, has_more = await store.list_items(conversation.id)

    # Verify we got the right number and types of items
    assert len(items) == 4, f"Expected 4 items, got {len(items)}"
    assert has_more is False

    # Check item types
    assert items[0].type == "message", "First item should be a message"
    assert items[0].role == "user"
    assert len(items[0].content) == 1
    text_content_0 = cast(InputTextContent, items[0].content[0])
    assert text_content_0.text == "What's the weather in SF?"

    assert items[1].type == "function_call", "Second item should be a function_call"
    assert items[1].call_id == "call_test123"
    assert items[1].name == "get_weather"
    assert items[1].arguments == '{"city": "San Francisco"}'
    assert items[1].status == "completed"

    assert items[2].type == "function_call_output", "Third item should be a function_call_output"
    assert items[2].call_id == "call_test123"
    assert items[2].output == '{"temperature": 65, "condition": "sunny"}'
    assert items[2].status == "completed"

    assert items[3].type == "message", "Fourth item should be a message"
    assert items[3].role == "assistant"
    assert len(items[3].content) == 1
    text_content_3 = cast(InputTextContent, items[3].content[0])
    assert text_content_3.text == "The weather is sunny, 65°F"

    # CRITICAL: Ensure no empty message items
    for item in items:
        if item.type == "message":
            assert len(item.content) > 0, f"Message item {item.id} has empty content!"


@pytest.mark.asyncio
async def test_list_items_handles_images_and_files():
    """Test that list_items properly converts data content (images/files) to OpenAI types."""
    from agent_framework import ChatMessage, ChatMessageStore, Role

    store = InMemoryConversationStore()

    # Create conversation
    conversation = store.create_conversation(metadata={"agent_id": "test_agent"})

    # Get the underlying thread
    thread = store.get_thread(conversation.id)
    assert thread is not None

    if thread.message_store is None:
        thread.message_store = ChatMessageStore()

    # Simulate message with image and file
    messages = [
        ChatMessage(
            role=Role.USER,
            contents=[
                {"type": "text", "text": "Check this image and PDF"},
                {"type": "data", "uri": "data:image/png;base64,iVBORw0KGgo=", "media_type": "image/png"},
                {"type": "data", "uri": "data:application/pdf;base64,JVBERi0=", "media_type": "application/pdf"},
            ],
        ),
    ]

    await thread.on_new_messages(messages)

    # List items
    items, has_more = await store.list_items(conversation.id)

    assert len(items) == 1
    assert items[0].type == "message"
    assert items[0].role == "user"
    assert len(items[0].content) == 3

    # Check content types
    assert items[0].content[0].type == "text"
    text_content = cast(InputTextContent, items[0].content[0])
    assert text_content.text == "Check this image and PDF"

    assert items[0].content[1].type == "input_image"
    image_content = cast(InputImageContent, items[0].content[1])
    assert image_content.image_url == "data:image/png;base64,iVBORw0KGgo="
    assert image_content.detail == "auto"

    assert items[0].content[2].type == "input_file"
    file_content = cast(InputFileContent, items[0].content[2])
    assert file_content.file_url == "data:application/pdf;base64,JVBERi0="
