# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import ChatClientAgent
from agent_framework.foundry import FoundryChatClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    load_dotenv()
    instructions = "You are a helpful assistant, you can help the user with weather information."

    client = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=AzureCliCredential())

    created_agent = await client.agents.create_agent(
        model=os.environ["FOUNDRY_MODEL_DEPLOYMENT_NAME"], name="WeatherAgent"
    )

    agent = ChatClientAgent(
        FoundryChatClient(client=client, agent_id=created_agent.id),
        instructions=instructions,
        tools=get_weather,
    )
    print(str(await agent.run("What's the weather in Amsterdam?")))


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
