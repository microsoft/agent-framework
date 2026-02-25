# Copyright (c) Microsoft. All rights reserved.

# Run with: uv run samples/02-agents/embeddings/openai_embeddings.py

import asyncio

from agent_framework.openai import OpenAIEmbeddingClient
from dotenv import load_dotenv

load_dotenv()

"""OpenAI Embedding Client Example

This sample demonstrates how to generate embeddings using the OpenAI embedding client.
It shows single and batch embedding generation, as well as custom dimensions.

Prerequisites:
    Set the OPENAI_API_KEY environment variable or add it to a .env file.
"""


async def main() -> None:
    """Generate embeddings with OpenAI."""
    client = OpenAIEmbeddingClient(model_id="text-embedding-3-small")

    # 1. Generate a single embedding.
    result = await client.get_embeddings(["Hello, world!"])
    print(f"Single embedding dimensions: {result[0].dimensions}")
    print(f"First 5 values: {result[0].vector[:5]}")
    print(f"Model: {result[0].model_id}")
    print(f"Usage: {result.usage}")
    print()

    # 2. Generate embeddings for multiple inputs.
    texts = [
        "The weather is sunny today.",
        "It is raining outside.",
        "Machine learning is fascinating.",
    ]
    result = await client.get_embeddings(texts)
    print(f"Batch of {len(result)} embeddings, each with {result[0].dimensions} dimensions")
    print(f"First embedding vector: {result[0].vector[:5]}")  # Print first 5 values of the first embedding
    print()

    # 3. Generate embeddings with custom dimensions.
    result = await client.get_embeddings(["Custom dimensions example"], options={"dimensions": 256})
    print(f"Custom dimensions: {result[0].dimensions}")
    print(f"First 5 values: {result[0].vector[:5]}")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
Single embedding dimensions: 1536
First 5 values: [0.012, -0.034, 0.056, -0.078, 0.090]
Model: text-embedding-3-small
Usage: {'prompt_tokens': 4, 'total_tokens': 4}

Batch of 3 embeddings, each with 1536 dimensions

Custom dimensions: 256
"""
