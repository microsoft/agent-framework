# Context Provider Samples

These samples demonstrate how to use context providers to enrich agent conversations with external knowledge — from custom logic to Azure AI Search (RAG) and memory services.

## Samples

| File / Folder | Description |
|---------------|-------------|
| [`simple_context_provider.py`](simple_context_provider.py) | Implement a custom context provider by extending `ContextProvider` to extract and inject structured user information across turns. |
| [`todo_provider.py`](todo_provider.py) | Use the built-in `TodoProvider` to give an agent todo-list tools. A scripted walkthrough that plans multi-step work and prints the evolving todo list after each turn. |
| [`agent_mode_provider.py`](agent_mode_provider.py) | Use the built-in `AgentModeProvider` to track and switch an agent's operating mode at runtime. An interactive loop with a `/mode` slash command demonstrating the built-in `plan`/`execute` modes and custom modes. |
| [`cross_session_observer.py`](cross_session_observer.py) | Detect injected context messages whose origins differ from the current session, via the `Message.additional_properties["_attribution"]["origin_session_ids"]` field. Self-contained — no LLM credentials required. |
| [`azure_ai_foundry_memory.py`](azure_ai_foundry_memory.py) | Use `FoundryMemoryProvider` to add semantic memory — automatically retrieves, searches, and stores memories via Microsoft Foundry. |
| [`file_memory_provider.py`](file_memory_provider.py) | Use the built-in `FileMemoryProvider` with `FileSystemAgentFileStore` to give an agent tools for storing and recalling memories as files, and configure the `scope` so memories persist and are recalled across separate sessions. |
| [`file_access_data_processing/`](file_access_data_processing/) | Use `FileAccessProvider` with `FileSystemAgentFileStore` to give an agent read/write/search access to a folder of CSV data files. See its own [README](file_access_data_processing/README.md). |
| [`azure_ai_search/`](azure_ai_search/) | Retrieval Augmented Generation (RAG) with Azure AI Search in semantic and agentic modes. See its own [README](azure_ai_search/README.md). |
| [`azure_content_understanding/`](azure_content_understanding/) | Analyze documents, images, audio, and video with Azure Content Understanding and inject the extracted content into agent context. |
| [`mem0/`](mem0/) | Memory-powered context using the Mem0 integration (open-source and managed). See its own [README](mem0/README.md). |
| [`redis/`](redis/) | Redis-backed context providers for conversation memory and sessions. See its own [README](redis/README.md). |

## Prerequisites

**For `cross_session_observer.py`:**
- No external dependencies; runs against in-memory `SessionContext`.

**For `simple_context_provider.py`:**
- `FOUNDRY_PROJECT_ENDPOINT`: Your Microsoft Foundry project endpoint
- `FOUNDRY_MODEL`: Model deployment name
- Azure CLI authentication (`az login`)

**For `todo_provider.py`:**
- `FOUNDRY_PROJECT_ENDPOINT`: Your Microsoft Foundry project endpoint
- `FOUNDRY_MODEL`: Model deployment name
- Azure CLI authentication (`az login`)

**For `agent_mode_provider.py`:**
- `FOUNDRY_PROJECT_ENDPOINT`: Your Microsoft Foundry project endpoint
- `FOUNDRY_MODEL`: Model deployment name
- Azure CLI authentication (`az login`)
- To try the custom `concise`/`detailed` modes instead of the built-in `plan`/`execute` modes, set the in-file `USE_CUSTOM_MODES` constant to `True`.
- This sample is interactive: it reads commands from the console in a loop (type `/exit` to quit).

**For `azure_ai_foundry_memory.py`:**
- `FOUNDRY_PROJECT_ENDPOINT`: Your Microsoft Foundry project endpoint
- `FOUNDRY_MODEL`: Chat/responses model deployment name
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME`: Embedding model deployment name (e.g., `text-embedding-ada-002`)
- Azure CLI authentication (`az login`)

**For `file_memory_provider.py`:**
- `FOUNDRY_PROJECT_ENDPOINT`: Your Microsoft Foundry project endpoint
- `FOUNDRY_MODEL`: Chat model deployment name
- Azure CLI authentication (`az login`)

**For `file_access_data_processing/`:**
- `FOUNDRY_PROJECT_ENDPOINT`: Your Microsoft Foundry project endpoint
- `FOUNDRY_MODEL`: Chat model deployment name
- Azure CLI authentication (`az login`)

See each subfolder's README for provider-specific prerequisites.
