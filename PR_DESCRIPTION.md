### Motivation and Context

`MessageMerger`, the internal component that folds streaming `AgentResponseUpdate` items into a final `AgentResponse`, had an implicit contract with no tests validating its ordering and grouping behavior. This created two issues:

1. **Message ordering bug**: When updates lacked `CreatedAt` timestamps, `CompareByDateTimeOffset` treated null timestamps as "greater than" any value, pushing untimestamped messages unpredictably to the end rather than preserving their arrival order. In multi-agent scenarios (handoff, group chat), this caused message reordering that broke conversation coherence.

2. **Missing invariant documentation**: The merger's guarantees were never written down, and the code contained dead state (`createdTimes` HashSet) suggesting abandoned functionality. Future refactors risked silently breaking the contract.

### Description

This PR fixes the message ordering issue, documents the merger invariants in ADR 0026, and adds comprehensive tests to pin the expected behavior.

**Bug fix in `MessageMerger.CompareByDateTimeOffset`**:
- Changed the comparison to use insertion index as tiebreaker when timestamps are missing or equal
- When `CreatedAt` is null for either message, or both timestamps are equal, the comparer now falls back to the original insertion index, preserving arrival order

**ADR 0026 establishes three invariants**:
1. **Single `ResponseId` per turn** — Hosting executors must assign a `ResponseId` if the agent doesn't provide one; updates with `ResponseId == null` are "dangling" and appended at the end
2. **Output order preservation** — When updates lack `CreatedAt`, their relative order in the merged output matches arrival order
3. **Per-`ResponseId` grouping** — Messages from each `ResponseId` appear as a contiguous block (no interleaving), enabling per-agent grouping in multi-agent scenarios

**Cleanup**:
- Removed unused `createdTimes` HashSet that was populated but never consumed

**Test coverage** added in `MessageMergerTests`:
- Insertion-order preservation with no timestamps
- Insertion-order preservation with mixed timestamps
- Determinism across repeated runs with mixed timestamps
- Per-`ResponseId` grouping for interleaved multi-agent streams
- Per-`ResponseId` grouping with distinct response IDs
- Function call/result ordering preservation
- `FinishReason` propagation

### Contribution Checklist

- [x] The code builds clean without any errors or warnings
- [x] The PR follows the [Contribution Guidelines](https://github.com/microsoft/agent-framework/blob/main/CONTRIBUTING.md)
- [x] All unit tests pass, and I have added new tests where possible
- [ ] **Is this a breaking change?** No — this fix preserves intended behavior while correcting a subtle ordering bug
