# Agent Framework PostgreSQL / pgvector

Store and search vector records in PostgreSQL with this alpha integration for
[Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/).
The package uses Psycopg 3 and the official pgvector Python adapter.

- **`PostgresCollection`** provides batch upsert, retrieval, deletion, and vector similarity search.
- **`PostgresStore`** creates collection clients that share a connection pool.
- **`PostgresSettings`** describes connection settings resolved by Agent Framework.

## Installation

```bash
pip install agent-framework-postgres --pre
```

Requires Python 3.10+, PostgreSQL 13+, and pgvector 0.8.0+.
Import the connector directly from `agent_framework_postgres`.

## Connection setup

Have your database administrator install and enable the `vector` extension and
provide an existing schema. The extension must be visible through the connection's
`search_path`. The connector never creates schemas, enables extensions, or changes
server-wide configuration. `ensure_collection_exists()` explicitly creates the
table and requested indexes; it requires the corresponding permissions and does
not migrate existing tables.

Set `POSTGRES_CONNECTION_STRING` to a PostgreSQL URI or Psycopg conninfo string,
or pass `connection_string` to either constructor. Both accept a string or AF
`SecretString`. Settings precedence is **explicit argument > selected `.env`
file > environment**. Select a file with `env_file_path` and optional
`env_file_encoding`; missing or empty connection strings are rejected.
The `schema` argument defaults to `public`.

A connector-created pool is closed by `close()` or an async context manager.
Alternatively, inject an open Psycopg `AsyncConnection` or `AsyncConnectionPool`
using `client`; it remains caller-owned and bypasses settings loading.
Injected clients cannot be combined with connection-string or `.env` options.
Collections created by a store borrow its pool, so keep the store open while
using them.

## Example

With `POSTGRES_CONNECTION_STRING` configured, create a typed collection and
search using precomputed embeddings:

```python
import asyncio
from dataclasses import dataclass
from typing import Annotated

from agent_framework import Filter, VectorStoreField, vectorstoremodel
from agent_framework_postgres import PostgresStore


@vectorstoremodel(collection_name="articles")
@dataclass
class Article:
    id: Annotated[str, VectorStoreField("key")]
    text: Annotated[str, VectorStoreField("data")]
    embedding: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


async def main() -> None:
    async with PostgresStore() as store:
        collection = store.get_collection(Article)
        await collection.ensure_collection_exists()
        await collection.upsert(
            [
                Article("1", "PostgreSQL supports vectors", [1, 0, 0]),
                Article("2", "A travel journal", [0, 1, 0]),
            ],
            generate_vectors=False,
        )
        results = await collection.search(
            vector=[1, 0, 0],
            filter=Filter("text", "contains_text", "PostgreSQL"),
            score_threshold=0.25,
            top=3,
        )
        async for result in results:
            print(result["record"].text, result["score"])


if __name__ == "__main__":
    asyncio.run(main())
```

Pass `generate_vectors=False` to preserve supplied embeddings. To generate them
locally, configure an `embedding_generator`. Retrieval excludes embeddings by
default; use `include_vectors=True` to return them.

## Capabilities and limits

The connector supports typed models, string/integer/UUID keys (including generated
keys), multiple nullable vector columns, storage aliases, and database-side
filters and paging. Batch writes are transactional; an existing transaction on
an injected connection remains under the caller's commit control.

Vector fields support `float`, `float32`, and `float16` declarations. PostgreSQL
`vector` storage uses 32-bit floats; `float16` defaults to 16-bit `halfvec`.
The `postgres.vector_type` provider annotation explicitly selects either storage
type. Ordinary Python floats and integer-valued elements are accepted and rounded
to the selected precision; declared `int` and `float64` vector fields are rejected.

Storage precision does not determine the model's Python scalar type. The default
decoder returns ordinary Python floats: use `list[float]` annotations even with
explicit `float16` or `float32` field metadata. Models annotated with
`list[numpy.float16]` or `list[numpy.float32]` require a custom `decoder` passed to
`vectorstoremodel` or `register_vectorstoremodel`. That decoder must reconstruct
each component with the declared NumPy scalar type and handle omitted vector
fields when `include_vectors=False`. NumPy is not a connector runtime dependency.

Exact search is the default. HNSW and IVFFlat are optional approximate indexes;
selective filters can reduce their recall. Use
`operation_options={"exact": True}` when complete recall is required.
`exact=False` requires an HNSW or IVFFlat field. Result metadata's `approximate`
flag identifies ANN-permitted query mode, not proof that PostgreSQL used an ANN
index.
IVFFlat needs data before index creation: first call
`ensure_collection_exists(operation_options={"create_indexes": False})`, load
records, then call `ensure_collection_exists()` again.
Storage supports up to 16,000 dimensions; ANN indexes support up to 2,000 for
`vector` and 4,000 for `halfvec`.

Scores use the selected metric's units, not probabilities. The default is cosine
distance, where lower is better and `score_threshold` is a maximum. Cosine
similarity and dot product use minimum thresholds; negative dot product, L2, and
L1 distances use maximum thresholds. IVFFlat does not support L1.

Keyword/hybrid/full-text search, sparse/binary vectors, nested filter paths,
schema migration, and server-side embedding generation are not supported.

## Documentation

- [Microsoft Agent Framework documentation](https://learn.microsoft.com/agent-framework/)
- [PostgreSQL documentation](https://www.postgresql.org/docs/current/)
- [pgvector setup, indexes, and distance functions](https://github.com/pgvector/pgvector)
- [Psycopg connection pools](https://www.psycopg.org/psycopg3/docs/advanced/pool.html)
