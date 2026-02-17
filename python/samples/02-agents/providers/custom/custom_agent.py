# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import AsyncIterable
from typing import Any

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseAgent,
    Content,
    InMemoryHistoryProvider,
    Message,
    Role,
    normalize_messages,
)

"""
Custom Agent Implementation Example

This sample demonstrates implementing a custom agent by extending BaseAgent class,
showing the minimal requirements for both streaming and non-streaming responses.
"""


class EchoAgent(BaseAgent):
    """A simple custom agent that echoes user messages with a prefix.

    This demonstrates how to create a fully custom agent by extending BaseAgent
    and implementing the required run() method with stream support.
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

    def run(
        self,
        messages: str | Message | list[str] | list[Message] | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> "AsyncIterable[AgentResponseUpdate] | asyncio.Future[AgentResponse]":
        """Execute the agent and return a response.

        Args:
            messages: The message(s) to process.
            stream: If True, return an async iterable of updates. If False, return an awaitable response.
            session: The conversation session (optional).
            **kwargs: Additional keyword arguments.

        Returns:
            When stream=False: An awaitable AgentResponse containing the agent's reply.
            When stream=True: An async iterable of AgentResponseUpdate objects.
        """
        if stream:
            return self._run_stream(messages=messages, session=session, **kwargs)
        return self._run(messages=messages, session=session, **kwargs)

    async def _run(
        self,
        messages: str | Message | list[str] | list[Message] | None = None,
        *,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """Non-streaming implementation."""
        # Normalize input messages to a list
        normalized_messages = normalize_messages(messages)

        if not normalized_messages:
            response_message = Message(
                role=Role.ASSISTANT,
                contents=[
                    Content.from_text(text="Hello! I'm a custom echo agent. Send me a message and I'll echo it back.")
                ],
            )
        else:
            # For simplicity, echo the last user message
            last_message = normalized_messages[-1]
            if last_message.text:
                echo_text = f"{self.echo_prefix}{last_message.text}"
            else:
                echo_text = f"{self.echo_prefix}[Non-text message received]"

            response_message = Message(role=Role.ASSISTANT, contents=[Content.from_text(text=echo_text)])

        # Store messages in session state if provided
        if session is not None:
            stored = session.state.setdefault("memory", {}).setdefault("messages", [])
            stored.extend(normalized_messages)
            stored.append(response_message)

        return AgentResponse(messages=[response_message])

    async def _run_stream(
        self,
        messages: str | Message | list[str] | list[Message] | None = None,
        *,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentResponseUpdate]:
        """Streaming implementation."""
        # Normalize input messages to a list
        normalized_messages = normalize_messages(messages)

        if not normalized_messages:
            response_text = "Hello! I'm a custom echo agent. Send me a message and I'll echo it back."
        else:
            # For simplicity, echo the last user message
            last_message = normalized_messages[-1]
            if last_message.text:
                response_text = f"{self.echo_prefix}{last_message.text}"
            else:
                response_text = f"{self.echo_prefix}[Non-text message received]"

        # Simulate streaming by yielding the response word by word
        words = response_text.split()
        for i, word in enumerate(words):
            # Add space before word except for the first one
            chunk_text = f" {word}" if i > 0 else word

            yield AgentResponseUpdate(
                contents=[Content.from_text(text=chunk_text)],
                role=Role.ASSISTANT,
            )

            # Small delay to simulate streaming
            await asyncio.sleep(0.1)

        # Store messages in session state if provided
        if session is not None:
            complete_response = Message(role=Role.ASSISTANT, contents=[Content.from_text(text=response_text)])
            stored = session.state.setdefault("memory", {}).setdefault("messages", [])
            stored.extend(normalized_messages)
            stored.append(complete_response)


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

    query = "Hello, custom agent!"
    print(f"\nUser: {query}")
    result = await echo_agent.run(query)
    print(f"Agent: {result.messages[0].text}")

    # Test streaming
    query2 = "This is a streaming test"
    print(f"\nUser: {query2}")
    print("Agent: ", end="", flush=True)
    async for chunk in echo_agent.run(query2, stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print()

    # Example with sessions
    print("\n--- Using Custom Agent with Session ---")
    session = echo_agent.create_session()

    # First message
    result1 = await echo_agent.run("First message", session=session)
    print("User: First message")
    print(f"Agent: {result1.messages[0].text}")

    # Second message in same thread
    result2 = await echo_agent.run("Second message", session=session)
    print("User: Second message")
    print(f"Agent: {result2.messages[0].text}")

    # Check conversation history
    memory_state = session.state.get(InMemoryHistoryProvider.DEFAULT_SOURCE_ID, {})
    messages = memory_state.get("messages", [])
    if messages:
        print(f"\nSession contains {len(messages)} messages in history")
    else:
        print("\nSession has no messages stored")


if __name__ == "__main__":
    asyncio.run(main())
