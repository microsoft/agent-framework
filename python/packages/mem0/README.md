# Get Started with Microsoft Agent Framework Mem0

Please install this package via pip:

```bash
pip install agent-framework-mem0 --pre
```

## Memory Context Provider

The Mem0 context provider enables persistent memory capabilities for your agents, allowing them to remember user preferences and conversation context across different sessions and threads.

### Basic Usage Example

See the [Mem0 basic example](../../samples/02-agents/context_providers/mem0/mem0_basic.py) which demonstrates:

- Setting up an agent with Mem0 context provider
- Teaching the agent user preferences
- Retrieving information using remembered context across new threads
- Persistent memory

### Memory Scoping

The provider separates the scope used to **store** memories from the scope used to **retrieve** them:

- `application_id` / `agent_id` / `user_id` stamp every memory that is written.
- `search_application_id` / `search_agent_id` / `search_user_id` select which memories are searched.

Note: `application_id` and `search_application_id` are only supported by the Platform client (`AsyncMemoryClient`), not the OSS `AsyncMemory` client.
Retrieval scope values never inherit from the storage scope. If none of the `search_*` values are
set, no memories are retrieved and a warning is logged. Set `search_user_id` for per-user memory,
and only set `search_agent_id` when memories under that agent are safe to share across all of its
users.

```python
provider = Mem0ContextProvider(
    api_key="your-key",
    user_id="user-id",
    search_user_id="user-id",
)
```

## Telemetry

Mem0's telemetry is **disabled by default** when using this package. If you want to enable telemetry, set the environment variable before importing:

```python
import os
os.environ["MEM0_TELEMETRY"] = "true"

from agent_framework.mem0 import Mem0ContextProvider
```
