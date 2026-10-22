# Copyright (c) Microsoft. All rights reserved.
# /// script
# requires-python = ">=3.10"
# dependencies = ["agent-framework-gemini"]
# ///

"""Generate document and query text embeddings with the stable Gemini Embedding 2 model.

Requires ``GOOGLE_API_KEY`` for the Developer API. Enterprise users
can instead set ``GOOGLE_GENAI_USE_ENTERPRISE``, ``GOOGLE_CLOUD_PROJECT``, and
``GOOGLE_CLOUD_LOCATION``. The optional ``GOOGLE_EMBEDDING_MODEL`` setting overrides
the default model.
"""

import asyncio

from agent_framework.gemini import GeminiEmbeddingClient
from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    """Embed a document and a search query for the same vector index."""
    # 1. Choose task instructions for each call, not for the client.
    client = GeminiEmbeddingClient()
    try:
        # 2. Use matching dimensions for stored documents and search queries.
        document = await client.get_embeddings(
            ["Agent Framework helps build and orchestrate AI agents."],
            options={"task_type": "RETRIEVAL_DOCUMENT", "title": "Agent Framework", "dimensions": 768},
        )
        query = await client.get_embeddings(
            ["How can I orchestrate AI agents?"],
            options={"task_type": "RETRIEVAL_QUERY", "dimensions": 768},
        )
        print(f"Document embedding: {document[0].dimensions} dimensions")
        print(f"Query embedding: {query[0].dimensions} dimensions")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
Document embedding: 768 dimensions
Query embedding: 768 dimensions
"""
