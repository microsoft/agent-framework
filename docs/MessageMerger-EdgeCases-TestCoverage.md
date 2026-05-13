# Agent Hosting Executor Invariants and Test Coverage

This document defines the **invariants** that Agent hosting executors must maintain, identifies edge cases in `MessageMerger`, and recommends additional test coverage.

## Hosting Executor Invariants

Agent hosting executors (e.g., `HostedAgentResponseExecutor`, `AIAgentResponseExecutor`, `WorkflowOrchestrator`) **must** maintain the following invariants:

### Invariant 1: Single ResponseId per Turn

**For a given "turn", only one ResponseId is emitted.**

- If the underlying Agent does not provide a `ResponseId`, the hosting executor **must** assign one.
- All `AgentResponseUpdate` items emitted during a single turn must share the same `ResponseId`.
- This ensures clients can reliably group streaming updates into a single logical response.

**Relevant Code:**
- `IdGenerator` creates a `ResponseId` in `InMemoryResponsesService.InitializeResponse()`
- `AgentInvocationContext.ResponseId` provides the single ResponseId for the turn
- `ToStreamingResponseAsync()` uses `context.ResponseId` for the `Response` object

### Invariant 2: Output Order Preservation for Untimestamped Messages

**For a given turn, all messages without `CreatedAt` must be merged in output (arrival) order.**

- When `AgentResponseUpdate` items lack a `CreatedAt` timestamp, their relative order must be preserved based on arrival sequence.
- The current `MessageMerger.CompareByDateTimeOffset()` falls back to index comparison when timestamps are missing or equal, which satisfies this invariant.
- Edge case: Mixed timestamped/untimestamped messages require careful handling to avoid non-transitive sort issues.

**Relevant Code:**
- `MessageMerger.CompareByDateTimeOffset()` uses index as tiebreaker
- `ResponseMergeState.AddUpdate()` preserves insertion order in lists

### Invariant 3: Agent Message Grouping (No Interleaving)

**For multi-agent systems speaking concurrently, a given agent's response messages must all be grouped together (not interleaved with other agents' messages).**

- When multiple agents emit responses concurrently (e.g., in handoff scenarios), messages from each agent must remain contiguous.
- The merged output should group messages by agent, not interleave them arbitrarily.
- This is critical for maintaining conversation coherence in multi-agent orchestration.

**Relevant Code:**
- `MessageMerger` groups by `ResponseId`, then by `MessageId`
- Multi-agent scenarios may emit different `ResponseId` values per agent
- `ComputeMerged()` processes responses in dictionary iteration order (first-seen order)

---

## Overview

`MessageMerger` (`dotnet/src/Microsoft.Agents.AI.Workflows/MessageMerger.cs`) handles merging streaming `AgentResponseUpdate` messages into a final `AgentResponse`. It groups updates by `ResponseId`, then by `MessageId`, sorts messages by `CreatedAt` timestamp, and produces a consolidated response.

---

## Edge Cases Identified

| # | Edge Case | Risk | Current Test Coverage |
|---|-----------|------|----------------------|
| 1 | **Non-transitive timestamp comparison** — mixed timestamped/untimestamped updates with 3+ messages can produce inconsistent sort order | High | ❌ Not covered |
| 2 | **Cross-ResponseId ordering** — messages from different ResponseIds are emitted in first-seen order, not chronological | Medium | ❌ Not covered |
| 3 | **ResponseId=null updates always last** — dangling updates appended after all response-scoped messages regardless of arrival time | Medium | ❌ Not covered |
| 4 | **MessageId=null updates within a response** — keyed messages always precede message-id-less updates | Low | ❌ Not covered |
| 5 | **CreatedAt overwritten** — all messages in a merged response get same `CreatedAt`, erasing original timestamps | Low | Partial (test asserts message timestamps) |
| 6 | **Dangling metadata lost** — `FinishReason`, `Usage`, `AgentId` from ResponseId=null updates not merged | Medium | ❌ Not covered |
| 7 | **Unused `createdTimes` collection** — final response uses `UtcNow`, collected times are unused | Low (code smell) | N/A |

---

## Edge Case Details

### 1. Non-transitive Timestamp Comparison (High Risk)

**Problem:** The `OrderBy` lambda uses a comparison that isn't transitive when some messages have `CreatedAt` and others don't:

```csharp
.OrderBy(kvp => kvp.Value.CreatedAt ?? m.CreatedAt)
```

With three messages:
- A: `CreatedAt = 10`, idx=0
- B: `CreatedAt = null`, idx=1
- C: `CreatedAt = 5`, idx=2

The comparison produces: A < B (10 < 10=false, so equal), B < C (10 < 5=false), but A > C (10 > 5). This violates transitivity and can cause non-deterministic sort results.

**Recommendation:** Use insertion order as fallback for null timestamps, or store original index.

---

### 2. Cross-ResponseId Ordering (Medium Risk)

**Problem:** When multiple `ResponseId`s arrive interleaved, messages are emitted in response-first-seen order:

```
Updates: R1-msg1 → R2-msg1 → R1-msg2 → R2-msg2
Output:  [R1-msg1, R1-msg2], [R2-msg1, R2-msg2]
```

This may not match chronological arrival order.

---

### 3. ResponseId=null Updates Always Last (Medium Risk)

**Problem:** Updates with `ResponseId = null` are grouped as "dangling" and always appended last, regardless of when they arrived:

```csharp
if (update.ResponseId is null)
{
    danglingUpdates.Add(update);
    continue;
}
```

This means metadata-only updates sent early in the stream appear at the end.

---

### 4. MessageId=null Updates Within a Response (Low Risk)

**Problem:** Within a `ResponseId` group, updates with `MessageId = null` are stored in a separate list and appended after keyed messages:

```csharp
if (update.MessageId is null)
{
    grouping.Value.noIds.Add(update);
}
```

This is likely intentional but not documented or tested.

---

### 5. CreatedAt Overwritten (Low Risk)

**Problem:** All messages in the final response receive the same `CreatedAt` timestamp:

```csharp
message.CreatedAt = m.CreatedAt ?? DateTimeOffset.UtcNow;
```

Individual message timestamps are overwritten with the response-level timestamp or current time.

---

### 6. Dangling Metadata Lost (Medium Risk)

**Problem:** When `ResponseId = null` updates contain `FinishReason`, `Usage`, or `AgentId`, these values are not merged into the final response:

```csharp
// Dangling updates become orphan messages, not merged with response metadata
foreach (var orphan in danglingUpdates)
{
    orphanMessages.Add(CreateAgentMessage(orphan));
}
```

---

### 7. Unused `createdTimes` Collection (Low Risk - Code Smell)

**Problem:** The code collects `CreatedAt` values into `createdTimes` list but never uses them:

```csharp
List<DateTimeOffset> createdTimes = [];
// ... later ...
if (update.CreatedAt.HasValue) createdTimes.Add(update.CreatedAt.Value);
// createdTimes is never used
```

---

## Recommended Additional Tests

### High Priority

1. **Non-transitive sorting with mixed timestamps**
   ```csharp
   [Fact]
   public void MergeMessages_MixedTimestamps_ProducesStableOrder()
   {
       // Arrange: 3 messages - A (CreatedAt=10), B (null), C (CreatedAt=5)
       // Act: Merge
       // Assert: Order is deterministic (either chronological or insertion order)
   }
   ```

2. **Function call/result sequencing with 3+ messages**
   ```csharp
   [Fact]
   public void MergeMessages_FunctionCallAndResultsWithMixedTimestamps_PreservesLogicalOrder()
   {
       // Arrange: FunctionCall (null), FunctionResult (T1), Assistant (null)
       // Act: Merge
       // Assert: FunctionCall precedes FunctionResult precedes Assistant
   }
   ```

### Medium Priority

3. **Multiple ResponseIds interleaved**
   ```csharp
   [Fact]
   public void MergeMessages_InterleavedResponseIds_GroupsByResponseId()
   {
       // Arrange: R1-msg1, R2-msg1, R1-msg2, R2-msg2
       // Act: Merge
       // Assert: Messages grouped by ResponseId, verify order
   }
   ```

4. **Dangling updates with FinishReason/Usage**
   ```csharp
   [Fact]
   public void MergeMessages_DanglingUpdatesWithMetadata_MetadataPropagates()
   {
       // Arrange: ResponseId=null update with FinishReason=Stop, Usage=(10,20,30)
       // Act: Merge
       // Assert: Final response contains FinishReason and Usage
   }
   ```

5. **ResponseId=null timing**
   ```csharp
   [Fact]
   public void MergeMessages_DanglingUpdatesFirst_AppearsAfterKeyedMessages()
   {
       // Arrange: null-response update, then keyed update
       // Act: Merge
       // Assert: Keyed messages appear before dangling
   }
   ```

### Low Priority

6. **MessageId=null updates ordering**
   ```csharp
   [Fact]
   public void MergeMessages_MixedMessageIds_KeyedBeforeUnkeyed()
   {
       // Arrange: Mix of keyed and unkeyed updates within same ResponseId
       // Act: Merge
       // Assert: Keyed messages precede unkeyed in arrival order
   }
   ```

---

## Summary

| Priority | Test Count | Risk Addressed |
|----------|------------|----------------|
| High | 2 | Non-deterministic sorting, Function sequencing |
| Medium | 3 | ResponseId grouping, Metadata propagation, Timing |
| Low | 1 | MessageId ordering |

**Recommendation:** Add at minimum the 2 high-priority tests and 2 medium-priority tests (interleaved ResponseIds, dangling metadata) to ensure `MessageMerger` behaves correctly in production streaming scenarios.

---

## Required Tests for Hosting Executor Invariants

### Invariant 1: Single ResponseId per Turn

```csharp
[Fact]
public async Task HostingExecutor_AssignsSingleResponseId_WhenAgentProvidesNone()
{
    // Arrange: Agent that emits updates without ResponseId
    // Act: Execute through hosting executor
    // Assert: All emitted updates have the same ResponseId assigned by executor
}

[Fact]
public async Task HostingExecutor_PreservesAgentResponseId_WhenProvided()
{
    // Arrange: Agent that emits updates with a consistent ResponseId
    // Act: Execute through hosting executor
    // Assert: ResponseId from agent is preserved (or overridden if executor policy requires)
}

[Fact]
public async Task HostingExecutor_RejectsMultipleResponseIds_InSingleTurn()
{
    // Arrange: Agent that incorrectly emits updates with different ResponseIds
    // Act: Execute through hosting executor
    // Assert: Executor normalizes to single ResponseId or throws validation error
}
```

### Invariant 2: Output Order Preservation

```csharp
[Fact]
public void MessageMerger_PreservesInsertionOrder_WhenNoTimestamps()
{
    // Arrange: Multiple updates without CreatedAt, in specific order A, B, C
    // Act: Merge
    // Assert: Output order is A, B, C
}

[Fact]
public void MessageMerger_PreservesInsertionOrder_WhenMixedTimestamps()
{
    // Arrange: Updates where some have CreatedAt and some don't
    // Act: Merge
    // Assert: Untimestamped updates maintain relative order among themselves
}

[Fact]
public void MessageMerger_StableSort_WithThreeOrMoreMixedTimestampMessages()
{
    // Arrange: 3+ messages with mixed null/non-null CreatedAt values
    // Act: Merge multiple times
    // Assert: Result is deterministic and consistent across runs
}
```

### Invariant 3: Agent Message Grouping

```csharp
[Fact]
public void MessageMerger_GroupsMessagesByAgent_InMultiAgentScenario()
{
    // Arrange: Interleaved updates from Agent1 and Agent2
    //   A1-msg1, A2-msg1, A1-msg2, A2-msg2
    // Act: Merge
    // Assert: Output groups Agent1 messages together, Agent2 messages together
    //   Either [A1-msg1, A1-msg2, A2-msg1, A2-msg2] or [A2-msg1, A2-msg2, A1-msg1, A1-msg2]
}

[Fact]
public void MessageMerger_MaintainsAgentGrouping_WithDifferentResponseIds()
{
    // Arrange: Agent1 uses ResponseId=R1, Agent2 uses ResponseId=R2
    // Act: Merge with primaryResponseId
    // Assert: Messages from each agent are contiguous, not interleaved
}

[Fact]
public async Task HostingExecutor_HandoffScenario_MaintainsMessageCoherence()
{
    // Arrange: Agent1 hands off to Agent2 mid-conversation
    // Act: Execute through hosting executor
    // Assert: Agent1's messages appear before Agent2's messages (no interleaving)
}

[Fact]
public void MessageMerger_PreservesAgentMessageOrder_WithConcurrentAgents()
{
    // Arrange: Two agents emitting messages concurrently with timestamps
    //   A1 at T1, A2 at T2, A1 at T3, A2 at T4 (where T1 < T2 < T3 < T4)
    // Act: Merge
    // Assert: Agent grouping is maintained, not sorted purely by timestamp
}
```

---

## Implementation Recommendations

### For Invariant 1 (Single ResponseId)

1. **Hosting Executor Layer**: The `AgentInvocationContext` already generates a `ResponseId`. Ensure this is consistently applied to all outgoing `AgentResponseUpdate` items.

2. **Validation**: Consider adding runtime validation that throws if an agent emits conflicting `ResponseId` values during a single turn.

3. **Code Location**: `ToStreamingResponseAsync()` in `AgentResponseUpdateExtensions.cs` should ensure the `context.ResponseId` is used consistently.

### For Invariant 2 (Output Order)

1. **Index Tracking**: Store original insertion index alongside each update to ensure stable sorting.

2. **Code Location**: `MessageMerger.ResponseMergeState.AddUpdate()` should track insertion order explicitly.

3. **Sort Stability**: Replace the current `OrderBy` with a stable sort that uses insertion index as the final tiebreaker.

### For Invariant 3 (Agent Grouping)

1. **Agent-First Grouping**: Modify `ComputeMerged()` to group by `AgentId` before processing.

2. **Deterministic Order**: Define explicit ordering rules (e.g., first-seen agent order, or alphabetical by AgentId).

3. **Code Location**: `MessageMerger.ComputeMerged()` needs logic to ensure agent messages are contiguous.
