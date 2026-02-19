# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64
import tempfile
from pathlib import Path

import anyio
from agent_framework import Content
from agent_framework.openai import OpenAIResponsesClient

"""OpenAI Responses Client Streaming Image Generation Example

Demonstrates streaming partial image generation using OpenAI's image generation tool.
Shows progressive image rendering with partial images for improved user experience.

Note: The number of partial images received depends on generation speed:
- High quality/complex images: More partials (generation takes longer)
- Low quality/simple images: Fewer partials (generation completes quickly)
- You may receive fewer partial images than requested if generation is fast

Important: The final partial image IS the complete, full-quality image. Each partial
represents a progressive refinement, with the last one being the finished result.
"""


async def save_image_from_data_uri(data_uri: str, filename: str) -> None:
    """Save an image from a data URI to a file."""
    try:
        if data_uri.startswith("data:image/"):
            # Extract base64 data
            base64_data = data_uri.split(",", 1)[1]
            image_bytes = base64.b64decode(base64_data)

            # Save to file
            await anyio.Path(filename).write_bytes(image_bytes)
            print(f"    Saved: {filename} ({len(image_bytes) / 1024:.1f} KB)")
    except Exception as e:
        print(f"    Error saving {filename}: {e}")


async def main():
    """Demonstrate streaming image generation with partial images."""
    print("=== OpenAI Streaming Image Generation Example ===\n")

    # Create agent with streaming image generation enabled
    client = OpenAIResponsesClient()
    agent = client.as_agent(
        instructions="You are a helpful agent that can generate images.",
        tools=[
            client.get_image_generation_tool(
                size="1024x1024",
                quality="high",
                partial_images=3,
            )
        ],
    )

    query = "Draw a beautiful sunset over a calm ocean with sailboats"
    print(f" User: {query}")
    print()

    # Track partial images
    image_count = 0

    # Use temp directory for output
    output_dir = Path(tempfile.gettempdir()) / "generated_images"
    output_dir.mkdir(exist_ok=True)

    print(" Streaming response:")
    async for update in agent.run(query, stream=True):
        for content in update.contents:
            # Handle partial images
            # The final partial image IS the complete, full-quality image. Each partial
            # represents a progressive refinement, with the last one being the finished result.
            if content.type == "image_generation_tool_result" and isinstance(content.outputs, Content):
                image_output: Content = content.outputs
                if (
                    image_output.type == "data"
                    and image_output.additional_properties.get("is_partial_image")
                ):
                    print(f"     Image {image_count} received")

                    # Extract file extension from media_type (e.g., "image/png" -> "png")
                    extension = "png"  # Default fallback
                    if image_output.media_type and "/" in image_output.media_type:
                        extension = image_output.media_type.split("/")[-1]

                    # Save images with correct extension
                    filename = output_dir / f"image{image_count}.{extension}"
                    await save_image_from_data_uri(image_output.uri, str(filename))

                    image_count += 1

    # Summary
    print("\n Summary:")
    print(f"    Images received: {image_count}")
    print(f"    Output directory: {output_dir}")
    print("\n Streaming image generation completed!")


if __name__ == "__main__":
    asyncio.run(main())
