# agent-framework-local-codeact

Local CodeAct integrations for Microsoft Agent Framework.

> [!WARNING]
> This package runs LLM-generated Python in the local environment. It is **not**
> a Python security sandbox and is not safe for untrusted prompts or code on a
> developer workstation or production host without an external sandbox.

`agent-framework-local-codeact` is intended for environments that already
provide process, filesystem, network, and credential isolation, especially
Foundry hosted agents. It provides the familiar CodeAct provider pattern used by
the Hyperlight and Monty packages while keeping the implementation local to the
agent container.

## Install

```bash
pip install agent-framework-local-codeact --pre
```

This is an alpha package and is not included in `agent-framework[all]`.

## Basic usage

```python
from agent_framework import Agent
from agent_framework_local_codeact import LocalCodeActProvider, ProcessExecutionLimits

agent = Agent(
    client=...,
    instructions="Use execute_code for Python control flow when it helps.",
    context_providers=[
        LocalCodeActProvider(
            execution_limits=ProcessExecutionLimits(timeout_seconds=5),
            # Optional: use a specific interpreter instead of the current one.
            # python_executable="/usr/bin/python3",
        )
    ],
)
```

For Foundry hosted agents, add the provider to the local agent before wrapping
it with `ResponsesHostServer`.

```python
from agent_framework_foundry_hosting import ResponsesHostServer

server = ResponsesHostServer(agent)
```

## What the package controls

- Validates generated code against AST allow-lists (allowed imports, builtins,
  and operations) before execution.
- Runs generated code in a child Python process by default.
- Uses `sys.executable` by default, or an explicit `python_executable` when
  configured.
- Does not inherit host environment variables unless explicitly provided.
- Does not invoke a shell.
- Applies code-size, timeout, stdout, stderr, and result-size limits.
- Allows only provider-owned host tools to be called from generated code.
- Propagates `always_require` approval from managed tools to `execute_code`.
- Captures new or modified files under configured writable mounts while
  skipping symlinks.

These are defense-in-depth controls, not a containment boundary. The AST
validator blocks common dangerous operations (`eval`, `exec`, `import subprocess`,
etc.) but does not make Python execution safe on an unsandboxed host.

## What the package does not protect

- Malicious Python working within allowed imports and operations.
- Network access unless the surrounding environment blocks it.
- Prompt-injected exfiltration through allowed host tools.
- Resource exhaustion outside the configured limits.
- Log, stdout, stderr, or result poisoning.

Use Foundry hosted agents, containers, VMs, or equivalent infrastructure as the
actual security boundary.

## Host tools

Register host tools on the provider. Generated code calls them with `await`:

```python
async def add(a: int, b: int) -> int:
    return a + b

provider = LocalCodeActProvider(tools=[add])
```

Inside `execute_code`:

```python
result = await add(a=2, b=3)
print(result)
```

`await call_tool("add", a=2, b=3)` is also available for tool names that are not
valid Python identifiers.

## Files

No project directory is exposed by default. If you configure `workspace_root` or
`file_mounts`, generated code receives the direct path to the configured host
directory inside the surrounding sandbox. Mount modes are used for instructions
and output capture; they are not an OS-level filesystem policy.

Only files under `read-write` mounts are captured after execution.

### Virtual mount paths are display labels

Each mount has a `mount_path` (for example `/input`, `/output`) that is used
**only** for instructions to the model and for tagging captured files in the
response. The subprocess executes against the real host filesystem and does
not see a chrooted virtual path. Filesystem isolation comes from the outer
sandbox (for example a Foundry hosted-agent container); within that sandbox
the validator and capture rules below provide defense-in-depth so that
generated code cannot redirect a virtual mount label to data outside the
configured host directory:

- Mount roots may not themselves be symbolic links — a symlinked `host_path`
  is rejected so it cannot silently point at another directory.
- Symbolic links inside a mount (file or directory) are skipped during
  capture, so a symlink created at runtime cannot leak content from outside
  the mount root.
- Hard links inside a mount are skipped during capture — a hardlink whose
  inode lives outside the mount (for example `ln /etc/passwd
  /input/loot.txt`) cannot surface protected host data through the mount.
- During capture every entry's resolved path is required to stay under the
  mount root, so OS features that bypass `is_symlink()` (junctions, bind
  mounts) still cannot escape.
- `mount_path` is normalized to reject `..` segments so the virtual path
  cannot be crafted to traverse out of the mount in captured-file metadata.

## Python interpreter and runner

Subprocess mode launches Python as:

```text
<python_executable> -I -m agent_framework_local_codeact._runner
```

`python_executable` defaults to the current Python interpreter. If you point it
at a different virtual environment or system Python, that environment must be
able to import `agent_framework_local_codeact._runner`.

For hosts that cannot rely on a Python package import, such as a future .NET
host bundling the runner itself, pass `runner_script` to execute the runner by
file path instead:

```python
LocalCodeActProvider(
    python_executable="/usr/bin/python3",
    runner_script="/app/local_codeact_runner.py",
)
```

The framed JSON-lines protocol between parent and runner is intended to be the
cross-language boundary for a .NET implementation. The .NET version should use
subprocess mode only; same-interpreter execution is Python-specific.

## Code validation

Generated code is validated against AST allow-lists before execution:

- **Allowed imports**: `asyncio`, `pathlib`, `json`, `math`, `datetime`, `time`,
  `os` (limited to `os.environ`, `os.path`), and a few others.
- **Blocked imports**: `subprocess`, `sys`, `socket`, `urllib`, `requests`,
  `threading`, `multiprocessing`, and others.
- **Blocked builtins**: `eval`, `exec`, `compile`, `__import__`, `globals`,
  `locals`, `open`, and others.
- **`os` attribute allow-list**: only `os.environ` and `os.path` are permitted.
  Every other `os.<attr>` access (`os.system`, `os.exec*`, `os.popen`,
  `os.fork`, `os.listdir`, `os.open`, `os.getcwd`, file-system mutations, etc.)
  is rejected. Override via `allowed_os_attrs` to opt in to a different set.

Validation errors are returned as `Content.from_error` with details about which
operations are not allowed. This is defense-in-depth only and does not make
Python execution safe on an unsandboxed host.

### Customizing allow-lists

Use custom allow/block lists to adapt validation to your use case:

```python
from agent_framework_local_codeact import LocalExecuteCodeTool

# Allow specific imports (replaces defaults)
tool = LocalExecuteCodeTool(
    allowed_imports={"csv", "json", "pathlib"},
    blocked_imports=set(),  # Empty block-list
)

# Block specific imports (replaces defaults)
provider = LocalCodeActProvider(
    blocked_imports={"json", "requests"},
)

# Block specific builtins (replaces defaults)
tool = LocalExecuteCodeTool(
    blocked_builtins={"len", "sum"},  # Prevent common operations
)
```

Custom lists **replace** the defaults entirely (they do not augment them).

## Unsafe in-process mode

`execution_mode="unsafe_in_process"` runs generated code with `exec` in the
agent process. This mode is intended only for debugging package behavior because
timeouts cannot stop CPU-bound or blocking code in the same interpreter. It also
does not provide subprocess-only behavior such as an explicit environment map or
working-directory isolation.
