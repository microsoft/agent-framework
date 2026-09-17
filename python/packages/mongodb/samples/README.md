# MongoDB samples

`mongodb_vectors.py` demonstrates deterministic dense vectors, indexed metadata
prefiltering, multiple vector fields, and vector exclusion during ordinary
retrieval. It creates and deletes a unique collection.

Run MongoDB Atlas or
[Atlas Local](https://www.mongodb.com/docs/atlas/cli/current/atlas-cli-deploy-local/),
set `MONGODB_URI` and `MONGODB_DATABASE_NAME`, and follow the
[package connection guidance](../README.md#connection). No embedding service is
required.
