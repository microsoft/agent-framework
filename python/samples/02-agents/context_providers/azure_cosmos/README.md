# Azure Cosmos DB Context Provider Examples

The Azure Cosmos DB context provider enables Retrieval Augmented Generation (RAG) for your agents using Azure Cosmos DB as a knowledge store. It retrieves relevant documents before each agent run (via vector, full-text, or hybrid search) and writes conversation messages back to the container after each run, building a growing knowledge base.

This folder contains examples demonstrating how to use the `CosmosContextProvider` with the Agent Framework.

## Examples

| File | Description |
|------|-------------|
| [`cosmos_context_basics.py`](cosmos_context_basics.py) | **Vector search + writeback**: Ask questions using vector search (default mode) and see how conversation exchanges are written back into the container for future retrieval. |
| [`cosmos_context_fulltext.py`](cosmos_context_fulltext.py) | **Full-text search**: Retrieve documents by keyword relevance using BM25 ranking. No embedding function needed. Queries with more than 5 terms are handled automatically via RRF chunking. |
| [`cosmos_context_hybrid.py`](cosmos_context_hybrid.py) | **Hybrid search**: Combine vector and full-text search via Reciprocal Rank Fusion (RRF). Also demonstrates optional weighted RRF to tune the balance between semantic and keyword results. |
| [`cosmos_context_shared.py`](cosmos_context_shared.py) | **Shared knowledge**: Use `partition_key` to share context across multiple agent sessions. Demonstrates seeding a common knowledge partition and having separate conversations query and contribute to it. |

## Prerequisites

### Required Resources

1. **Azure Cosmos DB account** with the following capabilities enabled **at account creation time**:
   - `EnableNoSQLVectorSearch`
   - `EnableNoSQLFullTextSearch` (required for full-text and hybrid modes)
   - `EnableServerless` (recommended for development/testing)

   > **Important**: These capabilities must be set when creating the account. Adding them via `az cosmosdb update` on an existing account may not propagate to the data plane.

   ```bash
   az cosmosdb create \
     --name <account-name> \
     --resource-group <resource-group> \
     --locations regionName=westus2 failoverPriority=0 \
     --capabilities EnableServerless EnableNoSQLVectorSearch EnableNoSQLFullTextSearch
   ```

2. **Database and container** with vector + full-text indexing policies:

   ```bash
   # Create the database
   az cosmosdb sql database create \
     --account-name <account-name> \
     --resource-group <resource-group> \
     --name <database-name>

   # Create the container with indexing policies
   az cosmosdb sql container create \
     --account-name <account-name> \
     --resource-group <resource-group> \
     --database-name <database-name> \
     --name <container-name> \
     --partition-key-path "/session_id" \
     --idx-policy '{
       "indexingMode": "consistent",
       "automatic": true,
       "includedPaths": [{"path": "/*"}],
       "excludedPaths": [{"path": "/\"_etag\"/?"},{"path": "/embedding/*"}],
       "vectorIndexes": [{"path": "/embedding", "type": "quantizedFlat"}],
       "fullTextIndexes": [{"path": "/content"}]
     }' \
     --vector-policy '{
       "vectorEmbeddings": [{
         "path": "/embedding",
         "dataType": "float32",
         "distanceFunction": "cosine",
         "dimensions": 3
       }]
     }' \
     --full-text-policy '{
       "defaultLanguage": "en-US",
       "fullTextPaths": [{"path": "/content", "language": "en-US"}]
     }'
   ```

   > When using real embeddings, change `"dimensions": 3` to match your model (e.g., 1536 for `text-embedding-ada-002`).

3. **RBAC permissions**: Assign the `Cosmos DB Built-in Data Contributor` role to your Azure CLI principal:

   ```bash
   az cosmosdb sql role assignment create \
     --account-name <account-name> \
     --resource-group <resource-group> \
     --role-definition-id 00000000-0000-0000-0000-000000000002 \
     --principal-id <your-principal-object-id> \
     --scope "/"
   ```

4. **Azure AI Foundry project** with a model deployment (e.g., GPT-4o) for the chat client.

### Authentication

Run `az login` before running the samples. The samples use `AzureCliCredential` for both Cosmos DB and the Foundry chat client.

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FOUNDRY_PROJECT_ENDPOINT` | Yes | Azure AI Foundry project endpoint |
| `FOUNDRY_MODEL` | Yes | Model deployment name (e.g., `gpt-4o`) |
| `AZURE_COSMOS_ENDPOINT` | Yes | Cosmos DB account endpoint (e.g., `https://<account>.documents.azure.com:443/`) |
| `AZURE_COSMOS_DATABASE_NAME` | Yes | Database name |
| `AZURE_COSMOS_CONTAINER_NAME` | Yes | Container name |
| `AZURE_COSMOS_KEY` | No | Account key. If not set, uses `AzureCliCredential` (Entra ID) |

### Example `.env` file

```env
FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
FOUNDRY_MODEL=gpt-4o
AZURE_COSMOS_ENDPOINT=https://<account>.documents.azure.com:443/
AZURE_COSMOS_DATABASE_NAME=agent-framework
AZURE_COSMOS_CONTAINER_NAME=knowledge
```

## Search Modes

`CosmosContextProvider` supports three retrieval modes:

| Mode | How it works | Best for |
|------|-------------|----------|
| **Vector** (default) | Generates an embedding for the user query and finds documents by `VectorDistance` | Semantic similarity search |
| **Full-text** | Uses `FullTextScore` (BM25) to find keyword matches | Keyword/exact-term search |
| **Hybrid** | Combines vector and full-text with `RRF` (Reciprocal Rank Fusion) | Best of both, recommended for production |

Set the mode via the `search_mode` constructor parameter:

```python
from agent_framework_azure_cosmos import CosmosContextProvider, CosmosContextSearchMode

provider = CosmosContextProvider(
    search_mode=CosmosContextSearchMode.HYBRID,  # or VECTOR, FULL_TEXT
    ...
)
```

## Partition Key Behavior

The provider always scopes queries to a single partition for performance and cost efficiency. By default, it uses the current session's `session_id` as the partition key value, keeping each conversation's context isolated.

### Per-conversation context (default)

When no `partition_key` is set, each conversation reads and writes only its own documents. This is the simplest setup and works well when each session should have independent context.

```python
# Each session has its own isolated context
provider = CosmosContextProvider(...)
```

### Shared context across conversations

To share context across multiple conversations, set `partition_key` on the constructor. All provider instances using the same `partition_key` value read from and write to the same partition, regardless of their session_id. See [`cosmos_context_shared.py`](cosmos_context_shared.py) for a working example.

```python
# All agents using this partition_key share the same context
provider = CosmosContextProvider(
    partition_key="team-knowledge",
    ...
)
```

### How session_id and partition_key interact

The provider always writes `session_id` into every document so you can trace which conversation produced each piece of context. How `session_id` relates to the container's partition key depends on your container configuration:

- **Container partition key path is `/session_id`** (recommended for per-conversation isolation): The `session_id` field doubles as the partition key. If you set a custom `partition_key` on the provider, that value is written into the `session_id` field of writeback documents, which means the document's `session_id` will be the partition key value rather than the real conversation ID. For shared knowledge scenarios, consider using a container with a different partition key path (see below).

- **Container partition key path is something else** (e.g., `/partition_key`): The provider writes both the `session_id` (real conversation ID) and the partition key field independently. This is the recommended setup for shared knowledge scenarios where you want to preserve the real conversation ID on every document.

### Important notes

- The provider reads the container's partition key path at startup and caches it. Only single, top-level partition key paths are supported (e.g., `/session_id`, `/partition_key`). Hierarchical and nested paths are not supported.
- All Cosmos DB configuration (partition key path, indexing policies, vector/full-text policies) is the application owner's responsibility. The provider does not create or modify Cosmos resources.
- Cosmos DB errors from partition key mismatches are surfaced directly to the caller.

## Using Real Embeddings

The samples use a toy 3-dimensional hash-based embedding function for simplicity. To use real embeddings:

```python
from agent_framework.openai import OpenAIEmbeddingClient
from azure.identity.aio import AzureCliCredential

# Create an embedding client
embedding_client = OpenAIEmbeddingClient(
    azure_endpoint="https://<resource>.openai.azure.com",
    model="text-embedding-ada-002",
    credential=AzureCliCredential(),
)

# Pass it to the context provider
provider = CosmosContextProvider(
    embedding_function=embedding_client,
    ...
)
```

When using real embeddings, update the container's vector embedding policy to match your model's dimensions (e.g., 1536 for `text-embedding-ada-002`).

## Running the Examples

```bash
# From the python/ directory:

# Vector search + writeback
uv run samples/02-agents/context_providers/azure_cosmos/cosmos_context_basics.py

# Full-text search
uv run samples/02-agents/context_providers/azure_cosmos/cosmos_context_fulltext.py

# Hybrid search
uv run samples/02-agents/context_providers/azure_cosmos/cosmos_context_hybrid.py

# Shared knowledge across conversations
uv run samples/02-agents/context_providers/azure_cosmos/cosmos_context_shared.py
```

## How the Samples Work

### Vector Search + Writeback (`cosmos_context_basics.py`)

1. Create a `CosmosContextProvider` with vector search mode
2. Ask questions -- the agent answers using its own knowledge
3. After each run, the conversation exchange is automatically written back to Cosmos
4. A follow-up question retrieves the written-back exchanges as additional context
5. Clean up all documents

### Full-Text Search (`cosmos_context_fulltext.py`)

1. Create a `CosmosContextProvider` with full-text search mode (no embedding function needed)
2. Ask questions -- the provider retrieves documents by BM25 keyword relevance
3. After each run, the exchange is written back to Cosmos
4. Follow-up questions can retrieve prior exchanges by keyword matching
5. Clean up all documents

### Hybrid Search (`cosmos_context_hybrid.py`)

1. Create a `CosmosContextProvider` with hybrid search mode
2. Ask questions -- the provider retrieves documents using both vector similarity and keyword matching via RRF
3. Demonstrate weighted hybrid search with custom RRF weights to tune the balance
4. Clean up all documents

### Shared Knowledge (`cosmos_context_shared.py`)

1. Seed knowledge documents into a shared partition (simulating pre-existing context from other sessions)
2. Run two separate agent sessions that both use the same `partition_key`
3. Both sessions can retrieve the shared knowledge and each other's written-back exchanges
4. Clean up all documents in the shared partition

## Troubleshooting

1. **403 Forbidden on data operations**
   - Assign the `Cosmos DB Built-in Data Contributor` role to your principal (see Prerequisites)
   - Run `az login` to refresh credentials

2. **403 on `create_database_if_not_exists`**
   - AAD data-plane tokens cannot perform control-plane operations (creating databases/containers)
   - Create the database and container via Azure CLI or the Portal instead

3. **Vector search errors (SC2210)**
   - Ensure your container has the correct vector embedding policy and vector index
   - Verify the `EnableNoSQLVectorSearch` capability is enabled on the account

4. **Full-text search errors**
   - Ensure `EnableNoSQLFullTextSearch` capability is enabled on the account
   - Verify the container has a full-text index on the `content` field

5. **No results returned**
   - By default, the provider scopes queries to the current `session_id`. If you seeded documents under a different partition, set `partition_key` on the provider to match
   - Verify documents have embeddings in the `embedding` field (for vector/hybrid modes)
   - Try increasing `top_k` or `scan_limit`

6. **Partition key configuration errors**
   - Make sure your container's partition key path and indexing policies are configured correctly before using the provider. The provider reads the partition key path from the container at startup to write the correct field into documents.
   - If you set a custom `partition_key` but the container's partition key path is `/session_id`, writeback documents will use your custom value as the `session_id` field. This means the real conversation ID is overwritten in that field. To keep them independent, use a container with a partition key path other than `/session_id`.
   - If queries return no results with a custom `partition_key`, verify that existing documents in the container actually have the matching partition key value. The provider always scopes queries to a single partition.
   - Cosmos DB errors from partition key mismatches are surfaced directly to the caller.

## Additional Resources

- [Azure Cosmos DB Vector Search](https://learn.microsoft.com/azure/cosmos-db/nosql/vector-search)
- [Azure Cosmos DB Full-Text Search](https://learn.microsoft.com/azure/cosmos-db/gen-ai/full-text-search)
- [Azure Cosmos DB Hybrid Search](https://learn.microsoft.com/azure/cosmos-db/gen-ai/hybrid-search)
- [Azure Cosmos DB RBAC](https://learn.microsoft.com/azure/cosmos-db/how-to-setup-rbac)
