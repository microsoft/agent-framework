# Copilot Studio Package (agent-framework-copilotstudio)

Integration with Microsoft Copilot Studio agents.

## Main Classes

- **`CopilotStudioAgent`** - Agent that connects to a Copilot Studio bot
- **`acquire_token`** - Helper function for authentication

## Usage

```python
from agent_framework.microsoft import CopilotStudioAgent

agent = CopilotStudioAgent(
    agent_identifier="your-agent-schema-name",
    environment_id="your-env-id",
)
response = await agent.run("Hello")
```

## Import Path

```python
from agent_framework.microsoft import CopilotStudioAgent
# or directly:
from agent_framework_copilotstudio import CopilotStudioAgent
```
