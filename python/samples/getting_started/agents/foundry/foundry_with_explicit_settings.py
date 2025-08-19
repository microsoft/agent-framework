# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import ChatClientAgent
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import DefaultAzureCredential
from pydantic import Field


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    print("=== Foundry Chat Client with Explicit Settings ===")

    # Since no Agent ID is provided, the agent will be automatically created
    # and deleted after getting a response
    async with (
        DefaultAzureCredential() as credential,
        ChatClientAgent(
            chat_client=FoundryChatClient(
                project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                model_deployment_name=os.environ["FOUNDRY_MODEL_DEPLOYMENT_NAME"],
                async_ad_credential=credential,
                agent_name="WeatherAgent",
            ),
            instructions="You are a helpful weather agent.",
            tools=get_weather,
        ) as agent,
    ):
        result = await agent.run("What's the weather like in New York?")
        print(f"Result: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
