# Claude Package (agent-framework-claude)

Integration with Anthropic Claude as a managed agent (Claude Agent SDK).

## Main Classes

- **`ClaudeAgent`** - Agent using Claude's native agent capabilities
- **`ClaudeAgentOptions`** - Options for Claude agent configuration
- **`ClaudeAgentSettings`** - Pydantic settings for configuration

## Usage

```python
from agent_framework_claude import ClaudeAgent

agent = ClaudeAgent(...)
response = await agent.run("Hello")
```

## Import Path

```python
from agent_framework_claude import ClaudeAgent
```

## Note

This package is for Claude's managed agent functionality. For basic Claude chat, use `agent-framework-anthropic` instead.
