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

## Session Option Defaults

`_build_session_kwargs` forwards options to the SDK verbatim except for a few keys that get
an explicit default: `on_permission_request` (deny-all) and `enable_file_hooks` (`False`, so
a session behaves the same way in every working directory). Callers opt in through
`default_options` or per-run options. Keep such defaults to options the working directory
controls: options that only shape prompt context (for example `enable_host_git_operations`)
are deliberately left alone.
