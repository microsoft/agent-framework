# Agent Framework SQL Server vector store

Store typed Agent Framework records in SQL Server and Azure SQL native `VECTOR`
columns, with exact, database-side similarity search. This alpha package exports
`SqlServerCollection`, `SqlServerStore`, `SqlServerSettings`, and
`SqlServerCommittedCleanupException` directly from `agent_framework_sql_server`.

## Install and provision

```bash
pip install agent-framework-sql-server --pre
```

Requires Python 3.10–3.14 and a vector-enabled database: SQL Server 2025
(17.x), Azure SQL Database, Azure SQL Managed Instance on the SQL Server 2025
or Always-up-to-date update policy, or SQL database in Microsoft Fabric.
Older SQL Server releases do not support `VECTOR`/`VECTOR_DISTANCE`.

The package uses Microsoft's [`mssql-python` 1.15+ driver](https://pypi.org/project/mssql-python/).
It installs its `mssql-python-odbc` binary companion automatically; no external
ODBC Driver 18 or driver manager is required. Published wheels cover CPython
3.10–3.14 on Windows x64, Linux x64/ARM64, and **macOS 15+**
Intel/Apple Silicon; Windows ARM64 wheels start at Python 3.11. macOS 14 is
listed in the driver's support documentation, but the published macOS wheels
are tagged `macosx_15_0_universal2` and there is no source distribution.
Python 3.15 has no published wheel yet: this package caps `requires-python`
below 3.15, and the repository's non-blocking 3.15 CI lane excludes it.
The workspace lockfile likewise limits Python below 3.15 while this package
remains a member; the experimental 3.15 lane excludes it before resolving.
Follow the [driver's installation instructions](https://learn.microsoft.com/sql/connect/python/mssql-python/installation)
for system libraries on Linux and OpenSSL on macOS.

The database administrator must provide an existing schema (default `dbo`).
`ensure_collection_exists()` creates the requested table and scalar indexes
there but never creates a schema, alters an existing table, or changes database
settings. `ensure_collection_deleted()` drops only that table.

## Connection settings and ownership

For local Azure SQL development with passwordless Microsoft Entra authentication,
sign in with Azure CLI, then set the environment variable used by the
[sample](samples/sql_server_vectors.py):

```bash
az login
export SQL_SERVER_CONNECTION_STRING='Server=<host>;Database=<db>;Authentication=ActiveDirectoryDefault;Encrypt=yes;'
```

Replace `<host>` with the Azure SQL server hostname (for example,
`my-server.database.windows.net`) and `<db>` with your existing database.
`ActiveDirectoryDefault` uses the driver's credential chain, which can use
your Azure CLI sign-in. The identity must be granted access to the database
and permission to create a table and index in the configured schema and
read/write its records. On an Azure-hosted app, use
`Authentication=ActiveDirectoryMSI` for managed identity; add
`UID=<client-id>` for a user-assigned identity. See
[Microsoft's Entra authentication guide](https://learn.microsoft.com/sql/connect/python/mssql-python/entra-authentication)
for setup, permissions, and other supported modes. This connector accepts
connection strings, not the driver's `token_provider=` credential argument.

Do not commit connection strings containing credentials. Alternatively, pass
`connection_string` as a string or Agent Framework `SecretString` to
`SqlServerStore` or `SqlServerCollection`. Settings precedence is **explicit
argument > selected `.env` file > process environment**. To read a `.env` file
in the run directory, pass `env_file_path=".env"` to `SqlServerStore` or
`SqlServerCollection`; `env_file_encoding` is optional. Missing or empty
connection strings are rejected.

The connector owns all connections. Each whole operation opens, uses, commits
or rolls back, and closes a `mssql-python` connection on a dedicated worker
thread, keeping Agent Framework's async calls nonblocking. The driver's
built-in pooling can reuse the underlying physical connection. A store and
its collections share one worker; a standalone collection owns its own.
Call `close()` or use an async context manager to release the worker. There is
no `client=` or connection-factory constructor argument: arbitrary caller-owned
`mssql-python` connections cannot safely cross threads (`threadsafety=1`).
This is intentionally narrower than connectors that support borrowed async
clients.

Batch writes commit or roll back together on one connection. Cancelling an
async operation waits for its worker to finish cleanup; it cannot interrupt an
already-running synchronous SQL statement, and the transaction may already
have committed. Set `query_timeout=30` (seconds, for example) on the store or
collection when bounding database calls; leaving it unset uses the driver's
default, and `0` disables the timeout. Prefer stable application-provided
keys when retrying writes.
If closing the connection fails after a successful commit,
`SqlServerCommittedCleanupException` explicitly signals that the transaction
**already committed**; do not automatically retry, especially with generated
keys. Cancellation remains `CancelledError` even if the worker fails while
finishing; that worker error is logged after cleanup.

## Example

With `SQL_SERVER_CONNECTION_STRING` configured, run the
[typed sample](samples/sql_server_vectors.py) from the `python/` directory:

```bash
uv run --package agent-framework-sql-server \
    python packages/sql-server/samples/sql_server_vectors.py
```

The sample creates a uniquely named table, upserts precomputed embeddings,
filters/ranks in SQL Server, retrieves an optional vector, and drops its own
table. Pass `generate_vectors=False` to preserve precomputed vectors; to
generate them locally, configure an `embedding_generator`.

## Capabilities and limits

The connector supports typed decorated models and dictionary definitions;
string/integer/UUID keys (including generated keys); multiple nullable float32
vector columns with **1–1998 dimensions**; field storage aliases; batch
upsert/get/delete; paged and ordered retrieval; scalar data indexes; and
parameterized top-level `Filter`/`FilterGroup` expressions. String keys cannot
end with a space because SQL Server ignores trailing spaces in key comparisons.
Indexed strings use `NVARCHAR(450)`; other strings use `NVARCHAR(MAX)`. List and
dictionary fields are stored as JSON, and timezone-aware `datetime` values are
normalized to UTC in `DATETIME2(7)` columns.
For an auto-generated integer (`IDENTITY`) key, omit the key on insert;
explicit keys can update existing rows but cannot create new identity rows.

Supported filters: scalar `eq`, `ne`, `in`, `not_in`, `is_null`, `is_not_null`,
`exists`; numeric/date/datetime `gt`, `gte`, `lt`, `lte`, `between`; and string
`starts_with`, `ends_with`, `contains_text`. `AND`/`OR`/`NOT` groups preserve
two-valued null semantics; string equality is byte-exact and text patterns
escape SQL Server wildcards. JSON fields support `is_null`, `is_not_null`, and
`exists`, **not** equality or collection-membership filters. Nested paths,
full-text filtering, and unknown operation options fail explicitly. The SQL
Server 2100-parameter limit is respected by batching key reads/deletes and
limiting other statements to 2000 bound parameters.

Search uses SQL Server's exact `VECTOR_DISTANCE` on native `VECTOR` columns,
with filters and score thresholds applied **before** offset/limit. The default
metric is cosine **distance** (lower is better). Euclidean and negative dot
product also return distances (maximum thresholds); `cosine_similarity` and
`dot_prod` return similarity/positive-dot scores (minimum thresholds).
Scores are raw metric units, not probabilities. Retrieval excludes vectors by
default; use `include_vectors=True` to return them. Approximate DiskANN
indexes/search, preview-only float16 vectors, keyword-hybrid search, sparse or
binary vectors, server-side embedding generation, and schema migration are
not supported.

The server stores native `VECTOR` columns, but `mssql-python` 1.15 does not
expose a native Python vector type. The connector binds JSON-encoded vectors
as parameters and parses JSON on retrieval; SQL Server converts to/from the
native type. It does not enable native driver vector bindings.

## Service tests

Unit tests need no database. Integration tests are opt-in: set
`SQL_SERVER_TEST_CONNECTION_STRING` to a deliberately designated test database
with table creation permissions and run:

```bash
uv run --package agent-framework-sql-server pytest \
    packages/sql-server/tests/sql_server/test_integration.py -m integration
```

The tests create uniquely named tables and remove only those tables. They
skip when the variable is absent or empty (including an unconfigured CI
secret), and fail rather than silently skipping when an explicitly
designated server lacks vector support.

## References

- [SQL Server vector type and database availability](https://learn.microsoft.com/sql/t-sql/data-types/vector-data-type)
- [Exact vector distance metrics](https://learn.microsoft.com/sql/t-sql/functions/vector-distance-transact-sql)
- [Microsoft's Python vector JSON example](https://learn.microsoft.com/sql/t-sql/data-types/vector-data-type#python)
- [mssql-python asynchronous integration patterns](https://learn.microsoft.com/sql/connect/python/mssql-python/asynchronous-patterns)
- [Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/)
