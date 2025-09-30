# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework.openai import OpenAIAssistantsClient
from pydantic import Field

"""
OpenAI Assistants Client Direct Usage Example

This sample demonstrates direct usage of OpenAIAssistantsClient for chat
interactions with OpenAI assistants without agent orchestration. The example includes:

- Direct assistants client instantiation with OpenAI API
- Function calling capabilities with custom business logic
- Automatic assistant creation and management
- Type-safe function definitions with Pydantic
- Simple OpenAI API key authentication

Direct assistants client usage provides access to OpenAI's advanced
assistant capabilities with minimal setup, ideal for applications requiring
persistent assistants with function calling without complex agent workflows.
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    async with OpenAIAssistantsClient() as client:
        message = "What's the weather in Amsterdam and in Paris?"
        stream = False
        print(f"User: {message}")
        if stream:
            print("Assistant: ", end="")
            async for chunk in client.get_streaming_response(message, tools=get_weather):
                if str(chunk):
                    print(str(chunk), end="")
            print("")
        else:
            response = await client.get_response(message, tools=get_weather)
            print(f"Assistant: {response}")


if __name__ == "__main__":
    asyncio.run(main())
