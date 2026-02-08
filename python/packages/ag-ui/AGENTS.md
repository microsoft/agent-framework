# AG-UI Package (agent-framework-ag-ui)

AG-UI protocol integration for building agent UIs with the AG-UI standard.

## Main Classes

- **`AgentFrameworkAgent`** - Wraps agents for AG-UI compatibility
- **`AGUIChatClient`** - Chat client that speaks AG-UI protocol
- **`AGUIHttpService`** - HTTP service for AG-UI endpoints
- **`AGUIEventConverter`** - Converts between Agent Framework and AG-UI events
- **`add_agent_framework_fastapi_endpoint()`** - Add AG-UI endpoint to FastAPI app

## Types

- **`AGUIRequest`** / **`AGUIChatOptions`** - Request types
- **`AgentState`** / **`RunMetadata`** - State management types
- **`PredictStateConfig`** - Configuration for state prediction

## Usage

```python
from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint
from fastapi import FastAPI

app = FastAPI()
add_agent_framework_fastapi_endpoint(app, agent)
```

## Import Path

```python
from agent_framework.ag_ui import AGUIChatClient, add_agent_framework_fastapi_endpoint
# or directly:
from agent_framework_ag_ui import AGUIChatClient
```
