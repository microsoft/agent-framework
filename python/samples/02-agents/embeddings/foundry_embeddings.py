# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-foundry",
# ]
# ///
# Run with: uv run samples/02-agents/embeddings/foundry_embeddings.py

# Copyright (c) Microsoft. All rights reserved.

import asyncio
import pathlib

from agent_framework import Content
from agent_framework.foundry import FoundryEmbeddingClient
from dotenv import load_dotenv

load_dotenv()

"""Microsoft Foundry Image Embedding Example

This sample demonstrates how to generate image embeddings using the
Foundry embedding client with the Cohere-embed-v3-english model.
Images are passed as ``Content`` objects created with ``Content.from_data()``.

Prerequisites:
    Deploy an embedding model to a Foundry-hosted inference endpoint that supports image inputs,
    such as Cohere-embed-v3-english.

    The details page for that model, has a target URI and a Key, which should be set in environment variables or a .env
    file as follows, the target URI should append the `/models` path:
    - FOUNDRY_MODELS_ENDPOINT: Your Foundry models endpoint URL, for instance:
        https://<apim-instance>.azure-api.net/<foundry-instance>/models
    - FOUNDRY_MODELS_API_KEY: Your API key
    - FOUNDRY_EMBEDDING_MODEL: The text embedding model name
      (e.g. "text-embedding-3-small")
    - FOUNDRY_IMAGE_EMBEDDING_MODEL: The image embedding model name
      (e.g. "Cohere-embed-v3-english")
"""

SAMPLE_IMAGE_PATH = pathlib.Path(__file__).parent.parent.parent / "shared" / "sample_assets" / "sample_image.jpg"


async def main() -> None:
    """Generate image embeddings with Foundry."""
    async with FoundryEmbeddingClient() as client:
        # 1. Generate an image embedding.
        image_bytes = SAMPLE_IMAGE_PATH.read_bytes()
        image_content = Content.from_data(data=image_bytes, media_type="image/jpeg")
        result = await client.get_embeddings([image_content])
        print(f"Image embedding dimensions: {result[0].dimensions}")
        print(f"First 5 values: {result[0].vector[:5]}")
        print(f"Model: {result[0].model}")
        print(f"Usage: {result.usage}")
        print()

        # 2. Generate image and text embeddings separately in one call.
        # The client dispatches text to the text endpoint and images to the image
        # endpoint, then reassembles results in the original input order.
        result = await client.get_embeddings(["A half-timbered house in a forested valley", image_content])
        print(f"Text embedding dimensions: {result[0].dimensions}")
        print(f"First 5 values: {result[0].vector[:5]}")
        print(f"Image embedding dimensions: {result[1].dimensions}")
        print(f"First 5 values: {result[1].vector[:5]}")
        print()

        # 3. Generate image embeddings with input_type option.
        result = await client.get_embeddings(
            [image_content],
            options={"input_type": "document"},
        )
        print(f"Document embedding dimensions: {result[0].dimensions}")
        print(f"First 5 values: {result[0].vector[:5]}")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output (using deployment: Cohere-embed-v3-english, which is Cohere's "embed-english-v3.0-image" model):
Image embedding dimensions: 1024
First 5 values: [0.029159546, -0.007926941, -0.0032978058, -0.0030403137, -0.012786865]
Model: embed-english-v3.0-image
Usage: {'input_token_count': 1000, 'output_token_count': 0}

Text embedding dimensions: 1536
First 5 values: [-0.019439403, 0.015791258, 0.012358093, 0.0028533707, -0.01649483]
Image embedding dimensions: 1024
First 5 values: [0.029159546, -0.007926941, -0.0032978058, -0.0030403137, -0.012786865]

Document embedding dimensions: 1024
First 5 values: [0.029159546, -0.007926941, -0.0032978058, -0.0030403137, -0.012786865]
"""
