# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64
import io

try:
    from PIL import Image

    pil_available = True
except ImportError:
    Image = None  # type: ignore
    pil_available = False

from agent_framework import DataContent, HostedImageGenerationTool, UriContent
from agent_framework.openai import OpenAIResponsesClient


def display_image(data_uri: str) -> None:
    """Display an image from a data URI using PIL if available."""
    if not pil_available or Image is None:
        print("Image generated! Install PIL to display: pip install Pillow")
        return

    try:
        # Extract base64 data and create PIL Image
        base64_data = data_uri.split(",", 1)[1] if data_uri.startswith("data:image/") else data_uri
        image_bytes = base64.b64decode(base64_data)
        image = Image.open(io.BytesIO(image_bytes))

        # Display the image and format information
        image.show()
        print(f"Image displayed! Size: {image.size}, Format: {image.format}")

    except Exception as e:
        print(f"Error displaying image: {e}")


async def main() -> None:
    print("=== OpenAI Responses Image Generation Agent Example ===")

    # Create an agent with customized image generation options
    agent = OpenAIResponsesClient().create_agent(
        instructions="You are a helpful AI that can generate images.",
        tools=[
            HostedImageGenerationTool(
                # Core parameters
                size="1536x1024",  # Landscape format (instead of default 1024x1024)
                background="transparent",  # Transparent background
                quality="low",  # Low quality generation
                format="webp",
                compression=85,
            )
        ],
    )

    query = "Generate a soccer team badge."
    print(f"User: {query}")
    print("Generating image with parameters: landscape, transparent, low quality, WebP format...")

    result = await agent.run(query)
    print(f"Agent: {result.text}")

    # Display the generated image
    for message in result.messages:
        for content in message.contents:
            if isinstance(content, (DataContent, UriContent)) and content.uri:
                display_image(content.uri)
                break


if __name__ == "__main__":
    asyncio.run(main())
