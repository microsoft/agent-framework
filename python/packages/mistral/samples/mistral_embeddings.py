# Copyright (c) Microsoft. All rights reserved.

"""Shows how to generate embeddings using the Mistral AI embedding client.

Requires ``MISTRAL_API_KEY`` and ``MISTRAL_EMBEDDING_MODEL`` environment variables.
"""

import asyncio

from dotenv import load_dotenv

from agent_framework_mistral import MistralEmbeddingClient

load_dotenv()


async def basic_embedding_example() -> None:
    """Generate embeddings for a list of texts."""
    print("=== Basic Embedding Generation ===")

    # 1. Create the embedding client (uses MISTRAL_API_KEY and MISTRAL_EMBEDDING_MODEL env vars).
    client = MistralEmbeddingClient()

    # 2. Generate embeddings for multiple texts.
    texts = ["Hello, world!", "How are you?", "Agent Framework with Mistral AI"]
    result = await client.get_embeddings(texts)

    # 3. Print results.
    print(f"Generated {len(result)} embeddings")
    for i, embedding in enumerate(result):
        print(f"  Text {i + 1}: dimensions={embedding.dimensions}, vector={embedding.vector[:5]}...")

    if result.usage:
        print(
            f"  Usage: {result.usage['input_token_count']} input tokens, "
            f"{result.usage['total_token_count']} total tokens"
        )


async def embedding_with_options_example() -> None:
    """Generate embeddings with custom dimensions."""
    print("\n=== Embedding with Custom Dimensions ===")

    from agent_framework_mistral import MistralEmbeddingOptions

    client = MistralEmbeddingClient()

    # Request a specific output dimension (model must support it).
    options: MistralEmbeddingOptions = {"dimensions": 256}
    result = await client.get_embeddings(["Dimensionality reduction example"], options=options)

    print(f"  Dimensions: {result[0].dimensions}")
    print(f"  Vector (first 5): {result[0].vector[:5]}...")


async def main() -> None:
    """Run embedding examples."""
    await basic_embedding_example()
    await embedding_with_options_example()


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
=== Basic Embedding Generation ===
Generated 3 embeddings
  Text 1: dimensions=1024, vector=[0.0123, -0.0456, 0.0789, -0.0012, 0.0345]...
  Text 2: dimensions=1024, vector=[0.0234, -0.0567, 0.0891, -0.0023, 0.0456]...
  Text 3: dimensions=1024, vector=[0.0345, -0.0678, 0.0912, -0.0034, 0.0567]...
  Usage: 15 input tokens, 15 total tokens

=== Embedding with Custom Dimensions ===
  Dimensions: 256
  Vector (first 5): [0.0456, -0.0789, 0.0123, -0.0456, 0.0789]...
"""
