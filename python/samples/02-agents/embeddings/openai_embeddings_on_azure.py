# Copyright (c) Microsoft. All rights reserved.

# Run with: uv run samples/02-agents/embeddings/azure_openai_embeddings.py

import asyncio
import os

from agent_framework.openai import OpenAIEmbeddingClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

"""This sample demonstrates Azure OpenAI embedding generation with ``OpenAIEmbeddingClient``.

Prerequisites:
    Set the following environment variables or add them to a local ``.env`` file:
    - ``AZURE_OPENAI_ENDPOINT``: Your Azure OpenAI endpoint URL
    - ``AZURE_OPENAI_EMBEDDING_MODEL``: The embedding deployment name
    - ``AZURE_OPENAI_API_VERSION``: Optional API version override

    Sign in with ``az login`` before running the sample.
"""

load_dotenv()


async def main() -> None:
    """Generate embeddings with Azure OpenAI."""
    async with AzureCliCredential() as credential:
        client = OpenAIEmbeddingClient(
            model=os.getenv("AZURE_OPENAI_EMBEDDING_MODEL"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            credential=credential,
        )

        # 1. Generate a single embedding.
        result = await client.get_embeddings(["Hello, world!"])
        print(f"Single embedding dimensions: {result[0].dimensions}")
        print(f"First 5 values: {result[0].vector[:5]}")
        print(f"Model: {result[0].model}")
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
        print(f"First embedding vector: {result[0].vector[:5]}")
        print()

        # 3. Generate embeddings with custom dimensions.
        result = await client.get_embeddings(["Custom dimensions example"], options={"dimensions": 256})
        print(f"Custom dimensions: {result[0].dimensions}")


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
