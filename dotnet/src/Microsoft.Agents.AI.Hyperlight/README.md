# Microsoft.Agents.AI.Hyperlight

First-class [CodeAct](../../../docs/decisions/0024-hyperlight-codeact-integration.md)
support for the Microsoft Agent Framework, backed by the
[Hyperlight](https://github.com/hyperlight-dev/hyperlight) VM-isolated sandbox.

The package exposes two entry points:

* **`HyperlightCodeActProvider`** — an `AIContextProvider` that injects an
  `execute_code` tool and CodeAct guidance into every agent invocation. Only
  one `HyperlightCodeActProvider` may be attached to a given agent; it
  enforces this through a fixed `StateKeys` value so `ChatClientAgent`'s
  state-key uniqueness validation rejects duplicate registrations.
* **`HyperlightExecuteCodeFunction`** — a standalone `AIFunction` wrapper for
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

## Requirements

* A published `HyperlightSandbox.Api` NuGet package (`0.1.0-preview` per
  [hyperlight-sandbox PR #46](https://github.com/hyperlight-dev/hyperlight-sandbox/pull/46)).
  Until this package is available on nuget.org the project restores will
  fail; the package is intentionally `IsPackable=false` in this state.
* A Hyperlight Python guest module when using `SandboxBackend.Wasm`.

## Status

Preview. API may change until the underlying Hyperlight SDK reaches a stable
release.
