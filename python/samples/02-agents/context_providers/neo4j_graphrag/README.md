# Neo4j GraphRAG Context Provider Examples

The [Neo4j GraphRAG context provider](https://github.com/neo4j-labs/neo4j-maf-provider) retrieves relevant documents from Neo4j vector and fulltext indexes and optionally enriches results by traversing graph relationships, giving agents access to connected knowledge that flat document search cannot provide.

This is a **read-only retrieval provider** — it queries a pre-existing knowledge base and does not modify data. For persistent agent memory that grows from interactions, see the [Neo4j Memory Provider](../neo4j_memory/README.md). For help choosing between the two, see the [Neo4j Context Providers overview](../neo4j/README.md).

## Examples

- **Vector search**: Semantic similarity search using embeddings to retrieve conceptually related document chunks
- **Fulltext search**: Keyword search using BM25 scoring — no embedder required
- **Hybrid search**: Vector + fulltext combined for best of both worlds
- **Graph-enriched search**: Any search mode combined with a custom Cypher `retrieval_query` to traverse related entities

For full runnable examples, see the [Neo4j GraphRAG Provider samples](https://github.com/neo4j-labs/neo4j-maf-provider/tree/main/python/samples).

## Installation

```bash
pip install agent-framework-neo4j
```

## Prerequisites

### Required Resources

1. **Neo4j database** with a vector or fulltext index containing your documents
   - [Neo4j AuraDB](https://neo4j.com/cloud/auradb/) (managed) or self-hosted
   - Documents must be indexed with a vector or fulltext index
2. **Azure AI Foundry project** with a model deployment (for the agent's chat model)
3. **For vector/hybrid search**: An embedding model endpoint (e.g., Azure AI `text-embedding-ada-002`)

### Authentication

- Neo4j: Username/password authentication
- Azure AI: Uses `DefaultAzureCredential` for embeddings and chat model

Run `az login` for Azure authentication.

## Configuration

### Environment Variables

**Neo4j** (auto-loaded by `Neo4jSettings`):
- `NEO4J_URI`: Neo4j connection URI (e.g., `neo4j+s://your-instance.databases.neo4j.io`)
- `NEO4J_USERNAME`: Database username
- `NEO4J_PASSWORD`: Database password

**Azure AI** (auto-loaded by `AzureAISettings`):
- `AZURE_AI_PROJECT_ENDPOINT`: Azure AI Foundry project endpoint
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`: Chat model deployment name (e.g., `gpt-4o`)
- `AZURE_AI_EMBEDDING_NAME`: Embedding model name (default: `text-embedding-ada-002`)

## Code Example

### Vector Search with Graph Enrichment

```python
import os

from agent_framework import Agent
from agent_framework.azure import AzureAIClient
from agent_framework_neo4j import Neo4jContextProvider, Neo4jSettings, AzureAIEmbedder, AzureAISettings
from azure.identity import DefaultAzureCredential
from azure.identity.aio import AzureCliCredential

neo4j_settings = Neo4jSettings()
azure_settings = AzureAISettings()

embedder = AzureAIEmbedder(
    endpoint=azure_settings.inference_endpoint,
    credential=DefaultAzureCredential(),
    model=azure_settings.embedding_model,
)

provider = Neo4jContextProvider(
    uri=neo4j_settings.uri,
    username=neo4j_settings.username,
    password=neo4j_settings.get_password(),
    index_name="chunkEmbeddings",
    index_type="vector",
    embedder=embedder,
    top_k=5,
    retrieval_query="""
        MATCH (node)-[:FROM_DOCUMENT]->(doc:Document)<-[:FILED]-(company:Company)
        RETURN node.text AS text, score, company.name AS company, doc.title AS title
        ORDER BY score DESC
    """,
)

async with (
    provider,
    AzureAIClient(
        credential=AzureCliCredential(),
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
    ) as client,
    Agent(
        client=client,
        name="FinancialAnalyst",
        instructions="You are a financial analyst assistant.",
        context_providers=[provider],
    ) as agent,
):
    session = agent.create_session()
    response = await agent.run("What risks does Acme Corp face?", session=session)
    print(response.text)
```

### Fulltext Search (No Embedder Required)

```python
provider = Neo4jContextProvider(
    uri=neo4j_settings.uri,
    username=neo4j_settings.username,
    password=neo4j_settings.get_password(),
    index_name="search_chunks",
    index_type="fulltext",
    top_k=5,
)
```

### Hybrid Search

```python
provider = Neo4jContextProvider(
    uri=neo4j_settings.uri,
    username=neo4j_settings.username,
    password=neo4j_settings.get_password(),
    index_name="chunkEmbeddings",
    index_type="hybrid",
    fulltext_index_name="chunkFulltext",
    embedder=embedder,
    top_k=5,
)
```

## Additional Resources

- [Neo4j GraphRAG Provider Repository](https://github.com/neo4j-labs/neo4j-maf-provider)
- [Neo4j GraphRAG Python Library](https://neo4j.com/docs/neo4j-graphrag-python/current/)
- [Neo4j Vector Index Documentation](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)
