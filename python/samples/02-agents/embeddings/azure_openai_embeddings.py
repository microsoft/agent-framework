# Copyright (c) Microsoft. All rights reserved.

# Run with: uv run samples/02-agents/embeddings/azure_openai_embeddings.py


import asyncio

from agent_framework.azure import AzureOpenAIEmbeddingClient
from dotenv import load_dotenv

load_dotenv()

"""Azure OpenAI Embedding Client Example

This sample demonstrates how to generate embeddings using the Azure OpenAI embedding client.
It supports both API key and Azure credential authentication.

Prerequisites:
    Set the following environment variables or add them to a .env file:
    - AZURE_OPENAI_ENDPOINT: Your Azure OpenAI endpoint URL
    - AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME: The embedding model deployment name
    - AZURE_OPENAI_API_KEY: Your API key (or use Azure credential instead)
"""


async def main() -> None:
    """Generate embeddings with Azure OpenAI."""
    # 1. Create a client using environment variables.
    # Reads AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME,
    # and AZURE_OPENAI_API_KEY from environment.
    client = AzureOpenAIEmbeddingClient()

    # 2. Generate a single embedding.
    result = await client.get_embeddings(["Hello, world!"])
    print(f"Single embedding dimensions: {result[0].dimensions}")
    print(f"First 5 values: {result[0].vector[:5]}")
    print(f"Model: {result[0].model_id}")
    print(f"Usage: {result.usage}")
    print()

    # 3. Generate embeddings for multiple inputs.
    texts = [
        "The weather is sunny today.",
        "It is raining outside.",
        "Machine learning is fascinating.",
    ]
    result = await client.get_embeddings(texts)
    print(f"Batch of {len(result)} embeddings, each with {result[0].dimensions} dimensions")
    print()

    # 4. Generate embeddings with custom dimensions.
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
