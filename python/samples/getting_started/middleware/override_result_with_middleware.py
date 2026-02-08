# Copyright (c) Microsoft. All rights reserved.

import asyncio
import re
from collections.abc import Awaitable, Callable
from random import randint
from typing import Annotated

from agent_framework import (
    AgentContext,
    AgentResponse,
    AgentResponseUpdate,
    ChatContext,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    ResponseStream,
    tool,
)
from agent_framework.openai import OpenAIResponsesClient
from pydantic import Field

"""
Result Override with MiddlewareTypes (Regular and Streaming)

This sample demonstrates how to use middleware to intercept and modify function results
after execution, supporting both regular and streaming agent responses. The example shows:

- How to execute the original function first and then modify its result
- Replacing function outputs with custom messages or transformed data
- Using middleware for result filtering, formatting, or enhancement
- Detecting streaming vs non-streaming execution using context.stream
- Overriding streaming results with custom async generators

The weather override middleware lets the original weather function execute normally,
then replaces its result with a custom "perfect weather" message. For streaming responses,
it creates a custom async generator that yields the override message in chunks.
"""


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def weather_override_middleware(context: ChatContext, next: Callable[[ChatContext], Awaitable[None]]) -> None:
    """Chat middleware that overrides weather results for both streaming and non-streaming cases."""

    # Let the original agent execution complete first
    await next(context)

    # Check if there's a result to override (agent called weather function)
    if context.result is not None:
        # Create custom weather message
        chunks = [
            "due to special atmospheric conditions, ",
            "all locations are experiencing perfect weather today! ",
            "Temperature is a comfortable 22°C with gentle breezes. ",
            "Perfect day for outdoor activities!",
        ]

        if context.stream and isinstance(context.result, ResponseStream):
            index = {"value": 0}

            def _update_hook(update: ChatResponseUpdate) -> ChatResponseUpdate:
                for content in update.contents or []:
                    if not content.text:
                        continue
                    content.text = f"Weather Advisory: [{index['value']}] {content.text}"
                    index["value"] += 1
                return update

            context.result.with_transform_hook(_update_hook)
        else:
            # For non-streaming: just replace with a new message
            current_text = context.result.text or ""  # type: ignore
            custom_message = f"Weather Advisory: [0] {''.join(chunks)} Original message was: {current_text}"
            context.result = ChatResponse(messages=[ChatMessage(role="assistant", text=custom_message)])


async def validate_weather_middleware(context: ChatContext, next: Callable[[ChatContext], Awaitable[None]]) -> None:
    """Chat middleware that simulates result validation for both streaming and non-streaming cases."""
    await next(context)

    validation_note = "Validation: weather data verified."

    if context.result is None:
        return

    if context.stream and isinstance(context.result, ResponseStream):

        def _append_validation_note(response: ChatResponse) -> ChatResponse:
            response.messages.append(ChatMessage(role="assistant", text=validation_note))
            return response

        context.result.with_result_hook(_append_validation_note)
    elif isinstance(context.result, ChatResponse):
        context.result.messages.append(ChatMessage(role="assistant", text=validation_note))


async def agent_cleanup_middleware(context: AgentContext, next: Callable[[AgentContext], Awaitable[None]]) -> None:
    """Agent middleware that validates chat middleware effects and cleans the result."""
    await next(context)

    if context.result is None:
        return

    validation_note = "Validation: weather data verified."

    state = {"found_prefix": False}

    def _sanitize(response: AgentResponse) -> AgentResponse:
        found_prefix = state["found_prefix"]
        found_validation = False
        cleaned_messages: list[ChatMessage] = []

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

            text = re.sub(r"\[\d+\]\s*", "", text)

            cleaned_messages.append(
                ChatMessage(
                    role=message.role,
                    text=text.strip(),
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

        cleaned_messages.append(ChatMessage(role="assistant", text=" Agent: OK"))
        response.messages = cleaned_messages
        return response

    if context.stream and isinstance(context.result, ResponseStream):

        def _clean_update(update: AgentResponseUpdate) -> AgentResponseUpdate:
            for content in update.contents or []:
                if not content.text:
                    continue
                text = content.text
                if "Weather Advisory:" in text:
                    state["found_prefix"] = True
                    text = text.replace("Weather Advisory:", "")
                text = re.sub(r"\[\d+\]\s*", "", text)
                content.text = text
            return update

        context.result.with_transform_hook(_clean_update)
        context.result.with_result_hook(_sanitize)
    elif isinstance(context.result, AgentResponse):
        context.result = _sanitize(context.result)


async def main() -> None:
    """Example demonstrating result override with middleware for both streaming and non-streaming."""
    print("=== Result Override MiddlewareTypes Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    agent = OpenAIResponsesClient(
        middleware=[validate_weather_middleware, weather_override_middleware],
    ).as_agent(
        name="WeatherAgent",
        instructions="You are a helpful weather assistant. Use the weather tool to get current conditions.",
        tools=get_weather,
        middleware=[agent_cleanup_middleware],
    )
    # Streaming example
    print("\n--- Streaming Example ---")
    query = "What's the weather like in Portland?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    response = agent.run(query, stream=True)
    # add the hooks to print what you want to see
    response.with_transform_hook(lambda chunk: print(chunk.text, end="", flush=True)).with_result_hook(
        lambda final: print(f"\nFinal streamed response: {final.text}", flush=True)
    )
    # consume the stream to trigger the hooks
    await response.get_final_response()

    # Non-streaming example
    print("\n--- Non-streaming Example ---")
    query = "What's the weather like in Seattle?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}")


if __name__ == "__main__":
    asyncio.run(main())
