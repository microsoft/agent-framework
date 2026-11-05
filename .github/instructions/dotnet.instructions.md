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
- Use consistent provider/domain qualifiers across related public types. Flag duplicate simple names in namespaces
  consumers commonly import together when they create ambiguity.
- Do not flag inherited or overridden names dictated by external contracts. Do not recommend breaking renames solely
  for stylistic consistency; explain the concrete discoverability or semantic problem. Treat unresolved namespace
  ordering or prefix choices as design questions, not established convention violations.
