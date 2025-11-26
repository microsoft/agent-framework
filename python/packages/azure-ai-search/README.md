# Get Started with Microsoft Agent Framework Azure AI Search

Please install this package via pip:

```bash
pip install agent-framework-azure-ai-search --pre
```

## Azure AI Search Integration

The Azure AI Search integration provides context providers for RAG (Retrieval Augmented Generation) capabilities with two modes:

- **Semantic Mode**: Fast hybrid search (vector + keyword) with semantic ranking
- **Agentic Mode**: Multi-hop reasoning using Knowledge Bases for complex queries

### Basic Usage Example

See the [Azure AI Search context provider examples](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/agents/azure_ai/) which demonstrate:

- Semantic search with hybrid (vector + keyword) queries
- Agentic mode with Knowledge Bases for complex multi-hop reasoning
- Environment variable configuration with Settings class
- API key and managed identity authentication
