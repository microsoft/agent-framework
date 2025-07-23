# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework import ChatClientAgent
from agent_framework.azure import AzureChatClient
from pydantic import Field


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    instructions = "You are a helpful assistant, you can help the user with weather information."
    agent = ChatClientAgent(AzureChatClient(), instructions=instructions, tools=get_weather)
    print(str(await agent.run("What's the weather in Amsterdam?")))


if __name__ == "__main__":
    asyncio.run(main())
