# Conversation & Session Management Samples

These samples demonstrate different approaches to managing conversation history and session state in Agent Framework.

## Samples

| File | Description |
|------|-------------|
| [`suspend_resume_session.py`](suspend_resume_session.py) | Suspend and resume conversation sessions, comparing service-managed sessions (Azure AI Foundry) with in-memory sessions (OpenAI). |
| [`custom_history_provider.py`](custom_history_provider.py) | Implement a custom history provider by extending `BaseHistoryProvider`, enabling conversation persistence in your preferred storage backend. |
| [`redis_history_provider.py`](redis_history_provider.py) | Use Redis as a history provider for persistent conversation history storage across sessions. |

## Prerequisites

**For `suspend_resume_session.py`:**
- `FOUNDRY_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint (service-managed session)
- `FOUNDRY_MODEL`: The Foundry model deployment name
- `OPENAI_API_KEY`: Your OpenAI API key (in-memory session)
- Azure CLI authentication (`az login`)

**For `custom_history_provider.py`:**
- `OPENAI_API_KEY`: Your OpenAI API key

**For `redis_history_provider.py`:**
- `OPENAI_API_KEY`: Your OpenAI API key
- A running Redis server — default URL is `redis://localhost:6379`
  - Override via the `REDIS_URL` environment variable for remote or authenticated instances
  - Quickstart with Docker: `docker run -d --name redis-stack -p 6379:6379 redis/redis-stack-server:latest`
