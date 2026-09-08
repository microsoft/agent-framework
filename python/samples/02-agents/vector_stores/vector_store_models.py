# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

# Run with: uv run samples/02-agents/vector_stores/vector_store_models.py
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, cast

import msgspec
from agent_framework import (
    VectorStoreCollectionDefinition,
    VectorStoreField,
    register_vectorstoremodel,
    vectorstoremodel,
)
from pydantic import BaseModel

"""This sample demonstrates the choices for defining vector store models.

When you own the model, use the representation that best fits the rest of your
application: a dataclass, Pydantic model, msgspec struct, plain class, or
dictionary. ``@vectorstoremodel`` adds vector store metadata without requiring
the application to adopt one specific modeling library.

When another package or team owns the model, adapt it instead of rewriting it.
Use ``register_vectorstoremodel`` with an explicit definition and codecs for a
model type, or pass a loose collection definition directly for dictionaries
and other schema-less records.

For NumPy vectors and DataFrame row containers, see
[optimized_data_formats.py](optimized_data_formats.py).

The examples are ordered using indicative serialization measurements, but the
right choice depends on validation, memory, interoperability, and the broader
application, not only handler round-trip speed.
"""


# 1. Custom codecs can be registered in two equivalent ways.
# The decorator creates the field definition from annotations and registers it with the codecs.
def encode_legacy_faq(faq: LegacyFaq) -> Mapping[str, Any]:
    """Convert a legacy FAQ to logical vector model fields."""
    return {"id": faq.faq_number, "question": faq.prompt}


def decode_legacy_faq(record: Mapping[str, Any]) -> LegacyFaq:
    """Restore a legacy FAQ from logical vector model fields."""
    return LegacyFaq(faq_number=cast(str, record["faq_number"]), prompt=cast(str, record["prompt"]))


@vectorstoremodel(
    collection_name="legacy-faqs",
    encoder=encode_legacy_faq,
    decoder=decode_legacy_faq,
)
@dataclass
class LegacyFaq:
    faq_number: Annotated[str, VectorStoreField("key", storage_name="id")]
    prompt: Annotated[str, VectorStoreField("data", storage_name="question")]


# The helper performs the same registration when the definition is supplied separately.
@dataclass
class LegacyArticle:
    article_id: int
    heading: str


def encode_legacy_article(article: LegacyArticle) -> Mapping[str, Any]:
    """Convert a legacy article to logical vector model fields."""
    return {"id": str(article.article_id), "title": article.heading}


def decode_legacy_article(record: Mapping[str, Any]) -> LegacyArticle:
    """Restore a legacy article from logical vector model fields."""
    return LegacyArticle(article_id=int(record["id"]), heading=cast(str, record["title"]))


legacy_definition = VectorStoreCollectionDefinition(
    [
        VectorStoreField("key", name="id", storage_name="article_id"),
        VectorStoreField("data", name="title", storage_name="heading"),
    ],
    collection_name="legacy-articles",
)
register_vectorstoremodel(
    LegacyArticle,
    definition=legacy_definition,
    encoder=encode_legacy_article,
    decoder=decode_legacy_article,
)


# 2. Plain dictionaries can be used as models; in that case, we just need the collection-specific definition.
dictionary_definition = VectorStoreCollectionDefinition(
    [
        VectorStoreField("key", name="id"),
        VectorStoreField("data", name="text"),
        VectorStoreField("vector", name="vector", dimensions=3),
    ],
    collection_name="dictionary-records",
)


# 3. Plain classes use their annotated constructor parameters.
@vectorstoremodel(collection_name="notes")
class Note:
    def __init__(
        self,
        note_id: Annotated[str, VectorStoreField("key")],
        text: Annotated[str, VectorStoreField("data")],
    ) -> None:
        self.note_id = note_id
        self.text = text


# 4. msgspec structs use the default registered codec.
@vectorstoremodel(collection_name="documents")
class Document(msgspec.Struct):
    document_id: Annotated[str, VectorStoreField("key")]
    title: Annotated[str, VectorStoreField("data")]
    vector: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


# 5. Dataclasses use the default registered codec.
@vectorstoremodel(collection_name="hotels")
@dataclass
class Hotel:
    hotel_id: Annotated[str, VectorStoreField("key")]
    name: Annotated[str, VectorStoreField("data", is_indexed=True)]
    description: Annotated[
        str | list[float] | None,
        VectorStoreField("vector", dimensions=3, distance_function="cosine_similarity"),
    ] = None


# 6. Pydantic models provide validation with additional round-trip cost.
@vectorstoremodel(collection_name="products")
class Product(BaseModel):
    product_id: Annotated[str, VectorStoreField("key")]
    name: Annotated[str, VectorStoreField("data", is_full_text_indexed=True)]
    vector: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


def main() -> None:
    """Inspect model definitions and registration choices."""
    model_definitions = (
        ("LegacyFaq", cast(VectorStoreCollectionDefinition, vars(LegacyFaq)["__vectorstoremodel_definition__"])),
        ("LegacyArticle", legacy_definition),
        ("dict", dictionary_definition),
        ("Note", cast(VectorStoreCollectionDefinition, vars(Note)["__vectorstoremodel_definition__"])),
        ("Document", cast(VectorStoreCollectionDefinition, vars(Document)["__vectorstoremodel_definition__"])),
        ("Hotel", cast(VectorStoreCollectionDefinition, vars(Hotel)["__vectorstoremodel_definition__"])),
        ("Product", cast(VectorStoreCollectionDefinition, vars(Product)["__vectorstoremodel_definition__"])),
    )
    for model_name, definition in model_definitions:
        print(f"{model_name}: collection={definition.collection_name}, fields={definition.names}")


if __name__ == "__main__":
    main()


"""
Sample output:
LegacyFaq: collection=legacy-faqs, fields=['faq_number', 'prompt']
LegacyArticle: collection=legacy-articles, fields=['id', 'title']
dict: collection=dictionary-records, fields=['id', 'text', 'vector']
Note: collection=notes, fields=['note_id', 'text']
Document: collection=documents, fields=['document_id', 'title', 'vector']
Hotel: collection=hotels, fields=['hotel_id', 'name', 'description']
Product: collection=products, fields=['product_id', 'name', 'vector']
"""
