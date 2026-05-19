---
status: accepted
contact: lokitoth
date: 2026-05-13
deciders: lokitoth
consulted:
informed:
---

# MessageMerger Streaming Merge Invariants

## Context and Problem Statement

`Microsoft.Agents.AI.Workflows.MessageMerger` is the internal component that
folds a stream of `AgentResponseUpdate` items emitted by an agent (or by a
hosting executor wrapping an agent) into a single `AgentResponse` for a turn.
Multi-agent workflows (handoff, group chat, orchestration) rely on this
merger to produce a coherent transcript even when updates arrive interleaved
across responses, messages, and timestamps.

Prior to this change the contract that hosting executors and the merger
should jointly enforce was implicit. The implementation also carried a small
amount of dead state (`createdTimes`) that was collected but never consumed,
suggesting that an earlier, timestamp-driven ordering scheme had been
abandoned without documentation, and the live code still ran an unreliable
`CreatedAt`-based sort that could reorder messages across concurrent agents
inside a single workflow super-step. There were no tests pinning down the
ordering or grouping behavior, so any future refactor risked silently
regressing it.

The problem this ADR addresses is therefore: **what merge guarantees does
`MessageMerger` make to its callers, and how do we lock those guarantees in
without changing observable behavior in non-pathological cases?**

## Decision Drivers

- **A. Predictable ordering.** Developers consuming a merged `AgentResponse`
  must be able to reason about the order in which messages appear without
  having to know whether updates carried `CreatedAt`.
- **B. Coherent multi-agent transcripts.** When several agents stream into
  one merger within a single workflow super-step, each agent's contribution
  must read as a contiguous block; and a step's updates must precede the
  next step's updates.
- **C. Stable hosting-executor contract.** A turn must be addressable by a
  single `ResponseId`; updates without one are an exceptional, "dangling"
  case rather than the norm.
- **D. Minimal behavioral change for non-pathological inputs.** This work
  is intended to document and test current behavior, not to alter what
  users see today in well-formed agent streams.
- **E. Discoverability for future contributors.** Known sharp edges (e.g.
  cross-`ResponseId` ordering, dangling-update placement) should be written
  down so they are not rediscovered as bugs.

## Considered Options

1. **Option 1 — Document invariants, pin them with tests, and use pure
   emission/insertion order for both responses and the messages inside
   each response.** Removes the unreliable `CreatedAt`-based sort and the
   dead `createdTimes` collection. Behavioral change only for inputs that
   relied on `CreatedAt` to re-order updates after the fact — which the
   prior comparer could not do correctly anyway (non-transitive).
2. **Option 2 — Rewrite `MessageMerger` to group strictly by `AgentId`
   (rather than `ResponseId`), and to use a stable, transitive comparer
   that mixes `CreatedAt` with insertion index.** Behavioral change; would
   also require updating hosting executors that currently assume
   `ResponseId`-based grouping.
3. **Option 3 — Leave the code and tests as-is; capture edge cases only
   in a working note.** No code or test change.

## Decision Outcome

Chosen option: **Option 1 — Document invariants, pin them with tests,
and use pure emission/insertion order; remove the dead `createdTimes`
collection.**

This option satisfies driver A (predictable ordering: emission order is
the simplest reasoning model), driver B (per-`ResponseId` grouping plus
first-seen ordering across responses gives both per-agent blocks within a
step and step-ordering across steps), driver C (single ResponseId per
turn is unchanged), and driver E (invariants and edge cases are now
written down and covered by tests).

Driver D (minimal behavioral change) is satisfied because well-formed
agent streams already emit updates in the order they want to appear; the
prior `CreatedAt`-based sort only mattered for pathological inputs (mixed
or out-of-order timestamps from concurrent agents), and on those inputs
the old comparer was non-transitive and therefore unreliable. Removing
the sort makes those inputs deterministic — they now follow emission
order — without disturbing the well-formed case.

Option 2 was rejected for this iteration because it changes what callers
observe in well-formed flows and would require a coordinated change
across hosting executors. It is a candidate for a follow-up ADR if the
known edge cases below are reported as bugs in practice.

Option 3 was rejected because it leaves the invariants un-tested and the
dead code in place, so the next refactor can break the contract without
any signal.

### Invariants

The following invariants are now part of the contract of
`MessageMerger`/hosting executors and are covered by tests in
`MessageMergerTests`:

1. **Single `ResponseId` per turn.** Every `AgentResponseUpdate` produced
   by a hosting executor in a single agent turn shares one `ResponseId`.
   If the underlying agent does not supply one, the executor assigns it.
   Updates with `ResponseId == null` are treated as "dangling" and
   flattened into loose messages at the end of the merged response.
2. **Pure emission-order preservation.** Within a `ResponseId` block,
   messages appear in the order their updates first arrived at the
   merger. Across `ResponseId` blocks, blocks appear in first-seen order.
   `CreatedAt` is **not** consulted when ordering messages or blocks —
   only when stamping the merged response and its child messages.
3. **Per-`ResponseId` grouping (no interleaving).** Messages produced
   under one `ResponseId` are emitted as a contiguous block in the merged
   `AgentResponse`. Combined with Invariant 1, this yields:
   - **Within a workflow super-step with one agent**: all messages
     appear together, in emission order.
   - **Within a super-step with multiple agents**: each agent's messages
     are a contiguous block, ordered by which agent emitted first.
   - **Across super-steps**: a step's blocks all precede the next step's
     blocks, because the next step cannot start emitting until the
     current step's emissions have arrived at the merger.

### Consequences

- Good, because the merge contract is now explicit, regression-tested,
  and trivially reasoned about (it is just emission order with
  per-`ResponseId` grouping).
- Good, because removing the unreliable `CreatedAt`-based sort eliminates
  a latent bug — the prior comparer was non-transitive on mixed-timestamp
  inputs, so `List<T>.Sort` could in principle return any of several
  orderings or throw on some runtimes.
- Good, because removing the unused `createdTimes` collection eliminates
  a misleading code smell.
- Good, because hosting-executor authors have a written checklist of
  invariants to satisfy.
- Neutral, because well-formed agent streams (those that emit updates in
  the order they want to appear) see no change in output.
- Bad, because callers who relied on a server-supplied `CreatedAt` to
  retro-correct out-of-order emissions will no longer see that
  correction — they must ensure emission order matches desired output
  order, or attach to `RawRepresentation` for original timestamps.

## Validation

- Unit tests in
  `dotnet/tests/Microsoft.Agents.AI.Workflows.UnitTests/MessageMergerTests.cs`
  cover each invariant:
  - Insertion-order preservation with no timestamps.
  - Insertion-order preservation with mixed timestamps (emission order
    wins over `CreatedAt`).
  - Determinism across repeated runs with mixed timestamps.
  - Per-`ResponseId` grouping for interleaved multi-agent streams within
    a single step.
  - Per-`ResponseId` grouping with distinct response ids.
- Existing tests for assembly, function-call/result ordering, and
  `FinishReason` propagation continue to pass.

## More Information

### Known edge cases (intentionally not fixed in this ADR)

These are properties of the *current* `MessageMerger` that callers should
be aware of. They are not invariants — they may change in a future ADR —
but they are present in the shipped behavior covered by tests above.

| # | Edge case | Risk | Notes |
|---|-----------|------|-------|
| 1 | Cross-`ResponseId` ordering follows first-seen-`ResponseId` order, not chronological order across responses. | Medium | Acceptable today because each turn has a single `ResponseId` (Invariant 1); only matters if a caller deliberately interleaves multiple response ids inside one step. |
| 2 | Updates with `ResponseId == null` are always emitted **after** all keyed responses, regardless of arrival time. | Medium | Documented as the "dangling" path; agents should always emit a `ResponseId`. |
| 3 | Within a response, updates with `MessageId == null` are always emitted **after** keyed messages. | Low | Same rationale as #2, scoped to messages within a response. |
| 4 | The merged response's `CreatedAt` is set to `DateTimeOffset.UtcNow`; per-response `CreatedAt` is propagated onto each contained `ChatMessage` instead of being preserved at the response level. | Low | Callers who need original per-update timestamps should read them from `RawRepresentation` or capture them before merging. |
| 5 | Metadata on dangling (`ResponseId == null`) updates — `FinishReason`, `Usage`, `AgentId`, `AdditionalProperties` — is **not** merged into the final `AgentResponse`; only their `Messages` are surfaced. | Medium | Hosting executors must attach metadata to a keyed update if they want it reflected in the merged response. |
| 6 | Emission order is the **only** ordering signal — `CreatedAt` differences between updates are ignored when ordering. | Low | This is the intended behavior under Invariant 2; producers must emit in the desired output order. |

If any of these become observable problems in production, the appropriate
follow-up is a new ADR that supersedes this one (likely realizing
"Option 2") rather than a silent fix.

### Code references

- `dotnet/src/Microsoft.Agents.AI.Workflows/MessageMerger.cs` — merger
  implementation. The previously-unused `createdTimes` collection and
  the `CreatedAt`-based sort have both been removed in this change.
- `dotnet/tests/Microsoft.Agents.AI.Workflows.UnitTests/MessageMergerTests.cs` —
  invariant tests added in this change.
- `AgentInvocationContext.ResponseId` and `ToStreamingResponseAsync` —
  the hosting-executor side of Invariant 1.
