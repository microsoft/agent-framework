# Copyright (c) Microsoft. All rights reserved.

"""Use two named dense vectors with a disposable Qdrant server collection.

Run from python/:
    export QDRANT_URL=http://localhost:6333
    uv run --package agent-framework-qdrant python packages/qdrant/samples/qdrant_vectors.py

QDRANT_URL is required; QDRANT_API_KEY is optional. Use a development server,
not production. No embedding model, inference service, or OpenAI credentials
are used: the vectors are deliberately small and deterministic.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Annotated
from uuid import uuid4

from agent_framework import Filter, VectorStoreField, vectorstoremodel

from agent_framework_qdrant import QdrantStore


@vectorstoremodel
@dataclass
class Document:
    id: Annotated[int, VectorStoreField("key")]
    title: Annotated[str, VectorStoreField("data", storage_name="document_title")]
    category: Annotated[str, VectorStoreField("data", is_indexed=True)]
    text_vector: Annotated[
        list[float] | None,
        VectorStoreField("vector", dimensions=3, storage_name="text", distance_function="dot_prod"),
    ] = None
    image_vector: Annotated[
        list[float] | None,
        VectorStoreField("vector", dimensions=3, storage_name="image", distance_function="dot_prod"),
    ] = None


async def main() -> None:
    # 1. The store owns its async client. Child collections borrow it.
    async with QdrantStore(url=os.environ["QDRANT_URL"], api_key=os.getenv("QDRANT_API_KEY")) as store:
        collection = store.get_collection(Document, collection_name=f"af_qdrant_sample_{uuid4().hex}")
        await collection.ensure_collection_exists()
        try:
            # 2. Preserve supplied vectors instead of generating embeddings.
            await collection.upsert(
                [
                    Document(1, "Qdrant guide", "reference", [1.0, 0.0, 0.0], [0.0, 0.5, 0.0]),
                    Document(2, "Image guide", "reference", [0.5, 0.0, 0.0], [0.0, 1.0, 0.0]),
                    Document(3, "Unrelated", "notes", [0.0, 0.0, 1.0], [0.0, 0.0, 1.0]),
                ],
                generate_vectors=False,
            )

            # 3. The server applies the filter and threshold before paging.
            results = await collection.search(
                vector=[0.0, 1.0, 0.0],
                vector_property_name="image_vector",
                filter=Filter("category", "eq", "reference"),
                score_threshold=0.75,
                top=2,
            )
            async for result in results:
                print(f"{result['record'].title}: {result['score']:.2f}")

            # 4. Vectors are excluded from retrieval unless requested.
            documents = await collection.get([1], include_vectors=True)
            print(f"Text vector: {documents[0].text_vector}")
        finally:
            # Delete only this sample's unique collection, including on errors.
            await collection.ensure_collection_deleted()


if __name__ == "__main__":
    asyncio.run(main())

# Expected output:
# Image guide: 1.00
# Text vector: [1.0, 0.0, 0.0]
