# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import pytest
import asyncio
from typing import List, AsyncIterator

from azure.ai.agent.simple_agent import SimpleAgent
from azure.ai.agent.abstract_agent import MemoryAgentThread
from azure.ai.agent.common import ChatMessage, ChatRole, ChatResponseUpdate

@pytest.mark.asyncio
async def test_simple_agent_initialization():
    """Test that a SimpleAgent can be initialized."""
    agent = SimpleAgent()
    assert agent is not None
    assert agent.name is None
    assert agent.description is None
    assert agent.instructions is None
    
    # Test with name, description and instructions
    name = "TestAgent"
    description = "A test agent"
    instructions = "Test instructions"
    agent = SimpleAgent(name=name, description=description, instructions=instructions)
    assert agent.name == name
    assert agent.description == description
    assert agent.instructions == instructions

@pytest.mark.asyncio
async def test_simple_agent_get_new_thread():
    """Test the get_new_thread method of SimpleAgent."""
    agent = SimpleAgent()
    thread = agent.get_new_thread()
    assert thread is not None
    assert isinstance(thread, MemoryAgentThread)

@pytest.mark.asyncio
async def test_simple_agent_run_async_with_messages():
    """Test the run_async_with_messages method of SimpleAgent."""
    response_text = "This is a test response."
    agent = SimpleAgent(response_text=response_text)
    
    # Create a message
    message = ChatMessage(ChatRole.USER, "Hello")
    
    # Run the agent
    response = await agent.run_async_with_messages([message])
    
    # Check the response
    assert response is not None
    assert len(response.messages) == 1
    assert response.messages[0].role == ChatRole.ASSISTANT
    assert response.messages[0].content == response_text

@pytest.mark.asyncio
async def test_simple_agent_run_async_with_thread():
    """Test running the agent with a thread."""
    response_text = "This is a test response."
    agent = SimpleAgent(response_text=response_text)
    
    # Create a thread
    thread = MemoryAgentThread()
    
    # Create a message
    message = ChatMessage(ChatRole.USER, "Hello")
    
    # Run the agent with the thread
    response = await agent.run_async_with_messages([message], thread)
    
    # Check the thread
    assert len(thread.messages) == 2
    assert thread.messages[0].role == ChatRole.USER
    assert thread.messages[0].content == "Hello"
    assert thread.messages[1].role == ChatRole.ASSISTANT
    assert thread.messages[1].content == response_text

@pytest.mark.asyncio
async def test_simple_agent_run_streaming_async_with_messages():
    """Test the run_streaming_async_with_messages method of SimpleAgent."""
    response_text = "This is a streaming test."
    agent = SimpleAgent(response_text=response_text)
    
    # Create a message
    message = ChatMessage(ChatRole.USER, "Hello")
    
    # Run the agent in streaming mode
    updates: List[ChatResponseUpdate] = []
    async for update in agent.run_streaming_async_with_messages([message]):
        updates.append(update)
    
    # Check we got updates
    assert len(updates) > 0
    
    # The final update should have the complete message
    final_update = updates[-1]
    assert final_update.message.role == ChatRole.ASSISTANT
    assert final_update.message.content == response_text
    
    # Check the stream grows incrementally (each update adds a character)
    for i in range(1, len(updates)):
        prev_content = updates[i-1].message.content
        current_content = updates[i].message.content
        assert len(current_content) >= len(prev_content)

@pytest.mark.asyncio
async def test_simple_agent_with_author_name():
    """Test that the agent sets the author_name on messages when name is provided."""
    name = "TestAgent"
    response_text = "This is a test response."
    agent = SimpleAgent(response_text=response_text, name=name)
    
    # Create a message
    message = ChatMessage(ChatRole.USER, "Hello")
    
    # Run the agent
    response = await agent.run_async_with_messages([message])
    
    # Check the response
    assert response.messages[0].author_name == name
