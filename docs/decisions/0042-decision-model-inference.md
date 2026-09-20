---
status: proposed
contact: joslat
date: 2026-09-20
deciders: westey-m, SergeyMenshykh, rogerbarreto
consulted:
informed:
---

# Decision-model inference in .NET Agent Framework: `IDecisionClient`, `DecisionLoopEvaluator`, and the TypeSafe provider

> **PR note:** This ADR ships in the same pull request as the initial .NET implementation: the experimental
> `IDecisionClient` contract in `Microsoft.Agents.AI.Abstractions`, `DecisionLoopEvaluator` in `Microsoft.Agents.AI`,
> the `Microsoft.Agents.AI.TypeSafe` provider package, their tests, and the `Harness_Step06_DecisionLoop` sample. The
> listed deciders are the .NET owners of the Harness/Loop code (proposed by the contributor; maintainers may adjust
> per `docs/decisions/README.md`). The repository's highest ADR number at the time of writing is `0041`; renumber if
> another ADR lands first.

## Context and Problem Statement

Microsoft Agent Framework (MAF) contains several places where the runtime must make a **bounded decision** rather than
generate open-ended text: should an agent loop continue, has the task been completed, which already-authorized tools or
Skills are relevant for this turn, which participant should act next, should a result be escalated.

Today these decisions are made with application code, deterministic rules, or a generative `IChatClient`. Those remain
valid. A new category of model is emerging whose primary operation is not text generation: it evaluates application
state against one or more **bounded, typed questions** and returns structured probabilistic decisions that application
code consumes directly. TypeSafe AI's **Jev** is the motivating implementation; it exposes three primitives:

- binary yes/no probability (`noul`);
- categorical choice with a probability distribution (`choice`);
- ordered score with a distribution (`score`).

The provider is not the architectural decision. The question is:

> **How should .NET Agent Framework integrate decision-oriented inference without treating it as chat generation,
> without permanently owning a provider-neutral inference abstraction that belongs in `Microsoft.Extensions.AI`,
> and without coupling MAF Core to Jev/TypeSafe, while still being implementable and usable today?**

Related proposals and requests:

- `dotnet/extensions#7764` — provider-neutral decision-model abstraction for `Microsoft.Extensions.AI` (MEAI).
  **Status at the time of writing: opened 2026-09-19 by a community member, `untriaged`, no maintainer response.**
  MEAI 10.10.0, the version this repository references, contains no decision types.
- `microsoft/agent-framework#8545` — .NET: integrate MEAI decision-model inference into agent decision points.
- `microsoft/agent-framework#8556` — Python: first-class support for TypeSafe AI's Jev.

The intended long-term ownership split is unchanged by the MEAI timing:

```text
Microsoft.Extensions.AI      long-term owner of the provider-neutral capability (IDecisionClient)
Microsoft Agent Framework    hosts an experimental reference copy of that contract until MEAI ships it,
                             and consumes it at orchestration seams
Provider packages            own transports (Microsoft.Agents.AI.TypeSafe for Jev; others later)
```

## Terminology

**Generative inference**: `messages -> IChatClient -> generated tokens -> optional structured parsing`. Appropriate for
reasoning, prose/code, tool arguments, free-form critique.

**Decision inference**: `state + bounded typed questions -> decision model -> probabilities / choices / scores`.
Appropriate for "Is the task complete?", "Which candidate applies?", "Where does this fall on an ordered rubric?".

**Decision policy**: the model returns a probability; the framework or application decides what it means
(`continue / stop / shortlist / escalate`). Thresholds and authorization are policy, not model semantics.

**Model-reported probability**: the value a decision model returns. It is not an empirically calibrated accuracy
unless a specific model/provider/workload establishes that property.

### Why this is not just structured `IChatClient` output

An `IChatClient` can be prompted to emit `{"answered": true}`; MAF already supports structured output (ADR-0036).
That provides *syntactic* structure. A decision contract standardizes what `IChatClient` intentionally does not: one
shared state, multiple heterogeneous questions, closed output domains declared before inference, explicit probability
and distributions, batching, and uncertainty that code can reason over. `P(task_complete) = 0.94` is not semantically
equivalent to `LLM-generated JSON -> parse bool -> true`. The distinction is analogous to MEAI having embedding
abstractions rather than modeling embeddings as "ask a chat model to output an array of numbers". This ADR does not
supersede ADR-0036.

## Existing architecture this decision builds on

### `LoopEvaluator` is the judgment seam

```csharp
public abstract class LoopEvaluator
{
    public abstract ValueTask<LoopEvaluation> EvaluateAsync(LoopContext context, CancellationToken cancellationToken = default);
}
```

Implementations: `AIJudgeLoopEvaluator`, `DelegateLoopEvaluator`, `CompletionMarkerLoopEvaluator`,
`TodoCompletionLoopEvaluator`, `BackgroundTaskCompletionLoopEvaluator`. `AIJudgeLoopEvaluator` sends the original
request and the latest response to an `IChatClient`, obtains a structured `JudgeVerdict` (`answered`, `gapAnalysis`),
and continues the loop with the gap analysis as feedback. A decision model is a natural second implementation of the
same seam that returns `P(task_complete)` instead of a verdict plus prose.

### `LoopAgent` ordering already provides a cascade

`LoopAgent` evaluates its evaluators **in order**. The first evaluator returning `Continue(...)` wins and drives the
next iteration; remaining evaluators are not consulted. The loop stops only when **every** evaluator returns `Stop()`.
Therefore `Stop()` means "this evaluator does not request another iteration", not a veto. (Verified in
`LoopAgent.EvaluateAndBuildNextAsync`.)

Ordering `[DecisionLoopEvaluator, AIJudgeLoopEvaluator]` yields an asymmetric cheap-then-strong cascade without any new
abstraction: a cheap "incomplete" skips the expensive judge and re-runs the agent; a cheap "complete" is verified by the
strong judge. A cheap false negative costs one iteration; a cheap false positive is still caught.

`LoopAgent` also shows why continuation feedback matters: in the default reused-session mode, `Continue()` with no
feedback re-invokes the agent with **no new input messages** (`BuildNextMessages`).

## Decision Drivers

- **Provider neutrality**: MAF Core must not depend on TypeSafe, Jev, or any decision-model vendor.
- **Correct abstraction ownership**: the reusable inference capability belongs in MEAI long term. Anything MAF
  defines meanwhile must mirror the upstream proposal so it can be deleted, not migrated.
- **Implementable and usable now**: the first integration must not be blocked on an untriaged upstream proposal, and
  a consumer such as AgentEval must be able to reference one shared contract instead of inventing its own.
- **Semantic clarity**: decision inference is not chat generation.
- **Compatibility**: optional; no change to existing `IChatClient`, agent, tool, Skill, approval, or workflow behavior.
- **Leverage existing seams**: `LoopEvaluator`, `AIContextProvider`, `GroupChatManager`, `AgentSkillsProvider`.
- **Minimal v1 surface**: solve loop completion; no universal selection/routing framework.
- **Safe orchestration**: probabilistic inference is never an authorization or approval mechanism.
- **Data minimization**: a second inference provider is a second external data boundary.
- **Explicit uncertainty and failure**: `P = 0.51` is not truth; provider failure is not "incomplete".
- **Concurrency and AOT**: stateless shareable components; explicit serialized state at the provider boundary.

## Considered Options

1. Represent decision models as `IChatClient` and use structured output.
2. Define a MAF-specific public `IDecisionClient` hierarchy.
3. Add Jev/TypeSafe directly as a MAF Core provider.
4. Keep decision inference entirely application-owned; no first-class MAF integration.
5. Gate MAF entirely on the MEAI abstraction (`dotnet/extensions#7764`) and implement nothing until it ships.
6. MEAI owns the future abstraction; MAF consumes decisions at existing seams through a minimal, evaluator-scoped
   callback now, and adds an `IDecisionClient` overload when MEAI ships it.
7. **MAF hosts an experimental reference implementation of the proposed MEAI contract in
   `Microsoft.Agents.AI.Abstractions`, mirroring `dotnet/extensions#7764`; consumers in Core take `IDecisionClient`;
   the Jev transport lives in a separate `Microsoft.Agents.AI.TypeSafe` provider package.**

## Decision Outcome

Chosen option: **7**, because it is implementable and usable today, keeps MAF Core provider-neutral, gives every
consumer (the loop evaluator, future selectors, and external frameworks such as AgentEval) one contract, and, by
mirroring the upstream proposal verbatim under `[Experimental]`, makes the eventual move to `Microsoft.Extensions.AI`
a namespace change rather than a redesign. Option 6 was the first iteration of this branch; it was superseded once
it became clear that a callback per consumer does not scale beyond the loop and leaves Choice and Score unusable.

### Decision 1: `Microsoft.Agents.AI.Abstractions` hosts an experimental reference copy of the MEAI proposal

The `Decisions/` folder of `Microsoft.Agents.AI.Abstractions` (namespace `Microsoft.Agents.AI`, all types
`[Experimental(MAAI001)]`) defines the contract proposed in `dotnet/extensions#7764`, name for name:

```text
IDecisionClient : IDisposable            GetResponseAsync(DecisionRequest, DecisionOptions?, ct); GetService(Type, key)
DecisionRequest                          JsonElement State; IList<DecisionQuestion> Questions (ids unique)
DecisionOptions                          ModelId, AdditionalProperties, RawRepresentationFactory, Clone()
DecisionQuestion (abstract)              Id, Instructions, AdditionalProperties
  BinaryDecisionQuestion                 Criteria { TrueDescription, FalseDescription }
  ChoiceDecisionQuestion                 IList<DecisionChoice> Choices (unique names, at least two)
  ScoreDecisionQuestion                  IList<DecisionScoreLevel> Levels (ordered, at least two)
DecisionResponse                         Answers keyed by question id, ResponseId, ModelId, UsageDetails Usage, RawRepresentation
DecisionAnswer (abstract)                RawRepresentation, AdditionalProperties
  BinaryDecisionAnswer                   TrueProbability (validated 0..1; no confidence)
  ChoiceDecisionAnswer                   SelectedChoice, Probabilities[name], Confidence?
  ScoreDecisionAnswer                    Score, Probabilities[levelIndex], Confidence?
DecisionClientMetadata                   ProviderName, ProviderUri, DefaultModelId (via GetService)
DecisionClientExtensions                 GetResponseAsync<TState>(state, JsonTypeInfo<TState>, questions); GetService<T>()
```

Two additions go beyond the proposal and are candidates to contribute upstream: `DecisionClientException` with a
`DecisionFailureKind` (`Authentication`, `InvalidRequest`, `RateLimited`, `Overloaded`, `ProviderUnavailable`,
`InvalidResponse`, `Unknown`) and `IsTransient`, so callers can distinguish a retryable condition from a permanent
one; and range validation on the answer types, so an out-of-range probability cannot exist as an object. Both were
adopted from AgentEval's `AgentEval.Decisions` contract (ADR-033 there), which is kept isomorphic to this one.

Provider limits (for example Jev's 255 choices or 10 levels) are not part of the contract; providers enforce them.

### Decision 2: the contract is a staging ground, not a fork

When `Microsoft.Extensions.AI` ships an equivalent abstraction, the MAF types are removed (the experimental
attribute is the licence to do so) and consumers retarget to the MEAI namespace. Mirroring the proposal verbatim is
what keeps that a mechanical change. MAF does not evolve the contract independently: shape changes go to
`dotnet/extensions#7764` first. If MEAI rejects the concept, this ADR is revisited and the types either stay as
MAF's own or move to a satellite package.

### Decision 3: `DecisionLoopEvaluator` is a `LoopEvaluator` over `IDecisionClient`

Takes an `IDecisionClient` and asks one binary question, `"Has the agent fully addressed the user's original request?"` (`QuestionId =
"task_completed"`), and maps the probability through `CompletionThreshold` (default 0.90):

```text
P >= threshold  -> LoopEvaluation.Stop()        (no continuation requested; later evaluators still run)
P <  threshold  -> LoopEvaluation.Continue(ContinueFeedbackMessage)
```

### Decision 4: `AIJudgeLoopEvaluator` is unchanged

They solve different problems. The judge produces a verdict **and** free-form gap analysis; the decision evaluator
produces a bounded probability. A decision model is not forced to fabricate prose.

### Decision 5: continuation carries deterministic, configurable feedback

Default: `"The original request is not yet fully addressed. Continue working on it."` This is application text, not
model output. Setting it to `null`/whitespace continues without feedback (documented consequence: no new input
messages in reused-session mode).

### Decision 6: operational failure is not "incomplete"

A `DecisionClientException` (or any other exception from the client), or a response without a
`BinaryDecisionAnswer` for the completion question, is handled by `DecisionLoopFailureBehavior`. A failure the client
classifies as transient (`DecisionClientException.IsTransient`: rate limit, overload, provider outage) follows the
separate `TransientFailureBehavior` when one is configured, so a loop can survive a hiccup while a rejected key or an
invalid request still surfaces. This adopts the concern raised in `microsoft/agent-framework#8545` (a loop should not
die on a momentary outage) without making "continue" the blanket default. The general policy:

```text
Throw                  (default) propagate
Continue               request another iteration with the feedback message
DeferToNextEvaluator   return Stop() so later evaluators decide; ends the loop if none remain
```

Caller cancellation always propagates. No failure mode is selected implicitly based on provider identity. When a policy
other than throwing is applied, the evaluator logs a warning carrying the exception, its kind, and its transience.

### Decision 7: default state projection is minimal, text-only, and fails loudly

```json
{ "originalRequest": [ { "role": "user", "text": "..." } ], "latestResponse": "...", "iteration": 2 }
```

Serialized through the source-generated `LoopJsonContext`. The evaluator never serializes `AgentSession`, tool
registries, memory, or provider objects. If an original request message contains content other than `TextContent`,
the default projection **throws** with a message pointing at `StateFactory`, instead of silently judging a lossy
representation. `StateFactory` (`Func<LoopContext, JsonElement>`) replaces the projection; the application then owns
the disclosed data. This deliberately differs from `AIJudgeLoopEvaluator`, whose `IChatClient` path can preserve
non-text `AIContent`. (Jev, for reference, accepts text-only state and limits a request to 64k tokens.)

Like `AIJudgeLoopEvaluator`, the default projection judges the **latest** response against the original request. Agents
that build an answer incrementally across turns need a `StateFactory` that accumulates responses (the sample shows one
that keeps its per-run list on `LoopContext.AdditionalProperties`). This was confirmed on the first live run: an agent
answering one sub-question per turn kept scoring `P ≈ 0.04` until it produced a self-contained recap.

### Decision 8: probability and policy stay separate

The evaluator applies `CompletionThreshold`; the callback must not. Documentation uses the term **model-reported
probability**. A false stop returns an incomplete result while a false continue costs one iteration, so a high
threshold is the safer default.

### Decision 9: decision models may shortlist but never authorize (future integrations)

```text
available candidates -> deterministic authorization / trust -> authorized candidates -> decision-model relevance -> subset
```

A decision model may reduce `A, B, C` to `A, C`; it may never introduce `D`. Tool approval (ADR-0006) and hook
enforcement (ADR-0035) are unchanged.

### Decision 10: use existing seams; no generic selector yet

Future tool/Skill shortlisting, group-chat routing, and workflow branching use `AIContextProvider`,
`AgentSkillsProvider`, `GroupChatManager.SelectNextAgentAsync`, and workflow executors. `IAICandidateSelector<T>` is
not added until at least two concrete consumers demonstrate the same stable shape.

### Decision 11: decision inference is not an evaluation framework

`IEvaluator`/`IAgentEvaluator`, Foundry evaluations, and third-party frameworks such as AgentEval are evaluation
operations; they may consume decision inference the same way they consume `IChatClient`.

### Decision 12: Jev lives in the `Microsoft.Agents.AI.TypeSafe` provider package

MAF Core and Abstractions contain no `Jev*`, `Noul*`, or `SystemOne*` types. `TypeSafeDecisionClient` implements
`IDecisionClient` over `POST https://api.typesafe.ai/v1/systemone` (or OpenRouter's relay of the same protocol),
mapping `BinaryDecisionQuestion` to `noul`, `ChoiceDecisionQuestion` to `choice`, and `ScoreDecisionQuestion` to
`score`. It parses strictly (every question answered with the matching kind, every probability in range, the
selected choice among the requested ones, score levels 0-indexed), classifies HTTP failures into
`DecisionFailureKind`, never retries silently, and never puts the API key into an exception. This follows the
repository's provider-package precedent (`.OpenAI`, `.Foundry`, `.CopilotStudio`, ADR-0021) and allocates feature
index 75 (`typesafe`) in the .NET feature-usage registry.

### Decision 13: pin model versions where reproducibility matters

Applications may use the moving alias `jev-latest`. Tests, calibration runs, and benchmarks pin a versioned id such as
`jev-1.13.0` (the TypeSafe id; `typesafe/jev-1.13` was an OpenRouter slug).

### Decision 14: decision inference is an additional external data boundary

Type docs and the sample state what is sent (projected original request + latest response, every iteration) and that
the default excludes session store, memories, tool catalogs, and `AdditionalProperties`.

### Decision 15: telemetry stays with the inference component; the evaluator logs orchestration facts only

The provider owns model-call telemetry. `DecisionLoopEvaluator` accepts an optional `ILoggerFactory` and logs one
debug line per evaluation (iteration, model-reported probability, threshold, outcome) and a warning when a failure
policy is applied. It never logs the projected state. This is the orchestration-level correlation ADR-0003 allows and
`microsoft/agent-framework#8545` asks for, and it doubles as the capture point for calibration and shadow-mode
comparisons without any wrapper client.

## Implemented .NET API

The contract types are listed under Decision 1. The loop consumer:

```csharp
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class DecisionLoopEvaluator : LoopEvaluator
{
    public const double DefaultCompletionThreshold = 0.90;
    public const string DefaultCompletionQuestion = "Has the agent fully addressed the user's original request?";
    public const string DefaultCompletedDescription = "...";
    public const string DefaultIncompleteDescription = "...";
    public const string DefaultContinueFeedbackMessage = "The original request is not yet fully addressed. Continue working on it.";
    public const string CompletionQuestionId = "task_completed";

    public DecisionLoopEvaluator(IDecisionClient decisionClient, DecisionLoopEvaluatorOptions? options = null, ILoggerFactory? loggerFactory = null);
    public override ValueTask<LoopEvaluation> EvaluateAsync(LoopContext context, CancellationToken cancellationToken = default);
}

public sealed class DecisionLoopEvaluatorOptions
{
    public double CompletionThreshold { get; set; } = 0.90;          // 0..1, validated at construction
    public string? CompletionQuestion { get; set; }                    // null -> default; blank -> ArgumentException
    public string? CompletedDescription { get; set; }                  // null -> omitted
    public string? IncompleteDescription { get; set; }
    public string? ContinueFeedbackMessage { get; set; }               // null/blank -> continue without feedback
    public Func<LoopContext, JsonElement>? StateFactory { get; set; }
    public DecisionLoopFailureBehavior FailureBehavior { get; set; } = DecisionLoopFailureBehavior.Throw;
    public DecisionLoopFailureBehavior? TransientFailureBehavior { get; set; }   // null -> FailureBehavior
}

public enum DecisionLoopFailureBehavior { Throw, Continue, DeferToNextEvaluator }
```

The provider:

```csharp
namespace Microsoft.Agents.AI.TypeSafe;

public sealed class TypeSafeDecisionClient : IDecisionClient
{
    public TypeSafeDecisionClient(string apiKey, TypeSafeDecisionClientOptions? options = null, HttpClient? httpClient = null);
    public Uri Endpoint { get; }
    public string ModelId { get; }
}

public sealed class TypeSafeDecisionClientOptions
{
    public const string DefaultEndpoint = "https://api.typesafe.ai/v1/systemone";
    public const string OpenRouterEndpoint = "https://openrouter.ai/api/v1/systemone";
    public const string DefaultModelId = "jev-latest";
    public Uri Endpoint { get; set; }
    public string ModelId { get; set; }
    public TimeSpan Timeout { get; set; }
}
```

Files: `dotnet/src/Microsoft.Agents.AI.Abstractions/Decisions/*.cs` (contract);
`dotnet/src/Microsoft.Agents.AI/Harness/Loop/DecisionLoopEvaluator.cs`, `DecisionLoopEvaluatorOptions.cs`,
`DecisionLoopFailureBehavior.cs`, `DecisionLoopState.cs` (internal projection), plus one `[JsonSerializable]` line in
`LoopJsonContext.cs` (consumer); `dotnet/src/Microsoft.Agents.AI.TypeSafe/*.cs` (provider).

## Composition patterns

### Decision model only

```csharp
var loop = new LoopAgent(
    innerAgent,
    new DecisionLoopEvaluator(jev, new() { CompletionThreshold = 0.95 }),
    new LoopAgentOptions { MaxIterations = 8 });
```

### Cheap decision + strong generative verifier (recommended)

```csharp
var loop = new LoopAgent(
    innerAgent,
    [
        new DecisionLoopEvaluator(jev, new()
        {
            CompletionThreshold = 0.95,
            TransientFailureBehavior = DecisionLoopFailureBehavior.DeferToNextEvaluator,
        }),
        new AIJudgeLoopEvaluator(strongJudgeChatClient),
    ],
    new LoopAgentOptions { MaxIterations = 8 });
```

```text
decision: incomplete      -> Continue -> strong judge not called -> agent runs again
decision: complete        -> Stop -> strong judge runs -> Continue + gap analysis | Stop -> loop ends
decision: transient failure -> Stop (defer) -> strong judge runs; permanent failure -> throws
```

### Provider and direct use (from the sample)

```csharp
using IDecisionClient jev = new TypeSafeDecisionClient(apiKey, new() { ModelId = "jev-1.13.0" });

DecisionResponse response = await jev.GetResponseAsync(new DecisionRequest(state,
[
    new BinaryDecisionQuestion("refund_requested", "Does the customer request a refund?"),
    new ChoiceDecisionQuestion("request_type", "What is the main request?", [new("refund"), new("rebooking"), new("information")]),
    new ScoreDecisionQuestion("frustration", "How frustrated is the customer?", [new("calm"), new("concerned"), new("angry")]),
]));

var refund = (BinaryDecisionAnswer)response.Answers["refund_requested"];   // refund.TrueProbability
```

The evaluator applies the completion threshold; a client never does.

## Security model

- **No authority**: identity, authorization, resource access, tool permission, approval, secrets, and privilege remain
  deterministic policy. A probability is a signal after those boundaries are established.
- **No approval bypass**: ADR-0006 unchanged. A selected or judged tool still follows approval semantics.
- **Deterministic policy wins where provable**: do not replace `if forbidden -> block` with "ask a decision model".
- **Untrusted state**: decision models consume user- and tool-provided content and can be manipulated like generative
  models. Authorization precedes selection; outputs are not proof; data is minimized; security-critical uncertainty
  escalates or falls back to deterministic policy. Complements ADR-0024 and ADR-0035.
- **Manipulated probabilities** can end a loop early (incomplete result) or prolong it (cost); `MaxIterations` bounds
  the latter, and the strong-judge cascade mitigates the former.

## Privacy and data boundary

A decision source may be a different provider from the primary `IChatClient`, creating a second data processor. Type
docs state what is sent. The default projection excludes persisted history beyond the original request, unrelated
memory, secrets, tool catalogs, provider-internal objects, and ambient service state. `StateFactory` users own what
they add.

## Failure and uncertainty semantics

| Situation | Meaning | Behavior |
| --- | --- | --- |
| auth failure, invalid request, malformed response, invalid probability | permanent operational failure | `FailureBehavior` (default `Throw`) |
| rate limit, overload, provider outage (`IsTransient`) | transient operational failure | `TransientFailureBehavior`, else `FailureBehavior` |
| Non-text original request with default projection | configuration error | always throws (points at `StateFactory`) |
| `P < threshold` | valid semantic result | `Continue(feedback)` |
| `P >= threshold` | valid semantic result | `Stop()` (no continuation requested) |
| caller cancellation | cancellation | propagates |

A future API may add an explicit uncertainty band (`confident incomplete / uncertain / confident complete`) with two
thresholds. Not required in v1: the ordered-evaluator chain already provides conservative cheap-then-strong
verification.

## Validation

The implementation is compliant with this ADR when:

1. The decision contract in `Microsoft.Agents.AI.Abstractions` mirrors `dotnet/extensions#7764` name for name, is
   `[Experimental]`, and adds only the exception model and range validation. ✔
2. MAF Core and Abstractions have no dependency on Jev or TypeSafe; the transport is in `Microsoft.Agents.AI.TypeSafe`. ✔
3. `DecisionLoopEvaluator` is a `LoopEvaluator`. ✔
4. `AIJudgeLoopEvaluator` behavior is unchanged. ✔ (existing tests pass)
5. Provider failure is never interpreted as a semantic probability. ✔ (evaluator tests for all three policies and a
   missing/mismatched answer; provider tests for every HTTP class, unusable bodies, and out-of-range values)
6. The default projection never silently discards material non-text input. ✔ (throws; `StateFactory` path tested)
7. Tool authorization/approval semantics are unchanged. ✔ (no changes outside `Harness/Loop`)
8. The evaluator composes with ordered loop evaluators as described. ✔ (LoopAgent composition tests)
9. Model-call telemetry remains with the provider; the evaluator logs orchestration facts only and never the state. ✔ (tested)
10. Existing agents behave exactly as before unless the evaluator is configured. ✔

Tests: `dotnet/tests/Microsoft.Agents.AI.UnitTests/Harness/Loop/DecisionLoopEvaluatorTests.cs` (evaluator: construction
validation, threshold boundaries, feedback, request contents and projection, criteria omission, non-text rejection,
`StateFactory`, all failure policies, transient versus permanent failures, missing/mismatched answer, cancellation,
provider-side `OperationCanceledException`, logging content and redaction, concurrency, and `LoopAgent` cascade behavior) and
`dotnet/tests/Microsoft.Agents.AI.TypeSafe.UnitTests/*.cs` (provider: request serialization for all three kinds,
provider limits, duplicate ids, strict parsing of a mixed batch, OpenRouter extras, every unusable-body case,
HTTP failure classification, bearer/endpoint/model override, redaction, network failure, cancellation, `GetService`,
feature-usage marking). The feature-registry validation test covers the new index.

## Consequences

### Positive

- MAF gains a genuinely different inference capability at an existing seam without coupling Core to a vendor.
- One contract for every consumer today (loop evaluator, AgentEval, future selectors); deletion rather than
  migration when MEAI ships, because the shape is the upstream proposal's.
- `AIJudgeLoopEvaluator` and `DecisionLoopEvaluator` stay semantically distinct.
- Existing evaluator ordering yields a cost-reducing cascade with no new orchestration engine.
- Probabilities remain available to policy instead of being flattened into generated JSON.
- Evaluation frameworks can reuse the same pattern (a probability source behind a callback) without MAF internals.

### Negative / trade-offs

- Another concept for developers to understand next to `IChatClient`.
- A separate decision provider is another external data boundary.
- Model-reported probabilities require workload-specific calibration and thresholds.
- Not all inputs have a lossless JSON representation; non-text requests need a `StateFactory`.
- Until MEAI ships, MAF carries a contract it does not intend to own; the experimental attribute and the verbatim
  mirroring bound that cost, but a divergent MEAI review outcome would still force a rename for early adopters.
- Neutral: some workloads remain better served by deterministic code or an `IChatClient` judge.

## Pros and Cons of the Options

### Option 1: `IChatClient` + structured output

- Good: broad existing integration; `AIJudgeLoopEvaluator` reusable unchanged.
- Bad: falsely advertises chat semantics; loses probability/distribution semantics; conflates syntactic structure with
  a distinct capability; encourages prose expectations a decision model does not satisfy.

### Option 2: MAF-specific public `IDecisionClient`

- Good: no waiting on MEAI; MAF controls the shape.
- Bad: decision inference is not agent-specific; duplicates a lower-layer abstraction; incompatible contracts across
  frameworks; avoidable public-API migration cost later.

### Option 3: Jev/TypeSafe directly in MAF Core

- Good: fast and ergonomic for one provider.
- Bad: vendor coupling; `Noul`/`System One` vocabulary leaks into the framework; parallel concepts for every provider.

### Option 4: application-owned only

- Good: no new Core types; existing extension points suffice for prototypes.
- Bad: every application rebuilds projection, question, threshold, failure policy, security docs; inconsistent seams;
  users may wrap decision providers as chat clients for convenience.

### Option 5: fully gated on MEAI

- Good: purest layering.
- Bad: not implementable today; `dotnet/extensions#7764` is untriaged with no maintainer signal; blocks samples,
  tests, calibration work, and the AgentEval integration indefinitely.

### Option 6: MEAI owns the future abstraction; evaluator-scoped callback now (superseded)

- Good: implementable today; no abstraction at all in MAF; follows the `DelegateLoopEvaluator` precedent.
- Bad: one callback per consumer does not scale to tool/Skill selection, routing, or workflows; Choice and Score are
  unusable; external consumers such as AgentEval get nothing to reference and invent their own contract.

### Option 7: experimental reference copy of the MEAI proposal in Abstractions; provider package for Jev (chosen)

- Good: implementable and usable today; one contract for all consumers; verbatim mirroring makes the MEAI transition a
  deletion; provider stays out of Core; follows the repository's provider-package precedent; gives `dotnet/extensions#7764`
  a working implementation, a provider, and consumers as evidence.
- Neutral: MAF temporarily carries a contract it does not intend to own.
- Bad: if MEAI's review lands a materially different shape, early adopters face a rename; developers must understand
  generation vs. decision inference; a second provider adds operational complexity.

## Cross-SDK considerations

The conceptual rule is cross-SDK: `decision model != chat model`, `provider transport != orchestration policy`,
`authorization != probabilistic selection`. Python may expose an analogous decision client through its provider
ecosystem (`microsoft/agent-framework#8556`) without mirroring the .NET types.

## Related ADRs

| ADR | Relationship |
| --- | --- |
| [ADR-0002 Agent Tools](0002-agent-tools.md) | Future tool shortlisting operates only over already-available/authorized tools. |
| [ADR-0003 Agent OpenTelemetry Instrumentation](0003-agent-opentelemetry-instrumentation.md) | Inference telemetry stays with the inference component; MAF adds orchestration-level facts only. |
| [ADR-0006 User Approval](0006-userapproval.md) | Decision inference never grants or bypasses approval. |
| [ADR-0014 Feature Collections](0014-feature-collections.md) / [ADR-0017 Additional Properties](0017-agent-additional-properties.md) | Future per-run decision policy should reuse existing extension mechanisms. |
| [ADR-0015 AgentRunContext](0015-agent-run-context.md) | Reuse run context rather than a parallel context abstraction. |
| [ADR-0021 Provider-Leading Client Design](0021-provider-leading-clients.md) | Provider transports stay out of core abstractions. |
| [ADR-0023 Evaluation Architecture](0023-foundry-evals-integration.md) | Evaluators may consume decision inference; it does not replace evaluation abstractions. |
| [ADR-0024 Prompt Injection Defense](0024-prompt-injection-defense.md) / [ADR-0035 Agent-Hooks Enforcement](0035-dotnet-agent-hooks-enforcement.md) | Decision models are signals; deterministic enforcement remains authoritative. |
| [ADR-0036 Structured Output](0036-structured-output.md) | Most important semantic comparison; not superseded. |
| [ADR-0037 Agent Skills](0037-agent-skills-design.md) | Future Skill shortlisting selects among trusted Skills only. |
| [ADR-0038 CodeAct Integration](0038-codeact-integration.md) | Precedent for optional dependencies outside core and reuse of context-provider seams. |

## Related issues and external references

- [microsoft/agent-framework#8545](https://github.com/microsoft/agent-framework/issues/8545) — .NET decision-model integration request.
- [microsoft/agent-framework#8556](https://github.com/microsoft/agent-framework/issues/8556) — Python Jev request.
- [microsoft/agent-framework#8562](https://github.com/microsoft/agent-framework/issues/8562) — this proposal: .NET `IDecisionClient` reference implementation, `DecisionLoopEvaluator`, and the TypeSafe provider package.
- [dotnet/extensions#7764](https://github.com/dotnet/extensions/issues/7764) — MEAI provider-neutral decision abstraction proposal.
- [TypeSafe documentation](https://docs.typesafe.ai/) — API: `POST /v1/systemone`; primitives `noul`/`choice`/`score`; models `jev-1.13.0`, `jev-latest`, `jev-preview`.

## Implementation sequence

1. **This PR**: ADR, the `IDecisionClient` contract in Abstractions, `DecisionLoopEvaluator` + options + failure
   behavior, the `Microsoft.Agents.AI.TypeSafe` provider, unit tests for all three, PublicAPI baselines, feature
   index 75, `Harness_Step06_DecisionLoop` sample (loop, cascade, direct mixed batch), Harness README updates.
2. **Upstream**: comment on `dotnet/extensions#7764` with this implementation as evidence; when MEAI lands the
   abstraction, delete the Abstractions copy and retarget consumers and the provider.
3. **Calibration**: use the sample's probability output (and AgentEval) to compare `DecisionLoopEvaluator` vs.
   `AIJudgeLoopEvaluator` vs. human labels on real loops; track false-stop rate separately.
4. **Tool-selection experiment** via `AIContextProvider`; **Skill-selection experiment** via `AgentSkillsProvider`.
5. **Generic selector** only if (4) demonstrates a stable shared shape; separate ADR.

## Revisit criteria

1. MEAI accepts, changes, or rejects a provider-neutral decision abstraction.
2. Multiple providers show incompatible semantics that make a shared shape misleading.
3. Selection use cases need a generic abstraction not expressible through existing seams.
4. Calibration shows model-reported probabilities are not useful enough for runtime policy.
5. Cross-SDK experience shows unacceptable conceptual divergence.

## One-sentence design principle

> **Let generative models generate, let deterministic policy authorize, and let decision models make bounded
> probabilistic judgments where a full generative call is unnecessary.**
