# DevUI Package (agent-framework-devui)

Interactive developer UI for testing and debugging agents and workflows.

## Main Classes

- **`serve()`** - Launch the DevUI server
- **`DevServer`** - The FastAPI-based development server
- **`register_cleanup()`** - Register cleanup hooks for entities
- **`CheckpointConversationManager`** - Manages conversation checkpoints

## Models

- **`AgentFrameworkRequest`** - Request model for agent invocations
- **`OpenAIResponse`** / **`OpenAIError`** - OpenAI-compatible response models
- **`DiscoveryResponse`** / **`EntityInfo`** - Entity discovery models

## Usage

```python
from agent_framework.devui import serve

agent = Agent(...)
serve(entities=[agent], port=8080, auto_open=True)
```

## CLI

```bash
# Run with auto-discovery
devui ./agents

# Run with specific entities
devui --entities my_agent.py
```

## Security Posture

DevUI is a development-only sample app, not a production hosting surface. Authentication is enabled by default.
Unauthenticated mode is allowed only on `localhost` / `127.0.0.1`; `0.0.0.0`, LAN IPs, and hostnames require
`DEVUI_AUTH_TOKEN` or `--auth-token`.

## Import Path

```python
from agent_framework.devui import serve, register_cleanup
# or directly:
from agent_framework_devui import serve
```
