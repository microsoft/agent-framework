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
  and shell functions persist across tool invocations.
- **Stateless** (`mode="stateless"`): each command runs in a fresh subprocess.

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

## `ShellEnvironmentProvider` — context provider

A model talking to a PowerShell session will sometimes default to bash
syntax (`export FOO=bar`, `ls -la`, `> /dev/null`) and vice versa.
`ShellEnvironmentProvider` is an `AIContextProvider` that probes the live
shell once per session — family, version, OS, working directory, and a
configurable list of CLI tools (`git`, `node`, `python`, `docker` by
default) — and injects a system-prompt block describing the shell idiom
to use and the available CLIs.

```python
from agent_framework_tools.shell import (
    LocalShellTool,
    ShellEnvironmentProvider,
    ShellEnvironmentProviderOptions,
)

shell = LocalShellTool()
provider = ShellEnvironmentProvider(
    shell,
    ShellEnvironmentProviderOptions(probe_tools=("git", "uv", "node")),
)
agent = Agent(
    client=client,
    tools=[client.get_shell_tool(func=shell.as_function())],
    context_providers=[provider],
)
```

Probe failures from expected error types (timeouts, policy rejections,
spawn failures) are recorded as `None` fields in the snapshot rather
than raised; a missing CLI never fails the agent. A failed first probe
does not poison the cache — the next call retries.

## `DockerShellTool` — sandboxed tier

When commands originate from untrusted input (e.g. the model is acting on
prompt-injected document content), prefer `DockerShellTool`. With the
default isolation flags and a trusted container runtime, the container
is the intended security boundary and approval gating becomes optional.

```python
import asyncio
from agent_framework_tools.shell import DockerShellTool


async def main() -> None:
    async with DockerShellTool(
        image="mcr.microsoft.com/azurelinux/base/core:3.0",
        approval_mode="never_require",  # container is the boundary
    ) as shell:
        result = await shell.run("uname -a && id")
        print(result.stdout)


asyncio.run(main())
```

Defaults applied to every container:

- `--network none` — no host or external network.
- `--user 65534:65534` — runs as `nobody:nogroup`.
- `--read-only` root filesystem; only mounted host paths are writable.
- `--cap-drop ALL` and `--security-opt no-new-privileges`.
- `--memory 512m`, `--pids-limit 256`, ephemeral `tmpfs /tmp`.

To expose a host directory, pass `host_workdir="/path"` (mounted
read-only by default; `mount_readonly=False` to allow writes). Swap the
container runtime with `docker_binary="podman"`.

## Sandbox tiers at a glance

| Use case | Tool | Sandbox |
|---|---|---|
| Run *code* (untrusted) | `HyperlightCodeActProvider.execute_code` (`agent-framework-hyperlight`) | Hyperlight WASM microVM |
| Run *shell* (untrusted) | `DockerShellTool` | OCI container (network-off, non-root, capabilities dropped) |
| Run *shell* (trusted dev) | `LocalShellTool` | Approval-in-the-loop |

## Relationship to `agent-framework-hyperlight`

`agent-framework-hyperlight` is a **code** sandbox (a single WASM guest
loaded into a microVM, called via a hostcall ABI — there is no kernel,
userland, or shell binary inside). It is the right tier for executing
generated *code*. For sandboxing *shell* commands, the realistic tier is
OCI, which `DockerShellTool` provides.
