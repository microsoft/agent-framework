---
applyTo: 'dotnet/**'
---

Before reviewing .NET changes, read and apply
[dotnet/AGENTS.md](../../dotnet/AGENTS.md). Use the task-specific skills under
`dotnet/.github/skills/` for build and test commands, project structure, pull
requests, and sample verification.

Do not duplicate purely mechanical findings that `dotnet format`, analyzers, or
other required CI checks will report.

## Public API Naming Review

- Apply these checks to new or renamed public APIs, not unrelated existing code. Cite the closest comparable
  repository API when reporting an inconsistency.
- Name methods for the value or operation they expose. Singular/plural terminology must match the logical result;
  a method returning a context object should not imply that it returns a collection of keys.
- Use `Extensions` classes for actual extension methods. Put ordinary static factories on an appropriately named
  factory type or the existing factory for that concept. Keep related factory overloads together where dependency
  boundaries permit.
- Group hosting extensions by receiver: service collection, host application builder, and endpoint route builder.
  Follow neighboring receiver-specific class names.
- Name a service's options type `<ServiceName>Options`, using the full service type name; for example,
  `FoundryToolboxService` uses `FoundryToolboxServiceOptions`.
- Give boolean options a direct, unambiguous predicate. Avoid redundant combinations such as `Allow...Enabled`;
  distinguish similarly named concepts such as agent-service response storage versus hosting response storage.
- Boolean settings should default to `false`. When a setting would otherwise default to `true`, consider
  reframing its name and implementation so `false` expresses the intended default behavior; for example,
  `AllowUnregisteredToolboxes = false` instead of `StrictMode = true`. Keep the name and conditional logic aligned.
  Do not simply flip an existing default or weaken safe behavior to satisfy this convention; changes to existing
  public settings must preserve compatibility or receive explicit approval for a breaking change.
- Use consistent provider/domain qualifiers across related public types. Flag duplicate simple names in namespaces
  consumers commonly import together when they create ambiguity.
- Do not flag inherited or overridden names dictated by external contracts. Do not recommend breaking renames solely
  for stylistic consistency; explain the concrete discoverability or semantic problem. Treat unresolved namespace
  ordering or prefix choices as design questions, not established convention violations.

## Service Options Review

- For new or materially edited service APIs, accept the concrete options type rather than `IOptions<TOptions>`,
  `IOptionsSnapshot<TOptions>`, or `IOptionsMonitor<TOptions>`. Resolve configuration in the registration layer and
  pass the resulting options to the service.
- Keep effective settings stable for the lifetime of a service, especially when it owns state initialized from
  those settings. Do not introduce configuration-change subscriptions or re-read changing options during operations
  unless live reconfiguration is an explicitly designed contract that preserves state consistency.
- `IOptions<TOptions>` does not itself reload options; `IOptionsMonitor<TOptions>` supports change notifications,
  and `IOptionsSnapshot<TOptions>` recomputes options per scope. The concrete-options convention keeps service APIs
  independent of these mechanisms; it does not make mutable options objects immutable.
