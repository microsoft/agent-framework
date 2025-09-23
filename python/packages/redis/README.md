# Get Started with Microsoft Agent Framework Redis

Please install this package as the extra for `agent-framework`:

```bash
pip install agent-framework[redis]
```

## Components

### Memory Context Provider

The `RedisProvider` enables persistent context & memory capabilities for your agents, allowing them to remember user preferences and conversation context across sessions and threads.

#### Basic Usage Examples

Review the set of [getting started examples](../../samples/getting_started/context_providers/redis/README.md) for using the Redis context provider.

### Redis Chat Message Store

The `RedisChatMessageStore` provides persistent conversation storage using Redis Lists, enabling chat history to survive application restarts and support distributed applications.

#### Key Features

- **Persistent Storage**: Messages survive application restarts
- **Thread Isolation**: Each conversation thread has its own Redis key
- **Message Limits**: Configurable automatic trimming of old messages
- **Serialization Support**: Full compatibility with Agent Framework thread serialization
- **Production Ready**: Connection pooling, error handling, and performance optimized

#### Basic Usage Examples

See the complete [Redis chat message store examples](../../samples/getting_started/threads/redis_chat_message_store_thread.py) including:
- User session management
- Conversation persistence across restarts  
- Thread serialization and deserialization
- Automatic message trimming
- Error handling patterns

### Installing and running Redis

You have 3 options to set-up Redis:

#### Option A: Local Redis with Docker
```bash
docker run --name redis -p 6379:6379 -d redis:8.0.3
```

#### Option B: Redis Cloud
Get a free db at https://redis.io/cloud/

#### Option C: Azure Managed Redis
Here's a quickstart guide to create **Azure Managed Redis** for as low as $12 monthly: https://learn.microsoft.com/en-us/azure/redis/quickstart-create-managed-redis
