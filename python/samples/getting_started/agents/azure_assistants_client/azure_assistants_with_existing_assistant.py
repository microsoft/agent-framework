# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import ChatClientAgent
from agent_framework.azure import AzureAssistantsClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncAzureOpenAI
from pydantic import Field


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    print("=== Azure OpenAI Assistants Chat Client with Existing Assistant ===")

    token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")

    client = AsyncAzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_ad_token_provider=token_provider,
        api_version="2025-01-01-preview",
    )

    # Create an assistant that will persist
    created_assistant = await client.beta.assistants.create(
        model=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"], name="WeatherAssistant"
    )

    try:
        async with ChatClientAgent(
            chat_client=AzureAssistantsClient(async_client=client, assistant_id=created_assistant.id),
            instructions="You are a helpful weather agent.",
            tools=get_weather,
        ) as agent:
            result = await agent.run("What's the weather like in Tokyo?")
            print(f"Result: {result}\n")
    finally:
        # Clean up the assistant manually
        await client.beta.assistants.delete(created_assistant.id)


if __name__ == "__main__":
    asyncio.run(main())
