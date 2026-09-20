# What this sample demonstrates

This sample demonstrates **`DecisionLoopEvaluator`**, a `LoopEvaluator` for `LoopAgent` that judges loop completion with a
*decision-oriented* model instead of a generative one. After each iteration it asks a decision source a single bounded
yes/no question ("Has the agent fully addressed the user's original request?") and receives a **model-reported
probability**. The evaluator compares that probability with a configured completion threshold: at or above it the
evaluator stops requesting iterations, below it the loop continues with a deterministic feedback message.

TypeSafe's **Jev** ("System One" model) is the decision model used here. Jev does not generate text: it evaluates a
piece of state against typed questions and returns probabilities directly, at a fraction of the latency and cost of a
generative judge. It is reached through the provider-neutral **`IDecisionClient`** abstraction
(`Microsoft.Agents.AI.Abstractions`, experimental, mirroring the shape proposed for `Microsoft.Extensions.AI` in
[dotnet/extensions#7764](https://github.com/dotnet/extensions/issues/7764)) and its TypeSafe implementation,
`TypeSafeDecisionClient` in the **`Microsoft.Agents.AI.TypeSafe`** package. The core framework has **no dependency** on
Jev or TypeSafe: `DecisionLoopEvaluator` only sees an `IDecisionClient`. The sample wraps the client in a small delegating
[`ConsoleObservingDecisionClient`](./ConsoleObservingDecisionClient.cs) that prints every probability.

## Looping patterns showcased

| # | Pattern | Evaluators | Notes |
| --- | --- | --- | --- |
| 1 | Decision-only loop | `DecisionLoopEvaluator` + `StateFactory` | Jev judges completion after every iteration. The loop stops once `P(complete) >= 0.90`. Because the agent spreads its answer across turns, a `StateFactory` sends Jev the original request plus **every response so far** (kept per run in `LoopContext.AdditionalProperties`). The console prints the probability, model id, and input tokens for each iteration. |
| 2 | Cheap-then-strong cascade | `DecisionLoopEvaluator` → `AIJudgeLoopEvaluator` | Uses the default latest-response projection for both evaluators, so they judge the same evidence. Jev runs first. While it says "incomplete" the loop continues immediately and the expensive generative judge is skipped. Once Jev says "complete", the AI judge verifies and can still send the loop back with a gap analysis. No new cascade abstraction is needed: this is existing `LoopAgent` ordering (first evaluator to request continuation wins; the loop stops only when every evaluator stops). |
| 3 | Direct decisions | `IDecisionClient` | One batched call with a binary, a choice, and a score question against the same state, printing the probability, the selected choice with its distribution, and the weighted score with its level distribution. |

The agent is deliberately instructed to answer only **one** of the three sub-questions per response, so each loop
visibly needs several iterations. `MaxIterations` caps every loop so it always terminates.

### How `DecisionLoopEvaluator` differs from `AIJudgeLoopEvaluator`

| | `AIJudgeLoopEvaluator` | `DecisionLoopEvaluator` |
| --- | --- | --- |
| Backed by | generative `IChatClient` | any `IDecisionClient` (decision model, or a test double) |
| Returns | verdict **and** free-form gap analysis | probability only |
| Feedback on continue | judge's gap analysis | deterministic `ContinueFeedbackMessage` |
| Threshold | none (boolean verdict) | `CompletionThreshold`, application policy |
| On provider failure | throws | `FailureBehavior`: `Throw` (default), `Continue`, or `DeferToNextEvaluator`; `TransientFailureBehavior` applies separately to rate limits, overload, and outages (`DecisionClientException.IsTransient`) |

Neither replaces the other; pattern 2 shows why they compose well.

## Prerequisites

1. An OpenAI API key, **or** an API key for any OpenAI-compatible chat-completions endpoint (for example Bitdeer with
   `zai-org/GLM-5.3-Flash`), for the primary agent and the generative judge.
2. A TypeSafe API key for Jev (https://typesafe.ai).

## Environment Variables

```bash
# Primary agent + AI judge — option A: OpenAI
export OPENAI_API_KEY="sk-..."
# Optional: chat model (defaults to gpt-5.4-mini)
export OPENAI_CHAT_MODEL_NAME="gpt-5.4-mini"

# Primary agent + AI judge — option B: any OpenAI-compatible endpoint (example: Bitdeer + GLM-5.3-Flash)
export OPENAI_COMPATIBLE_ENDPOINT="https://api-inference.bitdeer.ai/v1"
export OPENAI_COMPATIBLE_API_KEY="..."
export OPENAI_COMPATIBLE_MODEL="zai-org/GLM-5.3-Flash"

# Required: decision model (TypeSafe System One / Jev)
export TYPESAFE_API_KEY="ts-..."
# Optional: Jev model id (defaults to jev-latest; pin e.g. jev-1.13.0 for reproducible runs)
export TYPESAFE_MODEL="jev-latest"
```

## Running the Sample

```bash
cd dotnet
dotnet run --project samples/02-agents/Harness/Harness_Step06_DecisionLoop
```

> OpenAI-compatible does not mean behaviorally identical: structured output, tool calling, and streaming details vary
> by provider. `AIJudgeLoopEvaluator` falls back to text verdict markers when a provider ignores structured output.

## What to Expect

Each loop is executed with `RunStreamingAsync`, so output is printed live and every re-invocation of the inner agent is
marked with a `--- run N ---` header. After each run a `[Jev] iteration N: P(complete) = 0.xxx` line shows the
model-reported probability. In pattern 1 the first runs score low (one or two of three questions answered) and the loop
stops once the accumulated responses cover the whole request, typically after the third run. In pattern 2 the agent
only stops once a single response stands on its own as complete (usually a recap on the fourth run); you additionally
see `[AI judge] ...` lines only when Jev believed the work was complete, and a final count of generative judge calls,
which is smaller than the number of iterations.

Observed on a reference run (Jev `jev-1.13.0`, Bitdeer `zai-org/GLM-5.3-Flash`): pattern 1 produced 0.04, 0.07, 0.97 and
stopped after three runs; pattern 2 produced 0.04, 0.05, 0.05, 0.95 across four runs and called the generative judge
once, which confirmed completion; pattern 3 returned `refund_requested` P=0.99, `request_type` = refund (1.00), and a
frustration score of 1.09 on 0..2 with P(level 1) = 0.91.

## Design notes

- **Thresholds are policy, not model semantics.** A false stop returns an incomplete answer while a false continue only
  costs an extra iteration, so the sample uses a deliberately high threshold (0.90). Calibrate it for your workload;
  `P = 0.90` is a model-reported value, not an empirical accuracy guarantee.
- **Minimal state.** By default the evaluator sends only the text of the original request messages, the latest response
  text, and the iteration number. Requests containing non-text content (images, data) are rejected rather than silently
  flattened; supply `DecisionLoopEvaluatorOptions.StateFactory` to judge those. Jev accepts text-only state and limits a
  request to 64k tokens (32k for state).
- **Latest response vs. accumulated responses.** The default projection, like `AIJudgeLoopEvaluator`, judges the latest
  response against the original request. That is right for agents that produce a complete answer each turn. For agents
  that build the answer incrementally, use a `StateFactory` that accumulates (pattern 1); keep the accumulated list on
  `LoopContext.AdditionalProperties` so the evaluator stays stateless and shareable, and mind the provider's state limit.
- **Failure is not "incomplete".** A provider error is handled by `FailureBehavior`, never converted into a low
  probability. Pattern 2 sets `TransientFailureBehavior = DeferToNextEvaluator` so the AI judge decides when Jev is
  momentarily unavailable, while a permanent failure (rejected key, invalid request) still surfaces. Pass an
  `ILoggerFactory` to the evaluator to get one debug line per decision (iteration, probability, threshold, outcome) and a
  warning whenever a failure policy is applied; the projected state is never logged.

## Security Considerations

`DecisionLoopEvaluator` is an explicit opt-in to sending the projected original request and the agent's latest response
to an additional external inference boundary on every iteration. A compromised decision endpoint could exfiltrate that
data or return manipulated probabilities that prematurely end (or needlessly prolong) the loop. Only configure a decision
source you trust as much as the primary model, keep the state projection minimal, and never use the probability as an
authorization or approval signal. Pattern 2 additionally uses `AIJudgeLoopEvaluator`; see
[Harness_Step05_Loop](../Harness_Step05_Loop/README.md#security-considerations) for its considerations.
