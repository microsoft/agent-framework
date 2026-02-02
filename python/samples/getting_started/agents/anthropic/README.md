# Anthropic Examples

This folder contains examples demonstrating how to use Anthropic's Claude models with the Agent Framework.

## Anthropic Client Examples

| File | Description |
|------|-------------|
| [`anthropic_basic.py`](anthropic_basic.py) | Demonstrates how to setup a simple agent using the AnthropicClient, with both streaming and non-streaming responses. |
| [`anthropic_advanced.py`](anthropic_advanced.py) | Shows advanced usage of the AnthropicClient, including hosted tools and `thinking`. |
| [`anthropic_skills.py`](anthropic_skills.py) | Illustrates how to use Anthropic-managed Skills with an agent, including the Code Interpreter tool and file generation and saving. |
| [`anthropic_foundry.py`](anthropic_foundry.py) | Example of using Foundry's Anthropic integration with the Agent Framework. |

## Claude Agent Examples

| File | Description |
|------|-------------|
| [`anthropic_claude_basic.py`](anthropic_claude_basic.py) | Basic usage of ClaudeAgent with streaming, non-streaming, and custom tools. |
| [`anthropic_claude_with_tools.py`](anthropic_claude_with_tools.py) | Using built-in tools (Read, Glob, Grep, etc.). |
| [`anthropic_claude_with_shell.py`](anthropic_claude_with_shell.py) | Shell command execution with interactive permission handling. |
| [`anthropic_claude_with_multiple_permissions.py`](anthropic_claude_with_multiple_permissions.py) | Combining multiple tools (Bash, Read, Write) with permission prompts. |
| [`anthropic_claude_with_url.py`](anthropic_claude_with_url.py) | Fetching and processing web content with WebFetch. |
| [`anthropic_claude_with_mcp.py`](anthropic_claude_with_mcp.py) | Local (stdio) and remote (HTTP) MCP server configuration. |
| [`anthropic_claude_with_session.py`](anthropic_claude_with_session.py) | Session management, persistence, and resumption. |

## Environment Variables

### Anthropic Client

- `ANTHROPIC_API_KEY`: Your Anthropic API key (get one from [Anthropic Console](https://console.anthropic.com/))
- `ANTHROPIC_CHAT_MODEL_ID`: The Claude model to use (e.g., `claude-haiku-4-5`, `claude-sonnet-4-5-20250929`)

### Foundry

- `ANTHROPIC_FOUNDRY_API_KEY`: Your Foundry Anthropic API key
- `ANTHROPIC_FOUNDRY_ENDPOINT`: The endpoint URL for your Foundry Anthropic resource
- `ANTHROPIC_CHAT_MODEL_ID`: The Claude model to use in Foundry (e.g., `claude-haiku-4-5`)

### Claude Agent

- `CLAUDE_AGENT_CLI_PATH`: Path to the Claude Code CLI executable
- `CLAUDE_AGENT_MODEL`: Model to use (sonnet, opus, haiku)
- `CLAUDE_AGENT_CWD`: Working directory for Claude CLI
- `CLAUDE_AGENT_PERMISSION_MODE`: Permission mode (default, acceptEdits, plan, bypassPermissions)
- `CLAUDE_AGENT_MAX_TURNS`: Maximum number of conversation turns
- `CLAUDE_AGENT_MAX_BUDGET_USD`: Maximum budget in USD
