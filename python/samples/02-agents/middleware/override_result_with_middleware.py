# Copyright (c) Microsoft. All rights reserved.

import asyncio
import re
from collections.abc import Awaitable, Callable, Sequence
from random import randint
from typing import Annotated

from agent_framework import (
    Agent,
    AgentContext,
    AgentResponse,
    AgentResponseUpdate,
    ChatContext,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    tool,
)
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

"""
Result Override with MiddlewareTypes (Regular and Streaming)

This sample demonstrates how to use middleware to intercept and modify function results
after execution, supporting both regular and streaming agent responses. The example shows:

- How to execute the original function first and then modify its result
- Replacing function outputs with custom messages or transformed data
- Using middleware for result filtering, formatting, or enhancement
- Detecting streaming vs non-streaming execution using context.stream
- Overriding streaming results with result transforms and buffered re-derivation

The weather override middleware lets the original weather function execute normally,
then replaces its result with a custom "perfect weather" message. For streaming responses,
it buffers the existing ResponseStream and derives released updates from the replacement result.
"""


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


def _chat_response_to_updates(response: ChatResponse) -> Sequence[ChatResponseUpdate]:
    """Convert a replacement chat response into buffered release updates."""
    return [ChatResponseUpdate(contents=list(message.contents), role="assistant") for message in response.messages]


async def weather_override_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
    """Chat middleware that overrides weather results for both streaming and non-streaming cases."""
    chunks = [
        "due to special atmospheric conditions, ",
        "all locations are experiencing perfect weather today! ",
        "Temperature is a comfortable 22°C with gentle breezes. ",
        "Perfect day for outdoor activities!",
    ]

    if context.stream:
        replacement = ChatResponse(
            messages=[
                Message(role="assistant", contents=[f"Weather Advisory: [{i}] {chunk_text}"])
                for i, chunk_text in enumerate(chunks)
            ]
        )
        context.stream_result_transforms.append(lambda _: replacement)
        context.stream_buffer_updates = True
        context.stream_result_to_updates = _chat_response_to_updates
        await call_next()
        return

    # Non-streaming middleware updates the concrete result after it exists.
    await call_next()
    if context.result is not None:
        current_text = context.result.text if isinstance(context.result, ChatResponse) else ""
        custom_message = f"Weather Advisory: [0] {''.join(chunks)} Original message was: {current_text}"
        context.result = ChatResponse(messages=[Message(role="assistant", contents=[custom_message])])


async def validate_weather_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
    """Chat middleware that simulates result validation for both streaming and non-streaming cases."""
    validation_note = "Validation: weather data verified."

    if context.stream:

        def _append_validation(response: ChatResponse) -> ChatResponse:
            response.messages.append(Message(role="assistant", contents=[validation_note]))
            return response

        context.stream_result_transforms.append(_append_validation)
        context.stream_buffer_updates = True
        context.stream_result_to_updates = _chat_response_to_updates
        await call_next()
        return

    await call_next()
    if isinstance(context.result, ChatResponse):
        context.result.messages.append(Message(role="assistant", contents=[validation_note]))


async def agent_cleanup_middleware(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
    """Agent middleware that validates chat middleware effects and cleans the result."""
    validation_note = "Validation: weather data verified."
    state = {"found_prefix": False, "found_validation": False}

    def _sanitize(response: AgentResponse) -> AgentResponse:
        found_prefix = state["found_prefix"]
        found_validation = state["found_validation"]
        cleaned_messages: list[Message] = []

        for message in response.messages:
            text = message.text
            if text is None:
                cleaned_messages.append(message)
                continue

            if validation_note in text:
                found_validation = True
                text = text.replace(validation_note, "").strip()
                if not text:
                    continue

            if "Weather Advisory:" in text:
                found_prefix = True
                text = text.replace("Weather Advisory:", "")

            text = re.sub(r"\[\d+\]\s*", "", text).strip()
            if not text:
                continue

            cleaned_messages.append(
                Message(
                    role=message.role,
                    contents=[text],
                    author_name=message.author_name,
                    message_id=message.message_id,
                    additional_properties=message.additional_properties,
                    raw_representation=message.raw_representation,
                )
            )

        if not found_prefix:
            raise RuntimeError("Expected chat middleware prefix not found in agent response.")
        if not found_validation:
            raise RuntimeError("Expected validation note not found in agent response.")

        cleaned_messages.append(Message(role="assistant", contents=[" Agent: OK"]))
        response.messages = cleaned_messages
        return response

    def _clean_update(update: AgentResponseUpdate) -> AgentResponseUpdate:
        cleaned_contents: list[Content] = []

        for content in update.contents or []:
            if not content.text:
                cleaned_contents.append(content)
                continue
            text = content.text
            if "Weather Advisory:" in text:
                state["found_prefix"] = True
                text = text.replace("Weather Advisory:", "")
            if validation_note in text:
                state["found_validation"] = True
                text = text.replace(validation_note, "").strip()
                if not text:
                    continue
            text = re.sub(r"\[\d+\]\s*", "", text)
            content.text = text
            cleaned_contents.append(content)

        update.contents = cleaned_contents
        return update

    if context.stream:
        context.stream_update_transforms.append(_clean_update)
        context.stream_result_transforms.append(_sanitize)
        await call_next()
        return

    await call_next()
    if isinstance(context.result, AgentResponse):
        context.result = _sanitize(context.result)


async def main() -> None:
    """Example demonstrating result override with middleware for both streaming and non-streaming."""
    print("=== Result Override MiddlewareTypes Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    agent = Agent(
        client=OpenAIChatClient(
            middleware=[validate_weather_middleware, weather_override_middleware],
        ),
        name="WeatherAgent",
        instructions="You are a helpful weather assistant. Use the weather tool to get current conditions.",
        tools=get_weather,
        middleware=[agent_cleanup_middleware],
    )
    # Non-streaming example
    print("\n--- Non-streaming Example ---")
    query = "What's the weather like in Seattle?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}")

    # Streaming example
    print("\n--- Streaming Example ---")
    query = "What's the weather like in Portland?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    response = agent.run(query, stream=True)
    async for chunk in response:
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")
    print(f"Final Result: {(await response.get_final_response()).text}")


if __name__ == "__main__":
    asyncio.run(main())
