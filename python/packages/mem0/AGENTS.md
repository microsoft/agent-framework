# Mem0 Package (agent-framework-mem0)

Integration with Mem0 for agent memory management.

## Main Classes

- **`Mem0Provider`** - Context provider that integrates Mem0 memory into agents

## Usage

```python
from agent_framework.mem0 import Mem0Provider

provider = Mem0Provider(api_key="your-key")
agent = Agent(..., context_provider=provider)
```

## Import Path

```python
from agent_framework.mem0 import Mem0Provider
# or directly:
from agent_framework_mem0 import Mem0Provider
```

## Notes

Mem0 telemetry is disabled by default. Set `MEM0_TELEMETRY=true` to enable.
