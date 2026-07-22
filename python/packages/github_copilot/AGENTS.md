# GitHub Copilot Package (agent-framework-github-copilot)

Integration with GitHub Copilot extensions.

## Main Classes

- **`GitHubCopilotAgent`** - Agent for GitHub Copilot extensions
- **`GitHubCopilotOptions`** - Options for Copilot agent configuration
- **`GitHubCopilotSettings`** - Pydantic settings for configuration

## Usage

```python
from agent_framework.github import GitHubCopilotAgent

agent = GitHubCopilotAgent(...)
response = await agent.run("Hello")
```

## Import Path

```python
from agent_framework.github import GitHubCopilotAgent
# or directly:
from agent_framework_github_copilot import GitHubCopilotAgent
```
