# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework.openai import OpenAIChatClient
from pydantic import Field

"""
OpenAI Chat Client Direct Usage Example

Demonstrates direct OpenAIChatClient usage for chat interactions with OpenAI models.
Shows function calling capabilities with custom business logic.

"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    client = OpenAIChatClient()
    message = "What's the weather in Amsterdam and in Paris?"
    stream = True
    print(f"User: {message}")
    if stream:
        print("Assistant: ", end="")
        async for chunk in client.get_streaming_response(message, tools=get_weather):
            if chunk.text:
                print(chunk.text, end="")
        print("")
    else:
        response = await client.get_response(message, tools=get_weather)
        print(f"Assistant: {response}")


if __name__ == "__main__":
    asyncio.run(main())
