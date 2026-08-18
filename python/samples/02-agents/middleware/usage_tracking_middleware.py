# Copyright (c) Microsoft. All rights reserved.

"""
This sample demonstrates a single chat middleware that tracks per-model-call usage
for both non-streaming and streaming tool-loop runs.
"""

import asyncio
from collections.abc import Awaitable, Callable
from random import randint
from typing import Annotated

from agent_framework import (
    Agent,
    ChatContext,
    ChatResponse,
    ChatResponseUpdate,
    ResponseStream,
    chat_middleware,
    tool,
)
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()


NON_STREAMING_CALL_COUNT = 0
STREAMING_CALL_COUNT = 0


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/02-agents/tools/function_tool_with_approval.py
# and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


def _reset_usage_counters() -> None:
    """Reset call counters between sample runs."""
    global NON_STREAMING_CALL_COUNT, STREAMING_CALL_COUNT
    NON_STREAMING_CALL_COUNT = 0
    STREAMING_CALL_COUNT = 0


def _create_agent() -> Agent:
    """Create the shared agent used by both demonstrations."""
    return Agent(
        client=OpenAIChatClient(),
        instructions=(
            "You are a weather assistant. Always call the weather tool before answering weather questions, "
            "then summarize the tool result in one short paragraph."
        ),
        tools=[get_weather],
        middleware=[print_usage],
    )


@chat_middleware
async def print_usage(
    context: ChatContext,
    call_next: Callable[[], Awaitable[None]],
) -> None:
    """Print usage for each inner model call in both non-streaming and streaming runs."""
    global NON_STREAMING_CALL_COUNT, STREAMING_CALL_COUNT

    if context.stream:
        STREAMING_CALL_COUNT += 1
        call_number = STREAMING_CALL_COUNT
        usage_seen_in_updates = False

        def capture_usage_update(update: ChatResponseUpdate) -> ChatResponseUpdate:
            nonlocal usage_seen_in_updates

            for content in update.contents:
                if content.type == "usage":
                    usage_seen_in_updates = True
                    print(f"\n[Streaming model call #{call_number}] Usage update: {content.usage_details}")
            return update

        def capture_final_usage(result: ChatResponse) -> ChatResponse:
            if not usage_seen_in_updates and result.usage_details:
                print(f"\n[Streaming model call #{call_number}] Final usage: {result.usage_details}")
            return result

        context.stream_transform_hooks.append(capture_usage_update)
        context.stream_result_hooks.append(capture_final_usage)
        await call_next()
        return

    NON_STREAMING_CALL_COUNT += 1
    call_number = NON_STREAMING_CALL_COUNT

    await call_next()

    response = context.result
    if isinstance(response, ChatResponse) and response.usage_details:
        print(f"[Non-streaming model call #{call_number}] Usage: {response.usage_details}")


async def non_streaming_usage_example() -> None:
    """Run the non-streaming usage tracking example."""
    _reset_usage_counters()
    print("\n=== Non-streaming per-call usage tracking ===")

    # 1. Create an agent with middleware that prints usage after each inner model call.
    agent = _create_agent()

    # 2. Run a weather question and require a tool call so the function loop performs multiple model calls.
    query = "What is the weather in Seattle, and should I bring an umbrella?"
    print(f"User: {query}")
    result = await agent.run(
        query,
        options={"tool_choice": "required"},
    )

    # 3. Print the final user-visible answer after the middleware already logged per-call usage.
    print(f"Assistant: {result.text}")


async def streaming_usage_example() -> None:
    """Run the streaming usage tracking example."""
    _reset_usage_counters()
    print("\n=== Streaming per-call usage tracking ===")

    # 1. Create an agent with middleware that watches streaming usage for each inner model call.
    agent = _create_agent()

    # 2. Start a streaming run and force tool usage so the function loop performs multiple model calls.
    query = "What is the weather in Portland, and should I bring a jacket?"
    print(f"User: {query}")
    print("Assistant: ", end="", flush=True)
    stream: ResponseStream = agent.run(
        query,
        stream=True,
        options={"tool_choice": "required"},
    )

    # 3. Consume the stream normally while the middleware reports usage in the background.
    async for update in stream:
        if update.text:
            print(update.text, end="", flush=True)
    print()

    # 4. Finalize the stream so you can inspect the final response if needed.
    final_response = await stream.get_final_response()
    print(f"Final assistant message: {final_response.text}")


async def main() -> None:
    """Run both usage tracking demonstrations."""
    print("=== Usage Tracking Middleware Example ===")

    await non_streaming_usage_example()
    await streaming_usage_example()


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
=== Usage Tracking Middleware Example ===

=== Non-streaming per-call usage tracking ===
User: What is the weather in Seattle, and should I bring an umbrella?
[Non-streaming model call #1] Usage: {'input_tokens': ..., 'output_tokens': ..., ...}
[Non-streaming model call #2] Usage: {'input_tokens': ..., 'output_tokens': ..., ...}
Assistant: Based on the weather in Seattle, ...

=== Streaming per-call usage tracking ===
User: What is the weather in Portland, and should I bring a jacket?
Assistant: Based on the weather in Portland, ...
[Streaming model call #1] Usage update: {'input_tokens': ..., 'output_tokens': ..., ...}
[Streaming model call #2] Usage update: {'input_tokens': ..., 'output_tokens': ..., ...}
Final assistant message: Based on the weather in Portland, ...
"""
