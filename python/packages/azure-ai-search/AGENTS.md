# Azure AI Search Package (agent-framework-azure-ai-search)

Integration with Azure AI Search for RAG (Retrieval-Augmented Generation).

## Main Classes

- **`AzureAISearchContextProvider`** - Context provider that retrieves relevant documents from Azure AI Search
- **`AzureAISearchSettings`** - Pydantic settings for Azure AI Search configuration

## API versions: stable vs preview

The package depends on `azure-search-documents>=12.0.0,<13`, which spans both channels, and
auto-detects which build is installed — there is no `api_version` parameter:

| Channel | Install | SDK | Data-plane `api-version` (chosen by the SDK) |
| --- | --- | --- | --- |
| **Stable / GA** | `pip install azure-search-documents` | `12.0.0` | `2026-04-01` |
| **Preview** | `pip install --pre azure-search-documents` | `12.1.0b1` | `2026-05-01-preview` |

The provider never pins an `api-version`; the installed build picks its own default, so newer
releases work without code changes (single source of truth = the install).

Capability gating keys off `_preview_agentic_features_available` — whether the preview build's
agentic symbols (`KnowledgeRetrieval{Low,Medium}ReasoningEffort`, `KnowledgeRetrievalOutputMode`)
can be imported. Agentic **output mode** (`answer_synthesis`) and **extended reasoning effort**
(`low`/`medium`) ship only in the preview build; on a stable build the provider omits them
(extractive + minimal) and raises an actionable `ValueError` (citing the installed version) if
they are explicitly requested. Semantic mode is unaffected.

Agentic query-time user identity is also preview-only. It is gated by
`_query_source_authorization_available`; when enabled, `query_source_credential` supplies a
per-request Azure AI Search token through the `x-ms-query-source-authorization` header. Both sync
and async Azure token credentials are supported, starting with `azure-search-documents>=12.1.0b1`.

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
