# Get Started with Microsoft Agent Framework Azure AI Search

Please install this package via pip:

```bash
pip install agent-framework-azure-ai-search --pre
```

## Azure AI Search Integration

The Azure AI Search integration provides context providers for RAG (Retrieval Augmented Generation) capabilities with two modes:

- **Semantic Mode**: Fast hybrid search (vector + keyword) with semantic ranking
- **Agentic Mode**: Multi-hop reasoning using Knowledge Bases for complex queries

### API versions: stable vs preview

The integration follows the `azure-search-documents` SDK's stable/preview channels:

| Channel | Install | Default REST `api-version` |
| --- | --- | --- |
| **Stable** | `pip install azure-search-documents` (`>=12.0.0`) | `2026-04-01` |
| **Preview** | `pip install --pre azure-search-documents` (`12.1.0b1`) | `2026-05-01-preview` |

By default the provider lets the installed SDK pick its `api-version`. Pass `api_version`
to pin it explicitly using the exported constants:

```python
from agent_framework_azure_ai_search import PREVIEW_API_VERSION, STABLE_API_VERSION

provider = AzureAISearchContextProvider(..., api_version=STABLE_API_VERSION)
```

Agentic **output modes** (`answer_synthesis`) and **extended reasoning effort**
(`low`/`medium`) are preview-only: they require the preview SDK and `PREVIEW_API_VERSION`.
On the stable SDK the provider uses extractive output with minimal reasoning effort, and
raises an actionable error if a preview-only option is requested.

### Basic Usage Example

See the [Azure AI Search context provider examples](../../samples/02-agents/context_providers/azure_ai_search/) which demonstrate:

- Semantic search with hybrid (vector + keyword) queries
- Agentic mode with Knowledge Bases for complex multi-hop reasoning
- Environment variable configuration with Settings class
- API key and managed identity authentication
