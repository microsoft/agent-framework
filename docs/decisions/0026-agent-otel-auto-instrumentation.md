---
status: proposed
contact: rogerbarreto
date: 2026-05-20
deciders: sergeymenshykh, rogerbarreto, westey-m, chetantoshniwal
consulted: 
informed: 
---

# Agent Framework OpenTelemetry Auto-Instrumentation

## Context and Problem Statement

Today: telemetry on agent = manual `UseOpenTelemetry()` per agent (see
[ADR-0003](./0003-agent-opentelemetry-instrumentation.md)). Wrapper pattern
fine for explicit control. No match for .NET OTel ecosystem convention.
ASP.NET Core, EF Core, SqlClient = one `AddXxxInstrumentation()` on provider
builder, done.

Three frictions:

1. No convention entry point. User know `AddAspNetCoreInstrumentation()`. No
   `AddAgentFrameworkInstrumentation()` exist.
2. DI scenarios = per-agent ceremony. Many `AsAIAgent()` factories in
   provider packages (`OpenAI`, `Anthropic`, `Foundry`, `A2A`, etc.) not
   reached by any DI wrap.
3. No kill switch. Ops cannot disable Agent Framework telemetry without
   rebuild. `OTEL_DOTNET_AUTO_<COMPONENT>_INSTRUMENTATION_ENABLED` is the
   convention.

Need:

- Single call on `TracerProviderBuilder` / `MeterProviderBuilder`. Done.
- `AsAIAgent()` factories auto-wrap when DI present.
- Full parity with `UseOpenTelemetry()` knobs (source name, sensitive data).
  No worse-API trap.
- Env-var kill switch.
- Keep `OpenTelemetryAgent` + `UseOpenTelemetry()` as primitives.

## Decision Drivers

- **Convention alignment.** Match `AddXxxInstrumentation()` shape. User
  reflex wins discovery.
- **Dep hygiene.** Small + stable deps only. Use
  `OpenTelemetry.Api.ProviderBuilderExtensions` — the package OTel publishes
  exactly for library authors who expose provider-builder extensions
  without SDK pull.
- **Layer separation.** Core knows zero workflow. Workflow knows zero core
  internals. Each owns own surface.
- **Parity with `UseOpenTelemetry()`.** Every knob today reachable through
  new entry point. No regression.
- **No surprise.** Explicit user call. No env-var SDK bootstrap (spec
  forbid).
- **Auto-wire `AsAIAgent()`.** Factory result wrapped when caller pass
  `IServiceProvider`.
- **Back-compat.** Existing `UseOpenTelemetry()` unchanged.

## Considered Options

- Status quo. Keep `UseOpenTelemetry()` only.
- **Embed extensions in core assemblies.** Recommended.
- New dedicated instrumentation packages.
- Auto-wrap on generic `OTEL_*` env vars.
- Service-collection-only extension.

## Decision Outcome

Chosen: **Embed extensions in core assemblies.**

Add `OpenTelemetry.Api.ProviderBuilderExtensions` to `Microsoft.Agents.AI`.
Bump `Microsoft.Agents.AI.Workflows` from `OpenTelemetry.Api` to same.
Each assembly expose own `AddAgentFrameworkInstrumentation()` (workflows
flavor: `AddAgentFrameworkWorkflowsInstrumentation()`) on
`TracerProviderBuilder` + `MeterProviderBuilder`. Namespaces:
`OpenTelemetry.Trace` / `OpenTelemetry.Metrics` per ASP.NET Core
convention. Each extension subscribe only its own source. Neither know
other layer.

New `AgentFrameworkInstrumentationOptions` class. Two props mirror
`UseOpenTelemetry()` exactly: `SourceName` override + `ConfigureAgent`
callback. Activation register options as DI singleton. Options presence
= active signal. No separate marker type.

`AsAIAgent()` overloads gain optional `IServiceProvider? services = null`
parameter. When services pass + options registered → factory wrap result
with `OpenTelemetryAgent`, invoke `ConfigureAgent` callback, return.
Idempotent: skip if already wrapped. `Workflow.AsAIAgent()` join same
pattern via agents marker (its `WorkflowHostAgent` IS `AIAgent`).
Workflow internal spans still opt-in via `WorkflowBuilder.WithOpenTelemetry()`
at build time; activation only subscribe source.

Env-var kill switch: `OTEL_DOTNET_AGENTFRAMEWORK_INSTRUMENTATION_ENABLED`
(default `true`). When `false` → `AddAgentFrameworkInstrumentation()`
no-op. No source subscribe, no DI register, no auto-wire downstream.
Read once at extension-call time.

Multi-call semantics: **last-wins** via plain
`services.AddSingleton(options)`. App-level config beat library-level
default. Library cannot silently suppress explicit app override.

### Open question for reviewers

One sub-decision deliberately open:

**Do `OpenTelemetryAgent`, `UseOpenTelemetry()`, `OpenTelemetryConsts`
stay in core or move to new dedicated packages?**

- Recommended option above = **stay in core**. Activation extensions
  added alongside. No public types removed.
- "New dedicated instrumentation packages" alternative = **move out**.
  Clean separation. Breaking change for current `UseOpenTelemetry()`
  callers (need new package reference).

Two endpoints coherent. Middle ground = split-assembly awkward, not
recommended either way.

### Consequences

- **Good:** One-line `AddAgentFrameworkInstrumentation()` matches user
  ecosystem reflex.
- **Good:** `AsAIAgent()` factories auto-wrap under DI. Zero per-agent
  ceremony.
- **Good:** Full parity with `UseOpenTelemetry()`. No regression for
  migrating users.
- **Good:** Dep cost small + stable. Two net-new transitive packages
  (`OpenTelemetry.Api`, `OpenTelemetry.Api.ProviderBuilderExtensions`).
  Both `Stable` per OTel versioning. `M.E.DependencyInjection.Abstractions`
  + `System.Diagnostics.DiagnosticSource` already in core's closure,
  reused.
- **Good:** Ops get documented kill switch via single env var.
- **Good:** Non-breaking. Existing `UseOpenTelemetry()` chain unchanged.
- **Neutral:** Workflow internal spans still need
  `WorkflowBuilder.WithOpenTelemetry()` at build time. Activation only
  subscribe source. Document in samples.
- **Neutral:** Agents + workflows have separate activation methods. "No
  workflow knowledge in core" principle precludes unified method.
- **Bad:** Adds optional `IServiceProvider? services = null` to every
  `AsAIAgent()` overload across ~10–15 provider packages.
  Source-compatible + binary-compatible. Coordinated release needed.
- **Bad:** Core public API grows: one options class + four extensions
  per affected assembly. Reviewers minimizing core surface may prefer
  dedicated-packages alternative.

## Validation

- **Unit tests** assert `AddAgentFrameworkInstrumentation()` register
  correct source + meter. Options singleton resolvable via DI with
  configured values.
- **Unit tests** assert `AsAIAgent()` with options-registered DI →
  outermost wrapper = `OpenTelemetryAgent`. `ConfigureAgent` invoked.
- **Unit tests** assert `AsAIAgent()` without DI or without options
  registration → unwrapped agent (current behavior preserved).
- **Unit tests** assert already-wrapped input not double-wrapped.
- **Unit tests** assert last-wins on repeated activation: most recent
  options instance resolved.
- **Unit tests** assert
  `OTEL_DOTNET_AGENTFRAMEWORK_INSTRUMENTATION_ENABLED=false` → no-op
  activation.
- **Integration test** capture `invoke_agent` activity via in-memory
  exporter through new path. End-to-end. No explicit `UseOpenTelemetry()`.
- **Sample** demonstrate new activation alongside existing manual sample.
  README cross-link explain when to use each.

## Pros and Cons of the Options

### Status quo

Continue per-agent `AIAgentBuilder.UseOpenTelemetry()`. No new packages.
No new APIs.

- **Good:** Zero work. Zero new deps.
- **Good:** Explicit control preserved.
- **Bad:** Diverge from universal .NET OTel convention. New user reflex
  miss.
- **Bad:** Per-agent ceremony bad at DI scale. `AsAIAgent()` factories
  produce telemetry-less agents without per-callsite work.
- **Bad:** No kill switch.
- **Bad:** Exact problem this ADR fix.

### Embed extensions in core assemblies (recommended)

Add `OpenTelemetry.Api.ProviderBuilderExtensions` to
`Microsoft.Agents.AI` (workflows bump from `OpenTelemetry.Api` to same).
Add `AddAgentFrameworkInstrumentation()` +
`AddAgentFrameworkWorkflowsInstrumentation()` per assembly. Add options
class, DI auto-wire mechanism, kill-switch env var. Keep
`OpenTelemetryAgent`, `UseOpenTelemetry()`, `OpenTelemetryConsts` in
core unchanged.

- **Good:** Single-package install with convention-aligned extension.
- **Good:** Non-breaking. Existing `UseOpenTelemetry()` work as-is.
- **Good:** Dep surface minimal + stable. Two net-new transitive
  packages (`OpenTelemetry.Api`, `OpenTelemetry.Api.ProviderBuilderExtensions`).
  Verified by NuGet resolution against current
  `Microsoft.Agents.AI` graph.
  `M.E.DependencyInjection.Abstractions` + `System.Diagnostics.DiagnosticSource`
  already present, reused.
- **Good:** Workflows already depend on `OpenTelemetry.Api`. Bump to PBE
  = extend existing pattern, not new coupling.
- **Good:** Each assembly own its source name only. No cross-layer
  knowledge.
- **Good:** Auto-wire reuse `OpenTelemetryAgent`. No parallel pipeline.
- **Neutral:** Wrapper stays in same assembly as activation extension.
  Some reviewer may prefer split (see alternative).
- **Bad:** Core public API grows: one options class + four extensions
  (two per builder type) per affected assembly.
- **Bad:** Every `AsAIAgent()` overload across provider packages need
  optional `IServiceProvider? services = null`. Source + binary
  compatible. Breadth = coordinated release.

### New dedicated instrumentation packages

Move `OpenTelemetryAgent`, `UseOpenTelemetry()`, `OpenTelemetryConsts`
out of core to new `Microsoft.Agents.AI.OpenTelemetry` +
`Microsoft.Agents.AI.Workflows.OpenTelemetry` packages. New packages
depend on respective core assembly + `OpenTelemetry.Api.ProviderBuilderExtensions`.
Expose activation extensions alongside moved wrapper.

- **Good:** Strictest separation. Core assemblies regain zero OTel-aware
  code.
- **Good:** Match ASP.NET Core / EF Core packaging discipline most
  literally.
- **Good:** Library authors who reference `Microsoft.Agents.AI` but
  never want OTel pay nothing.
- **Bad:** Breaking-change release for current `UseOpenTelemetry()`
  callers. Need new package ref. `Microsoft.Agents.AI` still pre-GA so
  window open, but migration cost real.
- **Bad:** Two additional packages to publish + maintain. Own CHANGELOG,
  release cadence, version compat. For small amount of code.
- **Bad:** User friction higher. Two-package install for activation entry
  point vs one in recommended.

### Auto-wrap on generic `OTEL_*` env vars

Library detect standard OTel env vars (`OTEL_SERVICE_NAME`,
`OTEL_EXPORTER_OTLP_ENDPOINT`, ...) and auto-wrap every constructed
agent with `OpenTelemetryAgent`. No user activation call needed.

- **Good:** Zero user activation code in apps with standard env vars.
- **Bad:** Violate OTel spec: library not start SDK from env. App start
  SDK.
- **Bad:** Env vars in question = SDK config not "instrument me" signal.
  Presence in environment not intended for Agent Framework telemetry
  (e.g. CI configured for other app) silently activate.
- **Bad:** Serious double-wrap risk if user also call `UseOpenTelemetry()`.
  Detect "already wrapped" possible but fragile.
- **Bad:** Diverge from how every other .NET OTel instrumentation lib
  activate.

### Service-collection-only extension

Single `services.AddAgentFrameworkInstrumentation()` on `IServiceCollection`.
Register auto-wire decorator. Subscribe zero sources. User still subscribe
agent source manually on `TracerProviderBuilder`.

- **Good:** No new OTel package dep in core
  (`M.E.DependencyInjection.Abstractions` already there).
- **Bad:** Abandon most discoverable half of convention. User expect
  activation on builder where they configured tracing + metrics.
- **Bad:** User still call
  `tracerProviderBuilder.AddSource("Experimental.Microsoft.Agents.AI")`
  by hand. Defeat point of convention.
- **Bad:** Strict subset of recommended option's surface. Marginal dep
  savings.

## More Information

Additive to
[ADR-0003 (Agent OpenTelemetry Instrumentation)](./0003-agent-opentelemetry-instrumentation.md).
`OpenTelemetryAgent` + `UseOpenTelemetry()` remain underlying mechanism
for per-agent telemetry. This ADR add convention-aligned activation on
top. ADR-0003 not superseded.

Separate follow-on ADR anticipated for source-naming questions out of
scope here:

- Workflows source name carry `"Experimental."` prefix? (Currently no;
  agents source has it.)
- Consolidate workflows source under agents source? Or keep separate?
- When/how drop `"Experimental."` prefix in coordination with upstream
  gen-AI semantic convention stabilization.

`"Experimental."` prefix on agents source intentional. Mirror
`Microsoft.Extensions.AI` (`Experimental.Microsoft.Extensions.AI`).
Signal emitted telemetry conform to semconv still experimental. Drop
prefix prematurely = falsely advertise stability upstream not yet
provide.

Implementation tracked by GitHub issue
[#5852](https://github.com/microsoft/agent-framework/issues/5852).
Source-naming ADR implementation tracked separately when opened.

### Reference API shape

Recommended option produce approximately this user-facing API.
Signatures illustrative; final shape match
`OpenTelemetry.Instrumentation.AspNetCore` overload set.

```csharp
namespace Microsoft.Agents.AI;

public class AgentFrameworkInstrumentationOptions
{
    /// <summary>
    /// Overrides the default activity source name. When null, the default
    /// ("Experimental.Microsoft.Agents.AI") is used.
    /// </summary>
    public string? SourceName { get; set; }

    /// <summary>
    /// Invoked against every OpenTelemetryAgent instance produced by the
    /// auto-wiring pipeline. Use this to set EnableSensitiveData and any
    /// future per-wrapper options.
    /// </summary>
    public Action<OpenTelemetryAgent>? ConfigureAgent { get; set; }
}
```

```csharp
namespace OpenTelemetry.Trace;

public static class AgentFrameworkInstrumentationTracerProviderBuilderExtensions
{
    public static TracerProviderBuilder AddAgentFrameworkInstrumentation(this TracerProviderBuilder builder);
    public static TracerProviderBuilder AddAgentFrameworkInstrumentation(
        this TracerProviderBuilder builder,
        Action<AgentFrameworkInstrumentationOptions>? configure);
    public static TracerProviderBuilder AddAgentFrameworkInstrumentation(
        this TracerProviderBuilder builder,
        string? name,
        Action<AgentFrameworkInstrumentationOptions>? configure);
}
```

```csharp
// Symmetric extensions exist on MeterProviderBuilder in OpenTelemetry.Metrics.
// Symmetric extensions exist in Microsoft.Agents.AI.Workflows
// under the name AddAgentFrameworkWorkflowsInstrumentation.
```

### Reference activation example

```csharp
services.AddOpenTelemetry()
    .WithTracing(t => t
        .AddAgentFrameworkInstrumentation(o => o.ConfigureAgent = ot => ot.EnableSensitiveData = true)
        .AddAgentFrameworkWorkflowsInstrumentation()
        .AddOtlpExporter())
    .WithMetrics(m => m
        .AddAgentFrameworkInstrumentation()
        .AddOtlpExporter());

// Anywhere in the app
var agent = chatClient.AsAIAgent(services: serviceProvider);
// Auto-wrapped with OpenTelemetryAgent because options singleton present in serviceProvider.
```

### Reference kill-switch example

```bash
OTEL_DOTNET_AGENTFRAMEWORK_INSTRUMENTATION_ENABLED=false dotnet run
# AddAgentFrameworkInstrumentation() calls no-op. Agents not wrapped.
```
