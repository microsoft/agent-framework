# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-azure-ai-search",
#     "azure-identity",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Annotated
from uuid import uuid4

from agent_framework import Filter, VectorStoreField, vectorstoremodel
from agent_framework.azure import AzureAISearchStore
from azure.identity.aio import AzureCliCredential

"""
Vector and keyword-hybrid search in a disposable Azure AI Search index.

Run from the repository's python directory:
uv run --package agent-framework-azure-ai-search --with azure-identity python \
samples/02-agents/vector_stores/azure_ai_search.py
Use `az login` with Search Service Contributor and Search Index Data Contributor roles.
Set AZURE_SEARCH_ENDPOINT to your search service. Running this sample creates a
uniquely named index, uploads example documents, and deletes that index during
cleanup. Existing indexes are not modified. Vectors are deterministic; no embedding
service is called.

Expected output: vector and hybrid result labels, hotel names, and Azure search scores.
"""


@vectorstoremodel
@dataclass
class Hotel:
    key: Annotated[str, VectorStoreField("key", storage_name="hotel_id")]
    description: Annotated[str, VectorStoreField("data", is_full_text_indexed=True)]
    category: Annotated[str, VectorStoreField("data", is_indexed=True)]
    vector: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


async def main() -> None:
    # 1. Authenticate and create a uniquely named sample index.
    async with (
        AzureCliCredential() as credential,
        AzureAISearchStore(endpoint=os.environ["AZURE_SEARCH_ENDPOINT"], credential=credential) as store,
    ):
        collection = store.get_collection(Hotel, collection_name=f"af-vector-sample-{uuid4().hex}")
        # Create (not update) to ensure cleanup can only delete the index this run owns.
        await store.index_client.create_index(collection.build_index())
        try:
            # 2. Preserve precomputed vectors during a batch upsert.
            await collection.upsert(
                [
                    Hotel("1", "Quiet hotel near the park", "quiet", [1.0, 0.0, 0.0]),
                    Hotel("2", "Hotel with a lively music venue", "nightlife", [0.0, 1.0, 0.0]),
                ],
                generate_vectors=False,
            )
            for _ in range(60):
                if len(await collection.get(["1", "2"])) == 2:
                    break
                await asyncio.sleep(0.5)
            else:
                raise TimeoutError("Documents did not become searchable within 30 seconds.")

            # 3. Execute a portable filter natively, excluding vectors from the response.
            print("Vector results:")
            async for result in await collection.search(
                vector=[1.0, 0.0, 0.0],
                filter=Filter("category", "eq", "quiet"),
            ):
                print(result["record"].description, result["score"])

            # 4. Combine a text query with a supplied vector using Azure's native RRF.
            print("Hybrid results:")
            async for result in await collection.search(
                "hotel",
                vector=[1.0, 0.0, 0.0],
                search_type="keyword_hybrid",
                additional_property_name="description",
            ):
                print(result["record"].description, result["score"])
        finally:
            # 5. Delete only the uniquely named index created above.
            await collection.ensure_collection_deleted()


if __name__ == "__main__":
    asyncio.run(main())
