# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64

from agent_framework import DataContent, UriContent
from agent_framework.openai import OpenAIResponsesClient


def show_image_info(data_uri: str) -> None:
    """Display information about the generated image."""
    try:
        # Extract format and size info from data URI
        if data_uri.startswith("data:image/"):
            format_info = data_uri.split(";")[0].split("/")[1]
            base64_data = data_uri.split(",", 1)[1]
            image_bytes = base64.b64decode(base64_data)
            size_kb = len(image_bytes) / 1024

            print(" Image successfully generated!")
            print(f"   Format: {format_info.upper()}")
            print(f"   Size: {size_kb:.1f} KB")
            print(f"   Data URI length: {len(data_uri)} characters")
            print("")
            print(" To save and view the image:")
            print('   1. Install Pillow: "pip install pillow" or "uv add pillow"')
            print("   2. Use the data URI in your code to save/display the image")
            print("   3. Or copy the base64 data to an online base64 image decoder")
        else:
            print(f" Image URL generated: {data_uri}")
            print(" You can open this URL in a browser to view the image")

    except Exception as e:
        print(f" Error processing image data: {e}")
        print(" Image generated but couldn't parse details")


async def main() -> None:
    print("=== OpenAI Responses Image Generation Agent Example ===")

    # Create an agent with customized image generation options
    agent = OpenAIResponsesClient().create_agent(
        instructions="You are a helpful AI that can generate images.",
        tools=[
            {
                "type": "image_generation",
                # Core parameters
                "size": "1024x1024",
                "background": "transparent",
                "quality": "low",
                "format": "webp",
            }
        ],
    )

    query = "Generate a nice beach scenery with blue skies in summer time."
    print(f"User: {query}")
    print("Generating image with parameters: 1024x1024 size, transparent background, low quality, WebP format...")

    result = await agent.run(query)
    print(f"Agent: {result.text}")

    # Show information about the generated image
    for message in result.messages:
        for content in message.contents:
            if isinstance(content, (DataContent, UriContent)) and content.uri:
                show_image_info(content.uri)
                break


if __name__ == "__main__":
    asyncio.run(main())
