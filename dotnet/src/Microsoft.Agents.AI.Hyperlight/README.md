# Microsoft.Agents.AI.Hyperlight

First-class [CodeAct](../../../docs/decisions/0024-codeact-integration.md)
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

## Quick Start — Bundled Python Guest

The simplest way to get started is with the bundled Python guest module.
This package includes
[`Hyperlight.HyperlightSandbox.Guest.Python`](https://www.nuget.org/packages/Hyperlight.HyperlightSandbox.Guest.Python),
so no separate module path is needed:

```csharp
using Microsoft.Agents.AI.Hyperlight;

// Use the bundled Python guest — no module path required
var options = HyperlightCodeActProviderOptions.CreateForPython();
using var provider = new HyperlightCodeActProvider(options);
```

Or with the standalone function:

```csharp
using var executeCode = new HyperlightExecuteCodeFunction(
    HyperlightCodeActProviderOptions.CreateForPython());
```

## Other Backends

```csharp
// Built-in JavaScript (QuickJS) — default
var jsOptions = HyperlightCodeActProviderOptions.CreateForJavaScript();

// Custom Wasm guest module. See the Hyperlight Sandbox docs for creating a custom Wasm module.
var wasmOptions = HyperlightCodeActProviderOptions.CreateForWasm("/path/to/guest.aot");
```

## Requirements

* The [`Hyperlight.HyperlightSandbox.Api`](https://www.nuget.org/packages/Hyperlight.HyperlightSandbox.Api)
  and [`Hyperlight.HyperlightSandbox.Guest.Python`](https://www.nuget.org/packages/Hyperlight.HyperlightSandbox.Guest.Python)
  NuGet packages (included as dependencies).
* A hypervisor: [KVM](https://help.ubuntu.com/community/KVM/Installation) (Linux),
  [MSHV](https://github.com/rust-vmm/mshv), or
  [Hyper-V](https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/get-started/Install-Hyper-V) (Windows).

## Status

Preview. API may change until the underlying Hyperlight SDK reaches a stable
release.
