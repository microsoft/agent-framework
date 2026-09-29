# /// script
# dependencies = [
#   "agent-framework-core>=1.19.0,<2",
#   "agent-framework-mongodb>=1.0.0a260909,<2",
#   "agent-framework-openai>=1.14.4,<2",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Annotated
from uuid import uuid4

from agent_framework import (
    Agent,
    VectorCollectionContextProvider,
    VectorStoreField,
    vectorstoremodel,
)
from agent_framework.openai import OpenAIChatClient, OpenAIEmbeddingClient

from agent_framework_mongodb import MongoDBCollection, MongoDBStore

"""Answer questions from a MongoDB Atlas collection (retrieval-augmented generation).

``VectorCollectionContextProvider`` turns any vector collection into agent tools, so a
MongoDB collection is grounded through the same path as any other store, with no
retrieval library beyond Agent Framework itself.

Set ``MONGODB_URI`` and ``MONGODB_DATABASE_NAME`` for the deployment, and ``OPENAI_API_KEY``
for the embeddings and the agent. Vector search requires Atlas or Atlas Local; a standalone
``mongod`` cannot serve the query.

The collection name is unique per run and is deleted during cleanup, so existing
collections are untouched.
"""


@vectorstoremodel
@dataclass
class Article:
    """A support article the agent can retrieve but not modify."""

    id: Annotated[str, VectorStoreField("key")]
    # MongoDB rejects `is_full_text_indexed`; it has no Search text index or
    # keyword-hybrid support. Use `is_indexed` for metadata you want to filter on.
    text: Annotated[str, VectorStoreField("data")]
    category: Annotated[str, VectorStoreField("data", is_indexed=True)]
    text_vector: Annotated[
        list[float] | str | None,
        VectorStoreField("vector", dimensions=1536, distance_function="cosine_similarity"),
    ] = None

    def __post_init__(self) -> None:
        """Embed the article body when no vector is supplied."""
        if self.text_vector is None:
            self.text_vector = self.text


async def wait_until_searchable(collection: MongoDBCollection[str, Article], probe: str, expected: int) -> None:
    """Block until every newly written article is returned by vector search.

    MongoDB indexes new documents asynchronously, so a search issued straight after
    `upsert` can legitimately return nothing even though the index is queryable. A
    production ingestion path needs the same allowance.

    Vector search returns nearest neighbours rather than matches above a threshold, so
    the probe text only has to be non-empty; counting the results is what establishes
    that the whole batch is visible.
    """
    for _ in range(30):
        results = await collection.search(values=probe, top=expected)
        if len([record async for record in results]) >= expected:
            return
        await asyncio.sleep(2)
    raise TimeoutError(f"Only part of the batch became searchable; expected {expected} articles.")


async def main() -> None:
    articles = [
        Article("refunds", "Refunds are issued to the original payment method within five business days.", "billing"),
        Article("seats", "Team plans may add seats at any time; the next invoice is prorated.", "billing"),
        Article("sso", "Single sign-on is configured from the admin console under Security.", "account"),
    ]

    # 1. MongoDBStore resolves the URI and database through MongoDBSettings.
    async with MongoDBStore() as store:
        collection = store.get_collection(
            Article,
            collection_name=f"af_rag_{uuid4().hex}",
            embedding_generator=OpenAIEmbeddingClient(model="text-embedding-3-small"),
        )
        try:
            # 2. Create the collection and its Atlas vectorSearch index, then seed the
            #    knowledge base. Passing strings in the vector field lets upsert
            #    generate the embeddings.
            await collection.ensure_collection_exists()
            await collection.upsert(articles)
            await wait_until_searchable(collection, probe="support article", expected=len(articles))

            # 3. Expose retrieval only. The agent grounds its answers on the collection
            #    and cannot write to it, which is the usual shape for RAG.
            knowledge_base = VectorCollectionContextProvider(
                collection,
                scope_filter=None,
                include_upsert_tool=False,
                include_get_tool=False,
                include_delete_tool=False,
            )

            async with Agent(
                client=OpenAIChatClient(model="gpt-5.4-nano"),
                name="SupportAssistant",
                instructions=(
                    "Answer using the support articles returned by the search tool. "
                    "If the articles do not cover the question, say so instead of guessing."
                ),
                context_providers=[knowledge_base],
            ) as agent:
                session = agent.create_session()
                for question in (
                    "How long does a refund take?",
                    "Can we add more seats mid-cycle?",
                ):
                    response = await agent.run(question, session=session)
                    print(f"User: {question}")
                    print(f"Assistant: {response.text}\n")
        finally:
            await collection.ensure_collection_deleted()


if __name__ == "__main__":
    asyncio.run(main())


# Expected output resembles:
# User: How long does a refund take?
# Assistant: Refunds are issued to the original payment method within five business days.
#
# User: Can we add more seats mid-cycle?
# Assistant: Yes. Team plans may add seats at any time; the next invoice is prorated.
