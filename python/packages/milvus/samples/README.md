# Milvus samples

`milvus_vectors.py` demonstrates batch CRUD, dense-vector search, portable filtering
translated to Milvus boolean expressions, and selective vector retrieval using
deterministic vectors. It creates and deletes its own unique collection.

Set `MILVUS_URI` to a disposable Milvus 2.5+ server (e.g. `http://localhost:19530`); for
Milvus Lite, edit the sample to pass a local `.db` path as the `uri=` argument instead
(the `MILVUS_URI` env var must be a server address). Then follow the
[package README](../README.md#configuration). No embedding service is needed.
Optional `MILVUS_TOKEN`, `MILVUS_USER`, `MILVUS_PASSWORD` and `MILVUS_DB_NAME` are
supported by the connector's `MilvusSettings`, which also supports explicitly selected
`.env` files.
