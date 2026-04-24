# agent-framework-tools

Alpha built-in tools for the Microsoft Agent Framework. A home for first-party
Python tools that plug into any chat client's shell / function surface. The
first tool is `LocalShellTool`.

## Installation

```bash
pip install agent-framework-tools --pre
```

## `LocalShellTool` quick start

```python
import asyncio
from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from agent_framework_tools.shell import LocalShellTool


async def main() -> None:
    client = OpenAIChatClient(model="gpt-5.4-nano")
    async with LocalShellTool() as shell:
        agent = Agent(
            client=client,
            instructions="You are a helpful assistant that can run shell commands.",
            tools=[client.get_shell_tool(func=shell.as_function())],
        )
        result = await agent.run("Print the current working directory.")
        print(result.text)


asyncio.run(main())
```

### Modes

- **Persistent** (default): a single long-lived shell session. `cd`, `export`,
  and shell functions persist across tool invocations. Matches the semantics
  of Anthropic's `bash_20250124` tool and Claude Code's Bash tool.
- **Stateless** (`mode="stateless"`): each command runs in a fresh subprocess,
  matching AutoGen's `LocalCommandLineCodeExecutor` and OpenAI Agents SDK's
  `local_shell` protocol.

### Safety

Out of the box, `LocalShellTool`:

- **Requires approval** for every command (uses the framework's existing
  `user_input_requests` approval flow).
- **Denies destructive patterns** by default (`rm -rf /`, `mkfs`, `dd if=`,
  `shutdown`, `curl … | sh`, etc.).
- **Truncates output** to 64 KiB.
- **Enforces a 30 s timeout** per command and kills the whole process tree.
- **Confines `cd`** to the configured `workdir` (defaults to the current
  directory).

Override with `ShellPolicy`:

```python
from agent_framework_tools.shell import LocalShellTool, ShellPolicy

shell = LocalShellTool(
    policy=ShellPolicy(allowlist=[r"^ls\b", r"^cat\b", r"^git status$"]),
    approval_mode="never_require",
)
```

### Cross-OS

- **Windows**: `pwsh -NoProfile -Command -` (falls back to `powershell.exe`).
- **Linux / macOS**: `/bin/bash --noprofile --norc` (falls back to `/bin/sh`).
- Override via the `shell=` constructor argument or the
  `AGENT_FRAMEWORK_SHELL` environment variable.

## Relationship to `agent-framework-hyperlight`

`LocalShellTool` runs commands **directly on the host** and is complementary
to the sandboxed `execute_code` tool shipped by
`agent_framework_hyperlight.HyperlightCodeActProvider`. If you need
microVM-isolated execution, prefer CodeAct. A future `HyperlightShellExecutor`
backend is planned so callers can share one sandbox across both tools.
