# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatMessage, Content, Role
from agent_framework.ollama import OllamaChatClient

"""
Ollama Agent Multimodal Example

This sample demonstrates implementing a Ollama agent with multimodal input capabilities.

Ensure to install Ollama and have a model running locally before running the sample
Not all Models support multimodal input, to test multimodal input try gemma3:4b
Set the model to use via the OLLAMA_MODEL_ID environment variable or modify the code below.
https://ollama.com/

"""


def create_sample_image() -> str:
    """Create a simple 1x1 pixel PNG image for testing."""
    # This is a tiny red pixel in PNG format
    png_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
    return f"data:image/png;base64,{png_data}"


async def test_image() -> None:
    """Test image analysis with Ollama."""

    client = OllamaChatClient()

    image_uri = create_sample_image()

    message = ChatMessage(
        role=Role.USER,
        contents=[
            Content.from_text(text="What's in this image?"),
            Content.from_uri(uri=image_uri, media_type="image/png"),
        ],
    )

    response = await client.get_response(message)
    print(f"Image Response: {response}")


async def main() -> None:
    print("=== Testing Ollama Multimodal ===")
    await test_image()


if __name__ == "__main__":
    asyncio.run(main())
