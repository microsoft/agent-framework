# Qdrant samples

`qdrant_vectors.py` demonstrates batch CRUD, named dense-vector selection,
native portable filtering, and score thresholds using deterministic vectors.
It creates and deletes its own unique collection.

Run a disposable Qdrant 1.16.2+ server, set `QDRANT_URL`, and follow the
[package README](../README.md#connection-settings). No embedding
service is needed. Optional `QDRANT_API_KEY` is supported by the sample and
the connector's `QdrantSettings`, which also supports explicitly selected `.env` files.
Portable filters deliberately require a server, not `:memory:` local mode.
