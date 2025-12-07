# Context Provider Examples

Context providers enable agents to maintain memory, retrieve relevant information, and enhance conversations with external context. The Agent Framework supports various context providers for different use cases, from simple in-memory storage to advanced persistent solutions with search capabilities.

This folder contains examples demonstrating how to use different context providers with the Agent Framework.

## Overview

Context providers implement two key methods:

- **`invoking`**: Called before the agent processes a request. Provides additional context, instructions, or retrieved information to enhance the agent's response.
- **`invoked`**: Called after the agent generates a response. Allows for storing information, updating memory, or performing post-processing.

## Examples

### Simple Context Provider

| File | Description | Installation |
|------|-------------|--------------|
| [`simple_context_provider.py`](simple_context_provider.py) | Demonstrates building a custom context provider that extracts and stores user information (name and age) from conversations. Shows how to use structured output to extract data and provide dynamic instructions based on stored context. | No additional package required - uses core `agent-framework` |

**Install:**
```bash
pip install agent-framework-azure-ai
```

### Azure AI Search

| File | Description |
|------|-------------|
| [`azure_ai_search/azure_ai_with_search_context_agentic.py`](azure_ai_search/azure_ai_with_search_context_agentic.py) | **Agentic mode** (recommended for most scenarios): Uses Knowledge Bases in Azure AI Search for query planning and multi-hop reasoning. Provides more accurate results through intelligent retrieval. Slightly slower with more token consumption. |
| [`azure_ai_search/azure_ai_with_search_context_semantic.py`](azure_ai_search/azure_ai_with_search_context_semantic.py) | **Semantic mode** (fast queries): Fast hybrid search combining vector and keyword search with semantic ranking. Best for scenarios where speed is critical. |

**Install:**
```bash
pip install agent-framework-azure-ai-search agent-framework-azure-ai
```

**Prerequisites:**
- Azure AI Search service with a search index
- Azure AI Foundry project with a model deployment
- For agentic mode: Azure OpenAI resource for Knowledge Base model calls
- Environment variables: `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_INDEX_NAME`, `AZURE_AI_PROJECT_ENDPOINT`

**Key Concepts:**
- **Agentic mode**: Intelligent retrieval with multi-hop reasoning, better for complex queries
- **Semantic mode**: Fast hybrid search with semantic ranking, better for simple queries and speed

### Mem0

The [mem0](mem0/) folder contains examples using Mem0, a self-improving memory layer that enables applications to have long-term memory capabilities.

| File | Description |
|------|-------------|
| [`mem0/mem0_basic.py`](mem0/mem0_basic.py) | Basic example storing and retrieving user preferences across different conversation threads. |
| [`mem0/mem0_threads.py`](mem0/mem0_threads.py) | Advanced thread scoping strategies: global scope (memories shared), per-operation scope (memories isolated), and multiple agents with different memory configurations. |
| [`mem0/mem0_oss.py`](mem0/mem0_oss.py) | Using Mem0 Open Source self-hosted version as the context provider. |

**Install:**
```bash
pip install agent-framework-mem0
```

**Prerequisites:**
- Mem0 API key from [app.mem0.ai](https://app.mem0.ai/) OR self-host [Mem0 Open Source](https://docs.mem0.ai/open-source/overview)
- For Mem0 Platform: `MEM0_API_KEY` environment variable
- For Mem0 OSS: `OPENAI_API_KEY` for embedding generation

**Key Concepts:**
- **Global Scope**: Memories shared across all conversation threads
- **Thread Scope**: Memories isolated per conversation thread
- **Memory Association**: Records can be associated with `user_id`, `agent_id`, `thread_id`, or `application_id`

See the [mem0 README](mem0/README.md) for detailed documentation.

### Redis

The [redis](redis/) folder contains examples using Redis (RediSearch) for persistent, searchable memory with full-text and optional hybrid vector search.

| File | Description |
|------|-------------|
| [`redis/redis_basics.py`](redis/redis_basics.py) | Standalone provider usage and agent integration. Demonstrates writing messages, full-text/hybrid search, persisting preferences, and tool output memory. |
| [`redis/redis_conversation.py`](redis/redis_conversation.py) | Conversational examples showing memory persistence across sessions. |
| [`redis/redis_threads.py`](redis/redis_threads.py) | Thread scoping: global scope, per-operation scope, and multiple agents with isolated memory via different `agent_id` values. |

**Install:**
```bash
pip install agent-framework-redis
```

**Prerequisites:**
- Running Redis with RediSearch (Redis Stack or managed service)
  - **Docker**: `docker run --name redis -p 6379:6379 -d redis:8.0.3`
  - **Redis Cloud**: [redis.io/cloud](https://redis.io/cloud/)
  - **Azure Managed Redis**: [Azure quickstart](https://learn.microsoft.com/azure/redis/quickstart-create-managed-redis)
- Optional: `OPENAI_API_KEY` for vector embeddings (hybrid search)

**Key Concepts:**
- **Full-text search**: Fast keyword-based retrieval
- **Hybrid vector search**: Optional embeddings for semantic search (`vectorizer_choice="openai"` or `"hf"`)
- **Memory scoping**: Partition by `application_id`, `agent_id`, `user_id`, or `thread_id`
- **Thread scoping**: `scope_to_per_operation_thread_id=True` isolates memory per operation

See the [redis README](redis/README.md) for detailed documentation.

## Choosing a Context Provider

| Provider | Use Case | Persistence | Search | Complexity |
|----------|----------|-------------|--------|------------|
| **Simple/Custom** | Learning, prototyping, simple memory needs | No (in-memory) | No | Low |
| **Azure AI Search** | RAG, document search, enterprise knowledge bases | Yes | Hybrid + Semantic | Medium |
| **Mem0** | Long-term user memory, preferences, personalization | Yes (cloud/self-hosted) | Semantic | Low-Medium |
| **Redis** | Fast retrieval, session memory, full-text + vector search | Yes | Full-text + Hybrid | Medium |

## Common Patterns

### 1. User Preference Memory
Store and retrieve user preferences, settings, or personal information across sessions.
- **Examples**: `simple_context_provider.py`, `mem0/mem0_basic.py`, `redis/redis_basics.py`

### 2. Document Retrieval (RAG)
Retrieve relevant documents or knowledge base articles to answer questions.
- **Examples**: `azure_ai_search/azure_ai_with_search_context_*.py`

### 3. Conversation History
Maintain conversation context across multiple turns and sessions.
- **Examples**: `redis/redis_conversation.py`, `mem0/mem0_threads.py`

### 4. Thread Scoping
Isolate memory per conversation thread or share globally across threads.
- **Examples**: `mem0/mem0_threads.py`, `redis/redis_threads.py`

### 5. Multi-Agent Memory
Different agents with isolated or shared memory configurations.
- **Examples**: `mem0/mem0_threads.py`, `redis/redis_threads.py`

## Building Custom Context Providers

To create a custom context provider, implement the `ContextProvider` protocol:

```python
from agent_framework import ContextProvider, Context, ChatMessage
from collections.abc import MutableSequence, Sequence
from typing import Any

class MyContextProvider(ContextProvider):
    async def invoking(
        self,
        messages: ChatMessage | MutableSequence[ChatMessage],
        **kwargs: Any
    ) -> Context:
        """Provide context before the agent processes the request."""
        # Return additional instructions, messages, or context
        return Context(instructions="Additional instructions here")

    async def invoked(
        self,
        request_messages: ChatMessage | Sequence[ChatMessage],
        response_messages: ChatMessage | Sequence[ChatMessage] | None = None,
        invoke_exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """Process the response after the agent generates it."""
        # Store information, update memory, etc.
        pass

    def serialize(self) -> str:
        """Serialize the provider state for persistence."""
        return "{}"
```

See `simple_context_provider.py` for a complete example.

## Additional Resources

- [Agent Framework Documentation](https://github.com/microsoft/agent-framework)
- [Azure AI Search Documentation](https://learn.microsoft.com/azure/search/)
- [Mem0 Documentation](https://docs.mem0.ai/)
- [Redis Documentation](https://redis.io/docs/)
