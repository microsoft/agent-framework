# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import ChatClientAgent
from agent_framework.foundry import FoundryChatClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential
from pydantic import Field


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    print("=== Foundry Chat Client with Existing Agent ===")

    # Create the client
    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential) as client,
    ):
        # Create an agent that will persist
        created_agent = await client.agents.create_agent(
            model=os.environ["FOUNDRY_MODEL_DEPLOYMENT_NAME"], name="WeatherAgent"
        )

        try:
            async with ChatClientAgent(
                # passing in the client is optional here, so if you take the agent_id from the portal
                # you can use it directly without the two lines above.
                chat_client=FoundryChatClient(client=client, agent_id=created_agent.id),
                instructions="You are a helpful weather agent.",
                tools=get_weather,
            ) as agent:
                result = await agent.run("What's the weather like in Tokyo?")
                print(f"Result: {result}\n")
        finally:
            # Clean up the agent manually
            await client.agents.delete_agent(created_agent.id)


if __name__ == "__main__":
    asyncio.run(main())
