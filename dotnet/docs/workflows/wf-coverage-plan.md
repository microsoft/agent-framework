# Workflows Unit Test Coverage — Incremental Plan

Companion to [`wf-coverage-summary.md`](./wf-coverage-summary.md). That document
is the snapshot; this document is the proposal for **how to close the gap**
between today's `Microsoft.Agents.AI.Workflows` coverage (79.7% line / 67.2%
branch) and the team target (85%) and personal stretch target (90%).

## Goals

1. Reach **≥85% line coverage** on `Microsoft.Agents.AI.Workflows`, with
   branch coverage trending toward the same threshold.
2. Stretch to **≥90% line coverage**.
3. Prefer tests that exercise **public APIs** through their documented entry
   points rather than tests that bind to internals.
4. Keep each PR **small and reviewable** (a single class or a small group of
   tightly related classes), so coverage progresses incrementally rather than
   in one large unreviewable change.

## Out of scope (covered by pending PRs — do not duplicate)

The following classes are already addressed by in-flight PRs and are
**explicitly excluded** from every wave below. Re-check them once the PR(s)
merge before adding any new tests.

- `RouteBuilder` — [#5824](https://github.com/microsoft/agent-framework/pull/5824)
- `WorkflowBuilderExtensions` (`ForwardMessage`, `ForwardExcept`, `AddChain`,
  `AddExternalCall`, `AddSwitch`) and `SwitchBuilder` —
  [#5826](https://github.com/microsoft/agent-framework/pull/5826)
- `MagenticWorkflowBuilder`, `MagenticOrchestrator`, `MagenticTaskContext`,
  and the Magentic event/state record types —
  [#5833](https://github.com/microsoft/agent-framework/pull/5833)
- All of `Observability.*`, `OpenTelemetryWorkflowBuilderExtensions`, and the
  related delivery-status / activity helpers — re-enabled by
  [#5837](https://github.com/microsoft/agent-framework/pull/5837)

The following are also out of scope as not-worth-testing:

- `YieldsMessageAttribute`, `StreamsMessageAttribute` — both `[Obsolete]` and
  ignored by the source generator and runtime per their `Obsolete` message.

## Method

Each wave below states:

- **Target classes** with current line coverage and the approximate uncovered-
  line count from the snapshot.
- **What to test** — the user-visible behavior(s) the new tests should
  exercise. Tests should go through the public API where possible (e.g.,
  `WorkflowBuilder` / `WorkflowHostAgent` / `InProcessExecution`) and only
  reach into internals when there is no public path.
- **Estimated line-coverage delta** — the *upper bound* assuming every
  uncovered line in the listed classes becomes covered. Real deltas are
  typically 60–80% of the upper bound.
- **Suggested PR shape** — the smallest natural unit of work.

The waves are ordered by **(impact / effort)**, highest first. Stop after each
wave, re-run the snapshot, and re-prioritize.

---

## Wave 1 — Public API holes that are easy to write (largest single jump)

These are public types where the missing tests are mechanical (constructors,
guards, equality, simple round-trips) but cumulatively account for ~140
uncovered lines.

### 1A. `Workflow` (35 uncov, 44.4% line / 44.1% branch) — **public**

The bulk of the gap is around ownership and protocol-description paths that
are reachable but never asserted on directly:

- `Workflow.TakeOwnership` / `ReleaseOwnershipAsync`: each of the four
  `(subworkflow, _ownedAsSubworkflow)` switch arms (the four error messages
  enumerated in `TakeOwnership`), the "release by non-owner" branch, the
  `ObjectDisposedException`-substitute branch, and the
  `IResettableExecutor`-failure branch (the `"Cannot reuse Workflow with shared
  Executor instances that do not implement IResettableExecutor."` path).
- `Workflow.DescribeProtocolAsync`: protocol described from a workflow whose
  start executor is also an output executor; protocol described from a
  workflow whose start executor binds to a `RequestPort`.
- `Workflow.ReflectPorts` / `ReflectExecutors` / `ReflectEdges`: returns
  fresh-copy semantics (mutating returned dictionary does not mutate
  `Workflow`).

**Suggested PR**: `WorkflowOwnershipAndReflectionTests.cs`. Covers ownership
state machine + the three `Reflect*` accessors + `DescribeProtocolAsync`.

### 1B. `EdgeId` (15 uncov, 37.5% / 0%) — **public struct**

Zero branch coverage on a public equality type. Add a single
`EdgeIdEqualityTests.cs`:

- `Equals(object)` against `null`, `EdgeId`, `int`, and an unrelated type.
- `Equals(EdgeId)`.
- `==` and `!=` operators (equal, unequal, default).
- `GetHashCode()` consistency with `Equals`.
- `ToString()` round-trip with the underlying index.

This is ~10 minutes of code, lifts a public struct from 37→100%, and
contributes to the branch-coverage number disproportionately.

### 1C. `Execution.EdgeConnection` (30 uncov, 36.1% / 37.5%) — **public**

Public class with a documented ID-uniqueness factory and an `IEquatable<>`
contract that is largely untested. Add `EdgeConnectionTests.cs`:

- `EdgeConnection(sourceIds, sinkIds)` null-guards on both arguments.
- `EdgeConnection.WithUniqueIds(...)` (the factory documented in the source
  comment as enforcing uniqueness): both sides must reject duplicates with
  `ArgumentException`.
- `Equals` / `GetHashCode`: equal when both ordered lists match; unequal when
  source order differs (ordering is documented as significant); unequal when
  sink order differs.
- `ToString` / display formatting if applicable.

### 1D. `EdgeId` and `EdgeConnection` together unlock `EdgeIdConverter`

Once 1B + 1C land, `EdgeIdConverter` (currently 80%) typically reaches 100%
without additional code because the new equality assertions cause the
serializer round-trip to be exercised by existing JSON tests.

**Wave 1 upper-bound delta:** ~80 lines (~1.5 percentage points).

---

## Wave 2 — `WorkflowBuilder` public-surface gaps (largest single class)

`WorkflowBuilder` is currently 82.4% line / 79.4% branch with **48 uncovered
lines** — by far the largest absolute gap on a public type that is **not**
already addressed by [#5824](https://github.com/microsoft/agent-framework/pull/5824)
or [#5826](https://github.com/microsoft/agent-framework/pull/5826).

Audit the file (`dotnet/src/Microsoft.Agents.AI.Workflows/WorkflowBuilder.cs`)
for the specific uncovered lines before writing tests; the report-generator
HTML output highlights them. From the snapshot, the under-tested behaviors
are:

- The `WithName` / `WithDescription` / `WithStartExecutor` chain on
  pre-existing builders (re-assigning a start executor; assigning to the same
  executor twice).
- `AddFanInEdge` validation paths (duplicate sources, source equals sink,
  empty source list).
- `Build()` validation: workflow with no edges, workflow whose start executor
  is unreachable from any registered executor (cycle-only graph), workflow
  with a `RequestPort` not associated with any executor.
- `BindFunctionExecutor` / `Bind` overloads that take a custom id collision —
  the duplicate-id branch.
- The "telemetry context already set" branch reached when
  `OpenTelemetryWorkflowBuilderExtensions.WithOpenTelemetry` is called twice
  on the same builder.

**Suggested PR**: `WorkflowBuilderValidationTests.cs`, focused on the
not-yet-exercised validation branches and the rebinding behaviors. Avoid
duplicating anything already in `WorkflowBuilderSmokeTests.cs`.

**Wave 2 upper-bound delta:** ~48 lines (~0.9 pp).

---

## Wave 3 — `ExecutorBindingExtensions` (public, 32% covered)

`public static class ExecutorBindingExtensions` (50 lines, 34 uncovered) is
the canonical entry point for turning user code into `ExecutorBinding`
instances. Many of its overloads are completely untested:

- `BindExecutor(this Executor)` — round-trip through `WorkflowBuilder` to
  prove the `ExecutorInstanceBinding` resolves to the supplied instance.
- `BindExecutorFactory<TExecutor>(Func<ValueTask<TExecutor>>)` — including
  the eager-instantiation behavior documented in the XML comment ("...will be
  instantiated if a `ProtocolDescriptor` for the `Workflow` is requested, and
  it is the starting executor.").
- `BindExecutorFactory<TExecutor>(string id, Func<ValueTask<TExecutor>>)` —
  custom-id overload.
- `BindFunction` / `Bind<TInput>(Func<…>)` / `Bind<TInput, TOutput>(Func<…>)`
  — both sync and async overloads, both with and without `CancellationToken`,
  including null-guard on the function and on the id.

**Suggested PR**: `ExecutorBindingExtensionsTests.cs`. Mostly mechanical;
each overload becomes one or two `[Theory]` rows. This single PR alone is
worth ~30 lines / ~0.6 pp on its own and removes a 32%-covered public type
from the lagging list.

---

## Wave 4 — `WorkflowSession` and `WorkflowHostAgent` (public hosting surface)

`WorkflowSession` is internal but is the implementation of the
**public** `WorkflowHostAgent`. Together they account for ~80 uncovered
lines and several documented public guarantees that have no test coverage
today.

The uncovered lines concentrate in three areas:

1. **Resume from a serialized session.** `WorkflowSession(Workflow, JsonElement,
   IWorkflowExecutionEnvironment, …)` — currently exercised only on the happy
   path. Add tests for: invalid JSON payload, payload missing pending-request
   ids, payload referencing a different `Workflow` shape, round-trip through
   `Serialize()` → re-construct.
2. **External-request reconciliation.** The `_pendingRequests` plumbing
   (`AddPendingRequest`, `RemovePendingRequest`, `TryGetPendingRequest`) and
   the `NormalizeResponseContentForDelivery` / `CreateRequestContentForDelivery`
   / `CloneFunctionCallContent` / `CloneFunctionResultContent` /
   `CloneToolApprovalRequestContent` / `CloneToolApprovalResponseContent`
   helpers. Each helper has at least one branch (id mismatch, missing
   metadata, unsupported `AIContent` subtype) that is not hit today.
3. **`WorkflowHostAgent` failure paths.** Calling the agent against a
   `Workflow` with no checkpointing configured when checkpointing is required
   (the path validated by `VerifyCheckpointingConfiguration`); calling
   `RunAsync` after the session has terminated; passing `null` for the
   message list.

**Suggested PRs**:

- 4a — `WorkflowSessionResumeTests.cs` (resume + serialize round-trip).
- 4b — `WorkflowSessionExternalRequestTests.cs` (request/response cloning and
  pending-request bookkeeping).
- 4c — `WorkflowHostAgentValidationTests.cs` (agent-level guards).

**Wave 4 upper-bound delta:** ~80 lines (~1.5 pp). This is the single largest
uncovered area on the `Workflow*` public surface.

---

## Wave 5 — Checkpointing converters and the file-system store

Cluster of small but high-percentage wins. None of these is glamorous, but
together they take the `Checkpointing.*` namespace from "spotty" to
"comprehensive" and remove every <60% type from the namespace except the
abstract `JsonCheckpointStore` (which by itself is 1 line and not worth a
dedicated test).

| Class | Cov | Uncov | What's missing |
| ----- | ---:| ----:| -------------- |
| `Checkpointing.ExecutorIdentityConverter` | 12.5% | 14 | Read/write paths for null id, mixed-case id, non-string token. |
| `Checkpointing.JsonWireSerializedValue` | 48.1% | 14 | Read with missing `TypeId`, missing `Value`, type-id mismatch on `As<T>()`. |
| `Checkpointing.PortableValueConverter` | 57.5% | 14 | Round-trip of `null`, primitive, complex object, and the unknown-type branch. |
| `Checkpointing.FileSystemJsonCheckpointStore` | 62.2% | 20 | Index-file rebuild on missing index, corrupted index file (existing test only covers the happy path), retrieval of unknown checkpoint id, store created against a path that does not yet exist. |
| `Checkpointing.WorkflowInfo` | 80.3% | 10 | Equality/serialization branches for workflows that vary only in `Name` / `Description`. |

`FileSystemJsonCheckpointStoreTests.cs` already exists; the additions can go
into the same file.

**Suggested PRs**: one PR per file, or one combined "checkpointing-converter"
PR plus a separate "FileSystemJsonCheckpointStore-edge-cases" PR.

**Wave 5 upper-bound delta:** ~70 lines (~1.3 pp).

---

## Wave 6 — `HandoffWorkflowBuilderCore<TBuilder>` (public base, 80.7% / 65.7%)

`HandoffWorkflowBuilderCore` is the public base used by `HandoffWorkflowBuilder`
and friends. With 22 uncovered lines and only 65.7% branch coverage on a
public surface, it is one of the two remaining public builders without
exhaustive validation tests (`WorkflowBuilder` itself is the other — see
Wave 2). Cross-check against existing `HandoffOrchestrationTests.cs` and
`HandoffMessageFilterTests.cs` to avoid duplication.

Behaviors to cover:

- Null/empty arguments to each public `Add*` / `WithStart*` / `WithEnd*`
  method.
- Duplicate-id detection (per the `WorkflowBuilder` contract).
- `Build()` failure when no end executor is wired up.
- `Build()` failure when no handoff filter is supplied and the default rejects
  the configured handoff target.

**Wave 6 upper-bound delta:** ~22 lines (~0.4 pp).

---

## Wave 7 — Public statics and remaining 0% public types

These are short tests with disproportionate impact on the *count of public
types with 0% coverage*, which is itself a useful quality metric independent
of the line-coverage number.

- **`StatefulExecutor<TState, TInput, TOutput>` (public, 0% / 9 lines)** —
  add one minimal subclass that returns a value from `HandleAsync`, drive it
  through `WorkflowBuilder` + `InProcessExecution`, assert state survives
  across handler invocations. Mirror the existing tests for the two-type
  `StatefulExecutor<TState, TInput>` overload (which is already covered).
- **`Specialized.RequestPortExtensions` (internal, 7.1% / 13 lines)** — three
  tests: `ShouldProcessResponse` returns `false` when the response targets a
  different port; throws `InvalidOperationException` (with the specific
  message produced by `CreateExceptionForType`) when port matches but the
  payload type does not; returns `true` on a matching port and matching
  payload.
- **`MagenticPlanReviewRequest` / `MagenticPlanReviewResponse` (public, 0%)** —
  PR [#5833](https://github.com/microsoft/agent-framework/pull/5833) covers
  `MagenticPlanReviewResponse`. After it merges, add a one-shot test that
  constructs `MagenticPlanReviewRequest` with each documented constructor
  argument combination and asserts the property values, only if it is still
  not covered.
- **`WorkflowEvaluationExtensions` (public, 89.4%, 12 uncov)** — the gap is
  in two paths: the cancellation path through `EvaluateAsync` and the
  evaluator-throws path. Two `[Fact]`s.

**Wave 7 upper-bound delta:** ~35 lines (~0.6 pp).

---

## Wave 8 — Internal helpers behind public hot paths

Lower priority than waves 1–7 because the public-API gaps should be closed
first. Listed here so they aren't forgotten when chasing the 90% stretch
target.

- `Execution.ExecutorIdentity` (15 uncov) — equality with `null`, with
  `string`, with mismatched-case `ExecutorIdentity`, implicit `string` ↔
  `ExecutorIdentity` conversions.
- `InProc.InProcStepTracer` (20 uncov, but only 21.4% **branch** coverage) —
  drive a workflow that has both internal and external messages in the same
  super-step; assert `SuperStepStartInfo.HasExternalMessages`,
  `SuperStepCompletionInfo.HasPendingMessages` /
  `HasPendingRequests`, the `Reload(lastStepNumber)` API, and the
  `ToString()` formatting.
- `MessageMerger` (13 uncov, 89.6% / 85.7%) — the small remaining branches
  in `MessageMerger.ResponseMergeState` (split across multiple final
  fragments) and the empty-input branch.
- `ExecutorBinding` (11 uncov) — the abstract base; covered automatically as
  Waves 3 and 4 land. Re-check after.
- `Visualization.WorkflowVisualizer` (18 uncov, 92.1%) — the remaining gaps
  are escape-handling for unusual executor labels (newlines, double-quotes,
  unicode) and the "subworkflow-with-zero-edges" formatting path. Three
  `[Theory]` rows.

**Wave 8 upper-bound delta:** ~75 lines (~1.4 pp).

---

## Cumulative projection

| After… | Upper-bound line cov | Realistic (≈70%) |
| ------ | ---: | ---: |
| Today | 79.7% | — |
| In-flight PRs (#5824, #5826, #5833, #5837) merged | ~86–87% | — |
| Wave 1 (public structs + `Workflow` ownership) | +1.5 pp | +1.0 pp |
| Wave 2 (`WorkflowBuilder` validation) | +0.9 pp | +0.6 pp |
| Wave 3 (`ExecutorBindingExtensions`) | +0.6 pp | +0.4 pp |
| Wave 4 (`WorkflowSession` + `WorkflowHostAgent`) | +1.5 pp | +1.0 pp |
| Wave 5 (checkpointing converters + file-system store edges) | +1.3 pp | +0.9 pp |
| Wave 6 (`HandoffWorkflowBuilderCore`) | +0.4 pp | +0.3 pp |
| Wave 7 (zero-coverage public types) | +0.6 pp | +0.4 pp |
| Wave 8 (internal helpers) | +1.4 pp | +1.0 pp |

Realistic projection after **all four pending PRs + Waves 1–4**: **~89–90%
line coverage**, comfortably past the 85% team target and reaching the 90%
stretch target. Waves 5–8 then take the assembly above 90% on both line and
branch coverage.

## Workflow for executing the plan

1. Wait for the four in-flight PRs (#5824, #5826, #5833, #5837) to merge.
2. Re-run the snapshot in
   [`wf-coverage-summary.md`](./wf-coverage-summary.md) and refresh the
   per-class table. Some entries in this plan may already be addressed; drop
   them.
3. Open Wave 1 as **one** PR per sub-section (1A, 1B, 1C). Keep each PR
   focused on a single class so review stays mechanical.
4. After each wave merges, re-run the snapshot and re-prioritize. If a class
   listed in a later wave is already past 90% coverage, drop it.
5. When the assembly clears 85% line coverage, raise the
   `dotnet-check-coverage.ps1` threshold and add
   `Microsoft.Agents.AI.Workflows` to the `nonExperimentalAssemblies` list in
   that script so the bar cannot regress.

## Conventions for the new tests

- Follow the existing test-project conventions in
  `dotnet/tests/Microsoft.Agents.AI.Workflows.UnitTests`:
  xUnit v3 + Microsoft Testing Platform, `FluentAssertions`, and the existing
  helper classes in `TestingExecutor.cs`, `TestRunContext.cs`,
  `TestWorkflowContext.cs`, `MessageDeliveryValidation.cs`, etc. Reuse them
  rather than introducing parallel infrastructure.
- Preserve the `Throw.IfXYZ` validation idiom in production code. New tests
  should assert against the existing `ArgumentNullException` /
  `ArgumentException` thrown by those helpers; do not change production
  validation to a different style.
- For each new test file, prefer `[Theory]` over many near-duplicate
  `[Fact]`s when only a single argument varies — this keeps reviewer load
  low and matches the convention used in `WorkflowBuilderSmokeTests.cs` and
  `RouteBuilderTests.cs` (PR #5824).
