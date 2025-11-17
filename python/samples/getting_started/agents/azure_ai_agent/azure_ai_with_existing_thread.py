# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import ChatAgent
from agent_framework.azure import AzureAIAgentClient
from azure.ai.agents.aio import AgentsClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field

"""
Azure AI Agent with Existing Thread Example

This sample demonstrates working with pre-existing conversation threads
by providing thread IDs for thread reuse patterns.
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    print("=== Azure AI Chat Client with Existing Thread ===")

    # Create the client
    async with (
        AzureCliCredential() as credential,
        AgentsClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as agents_client,
    ):
        # Create an thread that will persist
        created_thread = await agents_client.threads.create()

        try:
            async with ChatAgent(
                # passing in the client is optional here, so if you take the agent_id from the portal
                # you can use it directly without the two lines above.
                chat_client=AzureAIAgentClient(agents_client=agents_client),
                instructions="You are a helpful weather agent.",
                tools=get_weather,
            ) as agent:
                thread = agent.get_new_thread(service_thread_id=created_thread.id)
                assert thread.is_initialized
                result = await agent.run("What's the weather like in Tokyo?", thread=thread)
                print(f"Result: {result}\n")
        finally:
            # Clean up the thread manually
            await agents_client.threads.delete(created_thread.id)


if __name__ == "__main__":
    asyncio.run(main())
