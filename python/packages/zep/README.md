# Get Started with Microsoft Agent Framework Zep

Please install this package via pip:

```bash
pip install agent-framework-zep --pre
```

## Zep Context Provider

The Zep context provider enables persistent, low-latency long-term memory capabilities for your agents using Zep's context engineering platform. Using temporal knowledge graphs, Zep builds a comprehensive understanding of user context across all conversations, allowing agents to:

- Remember user preferences and facts across sessions
- Retrieve relevant context automatically before each LLM call
- Build a temporal knowledge graph that understands relationships and changes over time
- Support multiple concurrent conversation threads while maintaining cross-thread memory

### How It Works

The Zep provider integrates with the Agent Framework's context provider system:

1. **Thread Creation**: When the framework creates a thread (via `service_thread_id`), the provider automatically creates a corresponding Zep thread associated with the configured `user_id`
2. **Before LLM Invocation**: Retrieves relevant context from Zep's knowledge graph using `get_user_context()`
3. **After LLM Invocation**: Persists conversation messages to Zep using `add_messages()`

Each thread maintains its own conversation history while contributing to a shared user knowledge graph, enabling cross-thread memory recall.

### Usage

Every ZepProvider must be associated with a `user_id`. Zep uses this to:

- Create and manage threads (threads belong to users in Zep)
- Build the user's knowledge graph across all their threads
- Retrieve user-specific context relevant to the current thread state

**Static Thread ID** - Shared memory across all conversations:

```python
from agent_framework_zep import ZepProvider
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential

async def main():
    async with AzureCliCredential() as credential:
        async with AzureAIAgentClient(async_credential=credential).create_agent(
            name="MyAgent",
            instructions="You are a helpful assistant.",
            context_providers=ZepProvider(
                user_id="user123",
                thread_id="global-session"  # Pre-created thread using the Zep SDK
            ),
        ) as agent:
            result = await agent.run("Remember that I prefer detailed reports")
            print(result)
```

**Dynamic Thread ID** - Isolated memory per conversation:

```python
from agent_framework_zep import ZepProvider
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential

async def main():
    async with AzureCliCredential() as credential:
        async with AzureAIAgentClient(async_credential=credential).create_agent(
            name="MyAgent",
            instructions="You are a helpful assistant.",
            context_providers=ZepProvider(
                user_id="user123",
                scope_to_per_operation_thread_id=True
            ),
        ) as agent:
            thread = agent.get_new_thread()
            result = await agent.run("Hello", thread=thread)
            print(result)
```

### Configuration Options

#### Authentication

Provide API key explicitly:

```python
ZepProvider(user_id="user123", api_key="your-api-key")
```

Or set environment variable:

```bash
export ZEP_API_KEY="your-api-key"
```

#### Custom Zep Client

For advanced use cases, provide a pre-configured AsyncZep client:

```python
from zep_cloud.client import AsyncZep

custom_client = AsyncZep(api_key="your-api-key")
provider = ZepProvider(user_id="user123", zep_client=custom_client)
```

### Examples

See the [Zep basic example](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/context_providers/zep/zep_basic.py) which demonstrates:

- Setting up an agent with Zep context provider
- Teaching the agent user preferences
- Retrieving information using remembered context across new threads
- Cross-thread knowledge graph memory

### Key Features

- **Automatic Context Retrieval**: Zep automatically surfaces relevant facts and memories before each LLM call
- **Temporal Understanding**: Zep understands when facts change over time (e.g., "User preferred tea" → "User now prefers coffee")
- **Cross-Thread Memory**: Knowledge learned in one thread is available in all other threads
- **Basic Context Mode**: Returns structured facts and entities for optimal context injection

### Learn More

- [Zep Documentation](https://help.getzep.com/)
- [Agent Framework Documentation](https://aka.ms/agent-framework)
