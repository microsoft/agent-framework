# Azure Cosmos DB Context Provider Examples

The Azure Cosmos DB context provider enables Retrieval Augmented Generation (RAG) for your agents using Azure Cosmos DB as a knowledge store. It retrieves relevant documents before each agent run (via vector, full-text, or hybrid search) and writes conversation messages back to the container after each run, building a growing knowledge base.

This folder contains examples demonstrating how to use the `CosmosContextProvider` with the Agent Framework.

## Examples

| File | Description |
|------|-------------|
| [`cosmos_context_basics.py`](cosmos_context_basics.py) | **Basic RAG**: Seed knowledge documents into Cosmos DB, then ask an agent questions — the provider retrieves relevant context automatically. Uses vector search with toy embeddings. |
| [`cosmos_context_writeback.py`](cosmos_context_writeback.py) | **Full lifecycle**: Conversation writeback + cross-session retrieval. Messages are persisted after each run, then retrieved as context in subsequent sessions — demonstrating knowledge accumulation. |

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
| `AZURE_COSMOS_KEY` | No | Account key — if not set, uses `AzureCliCredential` (Entra ID) |

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
| **Hybrid** | Combines vector and full-text with `RRF` (Reciprocal Rank Fusion) | Best of both — recommended for production |

Set the mode via the `search_mode` constructor parameter:

```python
from agent_framework_azure_cosmos import CosmosContextProvider, CosmosContextSearchMode

provider = CosmosContextProvider(
    search_mode=CosmosContextSearchMode.HYBRID,  # or VECTOR, FULL_TEXT
    ...
)
```

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

# Basic RAG sample
uv run samples/02-agents/context_providers/azure_cosmos/cosmos_context_basics.py

# Full lifecycle (writeback + retrieval)
uv run samples/02-agents/context_providers/azure_cosmos/cosmos_context_writeback.py
```

## How the Samples Work

### Basic RAG Flow (`cosmos_context_basics.py`)

1. Seed knowledge documents into the Cosmos container with embeddings
2. Create a `CosmosContextProvider` with vector search mode
3. Create an Agent with the provider as a context provider
4. User asks a question → provider retrieves relevant docs from Cosmos → agent answers
5. Clean up seeded documents

### Full Lifecycle Flow (`cosmos_context_writeback.py`)

1. Create a `CosmosContextProvider` (writeback is automatic via `after_run`)
2. First conversation turn — user message + assistant response are persisted to Cosmos with embeddings
3. Start a **new session** and ask a related question
4. Provider retrieves the previously written content as context → agent answers from accumulated knowledge
5. Clean up written documents

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
   - Check that documents have the correct `session_id` matching the provider's `partition_key`
   - Verify documents have embeddings in the `embedding` field (for vector/hybrid modes)
   - Try increasing `top_k` or `scan_limit`

## Additional Resources

- [Azure Cosmos DB Vector Search](https://learn.microsoft.com/azure/cosmos-db/nosql/vector-search)
- [Azure Cosmos DB Full-Text Search](https://learn.microsoft.com/azure/cosmos-db/nosql/query/full-text-search)
- [Azure Cosmos DB Hybrid Search](https://learn.microsoft.com/azure/cosmos-db/nosql/query/hybrid-search)
- [Azure Cosmos DB RBAC](https://learn.microsoft.com/azure/cosmos-db/how-to-setup-rbac)
