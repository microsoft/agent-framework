# Copyright (c) Microsoft. All rights reserved.
# /// script
# requires-python = ">=3.10"
# dependencies = ["agent-framework-gemini"]
# ///

"""Search local images with a text query using Gemini Embedding 2 and an Agent.

Requires ``GOOGLE_MODEL`` and ``GOOGLE_API_KEY`` for the Developer API, or the
Enterprise project, location, and credential settings. Pass local PNG or JPEG
image paths and a natural-language ``--query``. The in-memory collection is for
demonstration; use a persistent vector store for production data.
"""

import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
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
from google.genai import types

load_dotenv()

_EMBEDDING_DIMENSIONS = 768
_IMAGE_MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


@vectorstoremodel(collection_name="gemini-image-search")
@dataclass
class IndexedImage:
    image_id: Annotated[str, VectorStoreField("key")]
    path: Annotated[str, VectorStoreField("data")]
    vector: Annotated[
        list[float] | None,
        VectorStoreField("vector", dimensions=_EMBEDDING_DIMENSIONS, distance_function="cosine_similarity"),
    ] = None


async def main(image_paths: Sequence[Path], query: str) -> None:
    """Index image vectors without task instructions, then search by a text query."""
    embeddings = GeminiEmbeddingClient()
    collection: InMemoryCollection[str, IndexedImage] = InMemoryCollection(
        IndexedImage,
        embedding_generator=embeddings,
    )
    try:
        await collection.ensure_collection_exists()

        # 1. Media inputs have no task prefix. Store their vectors explicitly.
        records: list[IndexedImage] = []
        for image_path in image_paths:
            mime_type = _IMAGE_MEDIA_TYPES.get(image_path.suffix.lower())
            if mime_type is None:
                raise ValueError(f"Expected a PNG or JPEG image: {image_path}")
            image_part = types.Part.from_bytes(data=image_path.read_bytes(), mime_type=mime_type)
            generated = await embeddings.get_embeddings([image_part], options={"dimensions": _EMBEDDING_DIMENSIONS})
            records.append(IndexedImage(str(image_path), str(image_path), generated[0].vector))
        await collection.upsert(records, generate_vectors=False)

        # 2. The helper supplies the query task; Core adds the field dimensions.
        search_images = create_vector_search_tool(
            collection,
            name="search_images",
            description="Find images matching a text description and return their file paths.",
            top=3,
            result_mapper=lambda result: result["record"].path,
            embeddings_options={"task_type": "RETRIEVAL_QUERY"},
        )
        async with Agent(
            client=GeminiChatClient(),
            name="ImageSearchAssistant",
            instructions=(
                "Use search_images to find matching images. Return their file paths; do not claim to view them."
            ),
            tools=[search_images],
        ) as agent:
            response = await agent.run(query)
            print(response.text)
    finally:
        await embeddings.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ask a Gemini agent to search local PNG/JPEG images by text.")
    parser.add_argument("images", nargs="+", type=Path, help="Local PNG or JPEG files to index")
    parser.add_argument("--query", required=True, help="The image-search question for the agent")
    args = parser.parse_args()
    asyncio.run(main(args.images, args.query))

"""
Example:
uv run samples/02-agents/providers/gemini/gemini_image_search_agent.py \
  --query "Which image shows a dog?" photos/dog.jpg photos/cat.png

Sample output:
The matching image is photos/dog.jpg.
"""
