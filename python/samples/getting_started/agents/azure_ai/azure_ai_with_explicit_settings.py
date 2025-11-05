# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import ChatAgent
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field

"""
Azure AI Agent with Explicit Settings Example

This sample demonstrates creating Azure AI Agents with explicit configuration
settings rather than relying on environment variable defaults.
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    print("=== Azure AI Chat Client with Explicit Settings ===")

    # Since no Agent ID is provided, the agent will be automatically created
    # and deleted after getting a response
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        ChatAgent(
            chat_client=AzureAIAgentClient(
                project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
                model_deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                async_credential=credential,
                agent_name="WeatherAgent",
                should_cleanup_agent=True,  # Set to False if you want to disable automatic agent cleanup
            ),
            instructions="You are a helpful weather agent.",
            tools=get_weather,
        ) as agent,
    ):
        result = await agent.run("What's the weather like in New York?")
        print(f"Result: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
