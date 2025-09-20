# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import AsyncIterable
from typing import Any

from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    BaseAgent,
    ChatMessage,
    Role,
    TextContent,
)

"""
Custom Agent Implementation Example

This sample demonstrates how to implement a custom agent by extending the BaseAgent class.
Custom agents provide complete control over the agent's behavior and capabilities, allowing
developers to create specialized agents that don't rely on chat clients.

This approach is useful when you need to:
- Implement agents with custom logic that doesn't involve LLM interactions
- Create agents that integrate with specialized APIs or services
- Build agents with deterministic behaviors
- Implement new agent types for the Microsoft Agent Framework

The EchoAgent example shows the minimal requirements for implementing a custom agent,
including both streaming and non-streaming response handling.
"""


class EchoAgent(BaseAgent):
    """A simple custom agent that echoes user messages with a prefix.

    This demonstrates how to create a fully custom agent by extending BaseAgent
    and implementing the required run() and run_stream() methods.
    """

    echo_prefix: str = "Echo: "

    def __init__(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        echo_prefix: str = "Echo: ",
        **kwargs: Any,
    ) -> None:
        """Initialize the EchoAgent.

        Args:
            name: The name of the agent.
            description: The description of the agent.
            echo_prefix: The prefix to add to echoed messages.
            **kwargs: Additional keyword arguments passed to BaseAgent.
        """
        super().__init__(
            name=name,
            description=description,
            echo_prefix=echo_prefix,  # type: ignore
            **kwargs,
        )

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        """Execute the agent and return a complete response.

        Args:
            messages: The message(s) to process.
            thread: The conversation thread (optional).
            **kwargs: Additional keyword arguments.

        Returns:
            An AgentRunResponse containing the agent's reply.
        """
        # Normalize input messages to a list
        normalized_messages = self._normalize_messages(messages)

        if not normalized_messages:
            response_message = ChatMessage(
                role=Role.ASSISTANT,
                contents=[TextContent(text="Hello! I'm a custom echo agent. Send me a message and I'll echo it back.")],
            )
        else:
            # For simplicity, echo the last user message
            last_message = normalized_messages[-1]
            if last_message.text:
                echo_text = f"{self.echo_prefix}{last_message.text}"
            else:
                echo_text = f"{self.echo_prefix}[Non-text message received]"

            response_message = ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text=echo_text)])

        # Notify the thread of new messages if provided
        if thread is not None:
            await self._notify_thread_of_new_messages(thread, normalized_messages)
            await self._notify_thread_of_new_messages(thread, response_message)

        return AgentRunResponse(messages=[response_message])

    async def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Execute the agent and yield streaming response updates.

        Args:
            messages: The message(s) to process.
            thread: The conversation thread (optional).
            **kwargs: Additional keyword arguments.

        Yields:
            AgentRunResponseUpdate objects containing chunks of the response.
        """
        # Normalize input messages to a list
        normalized_messages = self._normalize_messages(messages)

        if not normalized_messages:
            response_text = "Hello! I'm a custom echo agent. Send me a message and I'll echo it back."
        else:
            # For simplicity, echo the last user message
            last_message = normalized_messages[-1]
            if last_message.text:
                response_text = f"{self.echo_prefix}{last_message.text}"
            else:
                response_text = f"{self.echo_prefix}[Non-text message received]"

        # Notify the thread of input messages if provided
        if thread is not None:
            await self._notify_thread_of_new_messages(thread, normalized_messages)

        # Simulate streaming by yielding the response word by word
        words = response_text.split()
        for i, word in enumerate(words):
            # Add space before word except for the first one
            chunk_text = f" {word}" if i > 0 else word

            yield AgentRunResponseUpdate(
                contents=[TextContent(text=chunk_text)],
                role=Role.ASSISTANT,
            )

            # Small delay to simulate streaming
            await asyncio.sleep(0.1)

        # Notify the thread of the complete response if provided
        if thread is not None:
            complete_response = ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text=response_text)])
            await self._notify_thread_of_new_messages(thread, complete_response)


async def main() -> None:
    """Demonstrates how to use the custom EchoAgent."""
    print("=== Custom Agent Example ===\n")

    # Create EchoAgent
    print("--- EchoAgent Example ---")
    echo_agent = EchoAgent(
        name="EchoBot", description="A simple agent that echoes messages with a prefix", echo_prefix="🔊 Echo: "
    )

    # Test non-streaming
    print(f"Agent Name: {echo_agent.name}")
    print(f"Agent ID: {echo_agent.id}")
    print(f"Display Name: {echo_agent.display_name}")

    query = "Hello, custom agent!"
    print(f"\nUser: {query}")
    result = await echo_agent.run(query)
    print(f"Agent: {result.messages[0].text}")

    # Test streaming
    query2 = "This is a streaming test"
    print(f"\nUser: {query2}")
    print("Agent: ", end="", flush=True)
    async for chunk in echo_agent.run_stream(query2):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print()

    # Example with threads
    print("\n--- Using Custom Agent with Thread ---")
    thread = echo_agent.get_new_thread()

    # First message
    result1 = await echo_agent.run("First message", thread=thread)
    print("User: First message")
    print(f"Agent: {result1.messages[0].text}")

    # Second message in same thread
    result2 = await echo_agent.run("Second message", thread=thread)
    print("User: Second message")
    print(f"Agent: {result2.messages[0].text}")

    # Check conversation history
    if thread.message_store:
        messages = await thread.message_store.list_messages()
        print(f"\nThread contains {len(messages)} messages in history")
    else:
        print("\nThread has no message store configured")


if __name__ == "__main__":
    asyncio.run(main())
