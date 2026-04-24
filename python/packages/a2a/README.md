# Get Started with Microsoft Agent Framework A2A

Please install this package via pip:

```bash
pip install agent-framework-a2a --pre
```

## A2A Agent Integration

The A2A agent integration enables communication with remote A2A-compliant agents using the standardized A2A protocol. This allows your Agent Framework applications to connect to agents running on different platforms, languages, or services.

### A2AAgent (Client)

The `A2AAgent` class is a client that wraps an A2A Client to connect the Agent Framework with external A2A-compliant agents.

```python
from agent_framework.a2a import A2AAgent

# Connect to a remote A2A agent
a2a_agent = A2AAgent(url="http://remote-agent/a2a")
response = await a2a_agent.run("Hello!")
```

### A2AExecutor (Hosting)

The `A2AExecutor` class bridges local AI agents built with the `agent_framework` library to the A2A protocol, allowing them to be hosted and accessed by other A2A-compliant clients.

```python
from agent_framework.a2a import A2AExecutor
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

# Create an A2A executor for your agent
executor = A2AExecutor(agent=my_agent)

# Set up the request handler and server application
request_handler = DefaultRequestHandler(
    agent_executor=executor,
    task_store=InMemoryTaskStore(),
)

app = A2AStarletteApplication(
    agent_card=my_agent_card,
    http_handler=request_handler,
).build()
```

### Basic Usage Example

See the [A2A agent examples](../../samples/04-hosting/a2a/) which demonstrate:

- Connecting to remote A2A agents
- Hosting local agents via A2A protocol
- Sending messages and receiving responses
- Handling different content types (text, files, data)
- Streaming responses and real-time interaction
