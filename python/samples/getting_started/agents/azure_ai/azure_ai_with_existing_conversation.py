# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import ChatAgent
from agent_framework.azure import AzureAIClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field

"""
Azure AI Agent with Existing Conversation Example

This sample demonstrates working with pre-existing conversation
by providing conversation ID for reuse patterns.
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    # Create the client
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project_client,
    ):
        openai_client = await project_client.get_openai_client()  # type: ignore

        # Create a conversation that will persist
        created_conversation = await openai_client.conversations.create()

        try:
            async with ChatAgent(
                chat_client=AzureAIClient(project_client=project_client),
                instructions="You are a helpful weather agent.",
                tools=get_weather,
                store=True,
            ) as agent:
                thread = agent.get_new_thread(service_thread_id=created_conversation.id)
                assert thread.is_initialized
                result = await agent.run("What's the weather like in Tokyo?", thread=thread)
                print(f"Result: {result}\n")
        finally:
            # Clean up the conversation manually
            await openai_client.conversations.delete(conversation_id=created_conversation.id)


if __name__ == "__main__":
    asyncio.run(main())
