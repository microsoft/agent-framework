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
        super().__init__(name=name, description=description, echo_prefix=echo_prefix, **kwargs)

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
                contents=[TextContent(text="Hello! I'm a custom echo agent. Send me a message and I'll echo it back.")]
            )
        else:
            # For simplicity, echo the last user message
            last_message = normalized_messages[-1]
            if last_message.text:
                echo_text = f"{self.echo_prefix}{last_message.text}"
            else:
                echo_text = f"{self.echo_prefix}[Non-text message received]"
            
            response_message = ChatMessage(
                role=Role.ASSISTANT,
                contents=[TextContent(text=echo_text)]
            )

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
            complete_response = ChatMessage(
                role=Role.ASSISTANT,
                contents=[TextContent(text=response_text)]
            )
            await self._notify_thread_of_new_messages(thread, complete_response)


class ReversalAgent(BaseAgent):
    """A custom agent that reverses user input text.
    
    This demonstrates another custom agent implementation with different behavior.
    """

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        """Execute the agent and return a complete response with reversed text.

        Args:
            messages: The message(s) to process.
            thread: The conversation thread (optional).
            **kwargs: Additional keyword arguments.

        Returns:
            An AgentRunResponse containing the reversed text.
        """
        # Normalize input messages to a list
        normalized_messages = self._normalize_messages(messages)
        
        if not normalized_messages:
            response_text = "Send me some text and I'll reverse it for you!"
        else:
            # Reverse the text of the last user message
            last_message = normalized_messages[-1]
            if last_message.text:
                response_text = f"Reversed: {last_message.text[::-1]}"
            else:
                response_text = "I can only reverse text messages."

        response_message = ChatMessage(
            role=Role.ASSISTANT,
            contents=[TextContent(text=response_text)]
        )

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
        """Execute the agent and yield streaming response updates with reversed text.

        Args:
            messages: The message(s) to process.
            thread: The conversation thread (optional).
            **kwargs: Additional keyword arguments.

        Yields:
            AgentRunResponseUpdate objects containing chunks of the response.
        """
        # For the streaming version, we'll get the complete response first
        # and then stream it character by character
        response = await self.run(messages, thread=thread, **kwargs)
        
        if response.messages:
            response_text = response.messages[0].text or ""
            
            # Stream the response character by character
            for char in response_text:
                yield AgentRunResponseUpdate(
                    contents=[TextContent(text=char)],
                    role=Role.ASSISTANT,
                )
                await asyncio.sleep(0.05)  # Small delay for streaming effect


async def main() -> None:
    """Demonstrates how to use custom agents."""
    print("=== Custom Agent Examples ===\n")

    # Example 1: EchoAgent
    print("--- EchoAgent Example ---")
    echo_agent = EchoAgent(
        name="EchoBot",
        description="A simple agent that echoes messages with a prefix",
        echo_prefix="🔊 Echo: "
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

    # Example 2: ReversalAgent
    print("\n--- ReversalAgent Example ---")
    reversal_agent = ReversalAgent(
        name="TextReverser",
        description="An agent that reverses text messages"
    )
    
    query3 = "Hello World"
    print(f"\nUser: {query3}")
    result = await reversal_agent.run(query3)
    print(f"Agent: {result.messages[0].text}")
    
    # Test streaming reversal
    query4 = "Python is awesome"
    print(f"\nUser: {query4}")
    print("Agent: ", end="", flush=True)
    async for chunk in reversal_agent.run_stream(query4):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print()

    # Example 3: Using with threads
    print("\n--- Using Custom Agent with Thread ---")
    thread = echo_agent.get_new_thread()
    
    # First message
    result1 = await echo_agent.run("First message", thread=thread)
    print(f"User: First message")
    print(f"Agent: {result1.messages[0].text}")
    
    # Second message in same thread
    result2 = await echo_agent.run("Second message", thread=thread)
    print(f"User: Second message")
    print(f"Agent: {result2.messages[0].text}")
    
    # Check conversation history
    if thread.message_store:
        messages = await thread.message_store.list_messages()
        print(f"\nThread contains {len(messages)} messages in history")
    else:
        print(f"\nThread has no message store configured")


if __name__ == "__main__":
    asyncio.run(main())