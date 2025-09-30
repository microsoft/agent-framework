# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatMessage, TextContent, UriContent
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential

"""
Azure OpenAI Responses Client with Image Analysis Example

This sample demonstrates how to use Azure OpenAI Responses for image analysis and vision tasks.
The example includes:

- Creating vision-capable agents using AzureOpenAIResponsesClient
- Multi-modal messages combining text and image content
- Image analysis using remote URLs (Wikipedia image example)
- Processing UriContent for image input with proper media type specification
- Vision capabilities for understanding and describing image content

This approach enables agents to analyze images, describe visual content, and answer
questions about images, making it ideal for applications requiring visual understanding
and multi-modal AI interactions.
"""


async def main():
    print("=== Azure Responses Agent with Image Analysis ===")

    # 1. Create an Azure Responses agent with vision capabilities
    agent = AzureOpenAIResponsesClient(credential=AzureCliCredential()).create_agent(
        name="VisionAgent",
        instructions="You are a helpful agent that can analyze images.",
    )

    # 2. Create a simple message with both text and image content
    user_message = ChatMessage(
        role="user",
        contents=[
            TextContent(text="What do you see in this image?"),
            UriContent(
                uri="https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Gfp-wisconsin-madison-the-nature-boardwalk.jpg/2560px-Gfp-wisconsin-madison-the-nature-boardwalk.jpg",
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
