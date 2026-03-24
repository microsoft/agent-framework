# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

"""
Foundry Chat Client with Explicit Settings Example

This sample demonstrates creating FoundryChatClient with explicit project endpoint and
model settings rather than relying on environment variable defaults.
"""


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/02-agents/tools/function_tool_with_approval.py
# and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    print("=== Foundry Chat Client with Explicit Settings ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    _client = FoundryChatClient(
        model=os.environ["FOUNDRY_MODEL"],
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=AzureCliCredential(),
    )
    agent = Agent(
        client=_client,
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    result = await agent.run("What's the weather like in New York?")
    print(f"Result: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
