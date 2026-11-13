# agent-framework-monty

Monty-backed CodeAct integrations for Microsoft Agent Framework.

> [!WARNING]
> This package is in **beta**. APIs may change before its stable release. It is
> included in `agent-framework[all]`.

## FIDES compatibility

> [!WARNING]
> **FIDES integration is not supported with CodeAct providers.** Host-tool calls
> made inside generated code bypass the agent's function middleware, so FIDES
> policy enforcement and label tracking do not apply to those nested calls or
> intermediate code values. Checks on the outer `execute_code` invocation do not
> enforce the policies of individual tools called inside it.
>
> Registering tools with recognized FIDES `additional_properties` logs a warning,
> but does not block execution. This is a best-effort diagnostic: FIDES also uses
> defaults for unannotated tools, so no warning does not imply support or safety.
> Keep tools that require FIDES as direct agent tools, not Monty-managed tools, and
> enforce authorization and destination restrictions inside host functions.
> See the [FIDES guide](../../samples/02-agents/security/FIDES_DEVELOPER_GUIDE.md).

## Error diagnostics

Host tool failures raise a generic `RuntimeError("Host tool execution failed.")`
inside generated code by default. Execution error contents omit raw diagnostic
details. This applies to both direct tool calls and `call_tool(...)`, including
failures that generated code catches and prints or returns.

Both `MontyCodeActProvider` and `MontyExecuteCodeTool` accept the host-side option
`include_detailed_errors=True` to retain original host exception types/messages
and execution diagnostics. Enable it only for a trusted channel: exception
messages can contain credentials or other sensitive data. This option is not a
parameter of `execute_code` and is independent of the outer chat client's error
policy and sensitive-data logging. Run snapshots and serialized state retain it.

Code that catches a specific host exception type, such as `ValueError`, must
instead handle the generic `RuntimeError` in the default mode. Failure signaling
and successful tool results are unchanged.

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
    resource_limits={                       # Monty 1.x ResourceLimits TypedDict
        "max_feed_duration_secs": 5.0,
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
- Capture is limited to **20 files and 20 MiB of raw file data per call across
  all read-write mounts**, with a **5 MiB per-file limit**. Empty files count
  toward the file limit. Files that do not fit the remaining byte budget are
  skipped; later smaller files can still be captured. Exact fits are accepted.
  Returned base64 data and Python objects add memory overhead beyond the raw
  byte budget.
- Files omitted by capture limits produce one text summary, not one warning
  per file. Omission does not undo filesystem writes. These limits bound
  attachment capture, not filesystem traversal, disk use, or all host memory.
- `overlay` mounts buffer writes in memory (nothing leaks to the host and
  nothing is captured). `read-only` mounts reject writes.
- **`resource_limits`** accepts Monty 1.x
  [`ResourceLimits`](https://github.com/pydantic/monty) keys. Monty 1.0 or later
  is required. `max_feed_duration_secs` limits total sandbox execution time
  across host round trips; `max_turn_duration_secs` resets at each host round
  trip. Both exclude time spent waiting on the host. The documented legacy
  `max_duration_secs` option remains supported as an alias for
  `max_feed_duration_secs`; specifying both is an error. Other keys include
  `max_memory`, `gc_interval`, `max_recursion_depth`, `max_suspensions`, and
  `max_total_sleep_secs`. These interpreter limits do not independently bound
  host-side post-execution attachment capture.
- Sandbox code runs in Monty worker processes, so it does not block the event
  loop, and cancelling an `execute_code` call discards its worker. When
  `resource_limits` sets neither `max_feed_duration_secs` nor `max_duration_secs`,
  a **30-second** `max_feed_duration_secs` applies. Set it to another value, or to
  `None` (`resource_limits={"max_feed_duration_secs": None}`), to change or remove
  the limit. A call that reaches the limit returns an `Execution error`; with
  `include_detailed_errors=True` its details name the limit
  (`TimeoutError: feed time limit exceeded`). Concurrent `execute_code` calls
  overlap and each starts its own worker process, so bound concurrency in your
  application when serving many callers.
- Calls that can write to the same host files take turns, so captured files stay
  attributed to the right call. A tool with a `read-write` mount (including
  `workspace_root`) serves one call at a time. This covers every run of one
  provider and works across event loops and threads. A call waits at most 10
  minutes for its turn and then returns an error, and a slow host tool holds up
  the calls behind it. A call that a host tool starts while its own call has the
  turn, such as a sub-agent that uses the same provider, is part of that call
  and does not wait; the outer call also returns the files that the inner call
  wrote. Separate tools or providers that mount the same host directory do not
  take turns with each other, so give each one its own directory.

## DSL inside `execute_code`

The model generates Python code that runs inside Monty's Rust-based interpreter.
Available primitives:

| Primitive | Behavior |
|-----------|----------|
| `await tool_name(**kwargs)` | Direct typed call to a registered host tool. Keyword arguments only; positional arguments are rejected. Argument types are checked before execution. |
| `await call_tool("name", **kwargs)` | Generic fallback that dispatches by tool name. Not type-checked. |
| `asyncio.gather(...)` | Fans out concurrent tool calls. |
| `print(...)` | Captured and surfaced as text in the tool result. |

## Network access and Python packages

Monty runs its own Python interpreter, not the host's Python environment. This
integration exposes no `pip` or package-installation option; installing a
dependency on the host does not make it importable in Monty code. Use the
interpreter's supported modules for code that runs inside Monty.

Unlike Hyperlight, `MontyCodeActProvider` and `MontyExecuteCodeTool` do not expose
an `allowed_domains` option. For external API calls or operations requiring
host-installed packages, register a host function in `tools` and invoke it with
`await tool_name(...)` or `await call_tool("name", ...)`. Keep credentials,
authorization, and any destination allow-list checks inside that function.
These functions execute on the host rather than inside the Monty interpreter.

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
  or positional-argument usage surface as a clear error before any host tool runs.
- The beta package is part of `agent-framework[all]` and is reachable through
  the lazy-loading namespace `agent_framework.monty`.
