# Mem0 Package (agent-framework-mem0)

Integration with Mem0 for agent memory management.

## Main Classes

- **`Mem0ContextProvider`** - Context provider that integrates Mem0 memory into agents

## Usage

```python
from agent_framework.mem0 import Mem0ContextProvider

provider = Mem0ContextProvider(
    api_key="your-key",
    # Storage scope: memories are written with this user_id.
    user_id="user-id",
    # Retrieval scope: must be set explicitly, it never inherits the storage scope.
    search_user_id="user-id",
)
```

## Memory Scoping

- `application_id` / `agent_id` / `user_id` are the **storage scope** stamped on written memories.
- `search_application_id` / `search_agent_id` / `search_user_id` are the **retrieval scope**.
- Retrieval scope never defaults to the storage scope. With no `search_*` value set, `before_run`
  retrieves nothing and logs a warning. This prevents memories written under a shared `agent_id`
  from being retrieved for every user of that agent.

## Import Path

```python
from agent_framework.mem0 import Mem0ContextProvider
# or directly:
from agent_framework_mem0 import Mem0ContextProvider
```

## Notes

Mem0 telemetry is disabled by default. Set `MEM0_TELEMETRY=true` to enable.
