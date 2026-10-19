# Azure AI Search Context Provider Examples

Azure AI Search context provider enables Retrieval Augmented Generation (RAG) with your agents by retrieving relevant documents from Azure AI Search indexes. It supports two search modes optimized for different use cases.

This folder contains examples demonstrating how to use the Azure AI Search context provider with the Agent Framework.

## Examples

| File | Description |
|------|-------------|
| [`search_context_agentic.py`](search_context_agentic.py) | **Agentic mode** (recommended for most scenarios): Uses Knowledge Bases in Azure AI Search for query planning and multi-hop reasoning. Provides more accurate results through intelligent retrieval with automatic query reformulation. Slightly slower with more token consumption for query planning. [Learn more](https://learn.microsoft.com/azure/search/agentic-retrieval-overview) |
| [`search_context_semantic.py`](search_context_semantic.py) | **Semantic mode** (fast queries): Fast hybrid search combining vector and keyword search with semantic ranking. Returns raw search results as context. Best for scenarios where speed is critical and simple retrieval is sufficient. |

## Installation

```bash
pip install agent-framework-azure-ai-search agent-framework-foundry
```

## Prerequisites

### Required Resources

1. **Azure AI Search service** with either an existing Knowledge Base (agentic mode) or a search index containing your documents (semantic mode or index-backed agentic setup)
   - [Create Azure AI Search service](https://learn.microsoft.com/azure/search/search-create-service-portal)
   - [Create and populate a search index](https://learn.microsoft.com/azure/search/search-what-is-an-index)

2. **Microsoft Foundry project** with a model deployment
   - [Create Microsoft Foundry project](https://learn.microsoft.com/azure/ai-studio/how-to/create-projects)
   - Deploy a model (e.g., GPT-4o)

3. **For index-backed agentic setup only**: Azure OpenAI resource for Knowledge Base model calls
   - [Create Azure OpenAI resource](https://learn.microsoft.com/azure/ai-services/openai/how-to/create-resource)
   - Note: This is separate from your Microsoft Foundry project endpoint

### Authentication

Both examples support two authentication methods:

- **API Key**: Set `AZURE_SEARCH_API_KEY` environment variable
- **Entra ID (Azure CLI)**: Uses `AzureCliCredential` when API key is not provided

Run `az login` if using Entra ID authentication.

### API versions (stable vs preview)

The provider auto-detects which build of `azure-search-documents` is installed — nothing to
configure in code:

- **Stable / GA** — `pip install azure-search-documents` (`>=12.0.0`) → api-version `2026-04-01`.
- **Preview** — `pip install --pre azure-search-documents` (e.g. `12.1.0b1`) → api-version `2026-05-01-preview`.

The installed build picks its own api-version, so newer releases work without code changes.

Agentic `knowledge_base_output_mode="answer_synthesis"` and `retrieval_reasoning_effort` of
`"low"`/`"medium"` ship **only** in the preview build. On a stable build the provider uses
extractive output with minimal reasoning effort and raises an actionable error if a preview-only
option is requested. To enable them, just install the preview build (`pip install --pre
azure-search-documents`) — no code change.

## Configuration

### Environment Variables

**Common (both modes):**
- `AZURE_SEARCH_ENDPOINT`: Your Azure AI Search endpoint (e.g., `https://myservice.search.windows.net`)
- `FOUNDRY_PROJECT_ENDPOINT`: Your Microsoft Foundry project endpoint
- `FOUNDRY_MODEL`: Model deployment name (e.g., `gpt-4o`, defaults to `gpt-4o`)
- `AZURE_SEARCH_API_KEY`: _(Optional)_ Your search API key - if not provided, uses AzureCliCredential

**Semantic mode:**
- `AZURE_SEARCH_INDEX_NAME`: Name of your search index

**Agentic mode (choose one setup):**
- Existing Knowledge Base: set `AZURE_SEARCH_KNOWLEDGE_BASE_NAME`.
- Create a Knowledge Base from an index: set `AZURE_SEARCH_INDEX_NAME` and `AZURE_OPENAI_RESOURCE_URL`; the sample uses `FOUNDRY_MODEL` for the Knowledge Base model.
  - **Important**: `AZURE_OPENAI_RESOURCE_URL` is different from `FOUNDRY_PROJECT_ENDPOINT`. It is needed only for the index-backed setup.

### Example .env file

**For Semantic Mode:**
```env
AZURE_SEARCH_ENDPOINT=https://myservice.search.windows.net
AZURE_SEARCH_INDEX_NAME=my-index
FOUNDRY_PROJECT_ENDPOINT=https://<resource-name>.services.ai.azure.com/api/projects/<project-name>
FOUNDRY_MODEL=gpt-4o
# Optional - omit to use Entra ID
AZURE_SEARCH_API_KEY=your-search-key
```

**For Agentic Mode with an existing Knowledge Base:**
```env
AZURE_SEARCH_ENDPOINT=https://myservice.search.windows.net
AZURE_SEARCH_KNOWLEDGE_BASE_NAME=my-knowledge-base
FOUNDRY_PROJECT_ENDPOINT=https://<resource-name>.services.ai.azure.com/api/projects/<project-name>
FOUNDRY_MODEL=gpt-4o
# Optional - omit to use Entra ID
AZURE_SEARCH_API_KEY=your-search-key
```

**For Agentic Mode that creates a Knowledge Base from an index:**
Use the semantic mode variables and add:
```env
AZURE_OPENAI_RESOURCE_URL=https://myresource.openai.azure.com
```

When constructing the provider directly, pass either `knowledge_base_name` or `index_name`, never both.

## Search Modes Comparison

| Feature | Semantic Mode | Agentic Mode |
|---------|--------------|--------------|
| **Speed** | Fast | Slower (query planning overhead) |
| **Token Usage** | Lower | Higher (query reformulation) |
| **Retrieval Strategy** | Hybrid search + semantic ranking | Multi-hop reasoning with Knowledge Base |
| **Query Handling** | Direct search | Automatic query reformulation |
| **Best For** | Simple queries, speed-critical apps | Complex queries, multi-document reasoning |
| **Additional Setup** | None | Existing Knowledge Base, or an index + OpenAI resource for Knowledge Base creation |

### When to Use Semantic Mode

- **Simple queries** where direct keyword/vector search is sufficient
- **Speed is critical** and you need low latency
- **Straightforward retrieval** from single documents
- **Lower token costs** are important

### When to Use Agentic Mode

- **Complex queries** requiring multi-hop reasoning
- **Cross-document analysis** where information spans multiple sources
- **Ambiguous queries** that benefit from automatic reformulation
- **Higher accuracy** is more important than speed
- You need **intelligent query planning** and document synthesis

## How the Examples Work

### Semantic Mode Flow

1. User query is sent to Azure AI Search
2. Hybrid search (vector + keyword) retrieves relevant documents
3. Semantic ranking reorders results for relevance
4. Top-k documents are returned as context
5. Agent generates response using retrieved context

### Agentic Mode Flow

1. User query is sent to the Knowledge Base
2. Knowledge Base plans the retrieval strategy
3. Multiple search queries may be executed (multi-hop)
4. Retrieved information is synthesized
5. Enhanced context is provided to the agent
6. Agent generates response with comprehensive context

## Code Example

### Semantic Mode

```python
from agent_framework import Agent
from agent_framework.azure import AzureAISearchContextProvider
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

# Create search provider with semantic mode (default)
search_provider = AzureAISearchContextProvider(
    endpoint=search_endpoint,
    index_name=index_name,
    api_key=search_key,  # Or use credential for Entra ID
    mode="semantic",  # Default mode
    top_k=3,  # Number of documents to retrieve
)

# Create agent with search context
async with FoundryChatClient(
    project_endpoint=project_endpoint,
    model=model_deployment,
    credential=AzureCliCredential(),
) as client:
    async with Agent(
        client=client,
        context_providers=[search_provider],
    ) as agent:
        response = await agent.run("What information is in the knowledge base?")
```

### Agentic Mode

```python
from agent_framework.azure import AzureAISearchContextProvider

# Connect to an existing Knowledge Base; no index-backed setup parameters are needed.
search_provider = AzureAISearchContextProvider(
    endpoint=search_endpoint,
    api_key=search_key,
    mode="agentic",
    knowledge_base_name=knowledge_base_name,
    top_k=5,
)

# Use with agent (same as semantic mode)
async with Agent(
    client=client,
    model=model_deployment,
    context_providers=[search_provider],
) as agent:
    response = await agent.run("Analyze and compare topics across documents")
```

## Running the Examples

1. **Set up environment variables** (see Configuration section above)

2. **Ensure you have an Azure AI Search index** with documents:
   ```bash
   # Verify your index exists
   curl -X GET "https://myservice.search.windows.net/indexes/my-index?api-version=2024-07-01" \
        -H "api-key: YOUR_API_KEY"
   ```

3. **For agentic mode**: Create a Knowledge Base in Azure AI Search
   - [Knowledge Base documentation](https://learn.microsoft.com/azure/search/knowledge-store-create-portal)

4. **Run the examples**:
   ```bash
   # Semantic mode (fast, simple)
   python search_context_semantic.py

   # Agentic mode (intelligent, complex)
   python search_context_agentic.py
   ```

## Key Parameters

### Common Parameters

- `endpoint`: Azure AI Search service endpoint
- `index_name`: Name of the search index
- `api_key`: API key for authentication (optional, can use credential instead)
- `credential`: Azure credential for Entra ID auth (e.g., `AzureCliCredential()`)
- `mode`: Search mode - `"semantic"` (default) or `"agentic"`
- `top_k`: Number of documents to retrieve (default: 5; the semantic sample explicitly uses 3)

### Semantic Mode Parameters

- `semantic_configuration_name`: Name of semantic configuration in your index (optional)

### Agentic Mode Parameters

- `knowledge_base_name`: Name of an existing Knowledge Base; omit `index_name` for this setup
- `index_name`: Index used to create a Knowledge Base; omit `knowledge_base_name` for this setup
- `azure_openai_resource_url`: Azure OpenAI resource URL, required for index-backed setup
- `model`: Azure OpenAI model deployment name, required for index-backed setup

## Troubleshooting

### Common Issues

1. **Authentication errors**
   - Ensure `AZURE_SEARCH_API_KEY` is set, or run `az login` for Entra ID auth
   - Verify your credentials have search permissions

2. **Index not found**
   - Verify `AZURE_SEARCH_INDEX_NAME` matches your index name exactly
   - Check that the index exists and contains documents

3. **Agentic mode errors**
   - Choose an existing Knowledge Base or index-backed setup, as described above
   - For index-backed setup, verify `AZURE_OPENAI_RESOURCE_URL` points to your Azure OpenAI resource (not the Foundry project endpoint)
   - For index-backed setup, check that your OpenAI resource has the necessary model deployments

4. **No results returned**
   - Verify your index has documents with vector embeddings (for semantic/hybrid search)
   - Check that your queries match the content in your index
   - Try increasing `top_k` parameter

5. **Slow responses in agentic mode**
   - This is expected - agentic mode trades speed for accuracy
   - Consider semantic mode for speed-critical applications

## Performance Tips

- **Use semantic mode** as the default for most scenarios - it's fast and effective
- **Switch to agentic mode** when you need multi-hop reasoning or complex queries
- **Adjust `top_k`** based on your needs - higher values provide more context but increase token usage
- **Enable semantic configuration** in your index for better semantic ranking
- **Use Entra ID authentication** in production for better security

## Additional Resources

- [Azure AI Search Documentation](https://learn.microsoft.com/azure/search/)
- [Microsoft Foundry Documentation](https://learn.microsoft.com/azure/ai-studio/)
- [RAG with Azure AI Search](https://learn.microsoft.com/azure/search/retrieval-augmented-generation-overview)
- [Semantic Search in Azure AI Search](https://learn.microsoft.com/azure/search/semantic-search-overview)
- [Knowledge Bases in Azure AI Search](https://learn.microsoft.com/azure/search/knowledge-store-concept-intro)
- [Agentic Retrieval in Azure AI Search](https://learn.microsoft.com/azure/search/agentic-retrieval-overview)
