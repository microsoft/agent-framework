# Workflows Unit Test Coverage — Snapshot

This document captures a coverage snapshot of `Microsoft.Agents.AI.Workflows`
produced by running the existing `Microsoft.Agents.AI.Workflows.UnitTests`
suite. It is the input for [`wf-coverage-plan.md`](./wf-coverage-plan.md), which
proposes incremental work to lift coverage to the 85%/90% targets.

## How this snapshot was produced

```bash
cd dotnet
dotnet build tests/Microsoft.Agents.AI.Workflows.UnitTests/Microsoft.Agents.AI.Workflows.UnitTests.csproj -f net10.0

dotnet test --project tests/Microsoft.Agents.AI.Workflows.UnitTests/Microsoft.Agents.AI.Workflows.UnitTests.csproj \
  -f net10.0 --no-build \
  --coverage --coverage-output-format cobertura \
  --coverage-output coverage.cobertura.xml \
  --coverage-settings tests/coverage.runsettings

reportgenerator \
  -reports:tests/Microsoft.Agents.AI.Workflows.UnitTests/bin/Debug/net10.0/TestResults/coverage.cobertura.xml \
  -targetdir:./coverage-report \
  -reporttypes:'Html_Dark;JsonSummary;TextSummary' \
  -assemblyfilters:'+Microsoft.Agents.AI.Workflows;-Microsoft.Agents.AI.Workflows.Declarative*'
```

- Tooling: `dotnet test` with `Microsoft.Testing.Extensions.CodeCoverage` (the
  same configuration documented in `dotnet/.github/skills/build-and-test/SKILL.md`).
- Scope: only the `Microsoft.Agents.AI.Workflows` assembly. The
  `Microsoft.Agents.AI.Workflows.Declarative*` family is excluded — those have
  their own test projects and a different ownership area.
- Test result: **460 passed, 22 skipped, 0 failed** (482 total). The 22 skipped
  tests are the previously-flaky `ObservabilityTests` and
  `WorkflowRunActivityStopTests`; **PR [#5837](https://github.com/microsoft/agent-framework/pull/5837)
  re-enables them all.**

## Headline numbers

| Metric                | Value                       | Target |
| --------------------- | --------------------------- | ------ |
| Line coverage         | **79.7%** (4386 / 5499)     | 85% / 90% |
| Branch coverage       | **67.2%** (1111 / 1653)     | — |
| Method coverage       | **80.9%** (903 / 1115)      | — |
| Fully-covered methods | **70.8%** (790 / 1115)      | — |
| Coverable lines       | 5,499                       | — |
| Uncovered lines       | **1,113**                   | — |
| Classes               | 237 (185 source files)      | — |

Distance to the 85% line target ≈ **+292 covered lines**.
Distance to the 90% personal target ≈ **+567 covered lines**.

The much larger branch-coverage gap (67.2%) is the bigger structural problem:
many code paths are reached but not all branches inside them are exercised.

## In-flight PRs that already address part of this gap

The plan in [`wf-coverage-plan.md`](./wf-coverage-plan.md) **excludes** the
classes covered by these PRs to avoid duplicate work or merge conflicts:

| PR | Classes added/improved |
| -- | ---------------------- |
| [#5824](https://github.com/microsoft/agent-framework/pull/5824) — `RouteBuilder` unit tests | `RouteBuilder` (143 lines, 58 currently uncovered) |
| [#5826](https://github.com/microsoft/agent-framework/pull/5826) — `WorkflowBuilder` specialized edge tests | `WorkflowBuilderExtensions` (51 lines, 21 uncov), `SwitchBuilder` (already 90.4%, but null-guard branches added) |
| [#5833](https://github.com/microsoft/agent-framework/pull/5833) — Magentic E2E coverage | `MagenticWorkflowBuilder` (69 lines, 0%), `MagenticOrchestrator` (52%), `MagenticTaskContext` (35%), and the related Magentic event types (all 0%) |
| [#5837](https://github.com/microsoft/agent-framework/pull/5837) — Re-enable `ObservabilityTests`/`WorkflowRunActivityStopTests` | `Observability/WorkflowTelemetryContext` (42.7%), `Observability/ActivityExtensions` (0%), `Observability/EdgeRunnerDeliveryStatusExtensions` (0%), `OpenTelemetryWorkflowBuilderExtensions` (0%), and the bulk of `Tags` / `EventNames` / `ActivityNames` |

Estimated combined impact once all four merge: **~360–410 of the current 1,113
uncovered lines** become covered, lifting line coverage to roughly **86–87%**
even before any of the new work proposed in the plan.

## Top uncovered classes (after excluding in-flight PRs)

Sorted by uncovered line count. "Public surface" indicates whether the class
itself or its uncovered members are part of the public API of the
`Microsoft.Agents.AI.Workflows` assembly — those are the highest-leverage
targets.

| # | Class | Public surface | Line cov | Branch cov | Coverable | Uncov |
|---|-------|:-:|---:|---:|---:|---:|
| 1 | `WorkflowSession` | internal (reached via `WorkflowHostAgent`) | 67.7% | 47.5% | 217 | **70** |
| 2 | `WorkflowBuilder` | **public** | 82.4% | 79.4% | 273 | **48** |
| 3 | `Workflow` | **public** | 44.4% | 44.1% | 63 | **35** |
| 4 | `ExecutorBindingExtensions` | **public** | 32.0% | n/a | 50 | **34** |
| 5 | `Execution.EdgeConnection` | **public** | 36.1% | 37.5% | 47 | **30** |
| 6 | `HandoffWorkflowBuilderCore<TBuilder>` | **public (base)** | 80.7% | 65.7% | 114 | **22** |
| 7 | `Checkpointing.FileSystemJsonCheckpointStore` | **public** | 62.2% | 57.1% | 53 | **20** |
| 8 | `InProc.InProcStepTracer` | internal | 62.9% | 21.4% | 54 | **20** |
| 9 | `Visualization.WorkflowVisualizer` | **public** | 92.1% | 93.5% | 230 | **18** |
| 10 | `EdgeId` | **public** struct | 37.5% | 0.0% | 24 | **15** |
| 11 | `Execution.ExecutorIdentity` | internal | 28.5% | 18.7% | 21 | **15** |
| 12 | `Checkpointing.ExecutorIdentityConverter` | internal | 12.5% | 0.0% | 16 | **14** |
| 13 | `Checkpointing.JsonWireSerializedValue` | internal | 48.1% | 50.0% | 27 | **14** |
| 14 | `Checkpointing.PortableValueConverter` | internal | 57.5% | 35.7% | 33 | **14** |
| 15 | `Execution.StateScope` | internal | 79.0% | 72.2% | 62 | **13** |
| 16 | `MessageMerger` | internal | 89.6% | 85.7% | 126 | **13** |
| 17 | `Specialized.RequestPortExtensions` | internal | 7.1% | 0.0% | 14 | **13** |
| 18 | `WorkflowEvaluationExtensions` | **public** | 89.4% | 75.0% | 114 | **12** |
| 19 | `ExecutorBinding` | internal (base) | 60.7% | 28.5% | 28 | **11** |
| 20 | `Checkpointing.WorkflowInfo` | internal | 80.3% | 54.5% | 51 | **10** |
| 21 | `WorkflowHostAgent` | **public** | 70.5% | 75.0% | 34 | **10** |
| 22 | `StatefulExecutor<TState, TInput, TOutput>` | **public** | **0.0%** | n/a | 9 | **9** |
| 23 | `CheckpointableRunBase` | internal (base of `Run`) | 42.8% | 16.6% | 14 | **8** |
| 24 | `Reflection.MessageHandlerInfo` | internal | 78.3% | 66.6% | 37 | **8** |
| 25 | `Specialized.ConcurrentEndExecutor` | internal | 78.9% | n/a | 38 | **8** |

### Other notable gaps

- **0% on small-but-public types**: `JsonCheckpointStore` (abstract base, 1
  line, no test instantiates it), `IResettableExecutor` (interface default
  method, 3 lines), `MagenticPlanReviewRequest`/`MagenticPlanReviewResponse`
  (5/2 lines — partly covered by [#5833](https://github.com/microsoft/agent-framework/pull/5833)).
- **Obsolete attributes** with 0% coverage but no value to test:
  `YieldsMessageAttribute`, `StreamsMessageAttribute`. Both are explicitly
  marked `[Obsolete]` and are ignored by both the source generator and the
  runtime — **excluded** from the plan.
- **Records / events** with low line counts (`SubworkflowWarningEvent`,
  `RequestHaltEvent`, `ResetChatSignal`, `MagenticReplannedEvent`, etc.) appear
  as 0% only because no test ever constructs them. Tiny absolute impact
  individually, but easy bulk wins via constructor smoke tests.
- **`Observability.*`** classes appear at 0–43% because the entire
  `ObservabilityTests` and `WorkflowRunActivityStopTests` files are skipped on
  `main`. Re-enabling them via PR [#5837](https://github.com/microsoft/agent-framework/pull/5837)
  is expected to lift those into the 80–95% range without any new test code.

## Per-area coverage breakdown

(Aggregated by namespace; `Microsoft.Agents.AI.Workflows.Declarative*` excluded.)

| Area | Approx line cov | Notes |
| ---- | ---: | ----- |
| Top-level (`Workflow`, `WorkflowBuilder`, `WorkflowSession`, `WorkflowHostAgent`, `Run`, `StreamingRun`) | ~75% | Largest absolute gap; many public-surface gaps. |
| `Execution.*` | ~85–90% on hot-path types, **<40%** on `EdgeConnection` and `ExecutorIdentity` | Identity/equality and connection-validation paths under-tested. |
| `Checkpointing.*` | ~80% mean | Several converter classes 12–58%; `FileSystemJsonCheckpointStore` 62% (concurrency / corruption / index-rebuild paths). |
| `InProc.*` | ~85% | `InProcStepTracer` is the only outlier (62.9% line, 21.4% branch). |
| `Reflection.*` | ~85% | Solid; minor gaps. |
| `Visualization.*` | 92.1% | Already strong; remaining 18 lines are escape-handling and a couple of unusual edge layouts. |
| `Observability.*` | **<45%** today, expected **>85%** after [#5837](https://github.com/microsoft/agent-framework/pull/5837). |
| `Specialized.Magentic.*` | 35–82% today; the orchestrator + builder + task context lift to high coverage after [#5833](https://github.com/microsoft/agent-framework/pull/5833). |
| `Specialized.*` (non-Magentic — handoff, group-chat, request-port helpers) | ~80–90% | `RequestPortExtensions` (7.1%) is the only sharp outlier. |
| `Evaluation.*` | 89.4% | Mostly there; only branch coverage gaps remain. |

## Reproducing the per-class data

The full per-class table used to build the buckets above is regenerated by:

```bash
python3 - <<'PY'
import json
data = json.load(open('coverage-report/Summary.json'))
asm = data['coverage']['assemblies'][0]
def uncov(c): return c['coverablelines'] - c['coveredlines']
for c in sorted(asm['classesinassembly'], key=lambda c: -uncov(c)):
    if uncov(c) == 0: continue
    print(f"{c['name']:80s}  {c['coverage']:5.1f}%  uncov={uncov(c):4d}  lines={c['coverablelines']}")
PY
```
