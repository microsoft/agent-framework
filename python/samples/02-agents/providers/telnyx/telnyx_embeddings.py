# Copyright (c) Microsoft. All rights reserved.

"""Telnyx Embeddings Example

This sample demonstrates using Telnyx for text embeddings through the
OpenAIEmbeddingClient by configuring the base_url to point to the
Telnyx AI API endpoint.

Telnyx provides an OpenAI-compatible API that supports embeddings
generation using models like `thenlper/gte-large`.

Environment Variables:
    TELNYX_API_KEY   — Your Telnyx API key (from https://portal.telnyx.com/)
    TELNYX_EMBEDDING_MODEL — Embedding model name (default: "thenlper/gte-large")
"""

import asyncio
import os

from agent_framework.openai import OpenAIEmbeddingClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


async def main() -> None:
    print("=== Telnyx Embeddings Example ===")

    # 1. Configure the OpenAI embedding client to use Telnyx as the backend.
    client = OpenAIEmbeddingClient(
        api_key=os.getenv("TELNYX_API_KEY"),
        base_url="https://api.telnyx.com/v2/ai/openai",
        model=os.getenv("TELNYX_EMBEDDING_MODEL", "thenlper/gte-large"),
    )

    # 2. Generate embeddings for a list of texts.
    texts = [
        "Telnyx provides telecom infrastructure for AI agents.",
        "Agent Framework makes it easy to build AI agents.",
    ]

    print(f"Generating embeddings for {len(texts)} texts...")
    response = await client.get_embeddings(texts)

    # 3. Print the embedding dimensions and a preview of each vector.
    for i, embedding in enumerate(response):
        print(f"Text {i + 1}: \"{texts[i]}\"")
        print(f"  Dimensions: {len(embedding)}")
        print(f"  Preview: [{', '.join(str(v) for v in embedding[:5])}, ...]")
        print()

    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

=== Telnyx Embeddings Example ===
Generating embeddings for 2 texts...
Text 1: "Telnyx provides telecom infrastructure for AI agents."
  Dimensions: 1024
  Preview: [0.0123, -0.0456, 0.0789, ...], ...

Text 2: "Agent Framework makes it easy to build AI agents."
  Dimensions: 1024
  Preview: [0.0234, -0.0567, 0.0890, ...], ...

Done!
"""
