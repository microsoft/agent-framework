# Agent Framework Azure DocumentDB

Store and search vector records in
[Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/) with this
alpha integration for
[Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/).
The package uses PyMongo's stable asynchronous API and Azure DocumentDB's
Mongo-compatible `$search.cosmosSearch` dialect.

- **`AzureDocumentDBCollection`** provides batch CRUD, metadata filters, index reconciliation, and vector search.
- **`AzureDocumentDBStore`** creates collection clients sharing one resolved database.
- **`AzureDocumentDBSettings`** defines the two Agent Framework-managed connection settings.

## Installation

```bash
pip install agent-framework-azure-documentdb --pre
```

Requires Python 3.10+, PyMongo 4.13+, and an Azure DocumentDB cluster. IVF
indexes are intended for smaller datasets and M10/M20 tiers. HNSW and DiskANN
require M30 or higher; consult the current service documentation before choosing
a production tier.

## Authentication and setup

Set `AZURE_DOCUMENTDB_CONNECTION_STRING` to the connection string from the
Azure portal and `AZURE_DOCUMENTDB_DATABASE_NAME` to an existing or intended
database. Settings precedence is explicit constructor value, selected `.env`
file, then process environment. Connection strings are held in Agent Framework
`SecretString` values.

Connector-created clients enforce TLS, disable retryable writes, and set an
application name. They are closed by `aclose()` or an async context manager.
An injected PyMongo `AsyncMongoClient`, `AsyncDatabase`, or `AsyncCollection`
remains caller-owned and bypasses settings loading.

The identity running `ensure_collection_exists()` needs permission to create
collections and indexes. Each filtered data field must declare
`is_indexed=True`; the connector creates its ordinary ascending index alongside
separate vector indexes.

## Example

```python
import asyncio
from dataclasses import dataclass
from typing import Annotated

from agent_framework import Filter, VectorStoreField, vectorstoremodel
from agent_framework_azure_documentdb import AzureDocumentDBStore


@vectorstoremodel(collection_name="articles")
@dataclass
class Article:
    id: Annotated[str, VectorStoreField("key")]
    category: Annotated[str, VectorStoreField("data", is_indexed=True)]
    embedding: Annotated[
        list[float] | None,
        VectorStoreField("vector", dimensions=3, index_kind="ivf_flat"),
    ] = None


async def main() -> None:
    async with AzureDocumentDBStore() as store:
        collection = store.get_collection(Article)
        await collection.ensure_collection_exists()
        await collection.upsert(
            [Article("one", "database", [1.0, 0.0, 0.0])],
            generate_vectors=False,
        )
        results = await collection.search(
            vector=[1.0, 0.0, 0.0],
            filter=Filter("category", "eq", "database"),
        )
        async for result in results:
            print(result["record"], result["score"])


asyncio.run(main())
```

## Limits

The connector supports explicit string and signed 64-bit integer `_id` keys,
multiple top-level dense vector fields, storage aliases, IVF/HNSW/DiskANN
indexes, native metadata filters, server-side paging, and native `searchScore`
values. Generated ObjectIds, ordered retrieval, hybrid/full-text search,
sparse/binary vectors, nested field paths, compressed vectors, and automatic
schema/index migration are not supported.

The core `default` index kind maps to IVF so it does not silently require an
M30+ tier. Select `hnsw` or `disk_ann` explicitly when those service contracts
and cluster requirements are appropriate.

Vector dimensions are conservatively limited to the service's 2,000-dimension
standard-vector contract. Azure DocumentDB also offers higher limits with
half-precision or product quantization; those distinct index/storage options are
outside this connector.

`score_threshold` uses native metric units after `$search` selects its `k`
candidates and before `$skip`/`$limit`. It is a minimum for cosine and inner
product scores, where larger is better, and a maximum for Euclidean distance,
where smaller is better. Set a larger `operation_options={"k": ...}` candidate
window when needed. Thresholded ANN search can return fewer than `top`; the
connector does not fetch or filter a client-side prefix. Algorithm tuning uses
`n_probes`, `ef_search`, or `l_search` for IVF, HNSW, or DiskANN respectively.

See the
[Azure DocumentDB vector search guide](https://learn.microsoft.com/azure/documentdb/vector-search),
[Azure DocumentDB limits](https://learn.microsoft.com/azure/documentdb/limitations),
[PyMongo async API](https://pymongo.readthedocs.io/en/stable/api/pymongo/asynchronous/),
and [Agent Framework documentation](https://learn.microsoft.com/agent-framework/).
