# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Content
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Azure OpenAI Responses Client with Image Analysis Example

This sample demonstrates using Azure OpenAI Responses for image analysis and vision tasks,
showing multi-modal messages combining text and image content.
"""


async def main():
    print("=== Azure Responses Agent with Image Analysis ===")

    # 1. Create an Azure Responses agent with vision capabilities
    agent = AzureOpenAIResponsesClient(credential=AzureCliCredential()).as_agent(
        name="VisionAgent",
        instructions="You are a image analysist, you get a image and need to respond with what you see in the picture.",
    )

    # 2. Get the agent's response
    print("User: What do you see in this image? [Image provided]")
    result = await agent.run(
        Content.from_uri(
            uri="https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800",
            media_type="image/jpeg",
        )
    )
    print(f"Agent: {result.text}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
