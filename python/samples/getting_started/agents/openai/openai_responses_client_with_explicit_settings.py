# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework.openai import OpenAIResponsesClient
from pydantic import Field

"""
OpenAI Responses Client with Explicit Settings Example

This sample demonstrates creating OpenAI Responses Client with explicit configuration
settings rather than relying on environment variable defaults.
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    print("=== OpenAI Responses Client with Explicit Settings ===")

    agent = OpenAIResponsesClient(
        model_id=os.environ["OPENAI_RESPONSES_MODEL_ID"],
        api_key=os.environ["OPENAI_API_KEY"],
    ).create_agent(
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    result = await agent.run("What's the weather like in New York?")
    print(f"Result: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
