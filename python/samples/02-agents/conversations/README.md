# Conversation & Session Management Samples

These samples demonstrate different approaches to managing conversation history and session state in Agent Framework.

## Samples

| File | Description |
|------|-------------|
| [`suspend_resume_session.py`](suspend_resume_session.py) | Suspend and resume conversation sessions, comparing service-managed sessions (Azure AI Foundry) with in-memory sessions (OpenAI). |
| [`custom_history_provider.py`](custom_history_provider.py) | Implement a custom history provider by extending `HistoryProvider`, enabling conversation persistence in your preferred storage backend. |
| [`file_history_provider.py`](file_history_provider.py) | Use the experimental `FileHistoryProvider` with `FoundryChatClient` and a function tool so the local JSON Lines file shows the full tool-calling loop. |
| [`file_history_provider_conversation_persistence.py`](file_history_provider_conversation_persistence.py) | Persist a tool-driven weather conversation with `FileHistoryProvider`, inspect the stored JSONL records, and continue with another city. |
| [`cosmos_history_provider.py`](cosmos_history_provider.py) | Use Azure Cosmos DB as a history provider for durable conversation storage with `CosmosHistoryProvider`. |
| [`cosmos_history_provider_conversation_persistence.py`](cosmos_history_provider_conversation_persistence.py) | Persist and resume conversations across application restarts using `CosmosHistoryProvider` — serialize session state, restore it, and continue with full Cosmos DB history. |
| [`cosmos_history_provider_messages.py`](cosmos_history_provider_messages.py) | Direct message history operations — retrieve stored messages as a transcript, clear session history, and verify data deletion. |
| [`cosmos_history_provider_sessions.py`](cosmos_history_provider_sessions.py) | Multi-session and multi-tenant management — per-tenant session isolation, `list_sessions()` to enumerate, switch between sessions, and resume specific conversations. |
| [`redis_history_provider.py`](redis_history_provider.py) | Use Redis as a history provider for persistent conversation history storage across sessions. |

## Prerequisites

**For `suspend_resume_session.py`:**
- `FOUNDRY_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint (service-managed session)
- `FOUNDRY_MODEL`: The Foundry model deployment name
- `OPENAI_API_KEY`: Your OpenAI API key (in-memory session)
- Azure CLI authentication (`az login`)

**For `custom_history_provider.py`:**
- `OPENAI_API_KEY`: Your OpenAI API key

**For `file_history_provider.py`:**
- `FOUNDRY_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
- `FOUNDRY_MODEL`: The Foundry model deployment name
- Azure CLI authentication (`az login`)
- The sample writes plaintext JSONL conversation logs to disk; use a trusted
  local directory and avoid treating the history files as secure secret storage

**For `file_history_provider_conversation_persistence.py`:**
- `FOUNDRY_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
- `FOUNDRY_MODEL`: The Foundry model deployment name
- Azure CLI authentication (`az login`)
- The sample writes plaintext JSONL conversation logs to disk; use a trusted
  local directory and avoid treating the history files as secure secret storage

**For Cosmos DB samples (`cosmos_history_provider*.py`):**
- `FOUNDRY_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
- `FOUNDRY_MODEL`: The Foundry model deployment name
- `AZURE_COSMOS_ENDPOINT`: Your Azure Cosmos DB account endpoint
- `AZURE_COSMOS_DATABASE_NAME`: The database that stores conversation history
- `AZURE_COSMOS_CONTAINER_NAME`: The container that stores conversation history
- Either `AZURE_COSMOS_KEY` or Azure CLI authentication (`az login`)

**For `redis_history_provider.py`:**
- `OPENAI_API_KEY`: Your OpenAI API key
- A running Redis server — default URL is `redis://localhost:6379`
  - Override via the `REDIS_URL` environment variable for remote or authenticated instances
  - Quickstart with Docker: `docker run -d --name redis-stack -p 6379:6379 redis/redis-stack-server:latest`
