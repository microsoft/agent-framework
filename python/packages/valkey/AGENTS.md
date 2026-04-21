# Valkey Package (agent-framework-valkey)

Valkey-based storage for agent conversations and context.

## Main Classes

- **`ValkeyChatMessageStore`** - Persistent chat history provider using Valkey
- **`ValkeyContextProvider`** - Context provider with Valkey-backed vector search retrieval

## Usage

```python
from agent_framework_valkey import ValkeyContextProvider, ValkeyChatMessageStore

context_provider = ValkeyContextProvider(host="localhost", port=6379, user_id="u1")
message_store = ValkeyChatMessageStore(host="localhost", port=6379)
```

## Import Path

```python
from agent_framework_valkey import ValkeyContextProvider, ValkeyChatMessageStore
```
