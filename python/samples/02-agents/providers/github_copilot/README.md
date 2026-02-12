# GitHub Copilot Agent Examples

This directory contains examples demonstrating how to use the `GitHubCopilotAgent` from the Microsoft Agent Framework.

> **Security Note**: These examples demonstrate various permission types (shell, read, write, url). Only enable permissions that are necessary for your use case. Each permission grants the agent additional capabilities that could affect your system.

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

## Examples

| File | Description |
|------|-------------|
| [`github_copilot_basic.py`](github_copilot_basic.py) | The simplest way to create an agent using `GitHubCopilotAgent`. Demonstrates both streaming and non-streaming responses with function tools. |
| [`github_copilot_with_session.py`](github_copilot_with_session.py) | Shows session management with automatic creation, persistence via thread objects, and resuming sessions by ID. |
| [`github_copilot_with_shell.py`](github_copilot_with_shell.py) | Shows how to enable shell command execution permissions. Demonstrates running system commands like listing files and getting system information. |
| [`github_copilot_with_file_operations.py`](github_copilot_with_file_operations.py) | Shows how to enable file read and write permissions. Demonstrates reading file contents and creating new files. |
| [`github_copilot_with_url.py`](github_copilot_with_url.py) | Shows how to enable URL fetching permissions. Demonstrates fetching and processing web content. |
| [`github_copilot_with_mcp.py`](github_copilot_with_mcp.py) | Shows how to configure MCP (Model Context Protocol) servers, including local (stdio) and remote (HTTP) servers. |
| [`github_copilot_with_multiple_permissions.py`](github_copilot_with_multiple_permissions.py) | Shows how to combine multiple permission types for complex tasks that require shell, read, and write access. |
