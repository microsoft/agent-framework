# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-foundry",
#     "azure-identity",
# ]
# ///
# Run with: uv run samples/02-agents/embeddings/foundry_embeddings.py

# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework.foundry import FoundryEmbeddingClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

"""Microsoft Foundry OpenAI Embedding Example

This sample demonstrates how to generate text embeddings with an OpenAI model
deployment exposed through a Microsoft Foundry project.

Prerequisites:
    Sign in with ``az login`` and set:
    - FOUNDRY_PROJECT_ENDPOINT: Your Foundry project endpoint, for example:
        https://<resource>.services.ai.azure.com/api/projects/<project>
    - FOUNDRY_EMBEDDING_MODEL: Your embedding deployment name, for example:
        text-embedding-3-small
"""


async def main() -> None:
    """Generate text embeddings through a Foundry project."""
    async with AzureCliCredential() as credential, FoundryEmbeddingClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_EMBEDDING_MODEL"],
        credential=credential,
    ) as client:
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

        # 3. Generate an embedding with custom dimensions.
        result = await client.get_embeddings(["Custom dimensions example"], options={"dimensions": 256})
        print(f"Custom dimensions: {result[0].dimensions}")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
Single embedding dimensions: 1536
First 5 values: [0.012, -0.034, 0.056, -0.078, 0.09]
Model: text-embedding-3-small
Usage: {'input_token_count': 4, 'total_token_count': 4}

Batch of 3 embeddings, each with 1536 dimensions
First embedding vector: [0.012, -0.034, 0.056, -0.078, 0.09]

Custom dimensions: 256
"""
