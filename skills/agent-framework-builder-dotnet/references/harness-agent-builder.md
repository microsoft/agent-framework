# Harness agent builder

Use a harness when the product needs an opinionated operating loop around a normal agent: planning, todos, memory,
approval handling, compaction, or optional autonomous capabilities.

`HarnessAgent` (package `Microsoft.Agents.AI.Harness`) is a convenience composition, not a separate agent abstraction.
It is a `DelegatingAIAgent` that wraps a `ChatClientAgent` built from the `IChatClient` you supply, configured through
`HarnessAgentOptions`. Everything it assembles can also be composed manually from a `ChatClientAgent`, `AIAgentBuilder`
decorators, context providers, a chat history provider, and instructions.

## Choose the composition direction

- Start with `HarnessAgent` and disable or replace features when the product wants most harness capabilities.
- Start with `ChatClientAgent` and add individual providers and decorators when the product needs only a few
  capabilities or exact ordering.
- Use a workflow instead when explicit graph topology, routing, checkpointed stages, or intermediate outputs define
  correctness.

## Important defaults and opt-ins

Keep only the defaults that affect architecture or safety in working memory; read the
[harness documentation](https://learn.microsoft.com/agent-framework/concepts/harness) or the `HarnessAgent` and
`HarnessAgentOptions` XML docs for the complete option list.

- Todo list, plan/execute mode, file memory, Agent Skills discovery, tool approval ("don't ask again" rules),
  OpenTelemetry, and a hosted web search tool are enabled by default; each has a `Disable...` option.
- Per-service-call history persistence is always on and has no `Disable...` option. If it must be omitted, compose the
  agent manually instead of using `HarnessAgent`.
- The default `HostedWebSearchTool` is not translated by many `IChatClient` providers. Set `DisableWebSearch = true`
  unless the provider supports it.
- Compaction applies only when a context-window budget or a custom strategy is supplied; `DisableCompaction` turns it
  off.
- File access (`FileAccessProvider`), background agents (`BackgroundAgentsProvider`), and looping (`LoopAgent` with
  `LoopEvaluator`s) are opt-in.
- When no history provider is supplied, the harness uses `InMemoryChatHistoryProvider`.
- Shell execution is provided by the separate `Microsoft.Agents.AI.Tools.Shell` package and is opt-in.
- Check current feature maturity (preview packages and `[Experimental]` APIs) before depending on file access,
  background agents, looping, or shell tooling.

## Operational gotchas

- Use an `AgentSession` when standing approval state or multi-turn behavior matters.
- File memory and file access are separate. File access tools require approval by default; file-memory writes do not.
- For hosted or untrusted workloads, disable file memory or supply a tenant-scoped `AgentFileStore` with quotas,
  retention, and server-owned cleanup. Do not rely on a shared default working-directory store.
- Load skills and background agents only from trusted sources; their content crosses the model and tool boundary.
- Bound autonomous loops and stop for unresolved approvals or user input. Two separate limits exist:
  `MaximumIterationsPerRequest` caps function-invocation iterations inside each inner run, while
  `LoopAgentOptions.MaxIterations` caps how many times `LoopAgent` repeats. Also use evaluator conditions.
- `HarnessAgentOptions.BackgroundAgents` creates an internal provider with no quota; child sessions and tasks persist
  until cleaned up. For hosted use, create and retain the `BackgroundAgentsProvider` yourself, bound how many agents
  and tasks a session may start, and call `ReleaseSessionAsync` when a session is evicted or disconnects.
- Treat shell command filters as a usability guard, not a security boundary. The host owns sandboxing and executor
  lifecycle.

## Validation

- Exercise enabled modes, memory, skills, and file roots rather than testing construction alone.
- Verify approval behavior for side effects.
- Prove loop termination and resource cleanup for optional autonomous features.

## Learn more

- [Harness concepts](https://learn.microsoft.com/agent-framework/concepts/harness)
- [Harness samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/Harness)
- [Agent mode sample](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/Agents/Agent_Step22_AgentMode)
- [Todo list sample](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/Agents/Agent_Step23_TodoList)
- [Agent Skills samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/AgentSkills)
