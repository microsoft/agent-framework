# CodeAct .NET implementation

This document describes the .NET realization of the CodeAct design in
[`docs/decisions/0024-codeact-integration.md`](../../decisions/0024-codeact-integration.md).

This document is intentionally focused on the .NET design and public API surface.
The initial public .NET type described here is `HyperlightCodeActProvider`. Future .NET backends, such as Monty, should follow the same conceptual model with their own concrete provider types rather than through a public abstract base class or a public executor parameter.

## What is the goal of this feature?

Goals:
- .NET developers can enable CodeAct through an `AIContextProvider`-based integration.
- Developers can configure a provider-owned CodeAct tool set that is separate from the agent's direct tool surface.
- Developers can use the same `execute_code` concept for both tool-enabled CodeAct and a standard code interpreter tool implementation.
- Developers can swap execution backends over time, starting with Hyperlight while keeping room for alternatives.
- Developers can configure execution capabilities such as workspace mounts and outbound network allow lists in a portable way.

Success Metric:
- .NET samples exist for both a tool-enabled CodeAct mode and a standard interpreter mode.

Implementation-free outcome:
- A .NET developer can attach a backend-specific CodeAct provider, choose which tools are available inside CodeAct, and configure execution capabilities without rewriting the function invocation loop or ChatClient pipeline.

## What is the problem being solved?

The cross-SDK problem statement and decision rationale live in the [ADR](../../decisions/0024-codeact-integration.md). The items below narrow that statement to .NET-specific design concerns:

- Today, the easiest way to prototype CodeAct in .NET is to manually configure an `AIFunction` and wire instructions — this is fragile and requires understanding internal sandbox lifecycle details.
- There is no first-class .NET design that simultaneously covers Hyperlight-backed CodeAct now, future backend-specific providers, and both tool-enabled and interpreter modes.
- Sandbox capabilities such as mounted file access and outbound network access need a portable configuration model instead of ad hoc backend-specific wiring.
- Approval behavior needs to be explicit and configurable, mapping to .NET's existing `ApprovalRequiredAIFunction` wrapper mechanism.

## API Changes

### CodeAct contract

#### Terminology

- **CodeAct** is the primary term.
- `execute_code` is the model-facing tool name used by the initial .NET provider in this spec.
- Tool-enabled versus interpreter behavior is derived from the presence of CodeAct-managed tools, not from a separate public profile object.

#### Provider-owned CodeAct tool registry

A concrete .NET CodeAct provider owns the set of tools available through `call_tool(...)` inside CodeAct.

Rules:
- Only tools explicitly configured on the concrete provider instance are available inside CodeAct.
- The provider must not infer its CodeAct-managed tool set from the agent's direct tool configuration (`ChatClientAgentOptions.Tools` or `AIContext.Tools`).
- Exclusive versus mixed behavior is achieved by where tools are configured, not by rewriting the agent's direct tool list.

Implications:
- **CodeAct-only tool**: configured on the concrete CodeAct provider only.
- **Direct-only tool**: configured on the agent only.
- **Tool available both ways**: configured on both the agent and the concrete CodeAct provider.

#### Managing tools and capabilities after provider construction

There is no separate runtime setup object in the .NET design. CodeAct tools, file mounts, and outbound network allow-list state are managed directly on the provider through CRUD-style registry methods.

Preferred pattern:
- `AddTools(params AIFunction[] tools) -> void`
- `GetTools() -> IReadOnlyList<AIFunction>`
- `RemoveTools(params string[] names) -> void`
- `ClearTools() -> void`
- `AddFileMounts(params FileMount[] mounts) -> void`
- `GetFileMounts() -> IReadOnlyList<FileMount>`
- `RemoveFileMounts(params string[] mountPaths) -> void`
- `ClearFileMounts() -> void`
- `AddAllowedDomains(params AllowedDomain[] domains) -> void`
- `GetAllowedDomains() -> IReadOnlyList<AllowedDomain>`
- `RemoveAllowedDomains(params string[] targets) -> void`
- `ClearAllowedDomains() -> void`

Requirements:
- The provider-owned CodeAct tool registry is keyed by tool name (from `AIFunction.Name`).
- `AddTools(...)` adds new tools and replaces an existing provider-owned registration when the same tool name is added again.
- `GetTools()` returns the provider's current configured CodeAct tool registry.
- `RemoveTools(...)` removes provider-owned CodeAct tools by name.
- `ClearTools()` removes all provider-owned CodeAct tools.
- File mounts are keyed by sandbox mount path.
- `AddFileMounts(...)` adds new file mounts and replaces an existing mount when the same mount path is added again.
- `GetFileMounts()` returns the provider's current configured file mounts.
- `RemoveFileMounts(...)` removes file mounts by mount path.
- `ClearFileMounts()` removes all configured file mounts.
- Allowed domains are keyed by normalized target string.
- `AddAllowedDomains(...)` adds allow-list entries and replaces an existing entry when the same target is added again.
- `GetAllowedDomains()` returns the current outbound allow-list entries.
- `RemoveAllowedDomains(...)` removes allow-list entries by target.
- `ClearAllowedDomains()` removes all configured allow-list entries.
- Tool, file-mount, and network-allow-list mutations affect subsequent runs only; runs already in progress keep the snapshot captured at run start.
- The provider must snapshot its effective tool registry and capability state at the start of each run so concurrent execution remains deterministic.

#### Approval model

The initial .NET design follows the ADR's bundled approval decision and maps to the existing `ApprovalRequiredAIFunction` wrapper from `Microsoft.Extensions.AI.Abstractions`:

- The provider exposes a default `ApprovalMode` for `execute_code` (enum: `CodeActApprovalMode.AlwaysRequire` / `CodeActApprovalMode.NeverRequire`).

Effective `execute_code` approval is computed as follows:

- If the provider default is `AlwaysRequire`, `execute_code` requires approval.
- If the provider default is `NeverRequire`, the provider evaluates the provider-owned CodeAct tool registry snapshot for that run.
  - If every provider-owned CodeAct tool in that snapshot is not an `ApprovalRequiredAIFunction`, `execute_code` does not require approval.
  - If any provider-owned CodeAct tool in that snapshot is an `ApprovalRequiredAIFunction`, `execute_code` requires approval, even if the generated code may not call that tool.
- When the effective approval resolves to `AlwaysRequire`, the generated `execute_code` function is wrapped in `ApprovalRequiredAIFunction` before being added to the `AIContext.Tools`.
- Provider-owned tool calls made through `call_tool(...)` during that execution run use the approval already determined for `execute_code`.
- Direct-only agent tools are excluded from this calculation.
- File and network capabilities do not create a separate runtime approval check in the initial model; configuring them on the provider is itself the approval for those capabilities.

This is intentionally conservative and matches the shape of the existing .NET function-tool approval flow, where `ApprovalRequiredAIFunction` signals to the `ChatClientAgent` that user approval is needed before invocation.

#### Shared execution flow

On each run:
1. `ProvideAIContextAsync(...)` snapshots the current CodeAct-managed tool registry and capability settings.
2. Computes the effective approval requirement for `execute_code` from the provider default plus the snapshotted tool registry.
3. Builds provider-defined instructions.
4. Builds a run-scoped `execute_code` `AIFunction` from the snapshot (optionally wrapped in `ApprovalRequiredAIFunction`).
5. Returns an `AIContext` containing the instructions and `execute_code` tool.
6. When `execute_code` is invoked by the model, the run-scoped function creates or reuses an execution environment.
7. If the current provider mode exposes host tools, `call_tool(...)` is bound only to the provider-owned tool registry snapshot.
8. Code is executed and results converted to a JSON result string.

Caching rules:
- The Hyperlight backend supports snapshots: the provider caches a reusable clean snapshot after the first sandbox initialization.
- No mutable per-run execution state may be shared across concurrent runs.
- In-memory interpreter state does not persist across separate `execute_code` calls.
- Configured workspace files, mounted files, and any writable artifact/output area are the supported persistence mechanism across calls when the backend exposes them.

### .NET public API

#### Core types

```csharp
/// <summary>
/// Represents a host-to-sandbox file mount configuration.
/// </summary>
/// <param name="HostPath">Absolute or relative path on the host filesystem.</param>
/// <param name="MountPath">Path inside the sandbox (e.g. "/input/data.csv").</param>
public sealed record FileMount(string HostPath, string MountPath);

/// <summary>
/// Represents an outbound network allow-list entry.
/// </summary>
/// <param name="Target">URL or domain (e.g. "https://api.github.com").</param>
/// <param name="Methods">
/// Optional HTTP methods to allow (e.g. ["GET", "POST"]).
/// Null allows all methods supported by the backend.
/// </param>
public sealed record AllowedDomain(string Target, IReadOnlyList<string>? Methods = null);

/// <summary>
/// Controls the approval behavior for execute_code invocations.
/// </summary>
public enum CodeActApprovalMode
{
    /// <summary>execute_code always requires user approval.</summary>
    AlwaysRequire,

    /// <summary>
    /// Approval is derived from the provider-owned tool registry:
    /// if any tool is an ApprovalRequiredAIFunction, execute_code requires approval.
    /// </summary>
    NeverRequire,
}
```

#### HyperlightCodeActProvider

```csharp
/// <summary>
/// An AIContextProvider that enables CodeAct execution through the
/// Hyperlight sandbox backend.
/// </summary>
/// <remarks>
/// <para>
/// This provider injects an <c>execute_code</c> tool into the model-facing
/// tool surface and builds CodeAct guidance instructions. Guest code executed
/// through <c>execute_code</c> runs in an isolated Hyperlight sandbox with
/// snapshot/restore for clean state per invocation.
/// </para>
/// <para>
/// If no CodeAct-managed tools are configured, the provider uses
/// interpreter-style behavior. If one or more CodeAct-managed tools are
/// configured, the provider uses tool-enabled behavior and exposes
/// <c>call_tool(...)</c> inside the sandbox bound to the configured tools.
/// </para>
/// </remarks>
public sealed class HyperlightCodeActProvider : AIContextProvider, IDisposable
{
    /// <summary>
    /// Initializes a new HyperlightCodeActProvider.
    /// </summary>
    /// <param name="options">Configuration options for the provider.</param>
    public HyperlightCodeActProvider(HyperlightCodeActProviderOptions options);

    // ----- Tool registry -----

    /// <summary>Adds tools to the provider-owned CodeAct tool registry.</summary>
    public void AddTools(params AIFunction[] tools);

    /// <summary>Returns the current CodeAct-managed tools.</summary>
    public IReadOnlyList<AIFunction> GetTools();

    /// <summary>Removes tools by name from the CodeAct tool registry.</summary>
    public void RemoveTools(params string[] names);

    /// <summary>Removes all CodeAct-managed tools.</summary>
    public void ClearTools();

    // ----- File mounts -----

    /// <summary>Adds file mount configurations.</summary>
    public void AddFileMounts(params FileMount[] mounts);

    /// <summary>Returns the current file mount configurations.</summary>
    public IReadOnlyList<FileMount> GetFileMounts();

    /// <summary>Removes file mounts by sandbox mount path.</summary>
    public void RemoveFileMounts(params string[] mountPaths);

    /// <summary>Removes all file mount configurations.</summary>
    public void ClearFileMounts();

    // ----- Network allow-list -----

    /// <summary>Adds outbound network allow-list entries.</summary>
    public void AddAllowedDomains(params AllowedDomain[] domains);

    /// <summary>Returns the current outbound allow-list entries.</summary>
    public IReadOnlyList<AllowedDomain> GetAllowedDomains();

    /// <summary>Removes allow-list entries by target.</summary>
    public void RemoveAllowedDomains(params string[] targets);

    /// <summary>Removes all outbound allow-list entries.</summary>
    public void ClearAllowedDomains();

    // ----- Lifecycle -----

    /// <summary>Releases the sandbox and all associated native resources.</summary>
    public void Dispose();
}
```

#### HyperlightCodeActProviderOptions

```csharp
/// <summary>
/// Configuration options for <see cref="HyperlightCodeActProvider"/>.
/// </summary>
public sealed class HyperlightCodeActProviderOptions
{
    /// <summary>
    /// The sandbox backend to use. Default is <c>Wasm</c>.
    /// </summary>
    public SandboxBackend Backend { get; set; } = SandboxBackend.Wasm;

    /// <summary>
    /// Path to the guest module (.wasm or .aot file).
    /// Required for the Wasm backend; not needed for JavaScript.
    /// When null, the provider attempts to locate the default packaged
    /// Python guest module.
    /// </summary>
    public string? ModulePath { get; set; }

    /// <summary>
    /// Guest heap size. Accepts human-readable strings ("50Mi", "2Gi")
    /// or raw byte values. Null uses the backend default.
    /// </summary>
    public string? HeapSize { get; set; }

    /// <summary>
    /// Guest stack size. Accepts human-readable strings ("35Mi")
    /// or raw byte values. Null uses the backend default.
    /// </summary>
    public string? StackSize { get; set; }

    /// <summary>
    /// Initial set of CodeAct-managed tools available inside the sandbox.
    /// </summary>
    public IEnumerable<AIFunction>? Tools { get; set; }

    /// <summary>
    /// Default approval mode for the execute_code tool.
    /// Default is <see cref="CodeActApprovalMode.NeverRequire"/>.
    /// </summary>
    public CodeActApprovalMode ApprovalMode { get; set; } = CodeActApprovalMode.NeverRequire;

    /// <summary>
    /// Optional workspace root directory on the host.
    /// When set, it is exposed as the sandbox's input directory.
    /// </summary>
    public string? WorkspaceRoot { get; set; }

    /// <summary>
    /// Initial file mount configurations.
    /// </summary>
    public IEnumerable<FileMount>? FileMounts { get; set; }

    /// <summary>
    /// Initial outbound network allow-list entries.
    /// </summary>
    public IEnumerable<AllowedDomain>? AllowedDomains { get; set; }

    /// <summary>
    /// State key used to store provider state in AgentSession.StateBag.
    /// Defaults to "HyperlightCodeActProvider". Override when using
    /// multiple provider instances on the same agent.
    /// </summary>
    public string? StateKey { get; set; }
}
```

#### Provider implementation contract

The concrete provider plugs into the existing .NET `AIContextProvider` surface from `Microsoft.Agents.AI.Abstractions`.

Required override:
- `ProvideAIContextAsync(InvokingContext, CancellationToken) -> ValueTask<AIContext>`

`ProvideAIContextAsync(...)` is responsible for:
- snapshotting the current CodeAct-managed tool registry and capability settings for the run,
- computing the effective approval requirement for `execute_code` from the provider default and the snapshotted tool registry,
- building a short CodeAct guidance instruction string,
- building a run-scoped `execute_code` `AIFunction` from the snapshot,
- optionally wrapping it in `ApprovalRequiredAIFunction` when approval is required,
- and returning an `AIContext` with `Instructions` and `Tools` set.

These steps run on every invocation rather than once at construction time because the provider supports CRUD mutations between runs, concurrent runs need independent snapshots, and the effective approval and instructions depend on the tool registry state captured at run start.

The provider overrides `StateKeys` to return the configured `StateKey` from options, enabling multiple provider instances on the same agent without key collisions.

Mutating the provider after `ProvideAIContextAsync(...)` has captured a run-scoped snapshot is allowed, but it affects subsequent runs only. Provider implementations synchronize state capture and CRUD operations so shared provider instances remain safe across concurrent runs.

#### AIFunction-to-sandbox tool bridging

The Hyperlight sandbox's `RegisterTool(name, Func<string, string>)` accepts a synchronous JSON-in / JSON-out delegate. Provider-owned CodeAct tools are `AIFunction` instances that are async and cancellation-aware.

Bridging strategy:
- At sandbox initialization time, the provider registers each CodeAct-managed tool with the sandbox using the raw JSON overload: `RegisterTool(name, Func<string, string>)`.
- When the sandbox guest calls `call_tool("name", ...)`, the bridge delegate:
  1. Deserializes the JSON arguments.
  2. Invokes `AIFunction.InvokeAsync(...)` synchronously (via `GetAwaiter().GetResult()`) since the sandbox FFI callback is inherently synchronous.
  3. Serializes the result back to JSON.
- This sync-over-async bridge is a known pragmatic trade-off constrained by the Hyperlight FFI boundary. It is safe because:
  - Sandbox execution already runs on the thread pool (via `Task.Run`).
  - The FFI callback runs on a worker thread with no synchronization context.
- If the Hyperlight .NET SDK later adds async tool registration, the bridge should migrate to that.

#### Runtime behavior

- `ProvideAIContextAsync(...)` adds a short CodeAct guidance block through `AIContext.Instructions`.
- `ProvideAIContextAsync(...)` adds `execute_code` through `AIContext.Tools`.
- The detailed `call_tool(...)`, sandbox-tool, and capability guidance is carried by the `execute_code` function's `Description`.
- `execute_code` invokes the configured Hyperlight sandbox guest.
- If the current CodeAct tool registry snapshot is non-empty, the runtime injects `call_tool(...)` bound to the provider-owned tool registry.
- The provider does not inspect or mutate the agent's `ChatClientAgentOptions.Tools` or the incoming `AIContext.Tools` to determine its CodeAct tool set.
- The provider snapshots the current CodeAct tool registry and capability state at run start, so later registry and allow-list mutations only affect future runs.
- Interpreter versus tool-enabled behavior is derived from the presence of CodeAct-managed tools.
- `execute_code` is traced like a normal tool invocation within the surrounding agent run.

#### Backend integration

Initial public provider:
- `HyperlightCodeActProvider`

Backend-specific notes:
- **Hyperlight**
  - The provider internally creates a `SandboxBuilder` from the options and uses the `Sandbox` API from `HyperlightSandbox.Api`.
  - The provider uses snapshot/restore to ensure clean execution state per `execute_code` invocation: a "warm" snapshot is taken after the first no-op initialization run, and restored before each subsequent execution.
  - File access maps to Hyperlight Sandbox's `WithInputDir()` / `WithOutputDir()` / `WithTempOutput()` capability model.
  - Network access is denied by default and is enabled through `Sandbox.AllowDomain(...)` per-target allow-list entries.
  - Guest module resolution: if `ModulePath` is null for the Wasm backend, the provider attempts to locate a packaged Python guest module (equivalent to the Python SDK's `python_guest.path` resolution).

#### Capability handling

Capabilities are first-class `HyperlightCodeActProviderOptions` properties and provider-managed CRUD surfaces:
- `WorkspaceRoot`
- `FileMounts`
- `AllowedDomains`

Enabling access means:
- Configuring `WorkspaceRoot` or any `FileMounts` enables the sandbox filesystem surface exposed through `/input` and `/output`.
- Leaving both `WorkspaceRoot` and `FileMounts` unset means no filesystem surface is configured.
- Adding any `AllowedDomains` entry enables outbound access only for the configured targets; leaving it empty means network access is disabled without a separate network mode flag.

Backends may implement stricter semantics than these top-level settings.

#### Execution output representation

Backend execution output maps to a JSON result string returned from the `execute_code` `AIFunction`:

```json
{
  "stdout": "Hello world\n",
  "stderr": "",
  "exit_code": 0,
  "success": true
}
```

Execution failures should surface readable error text in the `stderr` field and a non-zero `exit_code`. Timeouts, out-of-memory conditions, backend crashes, and similar sandbox failures are all `execute_code` failures and should surface as structured error results. Partial textual or file outputs may be returned only when the backend can report them unambiguously.

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

#### Thread safety and concurrency

- All CRUD methods (`AddTools`, `RemoveTools`, `AddFileMounts`, etc.) are synchronized via an internal lock.
- `ProvideAIContextAsync(...)` acquires the lock to snapshot current state, then releases it before building the run-scoped function. The run-scoped function closes over the immutable snapshot, not mutable provider state.
- Concurrent `execute_code` invocations from different runs use independent sandbox instances or synchronized access to a shared sandbox with snapshot/restore.
- Workspace directories (`WorkspaceRoot`, `FileMounts`) are external shared state: concurrent runs against the same workspace can race on files. This is the user's responsibility to manage (e.g., by using per-run output directories or separate provider instances).

### HyperlightExecuteCodeFunction

The provider package also exports a standalone `HyperlightExecuteCodeFunction` for direct-tool scenarios where a provider lifecycle is not needed. This is the .NET equivalent of the Python `HyperlightExecuteCodeTool`.

```csharp
/// <summary>
/// A standalone execute_code AIFunction backed by a Hyperlight sandbox.
/// Use this for manual/static wiring when the AIContextProvider lifecycle
/// is not needed.
/// </summary>
public sealed class HyperlightExecuteCodeFunction : IDisposable
{
    /// <summary>
    /// Creates a new standalone code execution function.
    /// </summary>
    /// <param name="options">Configuration options.</param>
    public HyperlightExecuteCodeFunction(HyperlightCodeActProviderOptions options);

    /// <summary>
    /// Returns this as an AIFunction for direct registration on an agent.
    /// When approval is required, the returned function is wrapped in
    /// ApprovalRequiredAIFunction.
    /// </summary>
    public AIFunction AsAIFunction();

    /// <summary>
    /// Builds a CodeAct instruction string describing the available
    /// tools and capabilities.
    /// </summary>
    /// <param name="toolsVisibleToModel">
    /// When false, the instructions include full tool descriptions
    /// (for use when tools are only accessible through CodeAct).
    /// When true, instructions are abbreviated (tools are already
    /// visible to the model as direct tools).
    /// </param>
    public string BuildInstructions(bool toolsVisibleToModel = false);

    /// <summary>Releases sandbox resources.</summary>
    public void Dispose();
}
```

### Internal implementation structure

The provider and standalone function share internal helpers:

```
Microsoft.Agents.AI.Hyperlight/
├── HyperlightCodeActProvider.cs        // AIContextProvider implementation
├── HyperlightCodeActProviderOptions.cs // Options record
├── HyperlightExecuteCodeFunction.cs    // Standalone AIFunction for manual wiring
├── FileMount.cs                        // File mount record
├── AllowedDomain.cs                    // Network allow-list record
├── CodeActApprovalMode.cs              // Approval enum
├── Internal/
│   ├── SandboxExecutor.cs              // Manages sandbox lifecycle, snapshot/restore
│   ├── InstructionBuilder.cs           // Builds CodeAct instruction strings
│   └── ToolBridge.cs                   // AIFunction ↔ Sandbox.RegisterTool adapter
```

`SandboxExecutor` encapsulates:
- Creating and configuring a `Sandbox` from options.
- Performing the initial no-op warm-up and snapshot.
- Registering bridged tools via `ToolBridge`.
- Restoring to the clean snapshot before each execution.
- Translating `ExecutionResult` to a JSON string.

`InstructionBuilder` generates:
- A short CodeAct guidance block for `AIContext.Instructions`.
- A detailed `execute_code` description including `call_tool(...)` signatures and capability documentation.

`ToolBridge` handles:
- Reflecting `AIFunction` metadata to build the sandbox tool registration.
- The sync-over-async invocation bridge.

## E2E Code Samples

### Tool-enabled CodeAct mode

```csharp
var fetchDocs = AIFunctionFactory.Create(FetchDocs, name: "fetch_docs");
var queryData = AIFunctionFactory.Create(QueryData, name: "query_data");
var lookupUser = AIFunctionFactory.Create(LookupUser, name: "lookup_user");

var codeact = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions
{
    Tools = [fetchDocs, queryData],
    WorkspaceRoot = "./workdir",
    AllowedDomains = [new AllowedDomain("api.github.com", ["GET"])],
});
codeact.AddTools(lookupUser);

var sendEmail = AIFunctionFactory.Create(SendEmail, name: "send_email");

var agent = chatClient.AsAIAgent(
    instructions: "You are a helpful assistant.",
    options: new ChatClientAgentOptions
    {
        Tools = [sendEmail],  // direct-only tool
        AIContextProviders = [codeact],
    });

await using var session = await agent.CreateSessionAsync();
var response = await agent.InvokeAsync("Analyze the latest docs", session);
```

### Standard code interpreter mode

```csharp
var codeact = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions
{
    WorkspaceRoot = "./data",
});

var agent = chatClient.AsAIAgent(
    instructions: "You are a code interpreter.",
    options: new ChatClientAgentOptions
    {
        AIContextProviders = [codeact],
    });
```

### Manual static wiring (no provider lifecycle)

When the tool registry and capability configuration are fixed, the provider lifecycle can be skipped entirely. Build the `execute_code` function and instructions once and pass them directly to the agent:

```csharp
using var executeCode = new HyperlightExecuteCodeFunction(
    new HyperlightCodeActProviderOptions
    {
        Tools = [fetchDocs, queryData],
        WorkspaceRoot = "./workdir",
        AllowedDomains = [new AllowedDomain("api.github.com", ["GET"])],
    });

var codeactInstructions = executeCode.BuildInstructions(toolsVisibleToModel: false);

var agent = chatClient.AsAIAgent(
    instructions: $"You are a helpful assistant.\n\n{codeactInstructions}",
    options: new ChatClientAgentOptions
    {
        Tools = [sendEmail, executeCode.AsAIFunction()],
    });
```

### With approval required

```csharp
var sensitiveAction = new ApprovalRequiredAIFunction(
    AIFunctionFactory.Create(DeleteRecords, name: "delete_records"));

var codeact = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions
{
    Tools = [fetchDocs, sensitiveAction],  // sensitiveAction triggers approval
});

// execute_code will be wrapped in ApprovalRequiredAIFunction because
// at least one managed tool (delete_records) requires approval.
var agent = chatClient.AsAIAgent(
    instructions: "You are a helpful assistant.",
    options: new ChatClientAgentOptions
    {
        AIContextProviders = [codeact],
    });
```

## Relationship to hyperlight-sandbox .NET SDK

This design depends on the .NET SDK being added in [hyperlight-dev/hyperlight-sandbox#46](https://github.com/hyperlight-dev/hyperlight-sandbox/pull/46). Key types consumed from that SDK:

| hyperlight-sandbox type | Used for |
|---|---|
| `Sandbox` | Core sandbox lifecycle: `Run()`, `RegisterTool()`, `AllowDomain()`, `Snapshot()`, `Restore()` |
| `SandboxBuilder` | Fluent sandbox construction from provider options |
| `SandboxBackend` | Backend selection (Wasm, JavaScript) |
| `ExecutionResult` | Capturing stdout, stderr, exit code from guest execution |
| `SandboxSnapshot` | Checkpoint/restore for clean state per execution |

The provider package (`Microsoft.Agents.AI.Hyperlight`) takes a NuGet dependency on `Hyperlight.HyperlightSandbox.Api` and `Microsoft.Extensions.AI.Abstractions`. It does **not** depend on `HyperlightSandbox.Extensions.AI` (`CodeExecutionTool`) — the provider implements its own sandbox lifecycle management with run-scoped snapshots to support concurrent invocations safely.

## Package structure

The CodeAct Hyperlight provider ships as an optional NuGet package:
- **Package**: `Microsoft.Agents.AI.Hyperlight`
- **Dependencies**:
  - `Microsoft.Agents.AI.Abstractions` (for `AIContextProvider`, `AIContext`)
  - `Microsoft.Extensions.AI.Abstractions` (for `AIFunction`, `ApprovalRequiredAIFunction`)
  - `Hyperlight.HyperlightSandbox.Api` (for sandbox API)
- **Target framework**: `net8.0`

This keeps CodeAct and its native sandbox dependencies optional — users who do not need CodeAct do not take on the Hyperlight installation and dependency footprint.

## Open questions

1. **Guest module distribution**: How should the default Python guest module (`.aot` file) be distributed for .NET consumers? Options include a separate NuGet package with native assets, a runtime download, or requiring users to build/provide their own.
2. **Async tool registration**: If the Hyperlight .NET SDK adds async tool callback support in a future release, the sync-over-async bridge should be replaced. This is tracked as a known technical debt item.
3. **Output file access**: The Hyperlight sandbox exposes `GetOutputFiles()` and `OutputPath` for retrieving files written by guest code. The initial design returns these as part of the JSON result. A future iteration could surface output files as framework-native content (e.g., `DataContent` or URI references).
4. **Multiple sandbox instances for concurrency**: The current design uses synchronized access to a single sandbox with snapshot/restore. An alternative pooling strategy (one sandbox per concurrent run) could improve throughput at the cost of memory. This is deferred to implementation time.
