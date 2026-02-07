# Azure AI Search Package (agent-framework-azure-ai-search)

Integration with Azure AI Search for RAG (Retrieval-Augmented Generation).

## Main Classes

- **`AzureAISearchContextProvider`** - Context provider that retrieves relevant documents from Azure AI Search
- **`AzureAISearchSettings`** - Pydantic settings for Azure AI Search configuration

## Usage

```python
from agent_framework.azure import AzureAISearchContextProvider

provider = AzureAISearchContextProvider(
    endpoint="https://your-search.search.windows.net",
    index_name="your-index",
)
agent = Agent(..., context_provider=provider)
```

## Import Path

```python
from agent_framework.azure import AzureAISearchContextProvider
# or directly:
from agent_framework_azure_ai_search import AzureAISearchContextProvider
```
