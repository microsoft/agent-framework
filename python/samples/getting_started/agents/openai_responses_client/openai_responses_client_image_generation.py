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

from agent_framework import ChatAgent, DataContent, HostedImageGenerationTool, UriContent
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

        # Display the image
        image.show()
        print(f"Image displayed! Size: {image.size}")

    except Exception as e:
        print(f"Error displaying image: {e}")


async def main() -> None:
    print("=== OpenAI Responses Image Generation Agent Example ===")

    agent = ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful AI that can generate images.",
        tools=[HostedImageGenerationTool()],
    )

    query = "Generate a soccer team badge."
    print(f"User: {query}")

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
