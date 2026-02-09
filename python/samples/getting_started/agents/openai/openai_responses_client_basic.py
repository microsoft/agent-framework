# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Awaitable, Callable
from random import randint
from typing import Annotated

from agent_framework import (
    ChatAgent,
    ChatContext,
    ChatMessage,
    ChatResponse,
    MiddlewareTermination,
    chat_middleware,
    tool,
)
from agent_framework.openai import OpenAIResponsesClient
from pydantic import Field

"""
OpenAI Responses Client Basic Example

This sample demonstrates basic usage of OpenAIResponsesClient for structured
response generation, showing both streaming and non-streaming responses.
"""


@chat_middleware
async def security_and_override_middleware(
    context: ChatContext,
    next: Callable[[ChatContext], Awaitable[None]],
) -> None:
    """Function-based middleware that implements security filtering and response override."""
    print("[SecurityMiddleware] Processing input...")

    # Security check - block sensitive information
    blocked_terms = ["password", "secret", "api_key", "token"]

    for message in context.messages:
        if message.text:
            message_lower = message.text.lower()
            for term in blocked_terms:
                if term in message_lower:
                    print(f"[SecurityMiddleware] BLOCKED: Found '{term}' in message")

                    # Override the response instead of calling AI
                    context.result = ChatResponse(
                        messages=[
                            ChatMessage(
                                role="assistant",
                                text="I cannot process requests containing sensitive information. "
                                "Please rephrase your question without including passwords, secrets, or other "
                                "sensitive data.",
                            )
                        ]
                    )

                    # Set terminate flag to stop execution
                    raise MiddlewareTermination

    # Continue to next middleware or AI execution
    await next(context)

    print("[SecurityMiddleware] Response generated.")
    print(type(context.result))


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def non_streaming_example() -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    agent = ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    query = "What's the weather like in Seattle?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Result: {result}\n")


async def streaming_example() -> None:
    """Example of streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    agent = ChatAgent(
        chat_client=OpenAIResponsesClient(
            middleware=[security_and_override_middleware],
        ),
        instructions="You are a helpful weather agent.",
        # tools=get_weather,
    )

    query = "What's the weather like in Portland?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    response = agent.run(query, stream=True)
    async for chunk in response:
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")
    print(f"Final Result: {await response.get_final_response()}")


async def main() -> None:
    print("=== Basic OpenAI Responses Client Agent Example ===")

    await streaming_example()
    await non_streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
