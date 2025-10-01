# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework.azure import AzureOpenAIAssistantsClient
from azure.identity import AzureCliCredential
from pydantic import Field

"""
Azure Assistants Client Direct Usage Example

Demonstrates direct AzureAssistantsClient usage for chat interactions with Azure OpenAI assistants.
Shows function calling capabilities and automatic assistant creation.
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with AzureOpenAIAssistantsClient(credential=AzureCliCredential()) as client:
        message = "What's the weather in Amsterdam and in Paris?"
        stream = False
        print(f"User: {message}")
        if stream:
            print("Assistant: ", end="")
            async for chunk in client.get_streaming_response(message, tools=get_weather):
                if str(chunk):
                    print(str(chunk), end="")
            print("")
        else:
            response = await client.get_response(message, tools=get_weather)
            print(f"Assistant: {response}")


if __name__ == "__main__":
    asyncio.run(main())
