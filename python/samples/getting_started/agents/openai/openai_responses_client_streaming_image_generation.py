# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64

import anyio
from agent_framework import DataContent
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
    agent = OpenAIResponsesClient().create_agent(
        instructions="You are a helpful agent that can generate images.",
        tools=[
            {
                "type": "image_generation",
                "size": "1024x1024",
                "quality": "high",
                "partial_images": 3,
            }
        ],
    )

    query = "Draw a beautiful sunset over a calm ocean with sailboats"
    print(f" User: {query}")
    print()

    # Track partial images
    image_count = 0

    # Create output directory
    output_dir = anyio.Path("generated_images")
    await output_dir.mkdir(exist_ok=True)

    print(" Streaming response:")
    async for update in agent.run_stream(query):
        for content in update.contents:
            # Handle partial images
            # The final partial image IS the complete, full-quality image. Each partial
            # represents a progressive refinement, with the last one being the finished result.
            if isinstance(content, DataContent) and content.additional_properties.get("is_partial_image"):
                print(f"     Image {image_count} received")

                # Extract file extension from media_type (e.g., "image/png" -> "png")
                extension = "png"  # Default fallback
                if content.media_type and "/" in content.media_type:
                    extension = content.media_type.split("/")[-1]

                # Save images with correct extension
                filename = output_dir / f"image{image_count}.{extension}"
                await save_image_from_data_uri(content.uri, str(filename))

                image_count += 1

    # Summary
    print("\n Summary:")
    print(f"    Images received: {image_count}")
    print("    Output directory: generated_images")
    print("\n Streaming image generation completed!")


if __name__ == "__main__":
    asyncio.run(main())
