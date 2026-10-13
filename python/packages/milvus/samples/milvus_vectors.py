# Copyright (c) Microsoft. All rights reserved.

"""Store and search dense vectors in a disposable Milvus collection.

Run from python/:
    export MILVUS_URI=http://localhost:19530   # or a local ".db" path for Milvus Lite
    uv run --package agent-framework-milvus python packages/milvus/samples/milvus_vectors.py

Use a development server or a local Milvus Lite file, not production. No embedding
model, inference service, or OpenAI credentials are used: the vectors are deliberately
small and deterministic.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Annotated
from uuid import uuid4

from agent_framework import Filter, VectorStoreField, vectorstoremodel

from agent_framework_milvus import MilvusStore


@vectorstoremodel
@dataclass
class Document:
    id: Annotated[int, VectorStoreField("key")]
    title: Annotated[str, VectorStoreField("data", storage_name="document_title")]
    category: Annotated[str, VectorStoreField("data")]
    embedding: Annotated[
        list[float] | None,
        VectorStoreField("vector", dimensions=3, distance_function="cosine_similarity"),
    ] = None


async def main() -> None:
    # 1. The store owns its client. Child collections borrow it.
    async with MilvusStore(uri=os.environ.get("MILVUS_URI", "http://localhost:19530")) as store:
        collection = store.get_collection(Document, collection_name=f"af_milvus_sample_{uuid4().hex}")
        await collection.ensure_collection_exists()
        try:
            # 2. Preserve supplied vectors instead of generating embeddings.
            await collection.upsert(
                [
                    Document(1, "Billing guide", "reference", [1.0, 0.0, 0.0]),
                    Document(2, "Image guide", "reference", [0.0, 1.0, 0.0]),
                    Document(3, "Unrelated", "notes", [0.0, 0.0, 1.0]),
                ],
                generate_vectors=False,
            )

            # 3. Vector search with a portable filter translated to a Milvus expression.
            results = await collection.search(
                vector=[1.0, 0.0, 0.0],
                filter=Filter("category", "eq", "reference"),
                top=2,
            )
            async for result in results:
                print(f"{result['record'].title}: {result['score']:.2f}")

            # 4. Vectors are excluded from retrieval unless requested.
            documents = await collection.get([1], include_vectors=True)
            print(f"Embedding: {documents[0].embedding}")
        finally:
            # Delete only this sample's unique collection, including on errors.
            await collection.ensure_collection_deleted()


if __name__ == "__main__":
    asyncio.run(main())

# Expected output (scores are cosine similarity, larger is closer):
# Billing guide: 1.00
# Image guide: 0.00
# Embedding: [1.0, 0.0, 0.0]
