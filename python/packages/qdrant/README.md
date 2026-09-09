# Qdrant vector stores

An alpha Qdrant integration for Microsoft Agent Framework. `QdrantCollection`
provides async batch storage and dense-vector search, `QdrantStore` manages
collection clients, and `QdrantSettings` handles connection configuration.

## Installation

```bash
pip install agent-framework-qdrant --pre
```

Requires Python 3.10+ and Qdrant server 1.16.2+. The official async
`qdrant-client` SDK is installed automatically.

## Connection settings

Set `QDRANT_URL` to your server URL and optionally `QDRANT_API_KEY` for
authentication. If no URL is supplied, the SDK defaults to localhost.

Both constructors resolve settings from explicit `url`/`api_key` arguments,
then an optional `env_file_path`, then environment variables. API keys accept
`str` or AF `SecretString` and are unwrapped only when creating the SDK client.

You can instead pass a configured `AsyncQdrantClient` as `async_client` for
advanced SDK options. Supplied clients bypass settings loading and remain
caller-owned unless `managed_client=True`; connector-created clients are closed
on async context exit.

## Usage

This example stores and searches a record using a supplied vector, without
an embedding service:

```python
import asyncio
from dataclasses import dataclass
from typing import Annotated

from agent_framework import Filter, VectorStoreField, vectorstoremodel
from agent_framework_qdrant import QdrantStore


@vectorstoremodel
@dataclass
class Document:
    id: Annotated[int, VectorStoreField("key")]
    title: Annotated[str, VectorStoreField("data")]
    embedding: Annotated[
        list[float] | None, VectorStoreField("vector", dimensions=3)
    ] = None


async def main() -> None:
    async with QdrantStore() as store:
        collection = store.get_collection(Document, collection_name="documents")
        await collection.ensure_collection_exists()
        await collection.upsert(
            [Document(1, "Hello Qdrant", [1.0, 0.0, 0.0])],
            generate_vectors=False,
        )
        results = await collection.search(
            vector=[1.0, 0.0, 0.0],
            filter=Filter("title", "eq", "Hello Qdrant"),
            top=3,
        )
        async for result in results:
            print(result["record"].title, result["score"])


asyncio.run(main())
```

Use `get([key], include_vectors=True)` to retrieve vectors, or `delete([key])`
to remove records. Without `include_vectors=True`, retrieval omits vectors.
Batch writes can partially succeed if the server reports an error.
Tuple payload values, including nested tuples, are stored as JSON arrays without
modifying the input records. Typed models restore tuples through their registered decoder.

Ordered retrieval (`order_by`) is not supported. Unordered retrieval uses bounded
scroll pages without retaining the skipped prefix.

## Capabilities and limits

- Keys must be unsigned 64-bit integers or UUIDs (`str` or `uuid.UUID`).
  Arbitrary strings and automatically generated keys are not supported.
- Multiple named dense-vector fields are supported. Binary, sparse,
  multivector-fusion, and keyword-hybrid search are not supported.
- Vector fields must declare a floating-point element type. Qdrant stores dense
  vectors as float32; integer-valued inputs remain valid for floating-point fields.
- Scores and thresholds use native Qdrant units. The default is cosine
  similarity; dot product, Euclidean distance, and Manhattan distance are also supported.
- Portable filters require a server. SDK local mode supports unfiltered storage
  and dense search, but rejects portable filters and does not build payload indexes.
- Filters support scalar comparisons, collection membership, and AND/OR/NOT.
  Literal text, nested-path, and array/object-equality filters are unsupported.
  Numeric range and mixed numeric membership operands are limited to
  `+/- (2**53-1)`; integer equality supports the full signed 64-bit range.

## Documentation

- [Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/)
- [Qdrant documentation](https://qdrant.tech/documentation/)
- [Points and IDs](https://qdrant.tech/documentation/manage-data/points/)
- [Search and metrics](https://qdrant.tech/documentation/search/search/)
- [Filtering](https://qdrant.tech/documentation/search/filtering/)
