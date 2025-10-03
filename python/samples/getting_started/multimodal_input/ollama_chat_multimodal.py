# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64

import requests
from agent_framework import ChatMessage, DataContent, Role, TextContent
from agent_framework.ollama import OllamaChatClient

"""
Ollama Agent Multimodal Example

This sample demonstrates implementing a Ollama agent with multimodal input capabilities.

Ensure to install Ollama and have a model running locally before running the sample
Not all Models support function calling, to test multimodal input try gemma3:4b
Set the model to use via the OLLAMA_CHAT_MODEL_ID environment variable or modify the code below.
https://ollama.com/

"""


async def test_image() -> None:
    """Test image analysis with Ollama."""

    client = OllamaChatClient()

    # Fetch image from httpbin
    image_url = "https://httpbin.org/image/jpeg"
    response = requests.get(image_url)
    image_b64 = base64.b64encode(response.content).decode()
    image_uri = f"data:image/jpeg;base64,{image_b64}"

    message = ChatMessage(
        role=Role.USER,
        contents=[
            TextContent(text="What's in this image?"),
            DataContent(uri=image_uri, media_type="image/jpeg"),
        ],
    )

    response = await client.get_response(message)
    print(f"Image Response: {response}")


async def main() -> None:
    print("=== Testing Ollama Multimodal ===")
    await test_image()


if __name__ == "__main__":
    asyncio.run(main())
