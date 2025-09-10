# Get Started with Microsoft Agent Framework Mem0

Please install this package as the extra for `agent-framework`:

```bash
pip install agent-framework[mem0]
```

## Memory Context Provider

The Mem0 context provider enables persistent memory capabilities for your agents, allowing them to remember user preferences and conversation context across different sessions and threads.

### Basic Usage Example

See the [Mem0 basic example](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/context_providers/mem0/mem0_basic.py) which demonstrates:

- Setting up an agent with Mem0 context provider
- Teaching the agent user preferences
- Retrieving information using remembered context across new threads
- Persistent memory

