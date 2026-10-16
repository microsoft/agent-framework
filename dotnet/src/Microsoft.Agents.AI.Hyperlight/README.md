# Microsoft.Agents.AI.Hyperlight

First-class [CodeAct](../../../docs/decisions/0038-codeact-integration.md)
support for the Microsoft Agent Framework, backed by the
[Hyperlight](https://github.com/hyperlight-dev/hyperlight) VM-isolated sandbox.

The package exposes two entry points:

* **`HyperlightCodeActProvider`** — an `AIContextProvider` that injects an
  `execute_code` tool and CodeAct guidance into every agent invocation. Only
  one `HyperlightCodeActProvider` may be attached to a given agent; it
  enforces this through a fixed `StateKeys` value so `ChatClientAgent`'s
  state-key uniqueness validation rejects duplicate registrations.
* **`HyperlightExecuteCodeFunction`** — a standalone `AIFunction` for
  static/manual wiring when the sandbox configuration is fixed for the
  agent's lifetime.

Both surfaces support:

* Provider-owned tools exposed inside the sandbox via `call_tool(...)`
  (multiple allowed).
* Opt-in filesystem mounts and outbound network allow-list.
* `CodeActApprovalMode` control: `NeverRequire` (default; approval propagates
  from tools wrapped in `ApprovalRequiredAIFunction`) and `AlwaysRequire`.
* Snapshot/restore per run so the guest starts from a known clean state
  every invocation.

## Host tool parameter schemas

The `execute_code` description lists each provider-owned tool with its existing
`AIFunction.JsonSchema`, so the model can see parameter names, requiredness,
descriptions, enums, and nested shapes and call `call_tool(...)` correctly.
Tools that do not describe their input are listed by name only.

Two things to keep in mind:

* Parameter names, descriptions, defaults, and enum values are **model-visible**.
  Do not put credentials, tenant identifiers, or other secrets in them.
* C# enums serialize as integers by default, so their member names do not reach
  the schema. Apply `JsonStringEnumConverter` to the enum if the model should see
  the allowed values.

This does not change `execute_code`'s own input schema, which remains the single
`code` parameter.

## Requirements

* The `Hyperlight.HyperlightSandbox.Api` NuGet package, published from the
  `src/sdk/dotnet` SDK in [hyperlight-dev/hyperlight-sandbox](https://github.com/hyperlight-dev/hyperlight-sandbox)
  (the .NET API was added in [PR #46](https://github.com/hyperlight-dev/hyperlight-sandbox/pull/46),
  now merged). Until the package is published to nuget.org the project
  restore will fail; this project is intentionally `IsPackable=false` in
  the meantime.
* A Hyperlight Python guest module when using `SandboxBackend.Wasm`.

## Network access and guest packages

`HyperlightCodeActProviderOptions.AllowedDomains` controls outbound requests
from the sandbox. It does not install guest packages or expose host-installed
dependencies to guest code.

`CreateForWasm(modulePath)` selects an existing `.wasm` or `.aot` guest module;
it does not build a guest or install Python packages. The Agent Framework
integration does not provide a custom guest build or package installation
workflow. Package availability depends on the selected module and backend;
the default JavaScript backend does not run Python code.

For operations requiring application dependencies or external APIs, register
an `AIFunction` in `Tools` and invoke it from the guest with `call_tool(...)`.
Keep credentials and authorization in the host function. These functions run
outside the guest, so `AllowedDomains` does not restrict their network requests;
enforce any required destination policy in the host function.

## Status

Preview. API may change until the underlying Hyperlight SDK reaches a stable
release.
