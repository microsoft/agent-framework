# Task: TASK-306 Workflow State Machine

**Phase**: 4
**Priority**: Critical
**Estimated Effort**: 6 hours
**Dependencies**: TASK-301 (Workflow Graph), TASK-302 (Workflow Executor), TASK-303 (Event System)

### Objective
Implement the workflow state machine that manages workflow execution state, transitions, and lifecycle including checkpointing and resumption.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-8 (Workflows - States)
- **Python Reference**: `/python/packages/core/agent_framework/workflows/runner.py` - State machine logic
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI.Workflows/StateMachine/` - Workflow state management
- **Standards**: CLAUDE.md § Python Architecture → Async-First Design

### Files to Create/Modify
- `src/workflows/execution/state-machine.ts` - WorkflowStateMachine class
- `src/workflows/execution/__tests__/state-machine.test.ts` - Unit tests
- `src/workflows/index.ts` - Export state machine

### Implementation Requirements

**Core Functionality**:
1. Create `WorkflowStateMachine` class to manage workflow state
2. Implement state tracking using `WorkflowRunState` enum
3. Handle state transitions (IN_PROGRESS → IDLE → FAILED, etc.)
4. Emit `WorkflowStatusEvent` on state changes
5. Track pending requests for human-in-the-loop
6. Manage checkpoint creation at state transitions
7. Implement `saveState()` for checkpoint creation
8. Implement `restoreState()` for checkpoint loading
9. Validate state transitions (prevent invalid transitions)
10. Provide state query methods (`getState()`, `isPending()`, etc.)

**State Transitions**:
11. Start: (none) → IN_PROGRESS
12. Request pending: IN_PROGRESS → IN_PROGRESS_PENDING_REQUESTS
13. Request resolved: IN_PROGRESS_PENDING_REQUESTS → IN_PROGRESS
14. Complete: IN_PROGRESS → IDLE
15. Error: * → FAILED
16. Resume: IDLE → IN_PROGRESS

**Checkpointing Integration**:
17. Create checkpoint on state transition
18. Store checkpoint ID with state
19. Restore state from checkpoint
20. Validate checkpoint compatibility before restore

**TypeScript Patterns**:
- Use state machine pattern
- Implement event emitter integration
- Use type-safe state transitions
- Export all types with comprehensive JSDoc
- Strict null checking

**Code Standards**:
- 120 character line length
- JSDoc documentation for all public APIs with `@example` tags
- Strict TypeScript mode enabled
- No `any` types without explicit justification comment

### Test Requirements
- [ ] Test WorkflowStateMachine creation
- [ ] Test initial state is correct
- [ ] Test state transition from initial to IN_PROGRESS
- [ ] Test state transition to IN_PROGRESS_PENDING_REQUESTS
- [ ] Test state transition back to IN_PROGRESS after request resolved
- [ ] Test state transition to IDLE on completion
- [ ] Test state transition to FAILED on error
- [ ] Test invalid state transitions are rejected
- [ ] Test WorkflowStatusEvent emitted on state change
- [ ] Test pending request tracking
- [ ] Test checkpoint creation on state transition
- [ ] Test state restoration from checkpoint
- [ ] Test checkpoint compatibility validation
- [ ] Test getState() returns current state
- [ ] Test isPending() returns correct value
- [ ] Test error scenarios

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] WorkflowStateMachine class implemented
- [ ] All state transitions handled correctly
- [ ] WorkflowStatusEvent emitted on state changes
- [ ] Pending request tracking implemented
- [ ] Checkpoint creation and restoration
- [ ] State transition validation prevents invalid transitions
- [ ] Tests pass with >85% coverage
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings
- [ ] JSDoc complete for all public APIs with examples
- [ ] Exports added to index.ts files

### Example Code Pattern
```typescript
import { WorkflowRunState, WorkflowStatusEvent } from '../events';
import { WorkflowCheckpoint, CheckpointStorage } from '../checkpoint';
import { WorkflowEventEmitter } from '../events/emitter';

/**
 * Workflow state machine managing execution state and transitions
 *
 * @example
 * ```typescript
 * const stateMachine = new WorkflowStateMachine(
 *   'workflow-123',
 *   emitter,
 *   checkpointStorage
 * );
 *
 * // Transition to IN_PROGRESS
 * await stateMachine.start();
 *
 * // Add pending request
 * stateMachine.addPendingRequest('request-1');
 *
 * // Resolve request
 * stateMachine.resolvePendingRequest('request-1');
 *
 * // Complete workflow
 * await stateMachine.complete();
 * ```
 */
export class WorkflowStateMachine {
  private state: WorkflowRunState;
  private previousState?: WorkflowRunState;
  private pendingRequests: Set<string> = new Set();
  private readonly workflowId: string;
  private readonly executionId: string;
  private readonly eventEmitter: WorkflowEventEmitter;
  private readonly checkpointStorage?: CheckpointStorage;
  private currentCheckpointId?: string;

  constructor(
    workflowId: string,
    executionId: string,
    eventEmitter: WorkflowEventEmitter,
    checkpointStorage?: CheckpointStorage,
    initialState: WorkflowRunState = WorkflowRunState.IDLE
  ) {
    this.workflowId = workflowId;
    this.executionId = executionId;
    this.state = initialState;
    this.eventEmitter = eventEmitter;
    this.checkpointStorage = checkpointStorage;
  }

  /**
   * Get current state
   */
  getState(): WorkflowRunState {
    return this.state;
  }

  /**
   * Get previous state
   */
  getPreviousState(): WorkflowRunState | undefined {
    return this.previousState;
  }

  /**
   * Check if workflow has pending requests
   */
  isPending(): boolean {
    return this.pendingRequests.size > 0;
  }

  /**
   * Get pending request IDs
   */
  getPendingRequests(): string[] {
    return Array.from(this.pendingRequests);
  }

  /**
   * Start workflow execution
   */
  async start(): Promise<void> {
    await this.transition(WorkflowRunState.IN_PROGRESS);
  }

  /**
   * Complete workflow execution
   */
  async complete(): Promise<void> {
    await this.transition(WorkflowRunState.IDLE);
  }

  /**
   * Fail workflow execution
   */
  async fail(error: Error): Promise<void> {
    await this.transition(WorkflowRunState.FAILED);
  }

  /**
   * Add a pending request (human-in-the-loop)
   */
  addPendingRequest(requestId: string): void {
    this.pendingRequests.add(requestId);

    if (this.state === WorkflowRunState.IN_PROGRESS) {
      this.transitionSync(WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS);
    } else if (this.state === WorkflowRunState.IDLE) {
      this.transitionSync(WorkflowRunState.IDLE_WITH_PENDING_REQUESTS);
    }
  }

  /**
   * Resolve a pending request
   */
  resolvePendingRequest(requestId: string): void {
    this.pendingRequests.delete(requestId);

    // If no more pending requests, transition back
    if (this.pendingRequests.size === 0) {
      if (this.state === WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS) {
        this.transitionSync(WorkflowRunState.IN_PROGRESS);
      } else if (this.state === WorkflowRunState.IDLE_WITH_PENDING_REQUESTS) {
        this.transitionSync(WorkflowRunState.IDLE);
      }
    }
  }

  /**
   * Transition to new state (async)
   */
  private async transition(newState: WorkflowRunState): Promise<void> {
    if (!this.isValidTransition(this.state, newState)) {
      throw new Error(`Invalid state transition: ${this.state} → ${newState}`);
    }

    const oldState = this.state;
    this.previousState = oldState;
    this.state = newState;

    // Emit state change event
    this.eventEmitter.emit({
      type: 'workflow_status',
      timestamp: new Date(),
      workflowId: this.workflowId,
      executionId: this.executionId,
      state: newState,
      previousState: oldState
    });

    // Create checkpoint if storage is available
    if (this.checkpointStorage) {
      await this.createCheckpoint();
    }
  }

  /**
   * Transition to new state (synchronous)
   */
  private transitionSync(newState: WorkflowRunState): void {
    if (!this.isValidTransition(this.state, newState)) {
      throw new Error(`Invalid state transition: ${this.state} → ${newState}`);
    }

    const oldState = this.state;
    this.previousState = oldState;
    this.state = newState;

    // Emit state change event
    this.eventEmitter.emit({
      type: 'workflow_status',
      timestamp: new Date(),
      workflowId: this.workflowId,
      executionId: this.executionId,
      state: newState,
      previousState: oldState
    });
  }

  /**
   * Validate state transition
   */
  private isValidTransition(from: WorkflowRunState, to: WorkflowRunState): boolean {
    // Define valid transitions
    const validTransitions: Record<WorkflowRunState, WorkflowRunState[]> = {
      [WorkflowRunState.IDLE]: [
        WorkflowRunState.IN_PROGRESS,
        WorkflowRunState.IDLE_WITH_PENDING_REQUESTS
      ],
      [WorkflowRunState.IN_PROGRESS]: [
        WorkflowRunState.IDLE,
        WorkflowRunState.FAILED,
        WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS
      ],
      [WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS]: [
        WorkflowRunState.IN_PROGRESS,
        WorkflowRunState.FAILED
      ],
      [WorkflowRunState.IDLE_WITH_PENDING_REQUESTS]: [
        WorkflowRunState.IDLE,
        WorkflowRunState.IN_PROGRESS
      ],
      [WorkflowRunState.FAILED]: []
    };

    return validTransitions[from]?.includes(to) ?? false;
  }

  /**
   * Create checkpoint for current state
   */
  private async createCheckpoint(): Promise<void> {
    if (!this.checkpointStorage) return;

    // Generate checkpoint ID
    const checkpointId = `${this.executionId}_${Date.now()}`;

    // Note: Actual checkpoint creation would include executor states
    // This is a simplified example
    const checkpoint: WorkflowCheckpoint = {
      checkpointId,
      workflowId: this.workflowId,
      executionId: this.executionId,
      timestamp: new Date(),
      graphSignatureHash: '', // Would come from graph
      executorStates: {},
      pendingMessages: Array.from(this.pendingRequests).map(id => ({
        requestId: id,
        executorId: '',
        data: {},
        timestamp: new Date()
      })),
      sharedState: {}
    };

    await this.checkpointStorage.saveCheckpoint(checkpointId, checkpoint);
    this.currentCheckpointId = checkpointId;
  }

  /**
   * Restore state from checkpoint
   */
  async restoreFromCheckpoint(checkpointId: string): Promise<void> {
    if (!this.checkpointStorage) {
      throw new Error('Checkpoint storage not available');
    }

    const checkpoint = await this.checkpointStorage.loadCheckpoint(checkpointId);
    if (!checkpoint) {
      throw new Error(`Checkpoint ${checkpointId} not found`);
    }

    // Restore pending requests
    this.pendingRequests.clear();
    for (const msg of checkpoint.pendingMessages) {
      this.pendingRequests.add(msg.requestId);
    }

    // Restore state
    // Note: Actual implementation would restore executor states too
    this.currentCheckpointId = checkpointId;
  }
}
```

### Related Tasks
- **Blocked by**: TASK-301 (Graph structure)
- **Blocked by**: TASK-302 (Execution engine)
- **Blocked by**: TASK-303 (Event system)
- **Blocks**: TASK-310 (Workflow serialization)
- **Related**: TASK-304 (Checkpoint storage)

---

## Implementation Notes

### Key Architectural Decisions

**State Transition Validation**:
Prevent invalid state transitions:
```typescript
const validTransitions = {
  IDLE: [IN_PROGRESS],
  IN_PROGRESS: [IDLE, FAILED, IN_PROGRESS_PENDING_REQUESTS],
  // ... etc
};
```

**Automatic Checkpointing**:
Create checkpoint on every state transition:
```typescript
private async transition(newState) {
  this.state = newState;
  await this.createCheckpoint(); // Automatic
}
```

**Pending Request Tracking**:
Automatically transition when requests added/resolved:
```typescript
addPendingRequest(id) {
  this.pendingRequests.add(id);
  if (this.state === IN_PROGRESS) {
    this.transition(IN_PROGRESS_PENDING_REQUESTS);
  }
}
```

### Common Pitfalls

- Always validate state transitions
- Emit events before creating checkpoints
- Handle pending requests affecting state
- Remember to track previous state for debugging
- Don't forget FAILED is a terminal state
