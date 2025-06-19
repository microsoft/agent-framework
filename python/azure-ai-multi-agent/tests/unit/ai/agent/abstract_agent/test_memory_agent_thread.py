# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import pytest
import asyncio

from azure.ai.agent.abstract_agent.memory_agent_thread import MemoryAgentThread
from azure.ai.agent.common import ChatMessage, ChatRole

@pytest.mark.asyncio
async def test_memory_agent_thread_initialization():
    """Test that a MemoryAgentThread can be initialized."""
    thread = MemoryAgentThread()
    assert thread is not None
    assert thread.id is None
    assert len(thread.messages) == 0
    
    # Test initialization with thread ID
    thread_id = "test-memory-thread-id"
    thread = MemoryAgentThread(thread_id)
    assert thread.id == thread_id

@pytest.mark.asyncio
async def test_memory_agent_thread_add_message():
    """Test adding a single message to a MemoryAgentThread."""
    thread = MemoryAgentThread()
    message = ChatMessage(ChatRole.USER, "Hello")
    
    thread.add_message(message)
    
    assert len(thread.messages) == 1
    assert thread.messages[0] == message
    
    # Test adding None message raises ValueError
    with pytest.raises(ValueError):
        thread.add_message(None)

@pytest.mark.asyncio
async def test_memory_agent_thread_add_messages():
    """Test adding multiple messages to a MemoryAgentThread."""
    thread = MemoryAgentThread()
    messages = [
        ChatMessage(ChatRole.USER, "Hello"),
        ChatMessage(ChatRole.ASSISTANT, "Hi there!")
    ]
    
    thread.add_messages(messages)
    
    assert len(thread.messages) == 2
    assert thread.messages[0] == messages[0]
    assert thread.messages[1] == messages[1]
    
    # Test adding None messages raises ValueError
    with pytest.raises(ValueError):
        thread.add_messages(None)

@pytest.mark.asyncio
async def test_memory_agent_thread_clear_messages():
    """Test clearing messages from a MemoryAgentThread."""
    thread = MemoryAgentThread()
    messages = [
        ChatMessage(ChatRole.USER, "Hello"),
        ChatMessage(ChatRole.ASSISTANT, "Hi there!")
    ]
    
    thread.add_messages(messages)
    assert len(thread.messages) == 2
    
    thread.clear_messages()
    assert len(thread.messages) == 0

@pytest.mark.asyncio
async def test_memory_agent_thread_on_new_messages_async():
    """Test the on_new_messages_async method of MemoryAgentThread."""
    thread = MemoryAgentThread()
    
    # Create some test messages
    messages = [
        ChatMessage(ChatRole.USER, "Hello"),
        ChatMessage(ChatRole.ASSISTANT, "Hi there!")
    ]
    
    # The implementation should add the messages to the internal store
    await thread.on_new_messages_async(messages)
    
    assert len(thread.messages) == 2
    assert thread.messages[0] == messages[0]
    assert thread.messages[1] == messages[1]

@pytest.mark.asyncio
async def test_memory_agent_thread_get_messages_async():
    """Test the get_messages_async method of MemoryAgentThread."""
    thread = MemoryAgentThread()
    
    # Create some test messages
    messages = [
        ChatMessage(ChatRole.USER, "Hello"),
        ChatMessage(ChatRole.ASSISTANT, "Hi there!")
    ]
    
    thread.add_messages(messages)
    
    # Get the messages asynchronously
    result_messages = []
    async for message in thread.get_messages_async():
        result_messages.append(message)
    
    assert len(result_messages) == 2
    assert result_messages[0] == messages[0]
    assert result_messages[1] == messages[1]

@pytest.mark.asyncio
async def test_memory_agent_thread_messages_property():
    """Test the messages property of MemoryAgentThread."""
    thread = MemoryAgentThread()
    
    # Create some test messages
    messages = [
        ChatMessage(ChatRole.USER, "Hello"),
        ChatMessage(ChatRole.ASSISTANT, "Hi there!")
    ]
    
    thread.add_messages(messages)
    
    # Get a copy of the messages
    copied_messages = thread.messages
    
    # Verify it's a copy by modifying it and checking the original is unchanged
    copied_messages.append(ChatMessage(ChatRole.SYSTEM, "Test"))
    
    assert len(thread.messages) == 2
    assert len(copied_messages) == 3
