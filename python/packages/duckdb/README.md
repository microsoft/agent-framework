# Agent Framework DuckDB vector store

Store and search typed records in DuckDB using the
[Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/)
vector-store APIs. This alpha package uses the **DuckDB Python client only**:
local files, DuckDB-supported connection URIs (including MotherDuck), and
caller-provided `duckdb.DuckDBPyConnection` objects use the same implementation.

## Installation

```bash
pip install agent-framework-duckdb --pre
```

Python 3.10+ and DuckDB 1.4.1–1.5.x are required. The package also installs
`pytz`, which DuckDB uses when returning timezone-aware timestamps. Import
`DuckDBStore` and `DuckDBCollection` directly from `agent_framework_duckdb`;
this alpha package is not part of `agent-framework-core[all]`.

## Connections and persistence

`DuckDBStore()` (and a directly constructed `DuckDBCollection`) defaults to
**`agent-framework.duckdb` in the current working directory**. It is a normal
persistent database file, not an in-memory database or temporary file. Give
each application a suitable writable location with
`connection_string="path/to/vectors.duckdb"`; parent directories must already
exist. The connection is opened lazily on the first async operation.
`aclose()` or an async context manager drains pending operations and releases
the file. Opening a *new* store against the same filename restores its tables
and records.

`DUCKDB_CONNECTION_STRING` can instead provide a filename or a URI. Settings
precedence is **explicit `connection_string` > selected `.env` file >
environment > persistent default**. Select a file with `env_file_path` and
optionally `env_file_encoding`; `.env` files are never discovered implicitly.
An explicitly empty connection string is an error. The URI is held as an AF
`SecretString` and never printed or logged by the connector.

To use [MotherDuck](https://motherduck.com/docs/getting-started/interfaces/client-apis/python/installation-authentication/),
configure the *same* DuckDB client with a `md:` URI and its usual credentials,
for example:

```bash
export DUCKDB_CONNECTION_STRING='md:my_db'
export MOTHERDUCK_TOKEN='<your access token>'
```

```python
from agent_framework_duckdb import DuckDBStore


async def list_remote_tables() -> None:
    async with DuckDBStore() as store:
        print(await store.list_collection_names())
```

For an application-managed token, pass
`DuckDBStore(connection_string="md:my_db",
config={"motherduck_token": SecretString(token)})` (import `SecretString`
from `agent_framework`). `config` is forwarded to `duckdb.connect`; it is
not loaded from the connector's `.env` file. Keep tokens outside source control
and avoid embedding them in a URI. Other DuckDB-supported services use their
documented URI/configuration or an injected client; no service-specific
adapter is installed. DuckDB/MotherDuck may need network access and compatible
client/extension versions; authentication and service availability are managed
by DuckDB, not by this connector.

Alternatively, use `DuckDBStore(client=duckdb.connect(...))` or
`DuckDBCollection(Record, client=...)` to **borrow** an existing connection.
The caller owns and closes that connection; `client` cannot be combined with
`connection_string`, `config`, or `.env` options. Collections obtained from a
store borrow its client, so keep the store open while using them. All connector
operations on one store/collection run serially on one worker thread, not on
the event loop. Coordinate any *external* use of an injected connection
yourself. Cancelling an awaiter does not stop a DuckDB query already running
on that thread; `aclose()` waits for it to finish.

## Example

```python
from dataclasses import dataclass
from typing import Annotated

from agent_framework import Filter, VectorStoreField, vectorstoremodel
from agent_framework_duckdb import DuckDBStore


@vectorstoremodel(collection_name="articles")
@dataclass
class Article:
    id: Annotated[str, VectorStoreField("key")]
    text: Annotated[str, VectorStoreField("data")]
    embedding: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


async def save_and_search() -> None:
    async with DuckDBStore(connection_string="articles.duckdb") as store:
        collection = store.get_collection(Article)
        await collection.ensure_collection_exists()
        await collection.upsert(
            [Article("one", "DuckDB persists records", [1, 0, 0])],
            generate_vectors=False,
        )

    async with DuckDBStore(connection_string="articles.duckdb") as reopened:
        collection = reopened.get_collection(Article)
        assert (await collection.get(["one"]))[0].text == "DuckDB persists records"
        results = await collection.search(
            vector=[1, 0, 0],
            filter=Filter("text", "contains_text", "persists"),
        )
        async for result in results:
            print(result["record"].text, result["score"])
```

Run a complete local example with
`uv run --package agent-framework-duckdb python packages/duckdb/samples/duckdb_vectors.py`
from the `python/` directory. It writes a default database file, reopens it,
and cleans up only its sample table.

## Capabilities and limits

- Tables are created by `ensure_collection_exists()`; `collection_exists()`,
  `list_collection_names()`, and `ensure_collection_deleted()` provide the
  corresponding lifecycle. Existing tables are **not migrated or reindexed**.
  Identifiers are quoted, values are parameterized, and collection names refer
  to tables in the connection's current database and schema.
- Batch upsert, retrieval, filtered/paged listing, and delete support string,
  signed 64-bit integer, and UUID keys; string and UUID keys can be generated
  when declared auto-generated. Records support string, integer, float,
  boolean, UUID, bytes, date, timezone-aware datetime, JSON list/dict data,
  and nullable dense vectors. Use `generate_vectors=False` for supplied
  embeddings or pass a local `embedding_generator`. Retrieval excludes vectors
  unless `include_vectors=True`.
- Exact SQL vector search supports `DEFAULT`/`cosine_distance`,
  `cosine_similarity`, `euclidean_distance`, `dot_prod`, and
  `negative_dot_prod`. The default score is cosine **distance**, so lower is
  better and `score_threshold` is a maximum; similarity/dot-product scores
  use a minimum threshold. Null vectors are omitted. Results are filtered
  and paged **in DuckDB**, with the primary key as a stable tie-breaker.
- Portable filters support scalar equality/inequality, null/presence checks,
  ordered scalar comparisons, `in`/`not_in`, text contains/prefix/suffix,
  and AND/OR/NOT groups. They do not coerce booleans into numbers, and text
  wildcards are literal. JSON equality/collection membership and nested
  paths are not supported.
- No approximate vector indexes, keyword/hybrid search, full-text or explicit
  data indexes, binary/sparse vectors, auto-generated integer keys, or
  server-side vectorization are provided. Unsupported options raise errors.
  DuckDB is an in-process database with file locking: multiple writer
  **processes** cannot concurrently write the same local file. Local records
  are unencrypted; choose and protect the database file appropriately.
  Connector-created batch upserts are transactional. On a borrowed connection
  the connector does not start/commit/roll back a caller transaction; without
  one, a failed batch may have partially persisted.
