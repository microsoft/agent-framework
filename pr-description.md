### Motivation and Context

Brings .NET Workflows' output handling to parity with Python's `intermediate_output` concept, and grows the orchestration-builder surface to first-class fluent types for all five shapes (Sequential, Concurrent, Handoff, GroupChat, Magentic). Lets workflow authors distinguish *intermediate* outputs (progress, partial results) from *terminal* outputs at the executor designation level, and lets `Workflow.AsAIAgent(...)` forward intermediates out to callers automatically — matching Python's `as_agent` behavior.

New behavior is gated behind a process-wide `Futures.EnableAgentResponseOutputTaggingAndFiltering` switch that ships **opt-in** (default `false`); existing consumers see no behavior change until they explicitly enable it.

### Description

**Six-commit stack**, each independently buildable and green. Test count goes 565 → 625; clean across `net472` / `netstandard2.0` / `net8.0` / `net9.0` / `net10.0`.

1. **`test:` test reshuffles** — pure rename/split moves in preparation; no cases added or removed.
2. **`feat:` OutputTag + Futures + tag-aware `WorkflowBuilder` API** — new `OutputTag` struct (`ChatRole`-shaped, single `Intermediate` singleton, internal ctor), `Futures` static class for opt-in pre-GA behavior, `WorkflowOutputEvent.Tags` as `HashSet<OutputTag>`, three `WorkflowBuilder.WithOutputFrom` overloads plus a `WithIntermediateOutputFrom` extension. JSON: `Workflow.OutputExecutors` now serializes as a map; the converter accepts the legacy `string[]` shape on read.
3. **`feat:` Futures-gated runner change** — `InProcessRunnerContext.YieldOutputAsync` rewritten so AgentResponse(Update) payloads no longer special-case the filter when the flag is on. Untagged terminals carry empty `Tags`; intermediate-designated executors carry `{Intermediate}`.
4. **`feat:` orchestration builders** — `Handoff` / `GroupChat` / `Magentic` builders gain `WithOutputFrom` / `WithIntermediateOutputFrom` (agent-typed, memoized) with Python-aligned defaults when no designation is made.
5. **`feat:` Workflow-as-Agent forwarding** — `WorkflowSession.InvokeStageAsync` updated so that under Futures-on, `AgentResponseEvent` is forwarded unconditionally (matching `AgentResponseUpdateEvent`'s today-behavior). `Futures` documentation gains a remark about the `AsAIAgent` interaction.
6. **`feat:` `SequentialWorkflowBuilder` / `ConcurrentWorkflowBuilder` + `OrchestrationBuilderBase<TBuilder>`** — promotes Sequential and Concurrent to first-class fluent types; introduces a generic abstract base that unifies `WithName` / `WithDescription` / `WithOutputFrom` / `WithIntermediateOutputFrom` across all five orchestration builders (~150 LOC of duplicated code removed). Static `AgentWorkflowBuilder.BuildSequential` / `BuildConcurrent` keep working; new `Create*BuilderWith` factories cover the full set.

**Default designations** (when no explicit call is made): terminal aggregator is `Output`, every participating agent is `Intermediate`. The bare `WorkflowBuilder` default is unchanged.

**Lifecycle**: `Futures.EnableAgentResponseOutputTaggingAndFiltering` is documented as a one-release migration helper — `[Obsolete]` in v2.0.0 when the new behavior becomes the default, removed in v3.0.0.

### Contribution Checklist

- [x] The code builds clean without any errors or warnings
- [x] The PR follows the [Contribution Guidelines](https://github.com/microsoft/agent-framework/blob/main/CONTRIBUTING.md)
- [x] All unit tests pass, and I have added new tests where possible
- ~~[ ] **Is this a breaking change?** No — new behavior is opt-in via the `Futures` flag; default `false` preserves current behavior. The full suite also passes with the flag forced ON globally.~~
