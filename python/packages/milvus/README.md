# Milvus for Microsoft Agent Framework

`agent-framework-milvus` provides a [Milvus](https://milvus.io/) vector store for the
Microsoft Agent Framework, implementing the framework's `BaseVectorStore` /
`BaseVectorCollection` interfaces. It works alongside the Postgres, Qdrant, Redis and
other vector-store connectors.

## Installation

```bash
pip install agent-framework-milvus
```

## Usage

```python
from agent_framework import VectorStoreCollectionDefinition, VectorStoreField
from agent_framework_milvus import MilvusStore

definition = VectorStoreCollectionDefinition([
    VectorStoreField("key", name="id", type_="int"),
    VectorStoreField("data", name="text", type_="str"),
    VectorStoreField("vector", name="embedding", dimensions=1536, distance_function="cosine_similarity"),
])

# Connects to a Milvus server; set MILVUS_URI or pass uri=...
# A local ".db" path uses Milvus Lite.
async with MilvusStore(uri="http://localhost:19530") as store:
    collection = store.get_collection(dict, definition=definition, collection_name="docs")
    await collection.ensure_collection_exists()
    await collection.upsert({"id": 1, "text": "hello", "embedding": [...]})
    results = await collection.search(vector=[...], top=5)
    async for hit in results:
        print(hit.record, hit.score)
```

## Configuration

Settings are resolved from explicit arguments, then an optional `.env` file, then
environment variables prefixed with `MILVUS_`:

| Setting    | Environment variable | Notes                                              |
| ---------- | -------------------- | -------------------------------------------------- |
| `uri`      | `MILVUS_URI`         | Server URI or a local `.db` path (Milvus Lite).    |
| `token`    | `MILVUS_TOKEN`       | Access token (API key or `user:password`).         |
| `user`     | `MILVUS_USER`        | Username.                                          |
| `password` | `MILVUS_PASSWORD`    | Password.                                          |
| `db_name`  | `MILVUS_DB_NAME`     | Database name.                                     |

## Notes

- The key field becomes the Milvus primary key (`INT64` for `int` keys, `VARCHAR`
  otherwise). Data fields map to typed scalar fields and vector fields to
  `FLOAT_VECTOR` fields, each with its own index.
- Distance functions map to Milvus metrics (`cosine_similarity`/`cosine_distance` →
  `COSINE`, `dot_prod` → `IP`, `euclidean_distance` → `L2`) and index kinds to Milvus
  index types (`hnsw`, `flat`, `ivf_flat`, `disk_ann`, and `default` → `AUTOINDEX`).
- Portable filters support `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `between`, `in`,
  `not_in`, and `and`/`or`/`not` groups, translated to Milvus boolean expressions.
