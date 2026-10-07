# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated, Any

from agent_framework import (
    Agent,
    InMemoryCollection,
    VectorCollectionContextProvider,
    VectorStoreField,
    vectorstoremodel,
)
from agent_framework.openai import OpenAIChatClient, OpenAIEmbeddingClient
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

"""
This sample demonstrates adding agent-usable vector collection tools through
VectorCollectionContextProvider.

The provider takes a collection with the application's own data model. By
default it adds instructions plus upsert, get, delete, and search tools.
Approval behavior can be configured for all tools or selected tools through
one `approval_mode` argument.

Set `OPENAI_API_KEY` before running this sample.
"""


@vectorstoremodel(collection_name="project-notes")
class ProjectNote(BaseModel):
    """A project note managed by the agent."""

    note_id: Annotated[str, VectorStoreField("key")]
    title: Annotated[str, VectorStoreField("data", is_full_text_indexed=True)]
    body: Annotated[str, VectorStoreField("data", is_full_text_indexed=True)]
    body_vector: Annotated[
        list[float] | str | None,
        VectorStoreField("vector", dimensions=1536, distance_function="cosine_similarity"),
    ] = None

    def model_post_init(self, context: Any) -> None:
        """Use the note body as the embedding input when no vector is supplied."""
        if self.body_vector is None:
            self.body_vector = self.body


async def main() -> None:
    """Give an agent CRUD and search access to a project-note collection."""
    collection: InMemoryCollection[str, ProjectNote] = InMemoryCollection(
        ProjectNote,
        embedding_generator=OpenAIEmbeddingClient(
            model="text-embedding-3-small",
        ),
    )
    await collection.ensure_collection_exists()

    # Omitted mapping entries keep their safe defaults. This sample disables
    # approval for upsert so the scripted interaction can run unattended;
    # delete still requires approval, while get and search remain read-only.
    collection_context = VectorCollectionContextProvider(
        collection,
        # This process-local collection contains records for only this sample.
        scope_filter=None,
        approval_mode={"upsert": "never_require"},
    )

    async with Agent(
        client=OpenAIChatClient(model="gpt-5.4-nano"),
        name="ProjectNotesAssistant",
        instructions="Use the collection tools to manage project notes. Do not invent stored notes.",
        context_providers=[collection_context],
    ) as agent:
        session = agent.create_session()

        for prompt in (
            (
                "Save a note with id release-checklist, title Release checklist, "
                "and body Verify rollback, monitoring, and owner sign-off."
            ),
            "Search the project notes for release readiness checks.",
            "Get the note with id release-checklist.",
        ):
            response = await agent.run(prompt, session=session)
            print(f"User: {prompt}")
            print(f"Assistant: {response.text}\n")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
Assistant: I saved the "Release checklist" note.
Assistant: The release checklist covers rollback, monitoring, and owner sign-off.
Assistant: The note release-checklist is titled "Release checklist".
"""
