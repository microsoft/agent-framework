# Copyright (c) Microsoft. All rights reserved.

"""Tests for conversation store implementation."""

from typing import cast

import pytest
from openai.types.conversations import InputTextContent
from openai.types.conversations.message import Message as OpenAIMessage
from openai.types.responses import ResponseInputFile, ResponseInputImage

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
async def test_get_session():
    """Test getting AgentSession for execution."""
    store = InMemoryConversationStore()

    # Create conversation
    conversation = store.create_conversation(metadata={"agent_id": "test_agent"})

    # Get session
    session = store.get_session(conversation.id)

    assert session is not None
    # AgentSession should have session_id
    assert hasattr(session, "session_id")


@pytest.mark.asyncio
async def test_get_session_not_found():
    """Test getting session for non-existent conversation."""
    store = InMemoryConversationStore()

    session = store.get_session("conv_nonexistent")

    assert session is None


@pytest.mark.asyncio
async def test_list_conversations_by_metadata():
    """Test filtering conversations by metadata."""
    store = InMemoryConversationStore()

    # Create multiple conversations
    _conv1 = store.create_conversation(metadata={"agent_id": "agent1"})
    _conv2 = store.create_conversation(metadata={"agent_id": "agent2"})
    conv3 = store.create_conversation(metadata={"agent_id": "agent1", "session_id": "sess_1"})

    # Filter by agent_id
    results = await store.list_conversations_by_metadata({"agent_id": "agent1"})

    assert len(results) == 2
    assert all(cast(dict[str, str], c.metadata).get("agent_id") == "agent1" for c in results if c.metadata)

    # Filter by agent_id and session_id
    results = await store.list_conversations_by_metadata({"agent_id": "agent1", "session_id": "sess_1"})

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
async def test_add_items_accepts_assistant_output_text():
    """Assistant Responses history is accepted by the conversation parser."""
    store = InMemoryConversationStore()
    conversation = store.create_conversation(metadata={"agent_id": "test_agent"})

    created_items = await store.add_items(
        conversation.id,
        items=[
            {
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Prior answer", "annotations": []}],
            }
        ],
    )
    listed_items, _ = await store.list_items(conversation.id)

    created_message = created_items[0]
    listed_message = listed_items[0]
    assert isinstance(created_message, OpenAIMessage)
    assert isinstance(listed_message, OpenAIMessage)
    assert created_message.role == "assistant"
    assert listed_message.role == "assistant"
    assert created_message.content is not None
    assert listed_message.content is not None
    created_text = cast(InputTextContent, created_message.content[0])
    listed_text = cast(InputTextContent, listed_message.content[0])
    assert created_text.text == "Prior answer"
    assert listed_text.text == "Prior answer"


@pytest.mark.asyncio
async def test_add_and_list_items_preserves_all_supported_message_parts():
    """Conversation conversion retains message boundaries and every supported part."""
    store = InMemoryConversationStore()
    conversation = store.create_conversation(metadata={"agent_id": "test_agent"})
    request_items = [
        {
            "role": "system",
            "content": [
                {"type": "input_text", "text": "First instruction"},
                {"type": "text", "text": "Second instruction"},
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "input_image",
                    "image_url": "https://example.com/photo.jpg?download=1",
                    "detail": "high",
                },
                {"type": "input_image", "file_id": "file_image", "detail": "low"},
                {"type": "input_file", "file_data": "JVBERi0=", "filename": "report.pdf"},
                {"type": "input_file", "file_id": "file_audio", "filename": "recording.mp3"},
                {"type": "input_file", "file_id": "file_scan", "filename": "scan.jpg"},
            ],
        },
    ]

    created_items = await store.add_items(conversation.id, items=request_items)
    listed_items, has_more = await store.list_items(conversation.id)

    created_system, created_user = created_items
    assert isinstance(created_system, OpenAIMessage)
    assert isinstance(created_user, OpenAIMessage)
    assert [created_system.role, created_user.role] == ["system", "user"]
    assert created_system.content is not None
    assert created_user.content is not None
    assert [len(created_system.content), len(created_user.content)] == [2, 5]

    created_url_image = created_user.content[0]
    created_hosted_image = created_user.content[1]
    created_data_file = created_user.content[2]
    created_audio_file = created_user.content[3]
    created_scan_file = created_user.content[4]
    assert isinstance(created_url_image, ResponseInputImage)
    assert isinstance(created_hosted_image, ResponseInputImage)
    assert isinstance(created_data_file, ResponseInputFile)
    assert isinstance(created_audio_file, ResponseInputFile)
    assert isinstance(created_scan_file, ResponseInputFile)
    assert created_url_image.image_url == "https://example.com/photo.jpg?download=1"
    assert created_url_image.detail == "high"
    assert created_hosted_image.file_id == "file_image"
    assert created_hosted_image.detail == "low"
    assert created_data_file.file_url == "data:application/pdf;base64,JVBERi0="
    assert created_data_file.filename == "report.pdf"
    assert created_audio_file.file_id == "file_audio"
    assert created_audio_file.filename == "recording.mp3"
    assert created_scan_file.file_id == "file_scan"

    stored_messages = store._conversations[conversation.id]["messages"]
    assert stored_messages[1].contents[0].media_type == "image/jpeg"
    assert stored_messages[1].contents[2].media_type == "application/pdf"
    assert stored_messages[1].contents[3].media_type == "audio/mpeg"
    assert stored_messages[1].contents[4].media_type == "image/jpeg"

    assert has_more is False
    listed_system, listed_user = listed_items
    assert isinstance(listed_system, OpenAIMessage)
    assert isinstance(listed_user, OpenAIMessage)
    assert [listed_system.role, listed_user.role] == ["system", "user"]
    assert listed_system.content is not None
    assert listed_user.content is not None
    assert [len(listed_system.content), len(listed_user.content)] == [2, 5]

    listed_url_image = listed_user.content[0]
    listed_hosted_image = listed_user.content[1]
    listed_data_file = listed_user.content[2]
    listed_audio_file = listed_user.content[3]
    listed_scan_file = listed_user.content[4]
    assert isinstance(listed_url_image, ResponseInputImage)
    assert isinstance(listed_hosted_image, ResponseInputImage)
    assert isinstance(listed_data_file, ResponseInputFile)
    assert isinstance(listed_audio_file, ResponseInputFile)
    assert isinstance(listed_scan_file, ResponseInputFile)
    assert listed_url_image.detail == "high"
    assert listed_hosted_image.file_id == "file_image"
    assert listed_data_file.file_url == "data:application/pdf;base64,JVBERi0="
    assert listed_audio_file.file_id == "file_audio"
    assert listed_scan_file.file_id == "file_scan"


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
    from agent_framework import Message

    store = InMemoryConversationStore()

    # Create conversation
    conversation = store.create_conversation(metadata={"agent_id": "test_agent"})

    # Simulate messages from agent execution with function calls
    messages = [
        Message(role="user", contents=[{"type": "text", "text": "What's the weather in SF?"}]),
        Message(
            role="assistant",
            contents=[
                {
                    "type": "function_call",
                    "name": "get_weather",
                    "arguments": '{"city": "San Francisco"}',
                    "call_id": "call_test123",
                }
            ],
        ),
        Message(
            role="tool",
            contents=[
                {
                    "type": "function_result",
                    "call_id": "call_test123",
                    "result": '{"temperature": 65, "condition": "sunny"}',
                }
            ],
        ),
        Message(role="assistant", contents=[{"type": "text", "text": "The weather is sunny, 65°F"}]),
    ]

    # Add messages to internal storage
    store._conversations[conversation.id]["messages"].extend(messages)

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
    from agent_framework import Message

    store = InMemoryConversationStore()

    # Create conversation
    conversation = store.create_conversation(metadata={"agent_id": "test_agent"})

    # Simulate message with image and file
    messages = [
        Message(
            role="user",
            contents=[
                {"type": "text", "text": "Check this image and PDF"},
                {"type": "data", "uri": "data:image/png;base64,iVBORw0KGgo=", "media_type": "image/png"},
                {"type": "data", "uri": "data:application/pdf;base64,JVBERi0=", "media_type": "application/pdf"},
            ],
        ),
    ]

    # Add messages to internal storage
    store._conversations[conversation.id]["messages"].extend(messages)

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
    image_content = items[0].content[1]
    assert image_content.image_url == "data:image/png;base64,iVBORw0KGgo="
    assert image_content.detail == "auto"

    assert items[0].content[2].type == "input_file"
    file_content = items[0].content[2]
    assert file_content.file_url == "data:application/pdf;base64,JVBERi0="
