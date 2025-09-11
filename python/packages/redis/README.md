# Get Started with Microsoft Agent Framework Redis

Please install this package as the extra for `agent-framework`:

```bash
pip install agent-framework[redis]
```

## Memory Context Provider

The Redis context provider enables persistent memory capabilities for your agents, allowing them to remember user preferences and conversation context across different sessions and threads.

### Basic Usage Example

See the [Redis memory example](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/context_providers/redis/redis_memory.py) which demonstrates:

- Setting up an agent with Redis context provider, using the OpenAI API
- Teaching the agent user preferences
- Retrieving information using remembered context across new threads
- Persistent memory


### Installing and running Redis

You have 3 options to set-up Redis:

#### Option A: Local Redis with Docker**
docker run --name redis -p 6379:6379 -d redis:8.0.3

#### Option B: Redis Cloud
Get a free db at https://redis.io/cloud/

#### Option C: Azure Managed Redis
Here's a quickstart guide to create Azure Managed Redis for as low as $12 monthly: https://learn.microsoft.com/en-us/azure/redis/quickstart-create-managed-redis