# A2A Package (agent-framework-a2a)

Agent-to-Agent (A2A) protocol support for inter-agent communication.

## Main Classes

- **`A2AAgent`** - Client to connect to remote A2A-compliant agents.
- **`A2AExecutor`** - Bridge to expose Agent Framework agents via the A2A protocol.

## Usage

### A2AAgent (Client)

```python
from agent_framework.a2a import A2AAgent

# Connect to a remote A2A agent
a2a_agent = A2AAgent(url="http://remote-agent/a2a")
response = await a2a_agent.run("Hello!")
```

### A2AExecutor (Server/Bridge)

```python
from agent_framework.a2a import A2AExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from starlette.applications import Starlette

# Create an A2A executor for your agent
executor = A2AExecutor(agent=my_agent)

# Set up the request handler (agent_card is required)
request_handler = DefaultRequestHandler(
    agent_executor=executor,
    task_store=InMemoryTaskStore(),
    agent_card=my_agent_card,
)

# Build a Starlette app with A2A routes
app = Starlette(
    routes=[
        *create_agent_card_routes(my_agent_card),
        *create_jsonrpc_routes(request_handler),
    ]
)
```

## Import Path

```python
from agent_framework.a2a import A2AAgent, A2AExecutor
# or directly:
from agent_framework_a2a import A2AAgent, A2AExecutor
```
