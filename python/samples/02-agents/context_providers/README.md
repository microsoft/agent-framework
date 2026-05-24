# Context Provider Samples

These samples demonstrate how to use context providers to enrich agent conversations with external knowledge — from custom logic to Azure AI Search (RAG) and memory services.

## Samples

| File / Folder | Description |
|---------------|-------------|
| [`simple_context_provider.py`](simple_context_provider.py) | Implement a custom context provider by extending `ContextProvider` to extract and inject structured user information across turns. |
| [`azure_ai_foundry_memory.py`](azure_ai_foundry_memory.py) | Use `FoundryMemoryProvider` to add semantic memory — automatically retrieves, searches, and stores memories via Azure AI Foundry. |
| [`azure_ai_search/`](azure_ai_search/) | Retrieval Augmented Generation (RAG) with Azure AI Search in semantic and agentic modes. See its own [README](azure_ai_search/README.md). |
| [`mem0/`](mem0/) | Memory-powered context using the Mem0 integration (open-source and managed). See its own [README](mem0/README.md). |
| [`redis/`](redis/) | Redis-backed context providers for conversation memory and sessions. See its own [README](redis/README.md). |

## Prerequisites

**For `simple_context_provider.py`:**
- `FOUNDRY_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
- `FOUNDRY_MODEL`: Model deployment name
- Azure CLI authentication (`az login`)

**For `azure_ai_foundry_memory.py`:**
- `FOUNDRY_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
- `FOUNDRY_MODEL`: Chat/responses model deployment name
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME`: Embedding model deployment name (e.g., `text-embedding-ada-002`)
- Azure CLI authentication (`az login`)

See each subfolder's README for provider-specific prerequisites.
