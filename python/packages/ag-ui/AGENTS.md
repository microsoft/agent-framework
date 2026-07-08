# AG-UI Package (agent-framework-ag-ui)

AG-UI protocol integration for building agent UIs with the AG-UI standard.

## Main Classes

- **`AgentFrameworkAgent`** - Wraps agents for AG-UI compatibility
- **`AgentFrameworkWorkflow`** - Wraps native `Workflow` objects, or accepts `workflow_factory(thread_id)` for thread-scoped workflow instances without subclassing
- **`AGUIChatClient`** - Chat client that speaks AG-UI protocol
- **`AGUIHttpService`** - HTTP service for AG-UI endpoints
- **`AGUIEventConverter`** - Converts between Agent Framework and AG-UI events
- **`add_agent_framework_fastapi_endpoint()`** - Add AG-UI endpoint to FastAPI app (`SupportsAgentRun` or `Workflow`)
- **`InMemoryAGUIThreadSnapshotStore`** - Memory-only latest AG-UI Thread Snapshot store for local development, demos, and tests

## Types

- **`AGUIRequest`** / **`AGUIChatOptions`** - Request types
- **`AGUIThreadSnapshot`** / **`AGUIThreadSnapshotStore`** - Replayable thread snapshot model and scoped async store protocol
- **`availableInterrupts` / `resume`** - Optional canonical AG-UI `Interrupt` and `ResumeEntry` protocol data
- **`AgentState`** / **`RunMetadata`** - State management types
- **`PredictStateConfig`** - Configuration for state prediction

## Protocol Notes

- Outbound custom events are emitted as AG-UI `CUSTOM`.
- Usage metadata from `Content(type="usage")` is surfaced as `CUSTOM` events with `name="usage"`.
- Inbound custom event aliases are accepted: `CUSTOM`, `CUSTOM_EVENT`, and `custom_event`.
- Multimodal user inputs support both legacy (`text`, `binary`) and draft-style (`image`, `audio`, `video`, `document`) shapes.
- Interrupted runs complete with `RUN_FINISHED.outcome.type == "interrupt"` and canonical `outcome.interrupts`; do not document or add new flows that depend on the legacy top-level `RUN_FINISHED.interrupt` field.
- `Interrupt` and `ResumeEntry` come from the `ag-ui-protocol` package (`ag_ui.core`), not from an Agent Framework-specific interrupt model.

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
