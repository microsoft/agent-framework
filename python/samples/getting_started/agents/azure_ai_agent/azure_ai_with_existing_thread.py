# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework.azure import AzureAIAgentsProvider
from azure.ai.agents.aio import AgentsClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field
from agent_framework import tool

"""
Azure AI Agent with Existing Thread Example

This sample demonstrates working with pre-existing conversation threads
by providing thread IDs for thread reuse patterns.
"""

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    print("=== Azure AI Agent with Existing Thread ===")

    # Create the client and provider
    async with (
        AzureCliCredential() as credential,
        AgentsClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as agents_client,
        AzureAIAgentsProvider(agents_client=agents_client) as provider,
    ):
        # Create a thread that will persist
        created_thread = await agents_client.threads.create()

        try:
            # Create agent using provider
            agent = await provider.create_agent(
                name="WeatherAgent",
                instructions="You are a helpful weather agent.",
                tools=get_weather,
            )

            thread = agent.get_new_thread(service_thread_id=created_thread.id)
            assert thread.is_initialized
            result = await agent.run("What's the weather like in Tokyo?", thread=thread)
            print(f"Result: {result}\n")
        finally:
            # Clean up the thread manually
            await agents_client.threads.delete(created_thread.id)


if __name__ == "__main__":
    asyncio.run(main())
