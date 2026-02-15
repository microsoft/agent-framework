# Get Started with Microsoft Agent Framework Azure AI

Please install this package via pip:

```bash
pip install agent-framework-azure-ai --pre
```

## Foundry Memory Context Provider

The Foundry Memory context provider enables semantic memory capabilities for your agents using Azure AI Foundry Memory Store. It automatically:
- Retrieves static (user profile) memories on first run
- Searches for contextual memories based on conversation
- Updates the memory store with new conversation messages

### Basic Usage Example

See the [Foundry Memory example](../../samples/02-agents/context_providers/azure_ai_foundry_memory.py) which demonstrates:

- Creating a memory store using Azure AI Projects client
- Setting up an agent with FoundryMemoryProvider
- Teaching the agent user preferences
- Retrieving information using remembered context across conversations
- Automatic memory updates with configurable delays

and see the [README](https://github.com/microsoft/agent-framework/tree/main/python/README.md) for more information.
