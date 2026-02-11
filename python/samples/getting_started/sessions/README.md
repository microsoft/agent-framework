# Sessions & Context Provider Examples

Sessions and context providers are the core building blocks for agent memory in the Agent Framework. Sessions hold conversation state across turns, while context providers add, retrieve, and persist context before and after each agent invocation.

## Core Concepts

- **`AgentSession`**: Lightweight state container holding a `session_id` and a mutable `state` dict. Pass to `agent.run()` to maintain conversation across turns.
- **`BaseContextProvider`**: Hook that runs `before_run` / `after_run` around each invocation. Use for injecting instructions, RAG context, or metadata.
- **`BaseHistoryProvider`**: Subclass of `BaseContextProvider` for conversation history storage. Implements `get_messages()` / `save_messages()` and handles load/store automatically.
- **`InMemoryHistoryProvider`**: Built-in provider storing messages in `session.state`. Auto-injected when no providers are configured.

## Examples

### Session Management

| File | Description |
|------|-------------|
| [`suspend_resume_session.py`](suspend_resume_session.py) | Suspend and resume sessions via `to_dict()` / `from_dict()` — both service-managed (Azure AI) and in-memory (OpenAI). |
| [`custom_history_provider.py`](custom_history_provider.py) | Implement a custom `BaseHistoryProvider` with dict-based storage. Shows serialization/deserialization. |
| [`redis_history_provider.py`](redis_history_provider.py) | `RedisHistoryProvider` for persistent storage: basic usage, user sessions, persistence across restarts, serialization, and message trimming. |

### Custom Context Providers

| File | Description |
|------|-------------|
| [`simple_context_provider.py`](simple_context_provider.py) | Build a custom `BaseContextProvider` that extracts and stores user information using structured output, then provides dynamic instructions based on stored context. |

### Azure AI Search

| File | Description |
|------|-------------|
| [`azure_ai_search/azure_ai_with_search_context_agentic.py`](azure_ai_search/azure_ai_with_search_context_agentic.py) | **Agentic mode** — Knowledge Bases with query planning and multi-hop reasoning. |
| [`azure_ai_search/azure_ai_with_search_context_semantic.py`](azure_ai_search/azure_ai_with_search_context_semantic.py) | **Semantic mode** — fast hybrid search with semantic ranking. |

### Mem0

| File | Description |
|------|-------------|
| [`mem0/mem0_basic.py`](mem0/mem0_basic.py) | Basic Mem0 integration for user preference memory. |
| [`mem0/mem0_sessions.py`](mem0/mem0_sessions.py) | Session scoping: global scope, per-operation scope, and multi-agent isolation. |
| [`mem0/mem0_oss.py`](mem0/mem0_oss.py) | Mem0 Open Source (self-hosted) integration. |

### Redis

| File | Description |
|------|-------------|
| [`redis/redis_basics.py`](redis/redis_basics.py) | Standalone provider usage, full-text/hybrid search, preferences, and tool output memory. |
| [`redis/redis_conversation.py`](redis/redis_conversation.py) | Conversation persistence across sessions. |
| [`redis/redis_sessions.py`](redis/redis_sessions.py) | Session scoping: global, per-operation, and multi-agent isolation. |
| [`redis/azure_redis_conversation.py`](redis/azure_redis_conversation.py) | Azure Managed Redis with Entra ID authentication. |

## Choosing a Provider

| Provider | Use Case | Persistence | Search |
|----------|----------|-------------|--------|
| **InMemoryHistoryProvider** | Prototyping, stateless apps | Session state only | No |
| **Custom BaseHistoryProvider** | File/DB-backed storage | Your choice | Your choice |
| **RedisHistoryProvider** | Fast persistent chat history | Yes (Redis) | No |
| **RedisContextProvider** | Searchable memory / RAG | Yes (Redis) | Full-text + Hybrid |
| **Mem0ContextProvider** | Long-term user memory | Yes (cloud/self-hosted) | Semantic |
| **AzureAISearchContextProvider** | Enterprise RAG | Yes (Azure) | Hybrid + Semantic |

## Building Custom Providers

### Custom Context Provider

```python
from agent_framework import AgentSession, BaseContextProvider, SessionContext, Message
from typing import Any

class MyContextProvider(BaseContextProvider):
    def __init__(self):
        super().__init__("my-context")

    async def before_run(self, *, agent: Any, session: AgentSession | None,
                         context: SessionContext, state: dict[str, Any]) -> None:
        context.extend_messages(self.source_id, [Message("system", ["Extra context here"])])

    async def after_run(self, *, agent: Any, session: AgentSession | None,
                        context: SessionContext, state: dict[str, Any]) -> None:
        pass  # Store information, update memory, etc.
```

### Custom History Provider

```python
from agent_framework import BaseHistoryProvider, Message
from collections.abc import Sequence
from typing import Any

class MyHistoryProvider(BaseHistoryProvider):
    def __init__(self):
        super().__init__("my-history")

    async def get_messages(self, session_id: str | None, **kwargs: Any) -> list[Message]:
        ...  # Load from your storage

    async def save_messages(self, session_id: str | None,
                            messages: Sequence[Message], **kwargs: Any) -> None:
        ...  # Persist to your storage
```

See `custom_history_provider.py` and `simple_context_provider.py` for complete examples.
