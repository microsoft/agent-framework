# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Content
from agent_framework.openai import OpenAIResponsesClient

"""
OpenAI Responses Client Image Analysis Example

This sample demonstrates using OpenAI Responses Client for image analysis and vision tasks,
showing multi-modal content handling with text and images.
"""


async def main():
    print("=== OpenAI Responses Agent with Image Analysis ===")

    # 1. Create an OpenAI Responses agent with vision capabilities
    agent = OpenAIResponsesClient().as_agent(
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
