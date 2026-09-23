# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated, Any

from agent_framework import (
    Agent,
    Filter,
    InMemoryCollection,
    Param,
    VectorCollectionContextProvider,
    VectorStoreField,
    create_vector_search_tool,
    vectorstoremodel,
)
from agent_framework.openai import OpenAIChatClient, OpenAIEmbeddingClient
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

"""
This sample demonstrates replacing the default collection search tool with
multiple searches that expose different inputs and result detail.

The context provider disables its default CRUD and search tools, then adds a
generic hotel discovery tool and a hotel-detail tool. Both tools use the same
user-defined collection while keeping their own descriptions, filters, result
mappers, and approval settings.

Set `OPENAI_API_KEY` before running this sample.
"""


@vectorstoremodel(collection_name="hotels")
class Hotel(BaseModel):
    """A hotel record with summary and detail fields."""

    hotel_id: Annotated[str, VectorStoreField("key")]
    name: Annotated[str, VectorStoreField("data", is_full_text_indexed=True)]
    city: Annotated[str, VectorStoreField("data", is_indexed=True)]
    summary: Annotated[str, VectorStoreField("data", is_full_text_indexed=True)]
    details: Annotated[str, VectorStoreField("data")]
    summary_vector: Annotated[
        list[float] | str | None,
        VectorStoreField("vector", dimensions=1536, distance_function="cosine_similarity"),
    ] = None

    def model_post_init(self, context: Any) -> None:
        """Use the summary as the embedding input when no vector is supplied."""
        if self.summary_vector is None:
            self.summary_vector = self.summary


async def main() -> None:
    """Expose two differently shaped search tools for one collection."""
    collection: InMemoryCollection[str, Hotel] = InMemoryCollection(
        Hotel,
        embedding_generator=OpenAIEmbeddingClient(
            model="text-embedding-3-small",
        ),
    )
    await collection.ensure_collection_exists()
    await collection.upsert([
        Hotel(
            hotel_id="hotel-1",
            name="Harbor View",
            city="Lisbon",
            summary="A waterfront Lisbon hotel with breakfast and a pool.",
            details="Includes airport transfers, late checkout, a rooftop pool, and breakfast from 7:00.",
        ),
        Hotel(
            hotel_id="hotel-2",
            name="Old Town Rooms",
            city="Lisbon",
            summary="A quiet guesthouse in Lisbon's historic center.",
            details="Includes breakfast, luggage storage, and self-service check-in. There is no pool.",
        ),
        Hotel(
            hotel_id="hotel-3",
            name="Market Square",
            city="Seattle",
            summary="A central Seattle hotel for short business stays.",
            details="Includes a workspace, gym access, and express checkout.",
        ),
    ])

    # 1. The discovery tool returns a compact result suitable for broad searches.
    discovery_tool = create_vector_search_tool(
        collection,
        name="search_hotels",
        description="Find hotels from a natural-language request and return a short summary.",
        top=3,
        result_mapper=lambda result: (
            f"{result['record'].hotel_id}: {result['record'].name} "
            f"({result['record'].city}) - {result['record'].summary}"
        ),
    )

    # 2. The detail tool exposes a required hotel_id filter and returns fields
    #    intentionally omitted from the discovery result.
    details_tool = create_vector_search_tool(
        collection,
        name="search_hotel_details",
        description="Get detailed information for a known hotel_id.",
        filter=Filter(
            "hotel_id",
            "eq",
            Param("hotel_id", str, description="The hotel_id returned by search_hotels.", required=True),
        ),
        top=1,
        result_mapper=lambda result: (
            f"{result['record'].name} ({result['record'].hotel_id}): {result['record'].details}"
        ),
    )

    # 3. Disable every generated tool and provide only the two tailored searches.
    collection_context = VectorCollectionContextProvider(
        collection,
        # This process-local collection contains records for only this sample.
        scope_filter=None,
        include_upsert_tool=False,
        include_get_tool=False,
        include_delete_tool=False,
        include_search_tool=False,
        additional_search_tools=[discovery_tool, details_tool],
    )

    async with Agent(
        client=OpenAIChatClient(model="gpt-5.4-nano"),
        name="HotelAssistant",
        instructions=("Use search_hotels for discovery. Use search_hotel_details only after you know a hotel_id."),
        context_providers=[collection_context],
    ) as agent:
        session = agent.create_session()

        for prompt in (
            "Find a Lisbon hotel with a pool.",
            "Give me the full details for that hotel.",
        ):
            response = await agent.run(prompt, session=session)
            print(f"User: {prompt}")
            print(f"Assistant: {response.text}\n")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
Assistant: Harbor View (hotel-1) is a waterfront Lisbon hotel with breakfast and a pool.
Assistant: Harbor View includes airport transfers, late checkout, a rooftop pool, and breakfast from 7:00.
"""
