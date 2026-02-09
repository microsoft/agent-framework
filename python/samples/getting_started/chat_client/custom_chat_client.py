# Copyright (c) Microsoft. All rights reserved.

import asyncio
import random
import sys
from collections.abc import AsyncIterable, Awaitable, Mapping, Sequence
from typing import Any, ClassVar, Generic

from agent_framework import (
    BaseChatClient,
    ChatMessage,
    ChatMiddlewareLayer,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationLayer,
    ResponseStream,
    Role,
)
from agent_framework._clients import TOptions_co
from agent_framework.observability import ChatTelemetryLayer

if sys.version_info >= (3, 13):
    pass
else:
    pass
if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover


"""
Custom Chat Client Implementation Example

This sample demonstrates implementing a custom chat client and optionally composing
middleware, telemetry, and function invocation layers explicitly.
"""


class EchoingChatClient(BaseChatClient[TOptions_co], Generic[TOptions_co]):
    """A custom chat client that echoes messages back with modifications.

    This demonstrates how to implement a custom chat client by extending BaseChatClient
    and implementing the required _inner_get_response() method.
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "EchoingChatClient"

    def __init__(self, *, prefix: str = "Echo:", **kwargs: Any) -> None:
        """Initialize the EchoingChatClient.

        Args:
            prefix: Prefix to add to echoed messages.
            **kwargs: Additional keyword arguments passed to BaseChatClient.
        """
        super().__init__(**kwargs)
        self.prefix = prefix

    @override
    def _inner_get_response(
        self,
        *,
        messages: Sequence[ChatMessage],
        stream: bool = False,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
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

        response_message = ChatMessage(role=Role.ASSISTANT, contents=[Content.from_text(response_text)])

        response = ChatResponse(
            messages=[response_message],
            model_id="echo-model-v1",
            response_id=f"echo-resp-{random.randint(1000, 9999)}",
        )

        if not stream:

            async def _get_response() -> ChatResponse:
                return response

            return _get_response()

        async def _stream() -> AsyncIterable[ChatResponseUpdate]:
            response_text_local = response_message.text or ""
            for char in response_text_local:
                yield ChatResponseUpdate(
                    contents=[Content.from_text(char)],
                    role=Role.ASSISTANT,
                    response_id=f"echo-stream-resp-{random.randint(1000, 9999)}",
                    model_id="echo-model-v1",
                )
                await asyncio.sleep(0.05)

        return ResponseStream(_stream(), finalizer=lambda updates: response)


class EchoingChatClientWithLayers(  # type: ignore[misc,type-var]
    ChatMiddlewareLayer[TOptions_co],
    ChatTelemetryLayer[TOptions_co],
    FunctionInvocationLayer[TOptions_co],
    EchoingChatClient[TOptions_co],
    Generic[TOptions_co],
):
    """Echoing chat client that explicitly composes middleware, telemetry, and function layers."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "EchoingChatClientWithLayers"


async def main() -> None:
    """Demonstrates how to implement and use a custom chat client with ChatAgent."""
    print("=== Custom Chat Client Example ===\n")

    # Create the custom chat client
    print("--- EchoingChatClient Example ---")

    echo_client = EchoingChatClientWithLayers(prefix="🔊 Echo:")

    # Use the chat client directly
    print("Using chat client directly:")
    direct_response = await echo_client.get_response("Hello, custom chat client!")
    print(f"Direct response: {direct_response.messages[0].text}")

    # Create an agent using the custom chat client
    echo_agent = echo_client.as_agent(
        name="EchoAgent",
        instructions="You are a helpful assistant that echoes back what users say.",
    )

    print(f"\nAgent Name: {echo_agent.name}")

    # Test non-streaming with agent
    query = "This is a test message"
    print(f"\nUser: {query}")
    result = await echo_agent.run(query)
    print(f"Agent: {result.messages[0].text}")

    # Test streaming with agent
    query2 = "Stream this message back to me"
    print(f"\nUser: {query2}")
    print("Agent: ", end="", flush=True)
    async for chunk in echo_agent.run(query2, stream=True):
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
