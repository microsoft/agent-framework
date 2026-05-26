# Local CodeAct Package (agent-framework-local-codeact)

Local subprocess-backed CodeAct integrations for the Microsoft Agent Framework.

> [!WARNING]
> This package runs LLM-generated Python in the local environment. It is **not**
> a Python security sandbox. Use it only inside an external sandbox such as a
> Foundry hosted-agent container, VM, or locked-down container runtime.

## Core Classes

- **`LocalCodeActProvider`** — `ContextProvider` that injects a run-scoped
  `execute_code` tool plus dynamic CodeAct instructions.
- **`LocalExecuteCodeTool`** — `FunctionTool` that validates generated code
  against AST allow-lists, then runs it in a local Python subprocess by default.
  Same-interpreter execution is available only through
  `execution_mode="unsafe_in_process"`.

## Public API

```python
from agent_framework_local_codeact import (
    CodeValidationError,
    ExecutionMode,
    FileMount,
    FileMountInput,
    LocalCodeActProvider,
    LocalExecuteCodeTool,
    MountMode,
    ProcessExecutionLimits,
)
```

## Architecture

- **`_types.py`** — public types for execution limits, execution mode, and file
  mount metadata.
- **`_provider.py`** — provider wrapper around a managed execute-code tool.
- **`_execute_code_tool.py`** — tool management, approval propagation,
  subprocess orchestration, state serialization, and output-file capture.
- **`_validator.py`** — AST-based allow-list code validation (blocks `eval`,
  `exec`, dangerous imports/builtins, and risky os operations).
- **`_bridge.py`** — parent-side framed IPC and optional unsafe in-process
  runner. Subprocess mode supports explicit `python_executable` and
  `runner_script` configuration so non-Python hosts can launch the same runner
  by file path.
- **`_runner.py`** — child-process entry point used by subprocess mode.
- **`_files.py`** — mount normalization and symlink-safe file capture helpers.
- **`_instructions.py`** — dynamic instructions and risk wording.

## Security posture

Do not describe this package as sandboxing Python code. AST validation, process
isolation, timeouts, output caps, environment allow-lists, and file capture
limits are defense-in-depth controls only. Host filesystem, network, credentials,
process table, and kernel resources must be isolated by the surrounding
environment.

## .NET portability notes

Keep the subprocess JSON-lines protocol stable where possible. A .NET port can
mirror the provider/tool/file/limit surface, but should omit
`unsafe_in_process` and require or strongly encourage an explicit
`python_executable`. If the .NET package bundles the Python runner instead of
requiring a Python wheel install, invoke it through the file-path
`runner_script` pattern rather than relying on `-m agent_framework_local_codeact._runner`.

The AST validator should be ported to .NET as well (likely using Roslyn for C#
code analysis if the .NET version supports generated C# execution, or a Python
AST parser if it still executes Python).
