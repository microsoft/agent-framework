# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import pytest
import asyncio

from azure.ai.agent.chat_completion_agent import ChatClientAgentThread, ChatClientAgentThreadType
from azure.ai.agent.common import ChatMessage, ChatRole

@pytest.mark.asyncio
async def test_chat_client_agent_thread_initialization():
    """Test that a ChatClientAgentThread can be initialized."""
    thread = ChatClientAgentThread()
    assert thread is not None
    assert thread.id is None
    assert thread.storage_location is None

@pytest.mark.asyncio
async def test_chat_client_agent_thread_storage_location():
    """Test the storage_location property of ChatClientAgentThread."""
    thread = ChatClientAgentThread()
    
    # Test setting and getting the storage location
    thread.storage_location = ChatClientAgentThreadType.IN_MEMORY_MESSAGES
    assert thread.storage_location == ChatClientAgentThreadType.IN_MEMORY_MESSAGES
    
    # Test setting to a different value
    thread.storage_location = ChatClientAgentThreadType.CONVERSATION_ID
    assert thread.storage_location == ChatClientAgentThreadType.CONVERSATION_ID
    
    # Test setting to None
    thread.storage_location = None
    assert thread.storage_location is None

@pytest.mark.asyncio
async def test_chat_client_agent_thread_on_new_messages_async():
    """Test the on_new_messages_async method of ChatClientAgentThread."""
    thread = ChatClientAgentThread()
    thread.storage_location = ChatClientAgentThreadType.IN_MEMORY_MESSAGES
    
    # Create some test messages
    messages = [
        ChatMessage(ChatRole.USER, "Hello"),
        ChatMessage(ChatRole.ASSISTANT, "Hi there!")
    ]
    
    # Add the messages
    await thread.on_new_messages_async(messages)
    
    # Check that the messages were added by retrieving them
    retrieved_messages = []
    async for message in thread.get_messages_async():
        retrieved_messages.append(message)
    
    assert len(retrieved_messages) == 2
    assert retrieved_messages[0].role == ChatRole.USER
    assert retrieved_messages[0].content == "Hello"
    assert retrieved_messages[1].role == ChatRole.ASSISTANT
    assert retrieved_messages[1].content == "Hi there!"

@pytest.mark.asyncio
async def test_chat_client_agent_thread_conversation_id_storage():
    """Test that a thread with CONVERSATION_ID storage doesn't store messages locally."""
    thread = ChatClientAgentThread()
    thread.storage_location = ChatClientAgentThreadType.CONVERSATION_ID
    
    # Create some test messages
    messages = [
        ChatMessage(ChatRole.USER, "Hello"),
        ChatMessage(ChatRole.ASSISTANT, "Hi there!")
    ]
    
    # Add the messages
    await thread.on_new_messages_async(messages)
    
    # Check that no messages were stored locally
    retrieved_messages = []
    async for message in thread.get_messages_async():
        retrieved_messages.append(message)
    
    assert len(retrieved_messages) == 0
