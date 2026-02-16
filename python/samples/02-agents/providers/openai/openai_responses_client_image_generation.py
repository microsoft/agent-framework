# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64
import tempfile
import urllib.request as urllib_request
from pathlib import Path

from agent_framework import Content
from agent_framework.openai import OpenAIResponsesClient

"""
OpenAI Responses Client Image Generation Example

This sample demonstrates how to generate images using OpenAI's DALL-E models
through the Responses Client. Image generation capabilities enable AI to create visual content from text,
making it ideal for creative applications, content creation, design prototyping,
and automated visual asset generation.
"""


def save_image(output: Content) -> None:
    """Save the generated image to a temporary directory.

    This sample is simplified, usually a async aware storing method would be better.
    """
    filename = "generated_image.webp"
    file_path = Path(tempfile.gettempdir()) / filename

    data_bytes: bytes | None = None
    uri = getattr(output, "uri", None)

    if isinstance(uri, str):
        if ";base64," in uri:
            try:
                b64 = uri.split(";base64,", 1)[1]
                data_bytes = base64.b64decode(b64)
            except Exception:
                data_bytes = None
        else:
            try:
                data_bytes = urllib_request.urlopen(uri).read()
            except Exception:
                data_bytes = None

    if data_bytes is None:
        raise RuntimeError("Image output present but could not retrieve bytes.")

    with open(file_path, "wb") as f:
        f.write(data_bytes)

    print(f"Image downloaded and saved to: {file_path}")


async def main() -> None:
    print("=== OpenAI Responses Image Generation Agent Example ===")

    # Create an agent with customized image generation options
    client = OpenAIResponsesClient()
    agent = client.as_agent(
        instructions="You are a helpful AI that can generate images.",
        tools=[
            client.get_image_generation_tool(
                size="1024x1024",
                output_format="webp",
            )
        ],
    )

    query = "Generate a black furry cat."
    print(f"User: {query}")
    print("Generating image with parameters: 1024x1024 size, WebP format...")

    result = await agent.run(query)
    print(f"Agent: {result.text}")

    # Find and save the generated image
    image_saved = False
    for message in result.messages:
        for content in message.contents:
            if content.type == "image_generation_tool_result" and content.outputs:
                output = content.outputs
                if isinstance(output, Content) and output.uri:
                    save_image(output)
                    image_saved = True
                elif isinstance(output, list):
                    for out in output:
                        if isinstance(out, Content) and out.uri:
                            save_image(out)
                            image_saved = True
                            break
                if image_saved:
                    break
        if image_saved:
            break

    if not image_saved:
        print("No image data found in the agent response.")


if __name__ == "__main__":
    asyncio.run(main())
