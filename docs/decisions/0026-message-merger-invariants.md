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
abandoned without documentation. There were no tests pinning down the
ordering or grouping behavior, so any future refactor risked silently
regressing it.

The problem this ADR addresses is therefore: **what merge guarantees does
`MessageMerger` make to its callers, and how do we lock those guarantees in
without changing observable behavior in this PR?**

## Decision Drivers

- **A. Predictable ordering**: developers consuming a merged `AgentResponse`
  must be able to reason about the order in which messages appear, even when
  some updates lack `CreatedAt`.
- **B. Coherent multi-agent transcripts**: when several agents stream
  concurrently into one merger (handoff, orchestrator-as-agent), each
  agent's contribution must read as a contiguous block.
- **C. Stable hosting-executor contract**: a turn must be addressable by a
  single `ResponseId`; updates without one are an exceptional, "dangling"
  case rather than the norm.
- **D. Minimal behavioral change**: this work is intended to document and
  test current behavior, not to alter what users see today.
- **E. Discoverability for future contributors**: known sharp edges (e.g.
  cross-`ResponseId` ordering, dangling-update placement) should be written
  down so they are not rediscovered as bugs.

## Considered Options

1. **Option 1 — Document invariants and pin them with tests; remove the
   dead `createdTimes` collection.** No behavioral change.
2. **Option 2 — Rewrite `MessageMerger` to group strictly by `AgentId`,
   and to use a stable, transitive comparer that mixes `CreatedAt` with
   insertion index.** Behavioral change; would also require updating
   hosting executors that currently assume `ResponseId`-based grouping.
3. **Option 3 — Leave the code and tests as-is; capture edge cases only
   in a working note.** No code or test change.

## Decision Outcome

Chosen option: **Option 1 — Document invariants and pin them with tests;
remove the dead `createdTimes` collection.**

This option satisfies driver D (minimal behavioral change) and driver E
(discoverability) while making real progress on A, B, and C: by writing the
invariants down and covering them with regression tests, future refactors
must either preserve the invariants or explicitly supersede this ADR. The
dead `createdTimes` collection is removed because it actively misleads
readers about the ordering strategy.

Option 2 was rejected for this iteration because it changes what callers
observe (e.g., would re-order outputs in any flow that relies on
`ResponseId`-based grouping today) and would require a coordinated change
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
   by a hosting executor in a single turn shares one `ResponseId`. If the
   underlying agent does not supply one, the executor assigns it. Updates
   with `ResponseId == null` are treated as "dangling" and flattened into
   loose messages at the end of the merged response.
2. **Output order preservation for untimestamped messages.** When updates
   lack `CreatedAt`, their relative order in the merged output matches
   their arrival order. `CompareByDateTimeOffset` falls back to insertion
   index when timestamps are missing or equal.
3. **Per-`ResponseId` grouping (no interleaving).** Messages produced
   under one `ResponseId` are emitted as a contiguous block in the merged
   `AgentResponse`. In multi-agent scenarios where each agent uses its
   own `ResponseId`, this also yields per-agent grouping.

### Consequences

- Good, because the merge contract is now explicit and regression-tested,
  reducing the risk of silent behavioral drift.
- Good, because removing the unused `createdTimes` collection eliminates
  a misleading code smell.
- Good, because hosting-executor authors have a written checklist of
  invariants to satisfy.
- Neutral, because no end-user behavior changes.
- Bad, because several known edge cases (see below) are documented but
  not fixed; consumers may still encounter them.

## Validation

- Unit tests in
  `dotnet/tests/Microsoft.Agents.AI.Workflows.UnitTests/MessageMergerTests.cs`
  cover each invariant:
  - Insertion-order preservation with no timestamps.
  - Insertion-order preservation with mixed timestamps.
  - Determinism across repeated runs with mixed timestamps.
  - Per-`ResponseId` grouping for interleaved multi-agent streams.
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
| 1 | `CompareByDateTimeOffset` is not transitive when some messages have `CreatedAt` and others do not (e.g. A=10, B=null, C=5 yields A<B by index, B<C by index, but A>C by timestamp). | Medium | `List<T>.Sort` is not guaranteed to produce a unique ordering for non-transitive comparers, but the current tests verify that repeated runs over identical input produce identical output. Use `CreatedAt` consistently per response to avoid this. |
| 2 | Cross-`ResponseId` ordering follows first-seen-`ResponseId` order, not chronological order across responses. | Medium | Acceptable today because each turn has a single `ResponseId` (Invariant 1); only matters if a caller deliberately interleaves multiple response ids. |
| 3 | Updates with `ResponseId == null` are always emitted **after** all keyed responses, regardless of arrival time. | Medium | Documented as the "dangling" path; agents should always emit a `ResponseId`. |
| 4 | Within a response, updates with `MessageId == null` are always emitted **after** keyed messages. | Low | Same rationale as #3, scoped to messages within a response. |
| 5 | The merged response's `CreatedAt` is set to `DateTimeOffset.UtcNow`; per-response `CreatedAt` is propagated onto each contained `ChatMessage` instead of being preserved at the response level. | Low | Callers who need original per-update timestamps should read them from `RawRepresentation` or capture them before merging. |
| 6 | Metadata on dangling (`ResponseId == null`) updates — `FinishReason`, `Usage`, `AgentId`, `AdditionalProperties` — is **not** merged into the final `AgentResponse`; only their `Messages` are surfaced. | Medium | Hosting executors must attach metadata to a keyed update if they want it reflected in the merged response. |

If any of these become observable problems in production, the appropriate
follow-up is a new ADR that supersedes this one (likely realizing
"Option 2") rather than a silent fix.

### Code references

- `dotnet/src/Microsoft.Agents.AI.Workflows/MessageMerger.cs` — merger
  implementation. The previously-unused `createdTimes` collection has
  been removed in this change.
- `dotnet/tests/Microsoft.Agents.AI.Workflows.UnitTests/MessageMergerTests.cs` —
  invariant tests added in this change.
- `AgentInvocationContext.ResponseId` and `ToStreamingResponseAsync` —
  the hosting-executor side of Invariant 1.
