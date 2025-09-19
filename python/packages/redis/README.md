# Get Started with Microsoft Agent Framework Redis

Please install this package as the extra for `agent-framework`:

```bash
pip install agent-framework[redis]
```

## Memory Context Provider

The `RedisProvider` enables persistent context & memory capabilities for your agents, allowing them to remember user preferences and conversation context across sessions and threads.

### Basic Usage Examples

Review the set of [getting started examples](../../samples/getting_started/context_providers/redis/README.md) for using the Redis context provider.


### Installing and running Redis

You have 3 options to set-up Redis:

#### Option A: Local Redis with Docker**
```bash
docker run --name redis -p 6379:6379 -d redis:8.0.3
```

#### Option B: Redis Cloud
Get a free db at https://redis.io/cloud/

#### Option C: Azure Managed Redis
Here's a quickstart guide to create **Azure Managed Redis** for as low as $12 monthly: https://learn.microsoft.com/en-us/azure/redis/quickstart-create-managed-redis
