# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-azure-ai",
# ]
# ///
# Run with: uv run samples/02-agents/embeddings/azure_ai_inference_embeddings.py

# Copyright (c) Microsoft. All rights reserved.

import asyncio
import pathlib

from agent_framework import Content
from agent_framework_azure_ai import AzureAIInferenceEmbeddingClient
from dotenv import load_dotenv

load_dotenv()

"""Azure AI Inference Image Embedding Example

This sample demonstrates how to generate image embeddings using the
Azure AI Inference embedding client with the Cohere-embed-v3-english model.
Images are passed as ``Content`` objects created with ``Content.from_data()``.

Prerequisites:
    Set the following environment variables or add them to a .env file:
    - AZURE_AI_INFERENCE_ENDPOINT: Your Azure AI model inference endpoint URL
    - AZURE_AI_INFERENCE_API_KEY: Your API key
    - AZURE_AI_INFERENCE_EMBEDDING_MODEL_ID: The text embedding model name
      (e.g. "text-embedding-3-small")
    - AZURE_AI_INFERENCE_IMAGE_EMBEDDING_MODEL_ID: The image embedding model name
      (e.g. "Cohere-embed-v3-english")
"""

SAMPLE_IMAGE_PATH = pathlib.Path(__file__).parent.parent.parent / "shared" / "sample_assets" / "sample_image.jpg"


async def main() -> None:
    """Generate image embeddings with Azure AI Inference."""
    async with AzureAIInferenceEmbeddingClient() as client:
        # 1. Generate an image embedding.
        image_bytes = SAMPLE_IMAGE_PATH.read_bytes()
        image_content = Content.from_data(data=image_bytes, media_type="image/jpeg")
        result = await client.get_embeddings([image_content])
        print(f"Image embedding dimensions: {result[0].dimensions}")
        print(f"First 5 values: {result[0].vector[:5]}")
        print(f"Model: {result[0].model_id}")
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
Sample output (using Cohere-embed-v3-english):
Image embedding dimensions: 1024
First 5 values: [0.023, -0.045, 0.067, -0.089, 0.011]
Model: Cohere-embed-v3-english
Usage: {'prompt_tokens': 1, 'total_tokens': 1}

Image+text (separate) results:
Text embedding dimensions: 1536
Image embedding dimensions: 1024

Document embedding dimensions: 1024
"""
