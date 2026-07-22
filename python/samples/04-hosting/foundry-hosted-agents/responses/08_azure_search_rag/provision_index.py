# Copyright (c) Microsoft. All rights reserved.

"""Provision the Azure AI Search index used by this sample.

Creates (or updates) the ``contoso-outdoors`` index with the schema documented
in README.md and seeds it with three Contoso Outdoors documents containing
unique canary tokens. Safe to re-run; existing documents are merged-or-uploaded.

Usage (from this directory, with the venv activated and ``az login`` done):

    python provision_index.py

Required env vars (also read from a local ``.env`` file if present):

    AZURE_SEARCH_ENDPOINT      e.g. https://<your-search>.search.windows.net
    AZURE_SEARCH_INDEX_NAME    e.g. contoso-outdoors

Your identity needs ``Search Service Contributor`` (to create the index) and
``Search Index Data Contributor`` (to upload documents) on the search service.
"""

import asyncio
import os

from azure.core.exceptions import ResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchableField,  # pyright: ignore[reportUnknownVariableType]
    SearchFieldDataType,
    SearchIndex,
    SimpleField,  # pyright: ignore[reportUnknownVariableType]
)
from dotenv import load_dotenv

DOCUMENTS: list[dict[str, str]] = [
    {
        "id": "return-policy",
        "sourceName": "Contoso Outdoors Return Policy",
        "sourceLink": "https://contoso.com/policies/returns",
        "content": (
            "Customers may return any item within 30 days of delivery. Items should be "
            "unused and include original packaging. Refunds are issued to the original "
            "payment method within 5 business days of inspection. As a thank you, every "
            "accepted return ships back with a complimentary Contoso TrailRunner sticker "
            "pack, item code TR-CANARY-7821."
        ),
    },
    {
        "id": "shipping-guide",
        "sourceName": "Contoso Outdoors Shipping Guide",
        "sourceLink": "https://contoso.com/help/shipping",
        "content": (
            "Standard shipping is free on orders over $50 and typically arrives in 3-5 "
            "business days within the continental United States. Expedited options are "
            "available at checkout. Use promo code SHIP-CANARY-4493 at checkout for a "
            "one-time free overnight upgrade on your first order."
        ),
    },
    {
        "id": "tent-care",
        "sourceName": "TrailRunner Tent Care Instructions",
        "sourceLink": "https://contoso.com/manuals/trailrunner-tent",
        "content": (
            "Clean the tent fabric with lukewarm water and a non-detergent soap. Allow "
            "it to air dry completely before storage and avoid prolonged UV exposure to "
            "extend the lifespan of the waterproof coating. Replacement waterproofing "
            "kits are stocked under SKU TENT-CANARY-9067."
        ),
    },
]


def build_index(name: str) -> SearchIndex:
    return SearchIndex(
        name=name,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.STRING, key=True, filterable=True),
            SearchableField(name="content", type=SearchFieldDataType.STRING, analyzer_name="standard.lucene"),
            SimpleField(name="sourceName", type=SearchFieldDataType.STRING, filterable=True, retrievable=True),
            SimpleField(name="sourceLink", type=SearchFieldDataType.STRING, retrievable=True),
        ],
    )


async def main() -> None:
    load_dotenv()

    endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
    index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]

    async with (
        DefaultAzureCredential() as credential,
        SearchIndexClient(endpoint=endpoint, credential=credential) as index_client,
        SearchClient(endpoint=endpoint, index_name=index_name, credential=credential) as search_client,
    ):
        index = build_index(index_name)
        try:
            await index_client.get_index(index_name)
            print(
                f"Index '{index_name}' already exists; leaving schema as-is "
                "(delete the index manually to change the schema)."
            )
        except ResourceNotFoundError:
            print(f"Creating index '{index_name}'...")
            await index_client.create_index(index)

        print(f"Uploading {len(DOCUMENTS)} document(s)...")
        results = await search_client.merge_or_upload_documents(documents=DOCUMENTS)  # type: ignore[arg-type]
        failed = [(r.key, r.error_message) for r in results if not r.succeeded]
        if failed:
            raise RuntimeError(f"Failed to upload documents: {failed}")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
