# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import pytest
import asyncio

from azure.ai.agent.abstract_agent.agent_thread import AgentThread
from azure.ai.agent.common import ChatMessage, ChatRole

@pytest.mark.asyncio
async def test_agent_thread_initialization():
    """Test that an AgentThread can be initialized."""
    thread = AgentThread()
    assert thread is not None
    assert thread.id is None

@pytest.mark.asyncio
async def test_agent_thread_id_property():
    """Test the id property of AgentThread."""
    thread = AgentThread()
    
    # Test setting and getting the id
    thread_id = "test-thread-id"
    thread.id = thread_id
    assert thread.id == thread_id
    
    # Test setting to None
    thread.id = None
    assert thread.id is None

@pytest.mark.asyncio
async def test_agent_thread_on_new_messages_async():
    """Test the on_new_messages_async method of AgentThread."""
    thread = AgentThread()
    
    # Create some test messages
    messages = [
        ChatMessage(ChatRole.USER, "Hello"),
        ChatMessage(ChatRole.ASSISTANT, "Hi there!")
    ]
    
    # The base implementation does nothing, so we just check that it doesn't raise an exception
    await thread.on_new_messages_async(messages)
    
    # Success if no exception is raised
