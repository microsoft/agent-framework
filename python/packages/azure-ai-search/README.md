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

The integration auto-detects which build of `azure-search-documents` is installed — there is
nothing to configure in code:

| Channel | Install | Data-plane `api-version` (chosen by the SDK) |
| --- | --- | --- |
| **Stable** | `pip install azure-search-documents` (`>=12.0.0`) | `2026-04-01` |
| **Preview** | `pip install --pre azure-search-documents` (e.g. `12.1.0b1`) | `2026-05-01-preview` |

The provider never pins an `api-version`; the installed build selects its own, so newer
releases work without code changes.

Agentic **output modes** (`answer_synthesis`) and **extended reasoning effort** (`low`/`medium`)
ship only in the preview build. When a stable build is installed, the provider uses extractive
output with minimal reasoning effort and raises an actionable error if a preview-only option is
explicitly requested. Switching channels is a single change — the install — with no code edits.

### Basic Usage Example

See the [Azure AI Search context provider examples](../../samples/02-agents/context_providers/azure_ai_search/) which demonstrate:

- Semantic search with hybrid (vector + keyword) queries
- Agentic mode with Knowledge Bases for complex multi-hop reasoning
- Environment variable configuration with Settings class
- API key and managed identity authentication
