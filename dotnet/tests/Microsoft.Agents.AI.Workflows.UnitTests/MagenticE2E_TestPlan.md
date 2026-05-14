# Magentic E2E Test Plan

## Overview

This document outlines a comprehensive plan for adding end-to-end (E2E) tests for the Magentic orchestrator, similar to the existing `HandoffOrchestrationTests.cs` and smoke test patterns. These tests will drive a fully-built workflow through `MagenticWorkflowBuilder.Build()` and verify correct behavior at every logical fork in the orchestrator logic.

## Background

### Magentic Orchestrator Logic Flow

Based on the analysis of `MagenticOrchestrator.cs`, the orchestrator follows this decision tree:

```
TakeTurn (Initial)
  └─> UpdatePlanAndDelegateAsync
       ├─> Create/Update Plan via MagenticManager.UpdatePlanAsync
       ├─> Emit MagenticPlanCreatedEvent or MagenticReplannedEvent
       └─> If requirePlanSignoff: SubmitPlanReviewRequestAsync
           └─> ProcessPlanReviewAsync (on human response)
               ├─> If Approved: DelegateToTeamAsync
               └─> If Revise: Add review to chat, UpdatePlanAndDelegateAsync
       └─> If !requirePlanSignoff: DelegateToTeamAsync

DelegateToTeamAsync
  └─> RunCoordinationRoundAsync
       ├─> CHECK: Hit round limit? → Yield termination message, set IsTerminated
       ├─> CHECK: Hit reset limit? → Yield termination message, set IsTerminated
       ├─> Increment RoundCount
       ├─> UpdateProgressLedgerAsync (with retries)
       │    └─> On exception (non-cancellation): ResetAndReplanAsync
       ├─> Emit MagenticProgressLedgerUpdatedEvent
       ├─> CHECK: IsRequestSatisfied? → PrepareFinalAnswerAsync
       ├─> CHECK: IsInLoop OR !IsProgressBeingMade? → Increment StallCount
       │    └─> Else: Decrement StallCount (min 0)
       ├─> CHECK: IsStalled (StallCount > MaxStallCount)? → ResetAndReplanAsync
       ├─> Validate NextSpeaker → Fallback to first participant if empty
       ├─> CHECK: Invalid NextSpeaker? → Warning + PrepareFinalAnswerAsync
       └─> Send instruction + TurnToken to next agent

PrepareFinalAnswerAsync
  └─> Get final answer from manager, yield output, set IsTerminated

ResetAndReplanAsync
  └─> Reset context, send ResetChatSignal, UpdatePlanAndDelegateAsync
```

## Test Categories

### 1. Happy Path Tests

| Test Name | Description | Expected Behavior |
|-----------|-------------|-------------------|
| `Task_Completes_When_RequestSatisfied` | Manager reports task satisfied on first coordination round | Workflow yields final answer and terminates |
| `Task_Delegates_To_Correct_Agent` | Manager selects specific agent as next speaker | Selected agent receives TurnToken |
| `Task_Completes_After_Multiple_Rounds` | Task requires multiple coordination rounds before completion | Each round delegates to specified agent, final answer produced when satisfied |
| `PlanSignoff_Disabled_Proceeds_Immediately` | With `requirePlanSignoff=false` | Workflow proceeds to team delegation without plan review request |

### 2. Plan Review Tests (Human-in-the-Loop)

| Test Name | Description | Expected Behavior |
|-----------|-------------|-------------------|
| `PlanReview_Approved_Proceeds` | Human approves initial plan | Workflow continues to DelegateToTeamAsync |
| `PlanReview_Revised_Triggers_Replan` | Human requests plan revision | Revision added to chat, plan updated, MagenticReplannedEvent emitted |
| `PlanReview_Multiple_Revisions` | Human revises multiple times | Each revision triggers replan until approved |
| `PlanReview_On_Stall_Replan` | Stall triggers replan with plan signoff | Plan review request sent with IsStalled=true |

### 3. Limit Enforcement Tests

| Test Name | Description | Expected Behavior |
|-----------|-------------|-------------------|
| `MaxRoundLimit_Terminates_Workflow` | RoundCount exceeds MaxRoundCount | Workflow terminates with "maximum round count limit" message |
| `MaxResetLimit_Terminates_Workflow` | ResetCount exceeds MaxResetCount | Workflow terminates with "maximum reset count limit" message |
| `MaxStallCount_Triggers_Reset` | StallCount exceeds MaxStallCount | ResetAndReplanAsync called, ResetChatSignal sent |

### 4. Stall Detection Tests

| Test Name | Description | Expected Behavior |
|-----------|-------------|-------------------|
| `Stall_IsInLoop_Increments_StallCount` | ProgressLedger reports IsInLoop=true | StallCount incremented |
| `Stall_NoProgress_Increments_StallCount` | ProgressLedger reports IsProgressBeingMade=false | StallCount incremented |
| `Progress_Made_Decrements_StallCount` | ProgressLedger reports progress being made | StallCount decremented (min 0) |
| `Consecutive_Stalls_Trigger_Reset` | Multiple stalls in a row exceed MaxStallCount | Reset and replan triggered |

### 5. Progress Ledger Validation Tests

| Test Name | Description | Expected Behavior |
|-----------|-------------|-------------------|
| `ProgressLedger_Retry_On_Parse_Failure` | First attempt fails JSON parsing | Retry up to MaxProgressLedgerRetryCount times |
| `ProgressLedger_Max_Retries_Triggers_Reset` | All retry attempts fail | ResetAndReplanAsync called |
| `ProgressLedger_Updated_Event_Emitted` | Valid progress ledger update | MagenticProgressLedgerUpdatedEvent emitted |

### 6. Next Speaker Validation Tests

| Test Name | Description | Expected Behavior |
|-----------|-------------|-------------------|
| `NextSpeaker_Empty_Falls_Back_To_First` | ProgressLedger returns empty next_speaker | First team member selected, warning emitted |
| `NextSpeaker_Invalid_Triggers_FinalAnswer` | next_speaker doesn't match any team member | Warning emitted, final answer prepared |
| `NextSpeaker_Valid_Delegates_Correctly` | Valid team member specified | TurnToken sent to correct executor |

### 7. Event Emission Tests

| Test Name | Description | Expected Behavior |
|-----------|-------------|-------------------|
| `Initial_Plan_Emits_PlanCreatedEvent` | First plan creation | MagenticPlanCreatedEvent emitted with full task ledger |
| `Replan_Emits_ReplannedEvent` | Plan update after initial | MagenticReplannedEvent emitted |
| `Warning_Events_On_Errors` | Various warning conditions | WorkflowWarningEvent emitted with appropriate message |

### 8. Checkpoint/Resume Tests

> **Note:** Direct checkpoint-state inspection tests (`Checkpoint_Saves_TaskContext`,
> `Checkpoint_Preserves_ProgressLedger`) are **skipped** — the serialized checkpoint format is an
> internal implementation detail. Checkpoint resume is instead verified behaviorally through
> plan-review workflows that pause and resume across checkpoint boundaries.

| Test Name | Description | Expected Behavior |
|-----------|-------------|-------------------|
| `Checkpoint_Saves_TaskContext` | ~~Workflow checkpointed mid-execution~~ | *Skipped — internal format* |
| `Checkpoint_Resume_Continues_Correctly` | Resume from checkpoint | TaskContext restored, execution continues from saved state (behaviorally covered by plan-review tests) |
| `Checkpoint_Preserves_ProgressLedger` | ~~Resume preserves ledger state~~ | *Skipped — internal format* |

### 9. Edge Cases

| Test Name | Description | Expected Behavior |
|-----------|-------------|-------------------|
| `Empty_Team_Handling` | No participants added | Appropriate error or fallback behavior |
| `Single_Agent_Team` | Only one participant | Workflow functions correctly with single agent |
| `Instruction_Message_Sent_When_Present` | ProgressLedger has instruction_or_question | Instruction added to chat history and sent |
| `Terminated_Context_Rejects_New_Messages` | After termination, new messages arrive | InvalidOperationException thrown |

## Implementation Approach

### Test Infrastructure

Following the patterns established in `HandoffOrchestrationTests.cs`:

1. **TestReplayAgent for Manager**: Configure to return specific plan/progress ledger responses
2. **TestEchoAgent for Participants**: Simple agents that echo or return controlled responses
3. **MockChatClient**: For fine-grained control of LLM responses
4. **WorkflowRunResult**: Capture updates, outputs, checkpoints, and pending requests
5. **RunWorkflowAsync helper**: Execute workflow and collect results

### Key Test Helpers Needed

```csharp
// Helper to create manager agent with specific responses
internal static TestReplayAgent CreateManagerAgent(
    List<List<ChatMessage>> planResponses,
    List<List<ChatMessage>> progressLedgerResponses,
    List<List<ChatMessage>> finalAnswerResponses);

// Helper to create progress ledger JSON responses
internal static ChatMessage CreateProgressLedgerResponse(
    bool isRequestSatisfied,
    bool isInLoop,
    bool isProgressBeingMade,
    string nextSpeaker,
    string instructionOrQuestion);

// Helper to build and run Magentic workflow
internal static Task<WorkflowRunResult> RunMagenticWorkflowAsync(
    AIAgent manager,
    List<AIAgent> team,
    List<ChatMessage> input,
    bool requirePlanSignoff = false,
    TaskLimits? limits = null,
    ExecutionEnvironment environment = ExecutionEnvironment.InProcess_Lockstep);
```

### Test File Structure

Create new test file: `MagenticOrchestrationTests.cs`

```
dotnet/tests/Microsoft.Agents.AI.Workflows.UnitTests/
├── MagenticOrchestrationTests.cs  (NEW - E2E tests)
├── MagenticOrchestratorTests.cs   (existing - protocol tests)
├── MagenticManagerTests.cs        (existing - manager unit tests)
├── MagenticProgressLedgerTests.cs (existing - ledger unit tests)
└── TestProgressLedgerState.cs     (existing - reuse for E2E)
```

## Test Execution Order

1. **Phase 1: Basic Flow Tests**
   - Happy path completion
   - Single agent delegation
   - Multiple rounds
   
2. **Phase 2: Plan Review Tests**
   - Approval flow
   - Revision flow
   
3. **Phase 3: Limit and Stall Tests**
   - Round limits
   - Reset limits
   - Stall detection and recovery
   
4. **Phase 4: Error Handling Tests**
   - Invalid next speaker
   - Progress ledger failures
   
5. **Phase 5: Checkpoint Tests**
   - Save and restore

## Success Criteria

- [ ] All logical forks in `MagenticOrchestrator` are covered by at least one test
- [ ] Tests use the same patterns as `HandoffOrchestrationTests`
- [ ] Tests run against fully-built workflows (not isolated components)
- [ ] Each test verifies specific event emissions and state changes
- [ ] Tests cover both `requirePlanSignoff=true` and `false` paths
- [ ] Checkpoint/resume functionality is verified

## Estimated Implementation

| Component | Estimated Tests | Complexity |
|-----------|-----------------|------------|
| Happy Path | 4 | Low |
| Plan Review | 4 | Medium |
| Limits | 3 | Low |
| Stall Detection | 4 | Medium |
| Progress Ledger | 3 | Medium |
| Next Speaker | 3 | Low |
| Events | 3 | Low |
| Checkpoints | 3 | High |
| Edge Cases | 4 | Medium |
| **Total** | **~31 tests** | |

## Dependencies

- Existing test helpers: `TestReplayAgent`, `TestEchoAgent`, `TestProgressLedgerState`
- Existing execution infrastructure: `RunWorkflowAsync`, `CheckpointManager`
- Extensions may be needed for Magentic-specific assertions
