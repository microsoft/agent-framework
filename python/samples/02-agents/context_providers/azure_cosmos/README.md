# Azure Cosmos DB Context Provider Examples

The Azure Cosmos DB context provider enables Retrieval Augmented Generation (RAG) for your agents using Azure Cosmos DB as a knowledge store. It retrieves relevant documents before each agent run (via vector, full-text, or hybrid search) and writes conversation messages back to the container after each run, building a growing knowledge base.

This folder contains examples demonstrating how to use the `CosmosContextProvider` with the Agent Framework.

## Examples

| File | Description |
|------|-------------|
| [`cosmos_context_basics.py`](cosmos_context_basics.py) | **Vector search + writeback**: Ask questions using vector search (default mode) and see how conversation exchanges are written back into the container for future retrieval. |
| [`cosmos_context_fulltext.py`](cosmos_context_fulltext.py) | **Full-text search**: Retrieve documents by keyword relevance using BM25 ranking. No embedding function needed. |
| [`cosmos_context_hybrid.py`](cosmos_context_hybrid.py) | **Hybrid search**: Combine vector and full-text search via Reciprocal Rank Fusion (RRF). Also demonstrates optional weighted RRF to tune the balance between semantic and keyword results. |

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

When no `partition_key` is set, each conversation reads and writes only its own documents. You can override this by setting `partition_key` on the constructor to scope reads and writes to a specific partition value.

```python
provider = CosmosContextProvider(
    partition_key="my-partition",
    ...
)
```

The provider reads the container's partition key path at startup and writes the correct field into documents on writeback. All Cosmos DB configuration (partition key path, indexing policies, vector/full-text policies) is the application owner's responsibility. The provider does not create or modify Cosmos resources.

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
   - Verify documents have embeddings in the `embedding` field (for vector/hybrid modes)
   - Try increasing `top_k` or `scan_limit`

6. **Partition key configuration errors**
   - Make sure your container's partition key path and indexing policies are configured correctly before using the provider. The provider reads the partition key path from the container at startup to write the correct field into documents.
   - Cosmos DB errors from partition key mismatches are surfaced directly to the caller.

## Additional Resources

- [Azure Cosmos DB Vector Search](https://learn.microsoft.com/azure/cosmos-db/nosql/vector-search)
- [Azure Cosmos DB Full-Text Search](https://learn.microsoft.com/azure/cosmos-db/gen-ai/full-text-search)
- [Azure Cosmos DB Hybrid Search](https://learn.microsoft.com/azure/cosmos-db/gen-ai/hybrid-search)
- [Azure Cosmos DB RBAC](https://learn.microsoft.com/azure/cosmos-db/how-to-setup-rbac)
