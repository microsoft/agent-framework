# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework import ChatClientAgent
from agent_framework.foundry import FoundryChatClient
from dotenv import load_dotenv
from pydantic import Field


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    print("=== Basic Foundry Chat Client Example ===")

    # Since no Agent ID is provided, the agent will be automatically created
    # and deleted after getting a response
    async with ChatClientAgent(
        chat_client=FoundryChatClient(),
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    ) as agent:
        result = await agent.run("What's the weather like in Seattle?")
        print(f"Result: {result}\n")


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
