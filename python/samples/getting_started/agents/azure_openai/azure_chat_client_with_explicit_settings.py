# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from pydantic import Field

"""
Azure OpenAI Chat Client with Explicit Settings Example

This sample demonstrates creating Azure OpenAI Chat Client with explicit configuration
settings rather than relying on environment variable defaults.
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    print("=== Azure Chat Client with Explicit Settings ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    agent = AzureOpenAIChatClient(
        deployment_name=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"],
        endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        credential=AzureCliCredential(),
    ).create_agent(
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    result = await agent.run("What's the weather like in New York?")
    print(f"Result: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
