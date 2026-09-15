# MongoDB vector stores

An alpha MongoDB integration for [Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/).
`MongoDBCollection` provides async BSON CRUD and dense-vector search,
`MongoDBStore` shares an official async PyMongo client across collections, and
`MongoDBSettings` defines connection configuration.

## Installation

```bash
pip install agent-framework-mongodb --pre
```

Requires Python 3.10+, PyMongo 4.13.2+, and a MongoDB deployment with
[MongoDB Vector Search](https://www.mongodb.com/docs/vector-search/). Search-index
creation requires the corresponding database permissions.

## Connection

Set `MONGODB_URI` and `MONGODB_DATABASE_NAME`; `MONGODB_APP_NAME` is optional.
Constructors resolve explicit arguments first, then an explicitly selected
`.env` file, then process environment variables. URIs accept `str` or AF
`SecretString` and are unwrapped only for PyMongo.

You can instead inject an `AsyncMongoClient` and pass `database_name`. An
injected client bypasses URI, app-name, and `.env` loading and always remains
caller-owned. Connector-created clients are closed by `close()` or async context
exit. Collections created by a store borrow its already-resolved client.

## Example

```python
import asyncio
from dataclasses import dataclass
from typing import Annotated

from agent_framework import Filter, VectorStoreField, vectorstoremodel
from agent_framework_mongodb import MongoDBStore


@vectorstoremodel(collection_name="articles")
@dataclass
class Article:
    id: Annotated[str, VectorStoreField("key")]
    topic: Annotated[str, VectorStoreField("data", is_indexed=True)]
    text: Annotated[str, VectorStoreField("data")]
    embedding: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


async def main() -> None:
    async with MongoDBStore() as store:
        collection = store.get_collection(Article)
        await collection.ensure_collection_exists()
        await collection.upsert(
            [Article("1", "database", "MongoDB stores BSON documents", [1, 0, 0])],
            generate_vectors=False,
        )
        results = await collection.search(
            vector=[1, 0, 0],
            filter=Filter("topic", "eq", "database"),
        )
        async for result in results:
            print(result["record"].text, result["score"])


asyncio.run(main())
```

## Capabilities and limits

- String, signed 64-bit integer, and BSON `ObjectId` `_id` values retain native
  identity. Only `ObjectId` keys can be generated. Typed `ObjectId` models must
  register an encoder and decoder that preserve `ObjectId`; IDs are never stringified
  or copied to hidden fields.
- Multiple top-level dense-vector fields are supported through one vector-search
  index per field. Use `provider_annotations={"mongodb.index_name": "..."}` to
  select an existing index name. Dimensions must be 1-8192. Metrics are cosine,
  dot product, and Euclidean; returned `vectorSearchScore` values are native
  normalized relevance scores where larger is better.
- `ensure_collection_exists()` creates missing indexes, waits for readiness, and
  validates existing semantic definitions. It never updates or migrates an
  incompatible collection or index. Newly written documents become searchable
  asynchronously, even after an index is queryable.
- Retrieval filters preserve whole-value equality, missing/null, direct array
  membership, boolean/number, and literal text semantics with server-side
  expressions. Collection filters require fields declared as `list` and reject
  mapping and non-list collection operands whose identity BSON cannot preserve.
  Vector prefilters are intentionally narrower: indexed scalar equality, range,
  membership, AND, and OR only. Nested paths, NOT, null/missing, list membership,
  and literal/analyzed text are rejected for vector search.
- Keyword-hybrid search, sparse/binary vectors, provider-side embedding
  generation, and automatic schema migration are not supported.
- ANN defaults `numCandidates` to the MongoDB recommendation of 20 times
  `skip + top`, capped at MongoDB's maximum of 10,000. Explicit values must be
  1-10,000 and at least `skip + top`; larger result windows require exact search.
  The vector stage selects its result window before score thresholding, skip,
  and limit, so selective thresholds can underfill a page. Deep offsets increase
  server cost; result prefixes are never materialized by the connector.
- Every record is fully validated against BSON's signed 64-bit integer and 16 MiB
  document limits before any batch write. PyMongo then chunks bulk writes using
  negotiated server limits. A server error can leave a successful prefix
  (`ordered=True`) or subset (`ordered=False`) persisted.

## Documentation

- [Microsoft Agent Framework documentation](https://learn.microsoft.com/agent-framework/)
- [MongoDB Vector Search documentation](https://www.mongodb.com/docs/vector-search/)
- [PyMongo async documentation](https://pymongo.readthedocs.io/en/stable/api/pymongo/asynchronous/)
- [MongoDB limits and thresholds](https://www.mongodb.com/docs/manual/reference/limits/)
