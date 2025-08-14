"""Mock agent implementations for testing"""

import asyncio
import os
import sys

# Framework agent types
sys.path.append(os.path.join(os.path.dirname(__file__), "../../packages/main"))

from agent_framework import AgentBase, AgentRunResponse, AgentThread, ChatMessage, ChatRole  # type: ignore


class MockAIAgent(AgentBase):
    """Mock AI agent that simulates different responses"""

    def __init__(self, name: str = "mock", responses: list[str] | None = None, **kwargs):
        super().__init__(name=name, **kwargs)
        self._responses = responses or [
            "Hello! How can I help you today?",
            "That's an interesting question!",
            "I understand what you're asking.",
            "Let me think about that...",
            "Here's what I think:",
        ]
        self._response_index = 0

    def get_new_thread(self) -> AgentThread:
        """Create a new conversation thread"""
        # This would normally be implemented by the framework
        # For now, return a simple object
        return type("AgentThread", (), {"messages": []})()

    async def run(
        self, messages: list[ChatMessage] | None = None, *, thread: AgentThread | None = None, **kwargs
    ) -> AgentRunResponse:
        """Provide mock responses"""
        if thread is None:
            thread = self.get_new_thread()

        # Add incoming messages to thread
        if messages:
            for message in messages:
                thread.messages.append(message)

        # Simulate some processing time
        await asyncio.sleep(0.1)

        # Generate response
        response_text = self._responses[self._response_index % len(self._responses)]
        self._response_index += 1

        response_message = ChatMessage(role=ChatRole.ASSISTANT, text=response_text)
        thread.messages.append(response_message)

        return AgentRunResponse(messages=[response_message])


class EchoAgent(AgentBase):
    """Echo agent for testing"""

    def __init__(self, name: str = "echo", **kwargs):
        super().__init__(name=name, **kwargs)

    def get_new_thread(self) -> AgentThread:
        """Create a new conversation thread"""
        return type("AgentThread", (), {"messages": []})()

    async def run(
        self, messages: list[ChatMessage] | None = None, *, thread: AgentThread | None = None, **kwargs
    ) -> AgentRunResponse:
        """Echo back the user's messages"""
        if thread is None:
            thread = self.get_new_thread()

        # Add incoming messages to thread
        if messages:
            for message in messages:
                thread.messages.append(message)

            # Get the last user message
            last_message = messages[-1]
            echo_content = f"Echo: {last_message.text}"
        else:
            echo_content = "Echo: (no message)"

        # Create response message
        response_message = ChatMessage(role=ChatRole.ASSISTANT, text=echo_content)

        # Add to thread
        thread.messages.append(response_message)

        return AgentRunResponse(messages=[response_message])
