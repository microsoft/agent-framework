# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import asyncio
import pytest
from typing import List, Dict, Any

from azure.ai.agent.abstract_agent import MemoryAgentThread, AgentRunOptions
from azure.ai.agent.simple_agent import SimpleAgent
from azure.ai.agent.common import ChatMessage, ChatRole

class TestMemoryAgentThreadInMultiAgentContext:
    """Tests that demonstrate using MemoryAgentThread in a multi-agent context."""
    
    @pytest.fixture
    def memory_thread(self):
        """Create a MemoryAgentThread instance for testing."""
        return MemoryAgentThread("test-memory-thread")
    
    @pytest.fixture
    def agents(self):
        """Create multiple agents for testing."""
        return {
            "greeter": SimpleAgent(response_text="Hello there!", name="Greeter"),
            "farewell": SimpleAgent(response_text="Goodbye!", name="Farewell"),
            "echo": SimpleAgent(response_text="You said: {message}", name="Echo")
        }
    
    @pytest.mark.asyncio
    async def test_memory_thread_with_multiple_agents(self, memory_thread, agents):
        """Test using a memory thread with multiple agents."""
        # Add a system message to the thread
        system_message = ChatMessage(ChatRole.SYSTEM, "This is a multi-agent conversation.")
        memory_thread.add_message(system_message)
        
        # Create a user message
        user_message = ChatMessage(ChatRole.USER, "Hi")
        
        # Get response from the greeter agent
        greeter_response = await agents["greeter"].run_async_with_messages([user_message], memory_thread)
        
        # Get response from the farewell agent
        farewell_response = await agents["farewell"].run_async_with_messages([user_message], memory_thread)
        
        # Verify the thread has all messages in order
        assert len(memory_thread.messages) == 4
        assert memory_thread.messages[0].role == ChatRole.SYSTEM
        assert memory_thread.messages[1].role == ChatRole.USER
        assert memory_thread.messages[1].content == "Hi"
        assert memory_thread.messages[2].role == ChatRole.ASSISTANT
        assert memory_thread.messages[2].content == "Hello there!"
        assert memory_thread.messages[2].author_name == "Greeter"
        assert memory_thread.messages[3].role == ChatRole.ASSISTANT
        assert memory_thread.messages[3].content == "Goodbye!"
        assert memory_thread.messages[3].author_name == "Farewell"
    
    @pytest.mark.asyncio
    async def test_echo_agent_with_message_formatting(self, memory_thread, agents):
        """Test an agent that formats its response based on user input."""
        # Create a user message
        user_message = ChatMessage(ChatRole.USER, "Testing echo!")
        
        # Create a custom echo agent that formats its response
        custom_echo = SimpleAgent(
            response_text="You said: Testing echo!",
            name="CustomEcho"
        )
        
        # Get response from the echo agent
        echo_response = await custom_echo.run_async_with_messages([user_message], memory_thread)
        
        # Verify the response
        assert echo_response.messages[0].content == "You said: Testing echo!"
        assert echo_response.messages[0].author_name == "CustomEcho"
    
    @pytest.mark.asyncio
    async def test_memory_thread_preserves_conversation_history(self, memory_thread, agents):
        """Test that the thread preserves the full conversation history across multiple turns."""
        # First turn
        user_message1 = ChatMessage(ChatRole.USER, "First message")
        await agents["greeter"].run_async_with_messages([user_message1], memory_thread)
        
        # Second turn
        user_message2 = ChatMessage(ChatRole.USER, "Second message")
        await agents["farewell"].run_async_with_messages([user_message2], memory_thread)
        
        # Third turn - back to the first agent
        user_message3 = ChatMessage(ChatRole.USER, "Third message")
        await agents["greeter"].run_async_with_messages([user_message3], memory_thread)
        
        # Verify full conversation history
        assert len(memory_thread.messages) == 6
        
        # Retrieve messages asynchronously
        messages = []
        async for message in memory_thread.get_messages_async():
            messages.append(message)
        
        # Verify we got all messages
        assert len(messages) == 6
        assert messages[0].content == "First message"
        assert messages[1].content == "Hello there!"
        assert messages[2].content == "Second message"
        assert messages[3].content == "Goodbye!"
        assert messages[4].content == "Third message"
        assert messages[5].content == "Hello there!"
