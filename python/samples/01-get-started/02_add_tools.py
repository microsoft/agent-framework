# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import tool
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

"""
Add Tools — Give your agent a function tool

This sample shows how to define a function tool with the @tool decorator
and wire it into an agent so the model can call it.

Environment variables:
  AZURE_AI_PROJECT_ENDPOINT        — Your Azure AI Foundry project endpoint
  AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME — Model deployment name (e.g. gpt-4o)
"""


# <define_tool>
# NOTE: approval_mode="never_require" is for sample brevity.
# Use "always_require" in production for user confirmation before tool execution.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."
# </define_tool>


async def main() -> None:
    credential = AzureCliCredential()
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        credential=credential,
    )

    # <create_agent_with_tools>
    agent = client.as_agent(
        name="WeatherAgent",
        instructions="You are a helpful weather agent. Use the get_weather tool to answer questions.",
        tools=get_weather,
    )
    # </create_agent_with_tools>

    # <run_agent>
    result = await agent.run("What's the weather like in Seattle?")
    print(f"Agent: {result}")
    # </run_agent>


if __name__ == "__main__":
    asyncio.run(main())
