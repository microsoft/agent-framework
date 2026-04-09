# CodeAct Python implementation

This document describes the Python realization of the CodeAct design in
[`docs/decisions/0024-codeact-integration.md`](../../decisions/0024-codeact-integration.md).

This document is intentionally focused on the Python design and public API surface.
The initial public Python type described here is `HyperlightCodeActProvider`. Future Python backends, such as Monty, should follow the same conceptual model with their own concrete provider types rather than through a public abstract base class or a public executor parameter.

## What is the goal of this feature?

Goals:
- Python developers can enable CodeAct through a `ContextProvider`-based integration.
- Developers can configure a provider-owned CodeAct tool set that is separate from the agent's direct `tools=` surface.
- Developers can use the same `execute_code` concept for both tool-enabled CodeAct and a standard code interpreter tool implementation.
- Developers can swap execution backends over time, starting with Hyperlight while keeping room for alternatives such as Pydantic's Monty.
- Developers can configure execution capabilities such as file access, workspace mounts, and outbound network allow lists in a portable way.

Success Metric:
- Python samples exist for both a tool-enabled CodeAct mode and a standard interpreter mode.

Implementation-free outcome:
- A Python developer can attach a backend-specific CodeAct provider, choose which tools are available inside CodeAct, and configure execution capabilities without rewriting the function invocation loop.

## What is the problem being solved?

- Today, the easiest way to prototype CodeAct is to infer or reshape the agent's direct tool surface, which is fragile and hard to reason about.
- In Python, inferring a CodeAct tool surface from generic agent tool configuration is fragile and hard to reason about.
- There is no first-class Python design that simultaneously covers Hyperlight-backed CodeAct now, future backend-specific providers such as Monty, and both tool-enabled and interpreter modes.
- Sandbox capabilities such as file access and network access need a portable configuration model instead of ad hoc backend-specific wiring.
- Approval behavior needs to be explicit and configurable, especially when CodeAct and direct tool calling may both be available.

## API Changes

### CodeAct contract

#### Terminology

- **CodeAct** is the primary term.
- **Code mode**, **codemode**, and **programmatic tool calling** refer to the same concept in this document.
- `execute_code` is the model-facing tool name used by the initial Python providers in this spec.

#### Provider-owned CodeAct tool registry

A concrete Python CodeAct provider owns the set of tools available through `call_tool(...)` inside CodeAct.

Rules:
- Only tools explicitly configured on the concrete provider instance are available inside CodeAct.
- The provider must not infer its CodeAct-managed tool set from the agent's direct `tools=` configuration.
- Exclusive versus mixed behavior is achieved by where tools are configured, not by rewriting the agent's direct tool list.

Implications:
- **CodeAct-only tool**: configured on the concrete CodeAct provider only.
- **Direct-only tool**: configured on the agent only.
- **Tool available both ways**: configured on both the agent and the concrete CodeAct provider.

#### Managing tools and capabilities after provider construction

There is no separate runtime setup object in the Python design. CodeAct tools, file mounts, and outbound network allow-list state are managed directly on the provider through CRUD-style registry methods.

Preferred pattern:
- `add_tools(...) -> None`
- `get_tools() -> Sequence[ToolTypes]`
- `remove_tool(...) -> None`
- `clear_tools() -> None`
- `add_file_mounts(...) -> None`
- `get_file_mounts() -> Sequence[FileMount]`
- `remove_file_mount(...) -> None`
- `clear_file_mounts() -> None`
- `add_allowed_domains(...) -> None`
- `get_allowed_domains() -> Sequence[str]`
- `remove_allowed_domain(...) -> None`
- `clear_allowed_domains() -> None`
- `add_allowed_http_methods(...) -> None`
- `get_allowed_http_methods() -> Sequence[str]`
- `remove_allowed_http_method(...) -> None`
- `clear_allowed_http_methods() -> None`

Requirements:
- The provider-owned CodeAct tool registry is keyed by tool name.
- `add_tools(...)` adds new tools and replaces an existing provider-owned registration when the same tool name is added again.
- `get_tools()` returns the provider's current configured CodeAct tool registry.
- `remove_tool(...)` removes provider-owned CodeAct tools by name.
- `clear_tools()` removes all provider-owned CodeAct tools.
- File mounts are keyed by sandbox mount path.
- `add_file_mounts(...)` adds new file mounts and replaces an existing mount when the same mount path is added again.
- `get_file_mounts()` returns the provider's current configured file mounts.
- `remove_file_mount(...)` removes file mounts by mount path.
- `clear_file_mounts()` removes all configured file mounts.
- Allowed domains are keyed by normalized domain string.
- `add_allowed_domains(...)` adds domains to the outbound allow list.
- `get_allowed_domains()` returns the current outbound domain allow list.
- `remove_allowed_domain(...)` removes domains from the outbound allow list.
- `clear_allowed_domains()` removes all configured allowed domains.
- Allowed HTTP methods are keyed by normalized method name.
- `add_allowed_http_methods(...)` adds methods to the outbound method allow list.
- `get_allowed_http_methods()` returns the current outbound method allow list.
- `remove_allowed_http_method(...)` removes methods from the outbound method allow list.
- `clear_allowed_http_methods()` removes all configured allowed HTTP methods.
- Tool, file-mount, and network-allow-list mutations affect subsequent runs only; runs already in progress keep the snapshot captured at run start.
- The provider must snapshot its effective tool registry and capability state at the start of each run so concurrent execution remains deterministic.

#### Approval model

The initial Python design follows the ADR's initial approval decision and reuses the existing tool approval vocabulary from `agent_framework._tools`:

- `approval_mode="always_require"`
- `approval_mode="never_require"`

The provider exposes a default `approval_mode` for `execute_code`.

Effective `execute_code` approval is computed as follows:

- If the provider default is `always_require`, `execute_code` requires approval.
- If the provider default is `never_require`, the provider evaluates the provider-owned CodeAct tool registry snapshot for that run.
- If every provider-owned CodeAct tool in that snapshot is `never_require`, `execute_code` is `never_require`.
- If any provider-owned CodeAct tool in that snapshot is `always_require`, `execute_code` is `always_require`, even if the generated code may not call that tool.
- Provider-owned tool calls made through `call_tool(...)` during that execution run use the approval already determined for `execute_code`.
- Direct-only agent tools are excluded from this calculation.
- File and network capabilities do not create a separate runtime approval check in the initial model; configuring them on the provider, including adding file mounts or outbound network allow-list entries, is itself the approval for those capabilities.

This is intentionally conservative and matches the shape of the current function-tool approval flow, where `FunctionTool` uses `always_require` / `never_require` and the auto-invocation loop escalates the whole batch if any called tool requires approval.

If the framework later standardizes pre-execution inspection or nested per-tool approvals, the Python provider surface can grow to expose that explicitly. The initial design does not assume that those extra modes are required.

#### Shared execution flow

On each run:
1. Resolve the provider's backend/runtime behavior, capabilities, provider default `approval_mode`, and provider-owned tool registry.
2. Compute the effective approval requirement for `execute_code` from the provider default plus the provider-owned tool registry snapshot.
3. Build provider-defined instructions.
4. Add `execute_code` to the model-facing tool surface.
5. Invoke the underlying model.
6. When `execute_code` is called, create or reuse an execution environment keyed by provider type, backend setup identity, capability configuration, and provider-owned tool signature.
7. If the current provider mode exposes host tools, expose `call_tool(...)` bound only to the provider-owned tool registry.
8. Execute code and convert results to framework-native content objects.

Caching rules:
- Backends that support snapshots may cache a reusable clean snapshot.
- Backends that do not support snapshots may still cache warm initialization artifacts.
- No mutable per-run execution state may be shared across concurrent runs.

### Python public API

#### Core types

```python
@dataclass(frozen=True)
class FileMount:
    host_path: str | Path
    mount_path: str


class HyperlightCodeActProvider(ContextProvider):
    def __init__(
        self,
        source_id: str = "hyperlight_codeact",
        *,
        backend: str = "wasm",
        module: str | None = "python_guest.path",
        module_path: str | None = None,
        tools: ToolTypes | None = None,
        approval_mode: Literal["always_require", "never_require"] = "never_require",
        filesystem_mode: Literal["none", "read_only", "read_write"] = "none",
        workspace_root: Path | None = None,
        file_mounts: Sequence[FileMount] = (),
        network_mode: Literal["none", "allow_list"] = "none",
        allowed_domains: Sequence[str] = (),
        allowed_http_methods: Sequence[str] = (),
    ) -> None: ...

    def add_tools(self, tools: ToolTypes | Sequence[ToolTypes]) -> None: ...
    def get_tools(self) -> Sequence[ToolTypes]: ...
    def remove_tool(self, name: str) -> None: ...
    def clear_tools(self) -> None: ...
    def add_file_mounts(self, mounts: FileMount | Sequence[FileMount]) -> None: ...
    def get_file_mounts(self) -> Sequence[FileMount]: ...
    def remove_file_mount(self, mount_path: str) -> None: ...
    def clear_file_mounts(self) -> None: ...
    def add_allowed_domains(self, domains: str | Sequence[str]) -> None: ...
    def get_allowed_domains(self) -> Sequence[str]: ...
    def remove_allowed_domain(self, domain: str) -> None: ...
    def clear_allowed_domains(self) -> None: ...
    def add_allowed_http_methods(self, methods: str | Sequence[str]) -> None: ...
    def get_allowed_http_methods(self) -> Sequence[str]: ...
    def remove_allowed_http_method(self, method: str) -> None: ...
    def clear_allowed_http_methods(self) -> None: ...
```

No public abstract `CodeActContextProvider` base or public `executor=` parameter is required for the initial Python API.

The initial alpha package also exports a standalone `HyperlightExecuteCodeTool`
for direct-tool scenarios where a provider is not needed. That standalone tool
should advertise `call_tool(...)`, the registered sandbox tools, and capability
state through its own `description` rather than requiring separate agent
instructions.

Provider modes:
- If no CodeAct-managed tools are configured, `HyperlightCodeActProvider` uses interpreter-style behavior.
- If one or more CodeAct-managed tools are configured, `HyperlightCodeActProvider` uses tool-enabled behavior.

#### Python provider implementation contract

The concrete provider plugs into the existing Python `ContextProvider` surface from `agent_framework._sessions`.

Required lifecycle hook:
- `before_run(*, agent, session, context, state) -> None`

Optional lifecycle hook:
- `after_run(*, agent, session, context, state) -> None`

`before_run(...)` is responsible for:
- snapshotting the current CodeAct-managed tool registry and capability settings for the run,
- computing the effective approval requirement for `execute_code` from the provider default and the snapshotted tool registry,
- adding a short CodeAct guidance block,
- adding `execute_code` to the run through `SessionContext.extend_tools(...)`,
- and wiring any backend-specific execution state needed for the run.

If the provider stores anything in `state`, that value must stay JSON-serializable.

`after_run(...)` is responsible for any backend-specific cleanup or post-processing that must happen after the model invocation completes.

If shared internal helpers are introduced later for multiple concrete providers, they should standardize responsibilities for:
- building instructions,
- computing effective approval,
- configuring file access,
- configuring network access,
- preparing or restoring execution state,
- executing code,
- and converting backend output into framework-native `Content`.

#### Runtime behavior

- `before_run(...)` adds a short CodeAct guidance block through `SessionContext.extend_instructions(...)`.
- `before_run(...)` adds `execute_code` through `SessionContext.extend_tools(...)`.
- The detailed `call_tool(...)`, sandbox-tool, and capability guidance is carried by `execute_code.description`.
- `execute_code` invokes the configured Hyperlight sandbox guest.
- If the current CodeAct tool registry is non-empty, the runtime injects `call_tool(...)` bound to the provider-owned tool registry.
- The provider does not inspect or mutate `Agent.default_options["tools"]` or `context.options["tools"]` to determine its CodeAct tool set.
- The provider snapshots the current CodeAct tool registry and capability state at run start, so later registry and allow-list mutations only affect future runs.
- Interpreter versus tool-enabled behavior is derived from the concrete provider and the presence of CodeAct-managed tools, not from a separate public profile object.

#### Backend integration

Initial public provider:
- `HyperlightCodeActProvider`

Backend-specific notes:
- **Hyperlight**
  - Provider construction needs a guest artifact via `module`, which may be a packaged guest module name or a path to a compiled guest artifact.
  - File access maps naturally to Hyperlight Sandbox's read-only `/input` and writable `/output` capability model.
  - Network access is denied by default and is enabled through allow-listed domains plus HTTP verbs.
- **Monty**
  - A future `MontyCodeActProvider` should be a separate public type rather than a `HyperlightCodeActProvider` mode.
  - Monty does not expose built-in filesystem or network access directly inside the interpreter.
  - File and URL access are mediated through host-provided external functions, so a Monty provider would need to translate provider settings into virtual files and allow-checked callbacks.
  - Monty setup may also include backend-specific inputs such as `script_name`, optional type-check stubs, or restored snapshots.

#### Capability handling

Capabilities are first-class `HyperlightCodeActProvider` init parameters and, for collection-shaped state, provider-managed CRUD surfaces:
- `filesystem_mode`
- `workspace_root`
- `file_mounts`
- `network_mode`
- `allowed_domains`
- `allowed_http_methods`

Concrete providers should normalize these settings internally. Hyperlight can map them directly to sandbox capabilities, while Monty must enforce them through host-mediated file and network functions and may apply stricter URL-level checks than the public provider surface expresses.

Expected management split:
- scalar policy settings such as `filesystem_mode`, `workspace_root`, and `network_mode` remain direct configuration values on the provider,
- file mounts are managed through provider CRUD methods,
- outbound domains are managed through provider CRUD methods,
- outbound HTTP methods are managed through provider CRUD methods.

Enabling access means:
- `filesystem_mode="none"` disables file access from sandboxed code.
- `filesystem_mode="read_only"` or `"read_write"` enables file access within the mounted/workspace surface exposed by the provider.
- `network_mode="none"` disables outbound network access.
- `network_mode="allow_list"` enables outbound access only for the configured `allowed_domains` and `allowed_http_methods`.

Backends may implement stricter semantics than these top-level settings. For example, Hyperlight naturally maps file access to `/input` and `/output`, while Monty would enforce equivalent policy through host-provided callbacks rather than direct interpreter I/O.

#### Execution output representation

Backend execution output should be translated into existing AF `Content` values rather than a custom `CodeActExecutionResult` type.

Use the existing content model from `agent_framework._types`, for example:
- `Content.from_code_interpreter_tool_result(outputs=[...])` to surface the overall result of sandboxed code execution,
- `Content.from_text(...)` for plain textual output,
- `Content.from_data(...)` or `Content.from_uri(...)` for generated files or binary artifacts,
- `Content.from_error(...)` for execution failures,
- and `Content.from_function_result(..., result=list[Content])` when surfacing the final result of `execute_code` through the normal tool result path.

#### `execute_code` input contract

```json
{
  "type": "object",
  "properties": {
    "code": {
      "type": "string",
      "description": "Code to execute using the provider's configured backend/runtime behavior."
    }
  },
  "required": ["code"]
}
```

Execution failures should surface readable error text and structured error `Content`, not a custom backend result object.

## E2E Code Samples

### Tool-enabled CodeAct mode

```python
codeact = HyperlightCodeActProvider(
    tools=[fetch_docs, query_data],
    filesystem_mode="read_write",
    workspace_root="./workdir",
    network_mode="allow_list",
    allowed_domains=["api.github.com"],
    allowed_http_methods=["GET"],
)
codeact.add_tools([lookup_user])

agent = Agent(
    client=client,
    name="assistant",
    tools=[send_email],  # direct-only tool
    context_providers=[codeact],
)
```

### Standard code interpreter mode

```python
code_interpreter = HyperlightCodeActProvider(
    filesystem_mode="read_only",
    workspace_root="./data",
    network_mode="none",
)

agent = Agent(
    client=client,
    name="interpreter",
    context_providers=[code_interpreter],
)
```
