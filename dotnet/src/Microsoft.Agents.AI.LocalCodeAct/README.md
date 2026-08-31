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

var options = new LocalCodeActProviderOptions()
{
    ExecutionLimits = new ProcessExecutionLimits { TimeoutSeconds = 5 },
};

using var provider = new LocalCodeActProvider("/usr/bin/python3", options);

// Register provider with your AIAgent's context providers.
```

## What the Package Controls

- **AST validation** (default on): Validates generated code against allow-lists
  before execution.
- **Subprocess execution**: Runs generated code in a child Python process.
- **Explicit Python path**: the provider and standalone function constructors require a Python executable path (no default).
- **Isolated environment**: Does not inherit host environment variables unless
  explicitly provided.
- **No shell invocation**: Launches Python directly without a shell.
- **Resource limits**: Applies timeout, stdout, stderr, and result-size limits.
- **Tool gating**: Only provider-owned host tools can be invoked from generated
  code via `await call_tool("<name>", ...)`.
- **File capture**: Captures new files under configured **read-write** mounts
  while skipping symlinks. Modifications to pre-existing files are not captured.

These are defense-in-depth controls, not a containment boundary. The AST
validator blocks common dangerous operations (`eval`, `exec`,
`import subprocess`, attribute access for `os.system`, `__class__`, etc.) but
does not make Python execution safe on an unsandboxed host.

## What the Package Does NOT Protect

- Malicious Python code working within allowed imports and operations.
- Network access unless the surrounding environment blocks it.
- Prompt-injected exfiltration through allowed host tools.
- Resource exhaustion outside the configured limits.
- Log, stdout, stderr, or result poisoning.

**Use Azure container instances, VMs, Foundry hosted agents, or equivalent
infrastructure as the actual security boundary.**

## Host Tools

Register host tools via the options or on the provider directly:

```csharp
var addFunction = AIFunctionFactory.Create(
    (int a, int b) => a + b,
    name: "add",
    description: "Adds two integers.");

using var provider = new LocalCodeActProvider("/usr/bin/python3", new LocalCodeActProviderOptions
{
    Tools = new[] { addFunction },
});

// Or mutate after construction:
provider.AddTools(addFunction);
```

Inside `execute_code`:

```python
total = await call_tool("add", a=2, b=3)
print(total)
```

## Code Validation

By default, the package validates Python code against allow-lists before
execution. The validator runs in its own short-lived Python subprocess with a
dedicated timeout (`ProcessExecutionLimits.ValidationTimeoutSeconds`).

- **Allowed imports**: `math`, `random`, `json`, `datetime`, `pathlib`, `os`
  (only `os.environ`, `os.path` attributes are reachable), etc.
- **Blocked imports**: `subprocess`, `sys`, `socket`, `importlib`, network and
  threading modules, etc.
- **Allowed builtins**: `print`, `len`, `str`, type constructors, etc.
- **Blocked builtins**: `eval`, `exec`, `compile`, `__import__`, `open`,
  `getattr`, `setattr`, etc.

See [`Resources/validator.py`](Resources/validator.py) for the full default
allow-lists.

### Customizing Validation

Override the default lists:

```csharp
using var provider = new LocalCodeActProvider("/usr/bin/python3", new LocalCodeActProviderOptions
{
    AllowedImports = new[] { "math", "datetime", "mymodule" },
    BlockedImports = new[] { "subprocess", "sys" },
    AllowedBuiltins = new[] { "print", "len", "str", "int" },
    BlockedBuiltins = new[] { "eval", "exec", "compile" },
});
```

Custom lists **replace** the defaults (not augment).

### Disabling Validation

Set `ValidationDisabled = true` to skip the AST validator entirely. Doing so
removes a critical defense-in-depth control. Only disable when the generated
code is trusted or when running inside a strong external sandbox.

## File Mounts

Mount host directories to expose them to generated code:

```csharp
using var provider = new LocalCodeActProvider("/usr/bin/python3", new LocalCodeActProviderOptions
{
    FileMounts = new[]
    {
        new FileMount("/tmp/data", "/input", FileMountMode.ReadOnly),
        new FileMount("/tmp/output", "/output", FileMountMode.ReadWrite),
    },
});
```

Generated code accesses mounts via `HostPath`. `MountPath` is descriptive
metadata only — the subprocess sees the real host path. Read-write mounts are
scanned for **new** files after execution, and those files are returned as
`DataContent`. Symlinks are skipped.

## Environment Variables

Pass environment variables explicitly. The subprocess does NOT inherit the host
environment by default:

```csharp
using var provider = new LocalCodeActProvider("/usr/bin/python3", new LocalCodeActProviderOptions
{
    Environment = new Dictionary<string, string>
    {
        ["API_KEY"] = "...",
        ["LOG_LEVEL"] = "INFO",
    },
});
```

## Standalone Function

If you do not want the provider machinery you can expose `execute_code` directly:

```csharp
var function = new LocalExecuteCodeFunction("/usr/bin/python3");
```

`LocalExecuteCodeFunction` snapshots tools and mounts at construction time and
is safe to reuse across invocations.

## Execution Modes

The .NET implementation only supports subprocess execution. There is no
"unsafe in-process" mode in .NET.

## License

MIT
