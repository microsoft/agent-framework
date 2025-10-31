# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework import ChatResponse
from agent_framework_litellm import LiteLlmResponsesClient
from pydantic import BaseModel, Field

"""
LiteLLM Client Direct Usage Example

Demonstrates direct LiteLlmResponsesClient usage for structured response generation with LiteLLM models.
Shows function calling capabilities with custom business logic.
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


class OutputStruct(BaseModel):
    """Structured output for weather information."""

    location: str
    weather: str


async def main() -> None:
    client = LiteLlmResponsesClient()
    message = "What's the weather in Amsterdam and in Paris?"
    stream = True
    print(f"User: {message}")
    if stream:
        response = await ChatResponse.from_chat_response_generator(
            client.get_streaming_response(message, tools=get_weather),
            output_format_type=OutputStruct,
        )
        print(f"Assistant: {response}")

    else:
        response = await client.get_response(message, tools=[])
        print(f"Assistant: {response}")


if __name__ == "__main__":
    asyncio.run(main())
