# Harness Agent Samples

This folder demonstrates `create_harness_agent` — a factory function that builds a
pre-configured, batteries-included agent by assembling the full agent pipeline
from a chat client.

## What is `create_harness_agent`?

`create_harness_agent` bundles the following features into a single `Agent` instance:

| Feature | Description |
|---------|-------------|
| Function invocation | Automatic tool calling loop |
| Per-service-call persistence | History persisted after every model call |
| Compaction | Context-window management (sliding window + tool result compaction) |
| TodoProvider | Todo list management for planning and tracking |
| AgentModeProvider | Plan/execute mode tracking |
| MemoryContextProvider | File-based durable memory (when `memory_store` provided) |
| SkillsProvider | File-based skill discovery and progressive loading |
| Shell tool | Shell command execution + environment probing (when `shell_executor` provided) |
| OpenTelemetry | Built-in observability |

Each feature can be disabled or customized via keyword arguments.

## Samples

| File | Description |
|------|-------------|
| `harness_research.py` | Interactive research assistant with web search and planning workflow |

## Running

```bash
# Set your Foundry environment variables
export FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project-name"
export FOUNDRY_MODEL="your-model-deployment-name"

# Authenticate with Azure (required for AzureCliCredential)
az login

# Run the research sample
python samples/02-agents/harness/harness_research.py
```

## Key Concepts

### Minimal Setup

`create_harness_agent` requires only a chat client:

```python
from agent_framework import create_harness_agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

agent = create_harness_agent(
    client=FoundryChatClient(credential=AzureCliCredential()),
)
```

### With Compaction

Provide token budget parameters to enable automatic context-window compaction:

```python
agent = create_harness_agent(
    client=FoundryChatClient(credential=AzureCliCredential()),
    max_context_window_tokens=128_000,
    max_output_tokens=16_384,
)
```

### Further Customization

Disable or customize any feature:

```python
agent = create_harness_agent(
    client=client,
    max_context_window_tokens=128_000,
    max_output_tokens=16_384,
    name="my-agent",
    agent_instructions="Custom instructions here.",
    disable_todo=True,          # Skip todo management
    disable_mode=True,          # Skip plan/execute modes
    disable_compaction=True,    # Skip compaction
)
```

### Plan/Execute Workflow

The `AgentModeProvider` enables a two-phase workflow:
1. **Plan mode** — Interactive: the agent asks questions, creates todos, gets approval
2. **Execute mode** — Autonomous: the agent works through todos independently

### Shell Tool

Pass a shell executor (e.g. `LocalShellTool` from `agent-framework-tools`) to enable shell
command execution plus automatic environment probing via a `ShellEnvironmentProvider`. The
tool is only wired when the chat client supports shell tools; otherwise a warning is logged
and the shell tool/provider are skipped. The caller owns the executor's lifecycle.

```python
from agent_framework_tools.shell import LocalShellTool, ShellEnvironmentProviderOptions

async with LocalShellTool(acknowledge_unsafe=True) as shell:
    agent = create_harness_agent(
        client=client,
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        shell_executor=shell,
        # Optional: customize environment probing.
        shell_environment_provider_options=ShellEnvironmentProviderOptions(probe_tools=("git", "python")),
    )
```

