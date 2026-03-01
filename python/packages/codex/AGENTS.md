# Codex Package (agent-framework-codex)

Integration with OpenAI Codex as a managed agent (Codex SDK).

## Main Classes

- **`CodexAgent`** - Agent using Codex's native agent capabilities
- **`CodexAgentOptions`** - Options for Codex agent configuration
- **`CodexAgentSettings`** - TypedDict-based settings populated via the framework's `load_settings()` helper

## Usage

```python
from agent_framework_codex import CodexAgent

agent = CodexAgent(...)
response = await agent.run("Hello")
```

## Import Path

```python
from agent_framework_codex import CodexAgent
```

## Note

This package is for Codex's managed agent functionality. For basic OpenAI chat, use `agent-framework-openai` instead.
