# Get Started with Microsoft Agent Framework GitHub Copilot

Please install this package via pip:

```bash
pip install agent-framework-github-copilot --pre
```

## GitHub Copilot Agent

The GitHub Copilot agent enables integration with GitHub Copilot, allowing you to interact with Copilot's agentic capabilities through the Agent Framework.

### Prerequisites

Before using the GitHub Copilot agent, you need:

1. **GitHub Copilot CLI**: The Copilot CLI must be installed and authenticated
2. **GitHub Copilot Subscription**: An active GitHub Copilot subscription

### Environment Variables

The following environment variables can be used for configuration:

- `GITHUB_COPILOT_CLI_PATH` - Path to the Copilot CLI executable (default: "copilot")
- `GITHUB_COPILOT_MODEL` - Model to use (e.g., "gpt-5", "claude-sonnet-4")
- `GITHUB_COPILOT_TIMEOUT` - Request timeout in seconds (default: 60)
- `GITHUB_COPILOT_LOG_LEVEL` - CLI log level (default: "info")

### Basic Usage Example

```python
import asyncio
from agent_framework.github_copilot import GithubCopilotAgent

async def main():
    # Create agent using environment variables or defaults
    async with GithubCopilotAgent() as agent:
        # Run a simple query
        result = await agent.run("What is the capital of France?")
        print(result)

asyncio.run(main())
```

### Streaming Example

```python
import asyncio
from agent_framework.github_copilot import GithubCopilotAgent

async def main():
    async with GithubCopilotAgent() as agent:
        print("Agent: ", end="", flush=True)
        async for chunk in agent.run_stream("Explain Python decorators"):
            if chunk.text:
                print(chunk.text, end="", flush=True)
        print()

asyncio.run(main())
```

### Using Typed Options

```python
import asyncio
from agent_framework.github_copilot import GithubCopilotAgent, GithubCopilotOptions

async def main():
    # Create agent with typed options for IDE autocomplete
    agent: GithubCopilotAgent[GithubCopilotOptions] = GithubCopilotAgent(
        default_options={"model": "claude-sonnet-4", "timeout": 120}
    )

    async with agent:
        result = await agent.run("Hello!")
        print(result)

asyncio.run(main())
```

### Using Tools

Tools are defined using standard Agent Framework patterns (functions, callables, or ToolProtocol instances):

```python
import asyncio
from agent_framework.github_copilot import GithubCopilotAgent

def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"The weather in {city} is sunny and 72F"

async def main():
    async with GithubCopilotAgent(tools=[get_weather]) as agent:
        result = await agent.run("What's the weather in Seattle?")
        print(result)

asyncio.run(main())
```

### Using Permissions

Enable Copilot to perform system operations by specifying allowed permissions:

```python
import asyncio
from agent_framework.github_copilot import GithubCopilotAgent

async def main():
    # Enable read and shell permissions
    async with GithubCopilotAgent(
        default_options={"allowed_permissions": ["read", "shell"]}
    ) as agent:
        result = await agent.run("List all Python files and show their line counts")
        print(result)

asyncio.run(main())
```

Available permission kinds:
- `shell` - Execute shell commands
- `read` - Read files from the filesystem
- `write` - Write files to the filesystem
- `mcp` - Use MCP servers
- `url` - Fetch content from URLs

### Examples

For more comprehensive examples, see the [GitHub Copilot examples](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/agents/github_copilot/) which demonstrate:

- Basic non-streaming and streaming execution
- Custom tool integration using Agent Framework patterns
- Shell command execution with permissions
- File read and write operations
- Combining multiple permissions for complex tasks
