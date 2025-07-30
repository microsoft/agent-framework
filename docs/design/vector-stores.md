# Vector Stores and Embedding Clients

A vector store is component that provides a unified interface for
interacting with different vector databases, similar to model clients.
It exposes indexing and querying methods, including vector, text-based
and hybrid queries.

The details can be filled in based on the existing vector abstraction
in Semantic Kernel.

The framework provides pre-built vector stores (already exist in
Semantic Kernel):

- Azure AI Search
- Cosmos DB
- Chroma
- Couchbase
- Elasticsearch
- Faiss
- In-memory
- JDBC
- MongoDB
- Pinecone
- Postgres
- Qdrant
- Redis
- SQL Server
- SQLite
- Volatile
- Weaviate

Many vector store implementations will require embedding clients
to function. An embedding client is a component that implements a unified interface
to interact with different embedding models.

The framework provides a set of pre-built embedding clients:

- TBD.
