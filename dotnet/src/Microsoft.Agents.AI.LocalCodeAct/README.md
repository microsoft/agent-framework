# Microsoft.Agents.AI.LocalCodeAct

Local CodeAct integration for Microsoft Agent Framework.

> [!WARNING]
> This package runs LLM-generated Python code in the local environment. It is **NOT**
> a Python security sandbox and is not safe for untrusted prompts or code on a
> developer workstation or production host without an external sandbox.

`Microsoft.Agents.AI.LocalCodeAct` is intended for environments that already
provide process, filesystem, network, and credential isolation (e.g., Azure
container instances, VMs, or Foundry hosted agents). It provides the familiar
CodeAct provider pattern used by the Hyperlight package while executing Python
locally in the agent environment.

## Installation

```bash
dotnet add package Microsoft.Agents.AI.LocalCodeAct --prerelease
```

This is a preview package.

## Basic Usage

```csharp
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.LocalCodeAct;

var agent = new Agent
{
    Client = ...,
    Instructions = "Use execute_code for Python control flow when it helps.",
    ContextProviders =
    [
        new LocalCodeActProvider
        {
            PythonExecutablePath = "/usr/bin/python3",  // Required in .NET
            ExecutionLimits = new ProcessExecutionLimits { TimeoutSeconds = 5 },
        }
    ],
};
```

## What the Package Controls

- **AST validation**: Validates generated code against allow-lists (allowed imports,
  built ins, and operations) before execution.
- **Subprocess execution**: Runs generated code in a child Python process.
- **Explicit Python path**: Requires `PythonExecutablePath` (no default).
- **Isolated environment**: Does not inherit host environment variables unless
  explicitly provided.
- **No shell invocation**: Launches Python directly without a shell.
- **Resource limits**: Applies code-size, timeout, stdout, stderr, and
  result-size limits.
- **Tool gating**: Allows only provider-owned host tools to be called from
  generated code.
- **File capture**: Captures new or modified files under configured writable
  mounts while skipping symlinks.

These are defense-in-depth controls, not a containment boundary. The AST
validator blocks common dangerous operations (`eval`, `exec`, `import subprocess`,
etc.) but does not make Python execution safe on an unsandboxed host.

## What the Package Does NOT Protect

- Malicious Python code working within allowed imports and operations.
- Network access unless the surrounding environment blocks it.
- Prompt-injected exfiltration through allowed host tools.
- Resource exhaustion outside the configured limits.
- Log, stdout, stderr, or result poisoning.

**Use Azure container instances, VMs, Foundry hosted agents, or equivalent
infrastructure as the actual security boundary.**

## Host Tools

Register host tools on the provider. Generated code calls them:

```csharp
Task<int> AddAsync(int a, int b) => Task.FromResult(a + b);

var provider = new LocalCodeActProvider
{
    PythonExecutablePath = "/usr/bin/python3",
    Tools = [Tool.From(AddAsync)],
};
```

Inside `execute_code`:

```python
result = await add(a=2, b=3)
print(result)
```

## Code Validation

By default, the package validates Python code against allow-lists before execution:

- **Allowed imports**: `math`, `random`, `json`, `datetime`, `pathlib`, etc.
- **Blocked imports**: `os`, `subprocess`, `sys`, `importlib`, network, etc.
- **Allowed builtins**: `print`, `len`, `str`, type constructors, etc.
- **Blocked builtins**: `eval`, `exec`, `compile`, `__import__`, `open`, `getattr`, etc.

See the Python implementation for the full default lists.

### Customizing Validation

Override the default lists:

```csharp
var provider = new LocalCodeActProvider
{
    Python ExecutablePath = "/usr/bin/python3",
    AllowedImports = ["math", "datetime", "mymodule"],
    BlockedImports = ["os", "subprocess", "sys"],
    AllowedBuiltins = ["print", "len", "str", "int"],
    BlockedBuiltins = ["eval", "exec", "compile"],
};
```

Custom lists **replace** the defaults (not augment).

## File Mounts

Mount host directories or files:

```csharp
var provider = new LocalCodeActProvider
{
    PythonExecutablePath = "/usr/bin/python3",
    FileMounts =
    [
        new FileMount
        {
            HostPath = "/tmp/data",
            MountPath = "/input",
            Mode = FileMountMode.ReadOnly,
        },
        new FileMount
        {
            HostPath = "/tmp/output",
            MountPath = "/output",
            Mode = FileMountMode.ReadWrite,
        },
    ],
};
```

Generated code accesses mounts via `HostPath`. `MountPath` is metadata only.
Read-write mounts are scanned for new/modified files after execution, and those
files are returned as data content.

## Environment Variables

Pass environment variables explicitly:

```csharp
var provider = new LocalCodeActProvider
{
    PythonExecutablePath = "/usr/bin/python3",
    Environment = new Dictionary<string, string>
    {
        ["API_KEY"] = "...",
        ["LOG_LEVEL"] = "INFO",
    },
};
```

The subprocess does NOT inherit the host environment by default.

## Execution Modes

The .NET implementation only supports `Subprocess` mode (Python execution in a
child process). There is no "unsafe in-process" mode in .NET.

## License

MIT
