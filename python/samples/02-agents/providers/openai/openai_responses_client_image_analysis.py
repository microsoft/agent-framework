# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Content, Message
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
        instructions="You are a helpful agent that can analyze images.",
    )

    # 2. Create a simple message with both text and image content
    user_message = Message(
        role="user",
        contents=[
            Content.from_text(text="What do you see in this image?"),
            Content.from_uri(
                uri="https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800",
                media_type="image/jpeg",
            ),
        ],
    )

    # 3. Get the agent's response
    print("User: What do you see in this image? [Image provided]")
    result = await agent.run(user_message)
    print(f"Agent: {result.text}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
