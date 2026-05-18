# Monty Package (agent-framework-monty)

Monty-backed CodeAct integrations for the Microsoft Agent Framework.

> [!NOTE]
> **Alpha package.** Not part of `agent-framework[all]` yet. Install explicitly
> with `pip install agent-framework-monty --pre`.

## Core Classes

- **`MontyCodeActProvider`** — `ContextProvider` that injects a run-scoped
  `execute_code` tool plus dynamic CodeAct instructions. Mirrors the
  `HyperlightCodeActProvider` API for the parts that apply to a non-sandboxed
  Python interpreter.
- **`MontyExecuteCodeTool`** — `FunctionTool` that wraps the Monty interpreter.
  Use directly for mixed-tool agents or manual static wiring. Mirrors
  `HyperlightExecuteCodeTool`.

## Public API

```python
from agent_framework_monty import (
    FileMount,
    FileMountInput,
    MontyCodeActProvider,
    MontyExecuteCodeTool,
    MountMode,
)
```

`MontyCodeActProvider` and `MontyExecuteCodeTool` both accept:
- `tools` — host tool callables / `FunctionTool`s
- `approval_mode` — `"never_require"` (default) or `"always_require"`
- `workspace_root` — host directory auto-mounted at `/input`
  (mirrors `HyperlightCodeActProvider.workspace_root`)
- `file_mounts` — sequence of `FileMountInput` (str shorthand,
  `(host_path, mount_path)` tuple, or `FileMount`)
- `resource_limits` — Monty `ResourceLimits` TypedDict

Tool-management methods on both classes: `add_tools`, `get_tools`,
`remove_tool`, `clear_tools`. Mount-management methods: `add_file_mounts`,
`get_file_mounts`, `remove_file_mount`, `clear_file_mounts`.

`MontyExecuteCodeTool` additionally exposes:
- `build_instructions(*, tools_visible_to_model: bool) -> str`
- `create_run_tool() -> MontyExecuteCodeTool`
- `build_serializable_state() -> dict[str, Any]`
- `workspace_root`, `resource_limits` properties

## Architecture

- **`_types.py`** — `FileMount`, `FileMountInput`, `MountMode` (public).
- **`_provider.py`** — `MontyCodeActProvider` (thin wrapper around the tool).
- **`_execute_code_tool.py`** — `MontyExecuteCodeTool` plus tool / mount
  normalization, approval helpers, dynamic `description`/`instructions`
  builders, and the post-execution file-capture flow that surfaces files
  written to `read-write` mounts as `Content.from_data` items.
- **`_monty_bridge.py`** — `InlineCodeBridge` and `generate_type_stubs`,
  adapted from the reference Monty CodeAct repo. Pauses on `FunctionSnapshot`
  to dispatch host calls, then resumes; supports direct typed tool calls,
  the `call_tool` fallback, `asyncio.gather` fan-out, and forwards
  ``mount`` / ``limits`` to `Monty(...).start(...)`.
- **`_instructions.py`** — dynamic instruction / tool-description builders
  (include filesystem capability summaries when mounts are configured).

## Not implemented (yet)

| Capability | Monty primitive | Status |
|------------|-----------------|--------|
| Custom virtual filesystem | `OSAccess` subclass passed to `Monty(...).start(os=...)` | Not exposed. Strictly more general than file mounts; useful when you want a fully synthetic FS. |
| Outbound URL allow-list | No Monty primitive — expose `fetch_url` as a host tool with the allow-list check in your tool function. | Not exposed in this package; users add it as a regular tool. |

## Out of scope (for now)

- **Durable execution** — the reference Monty CodeAct repo also offers a
  Durable-Functions-backed mode (`DurableCodeBridge`, `register_durable_codeact`,
  `wait_for_external_event`, per-tool approval via external events). That is
  intentionally not in this package yet.
