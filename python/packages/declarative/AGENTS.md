# Declarative Package (agent-framework-declarative)

YAML/JSON-based declarative agent and workflow definitions.

## Main Classes

- **`AgentFactory`** - Creates agents from declarative definitions
- **`WorkflowFactory`** - Creates workflows from declarative definitions
- **`WorkflowState`** - State management for declarative workflows
- **`ProviderTypeMapping`** - Maps provider types to implementations
- **`DeclarativeLoaderError`** / **`ProviderLookupError`** - Error types

## External Input Handling

- **`ExternalInputRequest`** / **`ExternalInputResponse`** - Human-in-the-loop support
- **`AgentExternalInputRequest`** / **`AgentExternalInputResponse`** - Agent-level input requests

## Usage

```python
from agent_framework.declarative import AgentFactory, WorkflowFactory

agent = AgentFactory.create_from_file("agent.yaml")
workflow = WorkflowFactory.create_from_file("workflow.yaml")
```

## Import Path

```python
from agent_framework.declarative import AgentFactory, WorkflowFactory
# or directly:
from agent_framework_declarative import AgentFactory
```
