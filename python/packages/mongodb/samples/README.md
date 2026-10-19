# MongoDB samples

`mongodb_vectors.py` demonstrates deterministic dense vectors, indexed metadata
prefiltering, multiple vector fields, and vector exclusion during ordinary
retrieval. It creates and deletes a unique collection.

`mongodb_agent_rag.py` grounds an agent on a MongoDB collection through
`VectorCollectionContextProvider`, which exposes the collection to the model as a
search tool. It seeds a small knowledge base, waits for the new documents to become
searchable, answers two questions, and deletes the collection it created.

Run MongoDB Atlas or
[Atlas Local](https://www.mongodb.com/docs/atlas/cli/current/atlas-cli-deploy-local/),
set `MONGODB_URI` and `MONGODB_DATABASE_NAME`, and follow the
[package connection guidance](../README.md#connection).

`mongodb_vectors.py` supplies its own vectors and needs no embedding service.
`mongodb_agent_rag.py` additionally needs `OPENAI_API_KEY` for the embeddings and
the agent.
