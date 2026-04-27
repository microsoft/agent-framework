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

> **`LocalShellTool` is not a sandbox.** It runs commands directly on the
> host with the agent process's privileges. The actual security boundary
> is **approval-in-the-loop**. For untrusted input use a sandboxed
> executor — see [`agent-framework-hyperlight`](#relationship-to-agent-framework-hyperlight).

Defenses (in priority order):

- **Approval-in-the-loop** — every command surfaces as a
  `user_input_request`; nothing runs without consent. Disabling this
  requires `acknowledge_unsafe=True`.
- **Process-tree termination on timeout** via `psutil`, so child
  processes (`make`, watchers, network tools) cannot survive the timeout.
- **Output truncation** to 64 KiB (head + tail with marker).
- **Audit hook** (`on_command=…`) for SIEM / append-only logs.
- **Best-effort policy denylist** (`rm -rf /`, `mkfs`, `dd if=`, fork
  bombs, `curl … | sh`, …). This is a guardrail, **not a boundary** —
  trivial bypasses include `\rm -rf /`, `${RM:=rm} -rf /`,
  `python -c "…"`, `eval $(echo … | base64 -d)`, `find / -delete`, and
  PowerShell-native `Remove-Item -Recurse -Force`. See
  `tests/test_security.py` for the documented residual risk surface.

Override with `ShellPolicy`:

```python
from agent_framework_tools.shell import LocalShellTool, ShellPolicy

shell = LocalShellTool(
    policy=ShellPolicy(allowlist=[r"^ls\b", r"^cat\b", r"^git status$"]),
    approval_mode="never_require",
    acknowledge_unsafe=True,  # required to bypass approval
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
