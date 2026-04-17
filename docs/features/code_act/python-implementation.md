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
- Developers can configure execution capabilities such as workspace mounts and outbound network allow lists in a portable way.

Success Metric:
- Python samples exist for both a tool-enabled CodeAct mode and a standard interpreter mode.

Implementation-free outcome:
- A Python developer can attach a backend-specific CodeAct provider, choose which tools are available inside CodeAct, and configure execution capabilities without rewriting the function invocation loop.

## What is the problem being solved?

The cross-SDK problem statement and decision rationale live in the [ADR](../../decisions/0024-codeact-integration.md). The items below narrow that statement to Python-specific design concerns:

- Today, the easiest way to prototype CodeAct is to infer or reshape the agent's direct tool surface, which is fragile and hard to reason about.
- In Python, inferring a CodeAct tool surface from generic agent tool configuration is fragile and hard to reason about.
- There is no first-class Python design that simultaneously covers Hyperlight-backed CodeAct now, future backend-specific providers such as Monty, and both tool-enabled and interpreter modes.
- Sandbox capabilities such as mounted file access and outbound network access need a portable configuration model instead of ad hoc backend-specific wiring.
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
- `get_allowed_domains() -> Sequence[AllowedDomain]`
- `remove_allowed_domain(...) -> None`
- `clear_allowed_domains() -> None`

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
- Allowed domains are keyed by normalized target string.
- `add_allowed_domains(...)` adds allow-list entries and replaces an existing entry when the same target is added again.
- `get_allowed_domains()` returns the current outbound allow-list entries.
- `remove_allowed_domain(...)` removes allow-list entries by target.
- `clear_allowed_domains()` removes all configured allow-list entries.
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

If one sensitive provider-owned tool causes `execute_code` to require approval more often than desired, the mitigation is to keep that tool direct-only or expose it through a different CodeAct provider/tool surface. The initial model does not try to infer whether generated code will actually call that tool before approval.

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
- In-memory interpreter state does not persist across separate `execute_code` calls.
- Configured workspace files, mounted files, and any writable artifact/output area are the supported persistence mechanism across calls when the backend exposes them.

### Python public API

#### Core types

```python
class FileMount(NamedTuple):
    host_path: str | Path
    mount_path: str

FileMountInput = str | tuple[str | Path, str] | FileMount


class AllowedDomain(NamedTuple):
    target: str
    methods: tuple[str, ...] | None = None


AllowedDomainInput = str | tuple[str, str | Sequence[str]] | AllowedDomain


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
        workspace_root: Path | None = None,
        file_mounts: Sequence[FileMountInput] = (),
        allowed_domains: Sequence[AllowedDomainInput] = (),
    ) -> None: ...

    def add_tools(self, tools: ToolTypes | Sequence[ToolTypes]) -> None: ...
    def get_tools(self) -> Sequence[ToolTypes]: ...
    def remove_tool(self, name: str) -> None: ...
    def clear_tools(self) -> None: ...
    def add_file_mounts(self, mounts: FileMountInput | Sequence[FileMountInput]) -> None: ...
    def get_file_mounts(self) -> Sequence[FileMount]: ...
    def remove_file_mount(self, mount_path: str) -> None: ...
    def clear_file_mounts(self) -> None: ...
    def add_allowed_domains(self, domains: AllowedDomainInput | Sequence[AllowedDomainInput]) -> None: ...
    def get_allowed_domains(self) -> Sequence[AllowedDomain]: ...
    def remove_allowed_domain(self, domain: str) -> None: ...
    def clear_allowed_domains(self) -> None: ...
```

`file_mounts` accepts three equivalent input forms:
- `"data/report.csv"` uses the same relative path on the host and in the sandbox.
- `("fixtures/users.json", "data/users.json")` or `(Path("fixtures/users.json"), "data/users.json")` uses distinct host and sandbox paths.
- `FileMount(Path("fixtures/users.json"), "data/users.json")` is the named-tuple form of the explicit pair.

`allowed_domains` accepts three equivalent input forms:
- `"github.com"` allows that target with all backend-supported methods.
- `("github.com", "GET")` or `("github.com", ["GET", "HEAD"])` uses an explicit per-target method list.
- `AllowedDomain("github.com", ("GET", "HEAD"))` is the named-tuple form of the explicit entry.

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

The Hyperlight package also depends on a small set of core hooks that must remain available from `agent-framework-core`:
- `ContextProvider.before_run(...)`
- `SessionContext.extend_instructions(...)`
- `SessionContext.extend_tools(...)`
- per-run runtime tool access via `SessionContext.options["tools"]`
- the shared `ApprovalMode` vocabulary used by `FunctionTool`

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

These steps run on every invocation rather than once at construction time because the provider supports CRUD mutations between runs, concurrent runs need independent snapshots, and the effective approval and instructions depend on the tool registry state captured at run start. When the tool registry and capability configuration are fixed for the lifetime of the agent, the manual wiring pattern (see `codeact_manual_wiring.py`) can be used instead, which passes the tool and instructions directly to the `Agent` constructor and avoids the per-run provider lifecycle entirely.

If the provider stores anything in `state`, that value must stay JSON-serializable.

Mutating the provider after `before_run(...)` has captured a run-scoped snapshot is allowed, but it affects subsequent runs only. Provider implementations should synchronize state capture and CRUD operations so shared provider instances remain safe across concurrent runs.

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
- `execute_code` should be traced like a normal tool invocation within the surrounding agent run, and provider-owned tool calls executed through `call_tool(...)` should continue to emit ordinary tool invocation telemetry.

#### Backend integration

Initial public provider:
- `HyperlightCodeActProvider`

Backend-specific notes:
- **Hyperlight**
  - Provider construction needs a guest artifact via `module`, which may be a packaged guest module name or a path to a compiled guest artifact.
  - File access maps naturally to Hyperlight Sandbox's read-only `/input` and writable `/output` capability model.
  - Network access is denied by default and is enabled through per-target allow-list entries.
- **Monty**
  - A future `MontyCodeActProvider` should be a separate public type rather than a `HyperlightCodeActProvider` mode.
  - Monty does not expose built-in filesystem or network access directly inside the interpreter.
  - File and URL access are mediated through host-provided external functions, so a Monty provider would need to translate provider settings into virtual files and allow-checked callbacks.
  - Monty setup may also include backend-specific inputs such as `script_name`, optional type-check stubs, or restored snapshots.

#### Capability handling

Capabilities are first-class `HyperlightCodeActProvider` init parameters and provider-managed CRUD surfaces:
- `workspace_root`
- `file_mounts`
- `allowed_domains`

Concrete providers should normalize these settings internally. Hyperlight can map them directly to sandbox capabilities, while Monty must enforce them through host-mediated file and network functions and may apply stricter URL-level checks than the public provider surface expresses.

Expected management split:
- `workspace_root` remains a direct configuration value on the provider,
- file mounts are managed through provider CRUD methods,
- outbound allow-list entries are managed through provider CRUD methods.

Enabling access means:
- Configuring `workspace_root` or any `file_mounts` enables the sandbox filesystem surface exposed through `/input` and `/output`.
- Leaving both `workspace_root` and `file_mounts` unset means no filesystem surface is configured.
- Adding any `allowed_domains` entry enables outbound access only for the configured targets; leaving it empty means network access is disabled without a separate `network_mode` flag.
- A string target allows all backend-supported methods for that target; an explicit tuple or `AllowedDomain` entry narrows the methods for that target.

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

Timeouts, out-of-memory conditions, backend crashes, and similar sandbox failures are all `execute_code` failures and should surface as structured error content. Partial textual or file outputs may be returned only when the backend can report them unambiguously; callers should not rely on partial-output recovery as a portable contract.

## E2E Code Samples

### Tool-enabled CodeAct mode

```python
codeact = HyperlightCodeActProvider(
    tools=[fetch_docs, query_data],
    workspace_root="./workdir",
    allowed_domains=[("api.github.com", "GET")],
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
codeact = HyperlightCodeActProvider(
    workspace_root="./data",
)

agent = Agent(
    client=client,
    name="interpreter",
    context_providers=[codeact],
)
```

### Manual static wiring (no per-run provider lifecycle)

When the tool registry and capability configuration are fixed, the provider lifecycle can be skipped entirely. Build the `execute_code` tool and instructions once and pass them directly to the agent:

```python
execute_code = HyperlightExecuteCodeTool(
    tools=[fetch_docs, query_data],
    workspace_root="./workdir",
    allowed_domains=[("api.github.com", "GET")],
    approval_mode="never_require",
)

codeact_instructions = execute_code.build_instructions(tools_visible_to_model=False)

agent = Agent(
    client=client,
    name="assistant",
    instructions=f"You are a helpful assistant.\n\n{codeact_instructions}",
    tools=[send_email, execute_code],
)
```
