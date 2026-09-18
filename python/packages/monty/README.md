# agent-framework-monty

Monty-backed CodeAct integrations for Microsoft Agent Framework.

> [!WARNING]
> This package is in **beta**. APIs may change before its stable release. It is
> included in `agent-framework[all]`.

## Installation

```bash
pip install agent-framework-monty --pre
```

The package depends on [`pydantic-monty`](https://github.com/pydantic/monty), a
Rust-based Python interpreter, so it runs on Linux, macOS, and Windows wherever
Monty wheels are published — no hypervisor or WASM backend required.

## Quick start

### Context provider (recommended)

Use `MontyCodeActProvider` to automatically inject the `execute_code` tool and
CodeAct instructions into every agent run. Tools registered on the provider are
available inside the Monty interpreter as **typed async functions** (e.g.
`await compute(operation="add", a=1, b=2)`), and as a fallback through
`call_tool(...)`.

```python
from agent_framework import Agent, tool
from agent_framework.monty import MontyCodeActProvider


@tool
def compute(operation: str, a: float, b: float) -> float:
    """Perform a math operation."""
    ops = {"add": a + b, "subtract": a - b, "multiply": a * b, "divide": a / b}
    return ops[operation]


codeact = MontyCodeActProvider(
    tools=[compute],
    approval_mode="never_require",
)

agent = Agent(
    client=client,
    name="CodeActAgent",
    instructions="You are a helpful assistant.",
    context_providers=[codeact],
)

result = await agent.run("Multiply 6 by 7 using execute_code.")
```

### Standalone tool

Use `MontyExecuteCodeTool` directly when you want full control over how the
tool is added to the agent (e.g. when mixing sandbox tools with direct-only
tools on the same agent).

```python
from agent_framework import Agent, tool
from agent_framework.monty import MontyExecuteCodeTool


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email (direct-only, not available inside the sandbox)."""
    return f"Email sent to {to}"


execute_code = MontyExecuteCodeTool(
    tools=[compute],
    approval_mode="never_require",
)

agent = Agent(
    client=client,
    name="MixedToolsAgent",
    instructions="You are a helpful assistant.",
    tools=[send_email, execute_code],
)
```

### Manual static wiring

For fixed configurations where provider lifecycle overhead is unnecessary,
build the CodeAct instructions once and pass them to the agent at construction
time:

```python
execute_code = MontyExecuteCodeTool(
    tools=[compute],
    approval_mode="never_require",
)

codeact_instructions = execute_code.build_instructions(tools_visible_to_model=False)

agent = Agent(
    client=client,
    name="StaticWiringAgent",
    instructions=f"You are a helpful assistant.\n\n{codeact_instructions}",
    tools=[execute_code],
)
```

### Tool parameter documentation

Both `MontyCodeActProvider` and `MontyExecuteCodeTool` accept the keyword-only
`tool_description_format` parameter. It controls the registered tools' parameter
documentation in both the `execute_code` description and CodeAct instructions:

- `"compact"` (default) lists scalar parameter types, required/optional status,
  descriptions, enum choices, and defaults.
- `"json"` includes the complete parameter JSON Schema.
- A mapping such as `{"compute": "json", "send_email": "compact"}` selects formats
  by exact, case-sensitive tool name. Names missing from the mapping use compact.

Compact automatically falls back to complete JSON Schema, with an explanatory
note, for schemas it cannot represent faithfully, such as nested objects, arrays,
references, unions, or additional constraints. Parameter schemas and runtime
type checking are not changed.

Mappings are copied at construction and for each run snapshot. Entries for
currently unregistered tools are retained for later `add_tools` calls, including
after removal or clearing of the registry. State snapshots include the configured
string or mapping in `tool_description_format`.

Only `"compact"`, `"json"`, or mappings from string names to these values are
accepted: unsupported choices raise `ValueError`; `None`, invalid input types,
non-string mapping keys, and non-string choices raise `TypeError`.

Tool parameter schemas are model-visible metadata, just as they are for direct
function calling. Do not put credentials, tenant identifiers, or other secrets in
parameter descriptions, enum values, defaults, or custom schema fields.

### Host tool lifetime

Registered `FunctionTool` instances retain their invocation and exception counters
across `execute_code` calls and provider runs. Their `max_invocations` and
`max_invocation_exceptions` limits use the same counters as direct invocations of
those instances. A provider's run-scoped snapshot captures tool membership; it
does not reset host tool counters.

### File mounts and resource limits

Mount host directories into the sandbox and cap execution resources:

```python
from agent_framework.monty import FileMount, MontyCodeActProvider

codeact = MontyCodeActProvider(
    tools=[compute],
    workspace_root="/host/workspace",       # auto-mounted at /input (read-write)
    file_mounts=[
        "/host/data",                                                # shorthand: same path on both sides
        ("/host/models", "/sandbox/models"),                          # explicit (host, mount_path)
        FileMount(                                                    # full control
            host_path="/host/cache",
            mount_path="/sandbox/cache",
            mode="overlay",                # "read-only" | "read-write" | "overlay"
            write_bytes_limit=10 * 1024 * 1024,
        ),
    ],
    resource_limits={                       # Monty ResourceLimits TypedDict
        "max_duration_secs": 5.0,
        "max_memory": 64 * 1024 * 1024,
    },
)
```

- **`workspace_root`** mirrors the Hyperlight default: the directory is mounted
  at `/input` in `read-write` mode.
- **`file_mounts`** accepts a string shorthand, a `(host_path, mount_path)`
  tuple, or a `FileMount` named tuple (with optional `mode` and
  `write_bytes_limit`).
- Files written by the sandbox to any **`read-write`** mount are scanned
  after each `execute_code` call and returned as `Content.from_data(...)`
  attachments (with a `path` annotation in `additional_properties`),
  mirroring Hyperlight's `/output` flow.
- `overlay` mounts buffer writes in memory (nothing leaks to the host and
  nothing is captured). `read-only` mounts reject writes.
- **`resource_limits`** is forwarded straight to Monty's
  [`ResourceLimits`](https://github.com/pydantic/monty) TypedDict
  (`max_duration_secs`, `max_memory`, `gc_interval`, `max_recursion_depth`,
  `max_suspensions`).

## DSL inside `execute_code`

The model generates Python code that runs inside Monty's Rust-based interpreter.
Available primitives:

| Primitive | Behavior |
|-----------|----------|
| `await tool_name(**kwargs)` | Direct typed call to a registered host tool. Argument types are checked before execution. |
| `await call_tool("name", **kwargs)` | Generic fallback that dispatches by tool name. Not type-checked. |
| `asyncio.gather(...)` | Fans out concurrent tool calls. |
| `print(...)` | Captured and surfaced as text in the tool result. |

## Notes

- `MontyCodeActProvider` and `MontyExecuteCodeTool` mirror the API surface of
  the `agent-framework-hyperlight` counterparts where the underlying runtime
  supports it.
- Monty interprets a **subset** of Python (a Rust-based interpreter). Most
  control flow, common stdlib modules (`sys`, `os`, `typing`, `asyncio`, `re`,
  `datetime`, `json`), and async functions are supported, but exotic features
  may not be available. OS-level access (filesystem, network, subprocess) is
  rejected with `PermissionError` **by default**; mount host directories with
  `workspace_root` / `file_mounts` to grant scoped filesystem access.
- Code is type-checked against tool signatures via
  [ty](https://docs.astral.sh/ty/) before execution, so wrong argument types
  surface as a clear error before any host tool runs.
- The beta package is part of `agent-framework[all]` and is reachable through
  the lazy-loading namespace `agent_framework.monty`.
