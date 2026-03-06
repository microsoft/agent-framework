# Context Compaction: Cross-Implementation Alignment Analysis

**Author**: GitHub Copilot  
**Date**: 2026-03-06  
**References**:
- Spec: [ADR-0019 – Context Compaction Strategy](../decisions/0019-python-context-compaction-strategy.md)
- Python PR: [#4469 – Python: Implement annotation-based context compaction](https://github.com/microsoft/agent-framework/pull/4469)
- .NET PR: [#4496 – .NET Compaction – Introducing compaction strategies and pipeline](https://github.com/microsoft/agent-framework/pull/4496)

---

## 1. Overview

ADR-0019 defines a cross-language compaction design for long-running agents. This document
analyses how the Python (PR #4469) and .NET (PR #4496) implementations align with the spec
and with each other, highlighting areas of agreement, divergence, and gaps.

---

## 2. Spec Decision Recap

The spec chose **Option 1** (Standalone `CompactionStrategy` object) with **Variant F2**
(`_`-annotated messages) as the primary implementation model. Key properties of this choice:

| Property | Spec Decision |
|---|---|
| **Core model** | F2: compaction state stored as `_`-prefixed `additional_properties` on messages; no sidecar container |
| **Strategy interface** | `Protocol` with `async __call__(messages: list[Message]) -> bool` |
| **Ownership of `_` attrs** | `BaseChatClient` exclusively — function-calling layer stays attribute-unaware |
| **Tokenizer** | `TokenizerProtocol` protocol; `BaseChatClient.tokenizer` attribute |
| **Composition** | `TokenBudgetComposedStrategy` as the spec-recommended "opinionated" composed strategy |
| **Trigger** | Strategy-internal short-circuit guard (call strategy every iteration; no-op when under threshold) |
| **Compaction points** | In-run, pre-write, existing-storage |
| **F1 status** | "Valid alternative" — explicitly documented but not the preferred choice |

---

## 3. Python PR #4469 — Alignment with Spec

### 3.1 What aligns

| Aspect | Spec | Python |
|---|---|---|
| **Variant** | F2 (message annotations) | ✅ F2 — state on `additional_properties` via `annotate_message_groups()` |
| **Protocol interface** | `async __call__(messages: list[Message]) -> bool` | ✅ Exact match |
| **Tokenizer protocol** | `TokenizerProtocol.count_tokens(text) -> int` | ✅ Exact match; `CharacterEstimatorTokenizer` as default fallback |
| **`BaseChatClient` ownership** | `compaction_strategy`, `tokenizer` attributes | ✅ Both added; propagated from `Agent` into client |
| **Per-call compaction** | Before every `get_response`, with compaction | ✅ `_prepare_messages_for_model_call()` called before every model call |
| **Composition** | `TokenBudgetComposedStrategy` as opinionated default | ✅ Shipped and matches spec signature exactly |
| **Strategy-internal trigger** | Short-circuit guard inside strategy | ✅ Strategies check thresholds internally |
| **Atomic groups** | Tool-call + results treated atomically | ✅ Enforced by `annotate_message_groups()` and all strategy implementations |
| **Built-in strategies** | `TruncationStrategy`, `SlidingWindowStrategy`, `SummarizationStrategy`, selective-tool | ✅ All four shipped |
| **Agent parameters** | `compaction_strategy`, `tokenizer` on `Agent`; propagated to client | ✅ Exact match |
| **`apply_compaction()` helper** | Mentioned in implementation guidance | ✅ Public helper shipped |
| **`included_messages()`, `included_token_count()`** | Public utility functions | ✅ Exported from package |
| **In-run integration** | Compaction runs inside `BaseChatClient.get_response` | ✅ Confirmed |

### 3.2 Gaps and deviations

| Area | Spec requirement | Python status |
|---|---|---|
| **Pre-write compaction** | `HistoryProvider` `compaction_strategy` parameter; compact before `save_messages()` | ⚠️ **Phase 2 only** — not in PR #4469 |
| **Existing-storage compaction** | `compact_storage()` / `compact()` method on `HistoryProvider` | ⚠️ **Phase 2 only** |
| **`store_excluded_messages`** | Option to persist excluded vs. included messages | ⚠️ **Phase 2 only** |
| **Incremental annotation** | Annotate only newly appended messages (not full re-scan every roundtrip) | ✅ Implemented via `_first_unannotated_index()` / `_reannotation_start()` |
| **Reasoning-message handling** | Spec calls out the OpenAI Responses API (the newer `/v1/responses` endpoint) reasoning content as atomic with tool-call groups | ⚠️ Not explicitly handled in Phase 1 (`.tool_calls` check only) |

### 3.3 Phase split

The Python PR explicitly splits work across two phases:

- **Phase 1 (PR #4469)**: Runtime compaction primitives in `_compaction.py`, in-run integration, tests, samples (`basics`, `advanced`, `custom`).
- **Phase 2 (PR 2)**: History/storage compaction (`upsert`-based full replacement), provider support, storage tests, storage sample.

This phasing aligns with the spec's acknowledgement of pre-write compaction as a non-trivial extension requiring storage overwrite support.

---

## 4. .NET PR #4496 — Alignment with Spec

### 4.1 What aligns

| Aspect | Spec | .NET |
|---|---|---|
| **Compaction points covered** | In-run, pre-write, existing-storage | ✅ In-run via `CompactingChatClient`; pre-write/existing-storage via `IChatReducer` on `InMemoryChatHistoryProvider` |
| **Atomic groups** | Tool-call + results atomic | ✅ Enforced by `MessageIndex` grouping algorithm |
| **Spec grouping kinds** | `system`, `user`, `assistant_text`, `tool_call` | ✅ All present; .NET adds `Summary` |
| **In-run integration** | Innermost in pipeline, before LLM calls incl. tool-loop iterations | ✅ `CompactingChatClient` inserted before `FunctionInvokingChatClient` |
| **Composition** | Multiple strategies composable | ✅ `PipelineCompactionStrategy` |
| **Trigger mechanism** | Configurable threshold-based trigger | ✅ `CompactionTrigger` predicate; `CompactionTriggers` factory methods |
| **Preserve system messages** | Strategies should not remove system messages | ✅ All strategies check `Kind != MessageGroupKind.System` |
| **Incremental processing** | Avoid re-processing entire history every call | ✅ `MessageIndex.Update()` appends delta only |
| **State persistence** | Compaction state survives across turns (session serialization) | ✅ `CompactingChatClient.State` serialized into `AgentSession.StateBag` |
| **Built-in strategies** | `TruncationStrategy`, `SlidingWindowStrategy`, `SummarizationStrategy`, selective-tool | ✅ All four shipped, plus `ChatReducerCompactionStrategy` |
| **`MinimumPreserved` floor** | Strategies must have a hard floor | ✅ Every strategy has `MinimumPreserved` param |
| **`IChatReducer` bridge** | Spec notes .NET had `IChatReducer`; new design should be compatible | ✅ `ChatReducerCompactionStrategy` bridges existing reducers |
| **Turn tracking** | Not spec-required but natural for `SlidingWindowCompactionStrategy` | ✅ `MessageGroup.TurnIndex` enables turn-level exclusion |
| **Streaming support** | Compaction should work for streaming calls | ✅ `CompactingChatClient` overrides both `GetResponseAsync` and `GetStreamingResponseAsync` |

### 4.2 Gaps and deviations

| Area | Spec requirement | .NET status |
|---|---|---|
| **Chosen variant** | Spec chose **F2** (message annotations), explicitly noted F1 as "valid alternative" | ⚠️ **Uses F1** (sidecar `MessageIndex` / `MessageGroup`). Intentional, leverages C# type system and session serialization. |
| **Strategy interface** | `Protocol` / interface with single `__call__` | ⚠️ Abstract base class (`CompactionStrategy`) rather than interface. `ApplyCompactionAsync` is abstract; base class handles trigger evaluation and metrics logging. |
| **`TokenBudgetComposedStrategy`** | Spec-recommended opinionated composed strategy enforcing a token budget | ❌ **Not implemented.** `.NET` uses `PipelineCompactionStrategy`, which sequences strategies but does not enforce a budget target. |
| **Pre-write via `CompactionStrategy`** | Spec: `HistoryProvider.compaction_strategy` param | ⚠️ Pre-write uses `IChatReducer` (existing MEAI) rather than `CompactionStrategy`. The two pipelines are not unified. |
| **`CompactionStrategy` on `InMemoryChatHistoryProvider`** | Spec envisions single strategy reusable across in-run and pre-write | ⚠️ `InMemoryChatHistoryProvider` uses `IChatReducer`, not `CompactionStrategy`. Users must configure two separate mechanisms if they want both. |
| **Source-attribution-aware compaction** | Spec describes `source_id` from ADR-0016 as input to strategy decisions | ❌ Not surfaced in any built-in .NET strategy (compaction decisions are role/token/turn based only). |
| **`Summary` group kind** | Not in spec | 🆕 .NET addition. Useful for `SummarizationCompactionStrategy` output, but Python doesn't have an equivalent enum value. |
| **Reasoning-message handling** | Spec calls out the OpenAI Responses API (`/v1/responses` endpoint, used by reasoning models) reasoning content as atomic with tool-call groups | ❌ Not handled in .NET grouping algorithm. |

---

## 5. Cross-Language Comparison

### 5.1 Side-by-side summary

| Dimension | Spec | Python PR #4469 | .NET PR #4496 |
|---|---|---|---|
| **Core data model** | F2 (message attrs) | ✅ F2 | ⚠️ F1 (sidecar `MessageIndex`) |
| **Strategy interface** | `Protocol` / callable | ✅ `Protocol` with `__call__` | ⚠️ Abstract base class with `ApplyCompactionAsync` |
| **Trigger mechanism** | Strategy-internal guard | ✅ Strategy-internal | ⚠️ Explicit `CompactionTrigger` predicate evaluated before dispatch |
| **Tokenizer** | `TokenizerProtocol` (extensible) | ✅ Protocol; `CharacterEstimatorTokenizer` default | ✅ `Microsoft.ML.Tokenizers.Tokenizer`; byte/4 fallback |
| **In-run integration** | Inside chat client before every model call | ✅ `BaseChatClient._prepare_messages_for_model_call` | ✅ `CompactingChatClient` (innermost in pipeline) |
| **State continuity** | Annotations persist on messages (F2) | ✅ via `additional_properties` on messages | ✅ `CompactingChatClient.State` in session bag |
| **Incremental updates** | Annotate/process only new messages | ✅ `_first_unannotated_index()` | ✅ `MessageIndex.Update()` |
| **Composition model** | `TokenBudgetComposedStrategy` | ✅ Shipped | ❌ `PipelineCompactionStrategy` (no budget enforcement) |
| **Pre-write compaction** | `HistoryProvider.compaction_strategy` | ⏳ Phase 2 | ⚠️ Via `IChatReducer` (separate mechanism) |
| **Tool-call collapse strategy** | Mentioned as "selective removal" | ✅ `SelectiveToolCallCompactionStrategy` | ✅ `ToolResultCompactionStrategy` |
| **Summarization** | `SummarizationStrategy` | ✅ | ✅ |
| **Truncation** | `TruncationStrategy` | ✅ | ✅ `TruncationCompactionStrategy` |
| **Sliding window** | `SlidingWindowStrategy` | ✅ | ✅ `SlidingWindowCompactionStrategy` |
| **`IChatReducer` bridge** | Noted as .NET-specific prior art | ➖ N/A | ✅ `ChatReducerCompactionStrategy` |
| **Summary group kind** | Not specified | ❌ Not present | 🆕 `MessageGroupKind.Summary` |
| **Reasoning-message atomicity** | Spec requires it for the OpenAI Responses API | ❌ Not present | ❌ Not present |
| **Turn tracking** | Not specified | ❌ Not present | 🆕 `MessageGroup.TurnIndex` |
| **Source attribution** | `source_id` usable by strategies | ⚠️ Available on messages but no built-in strategy uses it | ❌ Not surfaced |
| **Streaming support** | Implied requirement | ✅ | ✅ |
| **`[EXPERIMENTAL]` gate** | N/A | `_compaction.py` (internal convention) | ✅ `[Experimental]` attribute on all public types |

### 5.2 Shared strengths

Both implementations share the following design-correct properties:

1. **Atomic group preservation** — tool-call + result messages are always grouped and excluded/included together.
2. **Strategy-level trigger short-circuit** — strategies no-op cheaply when not needed (Python: internal guard; .NET: `Trigger` predicate).
3. **System message protection** — all strategies explicitly preserve system messages.
4. **Incremental processing** — both avoid re-processing the full message list every call.
5. **In-run scope** — compaction fires before every model call, covering both single-shot and tool-loop iterations.
6. **Session state** — compaction state is retained across turns so exclusion decisions accumulate.
7. **`MinimumPreserved` floor** (.NET) / threshold semantics (Python) — both prevent strategies from compacting too aggressively.

### 5.3 Areas of divergence

#### F2 vs. F1 data model

The spec chose F2 (state on messages) because it avoids a sidecar, aligns with `BaseChatClient` statelessness, and keeps compaction localized to the chat client. The .NET PR uses F1 (sidecar `MessageIndex`), which the spec acknowledged as a valid alternative that "leverages grouped state for strong isolation."

The practical consequences:

- **F2 (Python)**: Compaction state travels on the messages themselves, visible to any layer that reads `additional_properties`. No extra object to carry around.
- **F1 (.NET)**: `MessageIndex` is a typed, serializable snapshot of the conversation's grouping and exclusion state. Serialization into `AgentSession.StateBag` is natural for .NET's session model. Strategies operate on richly typed `MessageGroup` objects rather than dictionary keys.

Both are defensible; the divergence is intentional.

#### `TokenBudgetComposedStrategy` vs. `PipelineCompactionStrategy`

The spec describes `TokenBudgetComposedStrategy` as the "opinionated" default composition pattern that runs strategies sequentially until the token budget is satisfied (with optional early-stop). Python ships this exactly.

The .NET PR ships `PipelineCompactionStrategy` instead, which runs strategies sequentially but has no token-budget stopping condition — it always runs all strategies. This means .NET users cannot express "run strategies in order until budget is satisfied" with the current API. To reproduce spec-recommended behavior, a .NET user would need to write a custom `CompactionStrategy` subclass.

**Recommendation**: Add `TokenBudgetCompactionStrategy` (or equivalent named `BudgetedPipelineCompactionStrategy`) to .NET to close this gap and match Python.

#### Trigger design

Python uses the spec-recommended "strategy-internal trigger" pattern: the strategy is always called and returns `false` when under threshold. .NET has an additional layer of indirection: a `CompactionTrigger` predicate is evaluated in `CompactionStrategy.CompactAsync` before `ApplyCompactionAsync`. This is more explicit (each strategy declares its trigger condition at construction time) but it deviates from the spec's stated approach of letting strategies own their trigger logic internally. The .NET `CompactionTrigger` is not represented in the spec at all.

The .NET approach is architecturally valid and arguably cleaner for declarative composition. It also allows re-using triggers across strategies and combining them with `CompactionTriggers.All/Any`.

#### Pre-write compaction unification

The spec explicitly wants `CompactionStrategy` to be reusable across in-run and pre-write points without duplicating wiring. In .NET:

- **In-run**: `CompactionStrategy` on `ChatClientAgentOptions.CompactionStrategy`.
- **Pre-write**: `IChatReducer` on `InMemoryChatHistoryProvider`.

These are two separate abstractions. A user wanting both in-run and pre-write compaction must configure two different objects, potentially wrapping the same logic twice. The spec's unified vision is not yet realized in .NET.

Python Phase 2 will add `compaction_strategy` directly to `HistoryProvider`, achieving the unified configuration the spec envisions.

**Recommendation**: Add a `CompactionStrategy`-based path to `InMemoryChatHistoryProvider` (in addition to or instead of `IChatReducer`) so the same strategy instance can be wired for both in-run and pre-write use.

---

## 6. Summary of Recommendations

### For .NET PR #4496

| Priority | Recommendation | Rationale |
|---|---|---|
| **High** | Add `TokenBudgetCompactionStrategy` (or equivalent) | Closes the budget-enforcement gap relative to spec and Python |
| **High** | Add `CompactionStrategy`-based pre-write support to `InMemoryChatHistoryProvider` | Enables unified strategy configuration across in-run and pre-write as the spec intends |
| **Medium** | Add reasoning-message (`ReasoningContent`) handling to `MessageIndex.Create` | The spec requires reasoning content to be treated as atomic with its tool-call group (see ADR-0019 §"Message-list correctness constraint") |
| **Low** | Consider aligning `CompactionTrigger` documentation to spec's "strategy-internal trigger" guidance | The trigger is a .NET-only concept; add a note that it plays the role of the spec's internal guard |
| **Low** | Consider surfacing source attribution (`AgentRequestMessageSourceType`) in `MessageGroup` or strategy helper | Enables attribution-aware strategies as described in spec Appendix A |

### For Python PR #4469

| Priority | Recommendation | Rationale |
|---|---|---|
| **High** | Proceed with Phase 2 (pre-write/storage compaction) | Needed to reach spec's full three-point coverage |
| **Medium** | Add reasoning-message (`ReasoningContent`) handling to `annotate_message_groups()` | The spec requires reasoning content to be treated as atomic with its tool-call group (see ADR-0019 §"Message-list correctness constraint") |
| **Low** | Consider documenting `TokenBudgetComposedStrategy` as the canonical composition pattern explicitly, to help .NET align | Cross-language consistency |

---

## 7. Spec Coverage Matrix

How each implementation covers the three primary compaction points defined in the spec:

| Compaction Point | Spec | Python PR #4469 | .NET PR #4496 |
|---|---|---|---|
| **In-run** | ✅ Required | ✅ Implemented | ✅ Implemented |
| **Pre-write** | ✅ Required | ⏳ Phase 2 | ⚠️ Via `IChatReducer` (separate mechanism, not `CompactionStrategy`) |
| **Existing-storage** | ✅ Required | ⏳ Phase 2 | ⚠️ Via `SetMessages()` + manual call (no `compact_storage()` equivalent) |

---

## 8. Conclusion

Both PRs deliver sound, production-ready in-run compaction. The Python PR closely follows the
spec's F2 design and will complete full spec coverage in Phase 2. The .NET PR diverges
intentionally from F2 to F1, which is acceptable given the spec's explicit acknowledgement of
F1 as a valid alternative. The .NET approach fits naturally with C#'s type system and session
serialization patterns.

The most significant remaining gaps across both implementations are:

1. **Pre-write compaction unification** — .NET uses a separate mechanism (`IChatReducer`);
   Python defers to Phase 2.
2. **`TokenBudgetComposedStrategy` in .NET** — the spec's recommended composition pattern is
   present in Python but absent from .NET.
3. **Reasoning-message atomicity** — neither implementation handles `ReasoningContent` in the
   grouping algorithm, which the spec calls out as a correctness requirement for users of the
   OpenAI Responses API (the `/v1/responses` endpoint used by reasoning models).
