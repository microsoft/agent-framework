# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent, Content
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
OpenAI Chat Client Image Analysis Example

This sample demonstrates using OpenAI Chat Client for image analysis and vision tasks,
showing multi-modal content handling with text and images.
"""


async def main():
    print("=== OpenAI Chat Client Agent with Image Analysis ===")

    # 1. Create an OpenAI Chat agent with vision capabilities
    agent = Agent(
        client=OpenAIChatClient(),
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
