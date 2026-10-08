# Copyright (c) Microsoft. All rights reserved.
# /// script
# requires-python = ">=3.10"
# dependencies = ["agent-framework-gemini"]
# ///

"""Give an agent a vector search tool that explicitly selects document and query embedding tasks.

Requires ``GOOGLE_MODEL`` and ``GOOGLE_API_KEY`` for the Developer API, or the
Enterprise project, location, and credential settings. The in-memory collection
is for demonstration; use a persistent vector store for production data.
"""

import asyncio
from dataclasses import dataclass
from typing import Annotated

from agent_framework import (
    Agent,
    InMemoryCollection,
    VectorStoreField,
    create_vector_search_tool,
    vectorstoremodel,
)
from agent_framework.gemini import GeminiChatClient, GeminiEmbeddingClient
from dotenv import load_dotenv

load_dotenv()

_EMBEDDING_DIMENSIONS = 768


@vectorstoremodel(collection_name="gemini-reference-notes")
@dataclass
class ReferenceNote:
    id: Annotated[str, VectorStoreField("key")]
    title: Annotated[str, VectorStoreField("data")]
    text: Annotated[str, VectorStoreField("data")]
    vector: Annotated[
        str | list[float] | None,
        VectorStoreField("vector", dimensions=_EMBEDDING_DIMENSIONS, distance_function="cosine_similarity"),
    ] = None


async def main() -> None:
    """Index documents, then let an agent query them using the correct embedding task."""
    embeddings = GeminiEmbeddingClient()
    collection: InMemoryCollection[str, ReferenceNote] = InMemoryCollection(
        ReferenceNote,
        embedding_generator=embeddings,
    )
    try:
        await collection.ensure_collection_exists()
        sources = [
            ("one", "Agent Framework", "Agent Framework builds and orchestrates AI agents."),
            (
                "two",
                "Gemini embedding tasks",
                "Index documents with RETRIEVAL_DOCUMENT; embed search queries with RETRIEVAL_QUERY.",
            ),
        ]

        # 1. Each document's title applies only to its own embedding request.
        for note_id, title, text in sources:
            await collection.upsert(
                [ReferenceNote(note_id, title, text, text)],
                embeddings_options={"task_type": "RETRIEVAL_DOCUMENT", "title": title},
            )

        # 2. The search helper supplies the query task; Core adds the field dimensions.
        search_documents = create_vector_search_tool(
            collection,
            name="search_documents",
            description="Search indexed reference notes for relevant text.",
            top=2,
            result_mapper=lambda item: f"{item['record'].title}: {item['record'].text}",
            embeddings_options={"task_type": "RETRIEVAL_QUERY"},
        )
        async with Agent(
            client=GeminiChatClient(),
            name="ReferenceAssistant",
            instructions="Use search_documents to answer questions about the reference notes. Cite the note title.",
            tools=[search_documents],
        ) as agent:
            response = await agent.run("Which embedding task should I use to search for documents?")
            print(response.text)
    finally:
        await embeddings.close()


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
Use RETRIEVAL_QUERY for search queries (Gemini embedding tasks).
"""
