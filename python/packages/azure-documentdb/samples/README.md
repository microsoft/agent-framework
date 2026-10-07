# Azure DocumentDB vector store sample

`azure_documentdb_vectors.py` creates one uniquely named collection, writes
deterministic vectors, performs filtered searches across two vector fields, and
deletes the collection. Set `AZURE_DOCUMENTDB_CONNECTION_STRING` and
`AZURE_DOCUMENTDB_DATABASE_NAME` for a development database where collection
and index creation is authorized.

Run it from `python/`:

```bash
uv run --package agent-framework-azure-documentdb \
    python packages/azure-documentdb/samples/azure_documentdb_vectors.py
```
