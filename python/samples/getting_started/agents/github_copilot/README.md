# GitHub Copilot Agent Examples

This directory contains examples demonstrating how to use the `GithubCopilotAgent` from the Microsoft Agent Framework.

## Examples

| File | Description |
|------|-------------|
| [`github_copilot_basic.py`](github_copilot_basic.py) | The simplest way to create an agent using `GithubCopilotAgent`. Demonstrates both streaming and non-streaming responses with function tools. |
| [`github_copilot_with_shell.py`](github_copilot_with_shell.py) | Shows how to enable shell command execution permissions. Demonstrates running system commands like listing files and getting system information. |
| [`github_copilot_with_file_operations.py`](github_copilot_with_file_operations.py) | Shows how to enable file read and write permissions. Demonstrates reading file contents and creating new files. |
| [`github_copilot_with_multiple_permissions.py`](github_copilot_with_multiple_permissions.py) | Shows how to combine multiple permission types for complex tasks that require shell, read, and write access. |

## Prerequisites

1. **GitHub Copilot CLI**: Install and authenticate the Copilot CLI
2. **GitHub Copilot Subscription**: An active GitHub Copilot subscription
3. **Install the package**:
   ```bash
   pip install agent-framework-github-copilot --pre
   ```

## Environment Variables

The following environment variables can be configured:

| Variable | Description | Default |
|----------|-------------|---------|
| `GITHUB_COPILOT_CLI_PATH` | Path to the Copilot CLI executable | `copilot` |
| `GITHUB_COPILOT_MODEL` | Model to use (e.g., "gpt-5", "claude-sonnet-4") | Server default |
| `GITHUB_COPILOT_TIMEOUT` | Request timeout in seconds | `60` |
| `GITHUB_COPILOT_LOG_LEVEL` | CLI log level | `info` |

## Permission Kinds

When using `allowed_permissions`, the following permission kinds are available:

| Permission | Description |
|------------|-------------|
| `shell` | Execute shell commands on the system |
| `read` | Read files from the filesystem |
| `write` | Write or create files on the filesystem |
| `mcp` | Use MCP (Model Context Protocol) servers |
| `url` | Fetch content from URLs |

**Security Note**: Only enable permissions that are necessary for your use case. Each permission grants the agent additional capabilities that could affect your system.

## Usage Patterns

### Basic Usage (No Permissions)

```python
from agent_framework.github_copilot import GithubCopilotAgent

async with GithubCopilotAgent() as agent:
    response = await agent.run("Hello!")
```

### With Custom Tools

```python
from typing import Annotated

from agent_framework.github_copilot import GithubCopilotAgent
from pydantic import Field

def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    return f"The weather in {location} is sunny."

async with GithubCopilotAgent(tools=[get_weather]) as agent:
    response = await agent.run("What's the weather in Seattle?")
```

### With Permissions

```python
from agent_framework.github_copilot import GithubCopilotAgent

# Read-only access
async with GithubCopilotAgent(
    default_options={"allowed_permissions": ["read"]}
) as agent:
    response = await agent.run("Read the README.md file")

# Full development access
async with GithubCopilotAgent(
    default_options={"allowed_permissions": ["shell", "read", "write"]}
) as agent:
    response = await agent.run("Create a new Python file with a hello world function")
```

## Running the Examples

Each example can be run independently:

```bash
python github_copilot_basic.py
python github_copilot_with_shell.py
python github_copilot_with_file_operations.py
python github_copilot_with_multiple_permissions.py
```
