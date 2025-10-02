# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import ChatAgent
from agent_framework.azure import AzureAIAgentClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field

"""
Azure AI Agent with Existing Agent Example

This sample demonstrates working with pre-existing Azure AI Agents by providing
agent IDs, showing agent reuse patterns for production scenarios.
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    print("=== Azure AI Chat Client with Existing Agent ===")

    # Create the client
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as client,
    ):
        # Create an agent that will persist
        created_agent = await client.agents.create_agent(
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"], name="WeatherAgent"
        )

        try:
            async with ChatAgent(
                # passing in the client is optional here, so if you take the agent_id from the portal
                # you can use it directly without the two lines above.
                chat_client=AzureAIAgentClient(project_client=client, agent_id=created_agent.id),
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
