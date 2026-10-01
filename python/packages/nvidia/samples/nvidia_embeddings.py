# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass
from typing import Annotated

from agent_framework import InMemoryCollection, VectorStoreField, vectorstoremodel

from agent_framework_nvidia import NvidiaEmbeddingClient

"""Generate embeddings with models hosted on NVIDIA NIM, then retrieve with them.

Set ``NVIDIA_API_KEY`` to a key from https://build.nvidia.com/, then run from python/:
    uv run --package agent-framework-nvidia python packages/nvidia/samples/nvidia_embeddings.py

Model availability is per account. If a model name returns ``404 ... Not found for account``,
it exists but your key is not entitled to it; a retired model returns ``410 Gone``. List the
models available to your key rather than assuming the name is wrong.
"""


@vectorstoremodel(collection_name="nvidia-notes")
@dataclass
class Note:
    id: Annotated[str, VectorStoreField("key")]
    text: Annotated[str, VectorStoreField("data")]
    vector: Annotated[str | list[float] | None, VectorStoreField("vector", dimensions=2048)] = None


async def main() -> None:
    """Generate embeddings with NVIDIA NIM."""
    # The API key is read from NVIDIA_API_KEY.
    client = NvidiaEmbeddingClient(model="nvidia/nemotron-3-embed-1b")

    # To use a self-hosted NIM container instead of the hosted endpoint, set base_url
    # (also read from NVIDIA_BASE_URL):
    # client = NvidiaEmbeddingClient(
    #     model="nvidia/nemotron-3-embed-1b",
    #     base_url="http://localhost:8000/v1",
    #     api_key="not-used-by-local-nim",
    # )

    try:
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

        # 3. Retrieval: embed stored documents as passages and search text as a query.
        #    Asymmetric models such as nemotron embed the two differently, and the vector
        #    store forwards input_type to each embedding request.
        collection: InMemoryCollection[str, Note] = InMemoryCollection(Note, embedding_generator=client)
        await collection.ensure_collection_exists()
        sources = {
            "one": "NIM serves models behind an OpenAI-compatible API.",
            "two": "The weather is sunny today.",
        }
        # The vector field holds the text to embed until the collection replaces it with the vector.
        # truncate="END" keeps one over-long document from failing the whole upsert.
        notes = [Note(note_id, text, text) for note_id, text in sources.items()]
        await collection.upsert(notes, embeddings_options={"input_type": "passage", "truncate": "END"})
        results = await collection.search(
            "How do I call a model hosted on NIM?", embeddings_options={"input_type": "query"}, top=1
        )
        async for item in results:
            print(f"Best match: {item['record'].text}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
Single embedding dimensions: 2048
First 5 values: [0.4655469059944153, -0.027859577909111977, -0.1295825093984604, -0.0473068505525589,
-0.009855593554675579]
Model: nvidia/nemotron-3-embed-1b
Usage: {'input_token_count': 4, 'total_token_count': 4}

Batch of 3 embeddings, each with 2048 dimensions
First embedding vector: [0.22611355781555176, -0.003007160732522607, -0.0892254188656807,
-0.027936991304159164, 0.01019396260380745]

Best match: NIM serves models behind an OpenAI-compatible API.
"""
