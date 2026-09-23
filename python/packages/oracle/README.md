# Agent Framework Oracle vector store

An alpha connector for storing and searching native `VECTOR` columns in Oracle
Database 23ai or newer. `OracleCollection` implements async batch CRUD and
vector search; `OracleStore` shares a client across collections; `OracleSettings`
resolves connection configuration through Agent Framework.

## Installation and setup

```bash
pip install agent-framework-oracle --pre
```

Requires Python 3.10+, Oracle Database 23ai or newer with `COMPATIBLE` set to
**23.4.0 or higher**, `python-oracledb` 2.2.x or 3.x, and permission to
create/drop tables in the connected user's schema. The connector uses the
driver's async Thin-mode API; it does not initialize the Thick client or
provision a database.
It does not create or alter schemas, vector indexes, or existing tables.

Set `ORACLE_DSN` (for example `localhost:1521/FREEPDB1`), `ORACLE_USER`, and
`ORACLE_PASSWORD`, or pass `dsn`, `user`, and `password` to either constructor.
Credentials are resolved in order: **explicit argument > selected `.env` file
> process environment**. A `.env` file is read only when `env_file_path` is
specified; `env_file_encoding` overrides UTF-8. `password` accepts `str` or
Agent Framework `SecretString` and is unwrapped only when opening a connection.
Missing or empty credentials are errors.

Alternatively, pass a configured `oracledb.AsyncConnection` or
`oracledb.AsyncConnectionPool` as `client` for advanced authentication. A
supplied client cannot be combined with connection settings and remains
caller-owned. A connector-created pool opens on first use and closes on
`close()` or async context exit. A collection obtained from a store borrows its
client; closing that collection does not close the store. The store must remain
open while its collections are used.

Writes on pooled connections (both connector-owned and caller-supplied pools)
are committed on success and rolled back on failure. Writes to a supplied
`AsyncConnection` are left in the caller's transaction; **the caller must
commit or roll back**. Oracle DDL commits independently of the surrounding
transaction. Batch upserts on a borrowed connection may leave partial pending
work on failure, so roll it back before reuse.

`ensure_collection_exists()` leaves an existing table unchanged and does not
validate its schema; use a matching definition or create a new table. It never
migrates data or changes existing indexes.

## Usage

```python
import asyncio
from dataclasses import dataclass
from typing import Annotated

from agent_framework import Filter, VectorStoreField, vectorstoremodel
from agent_framework_oracle import OracleStore


@vectorstoremodel(collection_name="articles")
@dataclass
class Article:
    id: Annotated[str, VectorStoreField("key")]
    text: Annotated[str, VectorStoreField("data")]
    embedding: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


async def main() -> None:
    async with OracleStore() as store:
        collection = store.get_collection(Article)
        await collection.ensure_collection_exists()
        await collection.upsert([Article("one", "Oracle vector search", [1, 0, 0])], generate_vectors=False)
        results = await collection.search(
            vector=[1, 0, 0], filter=Filter("text", "contains_text", "Oracle"), top=3
        )
        async for result in results:
            print(result["record"].text, result["score"])


asyncio.run(main())
```

Pass `generate_vectors=False` for precomputed vectors, or configure an
`embedding_generator` for local generation. `get()` excludes vector columns by
default; pass `include_vectors=True` to restore them. `get(keys)` preserves
requested key order and duplicates, omitting missing keys; filtered retrieval
supports `top`, `skip`, and `order_by`. Both `get()` and `search()` execute
portable filters and paging in Oracle. The
[runnable sample](https://github.com/microsoft/agent-framework/blob/main/python/packages/oracle/samples/oracle_vectors.py)
creates and deletes a unique test table.

## Capabilities and limits

- A collection is one table in the **current user's schema**. Keys are
  application-provided strings (up to 512 UTF-8 bytes), signed 64-bit integers,
  or UUIDs; automatically generated keys are not supported.
- Multiple nullable native vector columns are supported. Vector fields may
  declare `float`/`float32` (Oracle `FLOAT32`), `float64` (`FLOAT64`), or `int8`
  (`INT8`); omitted element types use `FLOAT32`. Dimensions must be 1–65535.
  Supplied vectors must be dense finite numeric sequences with the declared
  dimensions. Binary and sparse vectors are not supported.
- Scalar data fields support `str` (up to 4000 UTF-8 bytes), `int` (signed
  64-bit), `float` (`BINARY_DOUBLE`), and `bool` (stored as `NUMBER(1,0)`).
  Oracle converts empty strings to `NULL`, so this connector rejects empty
  string **values** rather than changing their meaning. JSON fields, nested
  paths, provider annotations, data/full-text/vector indexes, and schema
  migration are not supported.
- Search uses Oracle `VECTOR_DISTANCE` with an explicit metric. The default
  is `COSINE` **distance**; `cosine_similarity`, Euclidean distance, dot
  product, negative dot product, squared Euclidean distance, and Manhattan
  distance are also available. Scores are native
  metric values, **not probabilities**. For distances a `score_threshold` is
  a maximum; for similarities/dot product it is a minimum. The cutoff is
  applied in SQL **before** paging. No ANN indexes are created or managed;
  Oracle may use an existing index if the table already has one. There is no
  exact/approximate toggle, server-side embedding generation, or
  keyword-hybrid search. Index-selected approximate searches may return fewer
  than the requested number of results.
- Portable filters support scalar equality (including `NULL` and boolean
  distinctions), `in`/`not_in`, numeric ranges, `is_null`, `is_not_null`,
  `exists`, literal text `contains_text`/`starts_with`/`ends_with`, and
  AND/OR/NOT. Collection membership and nested filters are rejected.
  Ordered filters on integer fields reject non-integral float operands.
  String comparison follows the configured Oracle collation. Input values
  are bound; identifiers are checked and quoted as individual names.

## Opt-in database tests

The unit tests require no Oracle server. To run the live integration test,
provide **all three** `ORACLE_TEST_DSN`, `ORACLE_TEST_USER`, and
`ORACLE_TEST_PASSWORD` for an explicitly designated disposable Oracle 23ai+
schema where the user can create and drop tables:

```bash
cd python
uv run --package agent-framework-oracle pytest packages/oracle/tests \
  -m integration
```

Without those variables, the integration test skips; it never falls back to
ordinary application credentials. The fixture creates a unique table and
deletes only that table.

## Documentation

- [Oracle Database AI Vector Search requirements](https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/overview-ai-vector-search.html)
- [python-oracledb 2.2 vector types](https://python-oracledb.readthedocs.io/en/v2.2.0/user_guide/vector_data_type.html)
- [Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/)
