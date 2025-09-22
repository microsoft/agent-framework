# Copyright (c) Microsoft. All rights reserved.

import asyncio
import random
from collections.abc import AsyncIterable, MutableSequence
from typing import Any

from agent_framework import (
    BaseChatClient,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Role,
    TextContent,
    use_function_invocation,
)

"""
Custom Chat Client Implementation Example

This sample demonstrates how to implement a custom chat client by extending the BaseChatClient class.
Custom chat clients allow you to integrate any backend service or create new LLM providers
for the Microsoft Agent Framework.

This approach is useful when you need to:
- Integrate with new or proprietary LLM services
- Create mock implementations for testing
- Add custom authentication or routing logic
- Implement specialized preprocessing or postprocessing of requests and responses
- Create new LLM providers that work seamlessly with the framework's ChatAgent

The EchoingChatClient example shows the minimal requirements for implementing a custom chat client,
including both streaming and non-streaming response handling, and demonstrates how to use the
custom client with ChatAgent through the create_agent() method.
"""


@use_function_invocation
class EchoingChatClient(BaseChatClient):
    """A custom chat client that echoes messages back with modifications.

    This demonstrates how to implement a custom chat client by extending BaseChatClient
    and implementing the required _inner_get_response() and _inner_get_streaming_response() methods.
    """

    OTEL_PROVIDER_NAME: str = "EchoingChatClient"

    prefix: str = "Echo:"

    def __init__(self, *, prefix: str = "Echo:", **kwargs: Any) -> None:
        """Initialize the EchoingChatClient.

        Args:
            prefix: Prefix to add to echoed messages.
            **kwargs: Additional keyword arguments passed to BaseChatClient.
        """
        super().__init__(
            prefix=prefix,  # type: ignore
            **kwargs,
        )

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        """Echo back the user's message with a prefix."""
        if not messages:
            response_text = "No messages to echo!"
        else:
            # Echo the last user message
            last_user_message = None
            for message in reversed(messages):
                if message.role == Role.USER:
                    last_user_message = message
                    break

            if last_user_message and last_user_message.text:
                response_text = f"{self.prefix} {last_user_message.text}"
            else:
                response_text = f"{self.prefix} [No text message found]"

        response_message = ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text=response_text)])

        return ChatResponse(
            messages=[response_message],
            model_id="echo-model-v1",
            response_id=f"echo-resp-{random.randint(1000, 9999)}",
        )

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Stream back the echoed message character by character."""
        # Get the complete response first
        response = await self._inner_get_response(messages=messages, chat_options=chat_options, **kwargs)

        if response.messages:
            response_text = response.messages[0].text or ""

            # Stream character by character
            for char in response_text:
                yield ChatResponseUpdate(
                    contents=[TextContent(text=char)],
                    role=Role.ASSISTANT,
                    response_id=f"echo-stream-resp-{random.randint(1000, 9999)}",
                    ai_model_id="echo-model-v1",
                )
                await asyncio.sleep(0.05)


async def main() -> None:
    """Demonstrates how to implement and use a custom chat client with ChatAgent."""
    print("=== Custom Chat Client Example ===\n")

    # Create the custom chat client
    print("--- EchoingChatClient Example ---")

    echo_client = EchoingChatClient(prefix="🔊 Echo:")

    # Use the chat client directly
    print("Using chat client directly:")
    direct_response = await echo_client.get_response("Hello, custom chat client!")
    print(f"Direct response: {direct_response.messages[0].text}")

    # Create an agent using the custom chat client
    echo_agent = echo_client.create_agent(
        name="EchoAgent",
        instructions="You are a helpful assistant that echoes back what users say.",
    )

    print(f"\nAgent Name: {echo_agent.name}")
    print(f"Agent Display Name: {echo_agent.display_name}")

    # Test non-streaming with agent
    query = "This is a test message"
    print(f"\nUser: {query}")
    result = await echo_agent.run(query)
    print(f"Agent: {result.messages[0].text}")

    # Test streaming with agent
    query2 = "Stream this message back to me"
    print(f"\nUser: {query2}")
    print("Agent: ", end="", flush=True)
    async for chunk in echo_agent.run_stream(query2):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print()

    # Example: Using with threads and conversation history
    print("\n--- Using Custom Chat Client with Thread ---")

    thread = echo_agent.get_new_thread()

    # Multiple messages in conversation
    messages = [
        "Hello, I'm starting a conversation",
        "How are you doing?",
        "Thanks for chatting!",
    ]

    for msg in messages:
        result = await echo_agent.run(msg, thread=thread)
        print(f"User: {msg}")
        print(f"Agent: {result.messages[0].text}\n")

    # Check conversation history
    if thread.message_store:
        thread_messages = await thread.message_store.list_messages()
        print(f"Thread contains {len(thread_messages)} messages")
    else:
        print("Thread has no message store configured")


if __name__ == "__main__":
    asyncio.run(main())
