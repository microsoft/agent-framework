# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import os
from typing import Annotated, Any, Literal
from urllib.request import urlopen

from agent_framework import (
    Agent,
    Filter,
    FilterGroup,
    InMemoryCollection,
    Param,
    VectorStoreField,
    create_vector_search_tool,
    vectorstoremodel,
)
from agent_framework.openai import OpenAIChatClient, OpenAIEmbeddingClient
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

load_dotenv()

"""
This sample demonstrates an agent using model-set filter values in a search tool.

This uses the hotel model and dataset based on the Azure AI Search vector sample dataset.
`Param` values define the exact filter parameters exposed to the model. Their native Python types and
constraints become JSON Schema without requiring another Pydantic parameter model.

Set `OPENAI_API_KEY` before starting the sample.
"""

HOTELS_URL = "https://raw.githubusercontent.com/Azure/azure-search-vector-samples/refs/heads/main/data/hotels.json"


def to_pascal(name: str) -> str:
    """Convert a Python field name to the dataset's PascalCase naming."""
    return "".join(part.capitalize() for part in name.split("_"))


class Room(BaseModel):
    """Describe one hotel room type."""

    type: str
    description: str
    description_fr: str = Field(alias="Description_fr")
    base_rate: float
    bed_options: str
    sleeps_count: int
    smoking_allowed: bool
    tags: list[str]

    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True, extra="ignore")


class Address(BaseModel):
    """Describe a hotel address."""

    street_address: str
    city: str | None
    state_province: str | None
    postal_code: str | None
    country: str | None

    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True, extra="ignore")


@vectorstoremodel(collection_name="hotels")
class Hotel(BaseModel):
    """Represent one hotel from the Azure AI Search sample dataset."""

    hotel_id: Annotated[str, VectorStoreField("key")]
    hotel_name: Annotated[str | None, VectorStoreField("data")] = None
    description: Annotated[str, VectorStoreField("data", is_full_text_indexed=True)]
    description_vector: Annotated[
        list[float] | str | None,
        VectorStoreField("vector", dimensions=1536, distance_function="cosine_similarity"),
    ] = None
    description_fr: Annotated[
        str,
        Field(alias="Description_fr"),
        VectorStoreField("data", is_full_text_indexed=True),
    ]
    description_fr_vector: Annotated[
        list[float] | str | None,
        VectorStoreField("vector", dimensions=1536, distance_function="cosine_similarity"),
    ] = None
    category: Annotated[str, VectorStoreField("data")]
    tags: Annotated[list[str], VectorStoreField("data", is_indexed=True)]
    parking_included: Annotated[bool | None, VectorStoreField("data")] = None
    last_renovation_date: Annotated[str | None, VectorStoreField("data")] = None
    rating: Annotated[float, VectorStoreField("data")]
    location: Annotated[dict[str, Any], VectorStoreField("data")]
    address: Annotated[Address, VectorStoreField("data")]
    rooms: Annotated[list[Room], VectorStoreField("data")]

    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True, extra="ignore")

    def model_post_init(self, context: Any) -> None:
        """Use the descriptions as embedding inputs when vectors are absent."""
        if self.description_vector is None:
            self.description_vector = self.description
        if self.description_fr_vector is None:
            self.description_fr_vector = self.description_fr


def load_hotels() -> list[Hotel]:
    """Load the existing Azure AI Search hotel dataset."""
    with urlopen(HOTELS_URL, timeout=60) as response:  # nosec B310 - fixed HTTPS sample URL
        records = json.loads(response.read())
    return [Hotel.model_validate(record) for record in records]


async def main() -> None:
    """Create an in-memory hotel search tool and give it to an agent."""
    api_key = os.environ["OPENAI_API_KEY"]
    collection: InMemoryCollection[str, Hotel] = InMemoryCollection(
        Hotel,
        embedding_generator=OpenAIEmbeddingClient(
            model="text-embedding-3-small",
            api_key=api_key,
        ),
    )
    await collection.ensure_collection_exists()

    # 1. Load the hotel records.
    hotels = await asyncio.to_thread(load_hotels)
    await collection.upsert(hotels)

    # 2. Param values become optional model-visible filter arguments.
    # When the allowed values are known, use Literal so the tool schema exposes
    # them as an enum.
    category = Param(
        "category",
        Literal["Boutique", "Budget", "Extended-Stay", "Luxury", "Resort and Spa", "Suite"],
        description="Only return hotels in this category.",
    )
    min_rating = Param(
        "min_rating",
        float,
        description="The minimum guest rating.",
        minimum=0,
        maximum=5,
    )
    tool = create_vector_search_tool(
        collection,
        description="Search the hotel dataset, optionally filtering by category and minimum rating.",
        filter=FilterGroup(
            "and",
            (
                Filter("category", "eq", category),
                Filter("rating", "gte", min_rating),
            ),
        ),
        result_mapper=lambda result: (
            f"(hotel_id: {result['record'].hotel_id}) {result['record'].hotel_name} "
            f"(rating {result['record'].rating}) - {result['record'].description}. "
            f"Address: {result['record'].address.city}, {result['record'].address.country}."
        ),
    )

    # 3. The agent chooses whether to supply the exposed category and minimum-rating filters.
    async with Agent(
        client=OpenAIChatClient(
            model="gpt-5.4-nano",
            api_key=api_key,
        ),
        name="HotelAgent",
        instructions=(
            "Always use the search tool to answer hotel questions. "
            "Use category and minimum rating filters when the request provides them. "
            "Include the hotel_id in the answer."
        ),
        tools=[tool],
    ) as agent:
        result = await agent.run("Find a resort and spa with a rating of at least 4.")
        print(result)


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
The Grand Gaming Resort (hotel_id: 20) is a Resort and Spa rated 4.2.
"""
