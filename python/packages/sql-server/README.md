# Agent Framework SQL Server vector store

Store typed Agent Framework records in SQL Server and Azure SQL native `VECTOR`
columns, with exact, database-side similarity search. This alpha package exports
`SqlServerCollection`, `SqlServerStore`, `SqlServerSettings`, and the
`SqlServerClient` type from `agent_framework_sql_server`.

## Install and provision

```bash
pip install agent-framework-sql-server --pre
```

Requires Python 3.10+, a registered **Microsoft ODBC Driver 18 for SQL Server**
(18.6.1.1 or later recommended), and a vector-enabled database: SQL Server
2025 (17.x), Azure SQL Database, Azure SQL Managed Instance on the SQL Server
2025 or Always-up-to-date update policy, or SQL database in Microsoft Fabric.
Older SQL Server releases do not support `VECTOR`/`VECTOR_DISTANCE`.

Install the ODBC driver **separately** on the machine running Python:
[macOS (Intel/Apple Silicon)](https://learn.microsoft.com/sql/connect/odbc/linux-mac/install-microsoft-odbc-driver-sql-server-macos),
[Linux](https://learn.microsoft.com/sql/connect/odbc/linux-mac/install-microsoft-odbc-driver-sql-server-linux),
or [Windows](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server).
On macOS the Microsoft Homebrew formula installs unixODBC as a dependency.
The Python dependencies `aioodbc` and `pyodbc` do **not** install the Microsoft
ODBC driver. Configure its `vectorTypeSupport=off` setting (the default):
the server stores native vectors while ODBC reads/writes their JSON-array
representation. `vectorTypeSupport=v1/v2` exposes a C-specific representation
that this Python package does not decode.

The database administrator must provide an existing schema (default `dbo`).
`ensure_collection_exists()` creates the requested table and scalar indexes
there but never creates a schema, alters an existing table, or changes database
settings. `ensure_collection_deleted()` drops only that table.

## Connection settings and ownership

Set `SQL_SERVER_CONNECTION_STRING` to an ODBC connection string for the selected
database with a registered `Driver={ODBC Driver 18 for SQL Server}` and your
chosen server, encryption, and authentication settings. Do not commit
connection strings containing credentials. Alternatively, pass
`connection_string` as a string or Agent Framework `SecretString` to
`SqlServerStore` or `SqlServerCollection`. Settings precedence is **explicit
argument > selected `.env` file > process environment**. Choose a file with
`env_file_path` and optional `env_file_encoding`; no `.env` file is discovered
implicitly, and missing/empty strings are rejected.

An owned store creates a lazy one-connection `aioodbc` pool with a dedicated
single-worker executor; `close()` or an async context manager releases both.
Collections created by the store share that pool: keep the store open while
using them. To borrow an existing `aioodbc.Connection` or `aioodbc.Pool`, pass
`client=` instead of connection settings. The connector never closes an
injected client. Raw `pyodbc.Connection` objects are **not** accepted; use the
async aioodbc type. Avoid using the same borrowed connection concurrently
outside the connector; for a caller-created pool, configure its executor
appropriately for your workload.

Batch writes on owned connections commit or roll back together. On borrowed
**connections** the connector starts/commits its own transaction if none is
active; otherwise it uses a SQL Server savepoint and leaves the caller's
transaction open. On a borrowed **pool**, each acquired connection's operation
is committed or rolled back before release; the pool must use
`autocommit=False` (aioodbc's default), and callers must return clean
connections to it. If a caller's transaction becomes uncommittable, the caller
must roll it back. SQL Server savepoints are not available in distributed
transactions.
`aioodbc` uses worker threads internally: cancelling a coroutine cannot
interrupt an already-running ODBC query, so a write may still finish. Set
appropriate database query timeouts, and prefer stable application-provided
keys when retrying writes.

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

`mssql-python` 1.15.0 was evaluated. It supports Python 3.10 and bound JSON
vectors, but has no released native async API, reports `threadsafety=1` (so
moving a caller-created raw connection between AF worker threads is unsafe),
and publishes only macOS 15+ wheels with no source distribution. This
connector instead uses `aioodbc`/`pyodbc` to retain an async, borrowed-client
interface and broader macOS compatibility at the cost of a separately
installed ODBC driver.

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
- [ODBC vector JSON compatibility mode](https://learn.microsoft.com/sql/connect/odbc/vector-data-type)
- [Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/)
