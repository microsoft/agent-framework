# Redis Package (agent-framework-redis)

Redis-based storage for agent threads and context.

## Main Classes

- **`RedisChatMessageStore`** - Persistent message store using Redis
- **`RedisProvider`** - Context provider with Redis backing

## Usage

```python
from agent_framework.redis import RedisChatMessageStore

store = RedisChatMessageStore(redis_url="redis://localhost:6379")
agent = ChatAgent(..., chat_message_store_factory=lambda: store)
```

## Import Path

```python
from agent_framework.redis import RedisChatMessageStore, RedisProvider
# or directly:
from agent_framework_redis import RedisChatMessageStore
```
