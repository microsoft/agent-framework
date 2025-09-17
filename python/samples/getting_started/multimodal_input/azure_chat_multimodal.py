#!/usr/bin/env python3

import asyncio
import base64
import requests
from agent_framework import ChatMessage, DataContent, Role, TextContent
from agent_framework.azure import AzureChatClient

async def test_image():
    """Test image analysis with Azure."""
    client = AzureChatClient()

    # Fetch image from httpbin
    image_url = "https://httpbin.org/image/jpeg"
    response = requests.get(image_url)
    image_b64 = base64.b64encode(response.content).decode()
    image_uri = f"data:image/jpeg;base64,{image_b64}"

    message = ChatMessage(
        role=Role.USER,
        contents=[
            TextContent(text="What's in this image?"),
            DataContent(uri=image_uri, media_type="image/jpeg")
        ]
    )

    response = await client.get_response(message)
    print(f"Image Response: {response}")

async def test_audio():
    """Test audio analysis with Azure (Note: requires gpt-4o-audio-preview model)."""
    print("Note: Audio requires gpt-4o-audio-preview or similar model in Azure deployment")
    # Audio example commented out since current Azure deployment doesn't support audio
    # client = AzureChatClient()
    # ... audio code would go here

async def main():
    print("=== Testing Azure Multimodal ===")
    await test_image()
    await test_audio()

if __name__ == "__main__":
    asyncio.run(main())
