# Azure AI Search Package (agent-framework-azure-ai-search)

Integration with Azure AI Search for RAG (Retrieval-Augmented Generation).

## Main Classes

- **`AzureAISearchContextProvider`** - Context provider that retrieves relevant documents from Azure AI Search
- **`AzureAISearchSettings`** - Pydantic settings for Azure AI Search configuration

## Constants

- **`STABLE_API_VERSION`** (`"2026-04-01"`) - data-plane REST api-version of the stable/GA SDK
- **`PREVIEW_API_VERSION`** (`"2026-05-01-preview"`) - data-plane REST api-version of the preview SDK

## API versions: stable vs preview

The package depends on `azure-search-documents>=12.0.0,<13`, which spans both channels:

| Channel | Install | SDK | Default REST `api-version` |
| --- | --- | --- | --- |
| **Stable / GA** | `pip install azure-search-documents` | `12.0.0` | `2026-04-01` |
| **Preview** | `pip install --pre azure-search-documents` | `12.1.0b1` | `2026-05-01-preview` |

`AzureAISearchContextProvider(..., api_version=...)` forwards the api-version to the
`SearchClient`, `SearchIndexClient`, and `KnowledgeBaseRetrievalClient`. When `api_version`
is `None` (default), the installed SDK chooses its own default.

Capability gating is auto-detected via `_preview_features_active()`, which requires **both**
the preview SDK (`_preview_agentic_features_available`) **and** a preview `api_version` (a
pinned stable api-version such as `2026-04-01` uses the GA wire and disables preview fields).
Agentic **output mode** (`answer_synthesis`) and **extended reasoning effort** (`low`/`medium`)
are preview-only; otherwise the provider omits them (extractive + minimal) and raises an
actionable `ValueError` if they are explicitly requested. Semantic mode is unaffected.

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
