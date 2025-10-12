# Task: TASK-304 Checkpoint Storage Interface

**Phase**: 4
**Priority**: High
**Estimated Effort**: 4 hours
**Dependencies**: TASK-301 (Workflow Graph), TASK-302 (Workflow Executor)

### Objective
Implement the checkpoint storage interface and data structures for persisting workflow state, enabling time-travel debugging and workflow resumption.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-8 (Workflows - Checkpointing)
- **Python Reference**: `/python/packages/core/agent_framework/workflows/checkpoint.py` - Checkpoint storage
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI.Workflows/Checkpointing/` - Checkpoint system
- **Standards**: CLAUDE.md § Python Architecture → Async-First Design

### Files to Create/Modify
- `src/workflows/checkpoint/storage.ts` - CheckpointStorage interface
- `src/workflows/checkpoint/types.ts` - Checkpoint data structures
- `src/workflows/checkpoint/__tests__/storage.test.ts` - Unit tests
- `src/workflows/index.ts` - Export checkpoint types

### Implementation Requirements

**Core Functionality**:
1. Create `CheckpointStorage` interface for checkpoint persistence
2. Implement `WorkflowCheckpoint` data structure
3. Define checkpoint metadata (checkpointId, workflowId, timestamp, etc.)
4. Include graph signature hash for compatibility validation
5. Store executor states (outputs, internal state)
6. Store pending messages and requests
7. Store shared state
8. Implement `saveCheckpoint()` method
9. Implement `loadCheckpoint()` method
10. Implement `listCheckpoints()` method for workflow history

**Checkpoint Data**:
11. Checkpoint ID (unique identifier)
12. Workflow ID (which workflow this checkpoint belongs to)
13. Execution ID (which execution run)
14. Timestamp (when checkpoint was created)
15. Graph signature hash (for compatibility checking)
16. Executor states (map of executor ID to state)
17. Pending requests (for human-in-the-loop)
18. Shared state (global workflow state)
19. Serialized execution context

**TypeScript Patterns**:
- Use interfaces for storage abstraction
- Implement async methods for I/O operations
- Use type-safe checkpoint data structures
- Export all types with comprehensive JSDoc
- Strict null checking

**Code Standards**:
- 120 character line length
- JSDoc documentation for all public APIs with `@example` tags
- Strict TypeScript mode enabled
- No `any` types without explicit justification comment

### Test Requirements
- [ ] Test CheckpointStorage interface definition
- [ ] Test WorkflowCheckpoint structure creation
- [ ] Test checkpoint metadata completeness
- [ ] Test graph signature hash inclusion
- [ ] Test executor states serialization
- [ ] Test pending messages storage
- [ ] Test shared state storage
- [ ] Test saveCheckpoint() saves all data
- [ ] Test loadCheckpoint() retrieves correct checkpoint
- [ ] Test loadCheckpoint() returns null for missing checkpoint
- [ ] Test listCheckpoints() filters by workflow ID
- [ ] Test deleteCheckpoint() removes checkpoint
- [ ] Test checkpoint serialization/deserialization
- [ ] Test error handling for invalid checkpoints
- [ ] Test concurrent checkpoint operations

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] CheckpointStorage interface defined
- [ ] WorkflowCheckpoint data structure complete
- [ ] All checkpoint metadata fields included
- [ ] Graph signature hash for compatibility
- [ ] Async storage methods implemented
- [ ] Tests pass with >85% coverage
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings
- [ ] JSDoc complete for all public APIs with examples
- [ ] Exports added to index.ts files

### Example Code Pattern
```typescript
/**
 * Interface for checkpoint storage implementations
 */
export interface CheckpointStorage {
  /**
   * Save a workflow checkpoint
   */
  saveCheckpoint(checkpointId: string, checkpoint: WorkflowCheckpoint): Promise<void>;

  /**
   * Load a workflow checkpoint by ID
   */
  loadCheckpoint(checkpointId: string): Promise<WorkflowCheckpoint | null>;

  /**
   * List all checkpoints for a workflow
   */
  listCheckpoints(workflowId: string): Promise<string[]>;

  /**
   * Delete a checkpoint
   */
  deleteCheckpoint(checkpointId: string): Promise<void>;
}

/**
 * Workflow checkpoint data structure
 */
export interface WorkflowCheckpoint {
  /**
   * Unique checkpoint identifier
   */
  checkpointId: string;

  /**
   * Workflow identifier
   */
  workflowId: string;

  /**
   * Execution identifier
   */
  executionId: string;

  /**
   * Timestamp when checkpoint was created
   */
  timestamp: Date;

  /**
   * Graph signature hash for compatibility validation
   */
  graphSignatureHash: string;

  /**
   * Executor states (outputs and internal state)
   */
  executorStates: Record<string, ExecutorState>;

  /**
   * Pending messages for human-in-the-loop
   */
  pendingMessages: PendingMessage[];

  /**
   * Shared state accessible to all executors
   */
  sharedState: Record<string, any>;

  /**
   * Execution context at time of checkpoint
   */
  executionContext?: SerializedExecutionContext;

  /**
   * Custom metadata
   */
  metadata?: Record<string, any>;
}

/**
 * Executor state at checkpoint
 */
export interface ExecutorState {
  executorId: string;
  output?: any;
  internalState?: any;
  completed: boolean;
  error?: {
    message: string;
    stack?: string;
    type: string;
  };
}

/**
 * Pending message for human-in-the-loop
 */
export interface PendingMessage {
  requestId: string;
  executorId: string;
  data: any;
  timestamp: Date;
}

/**
 * Serialized execution context
 */
export interface SerializedExecutionContext {
  workflowId: string;
  executionId: string;
  threadState?: any;
  sharedState: Record<string, any>;
  executorOutputs: Record<string, any>;
}

/**
 * Create a checkpoint from current workflow state
 */
export function createCheckpoint(
  workflowId: string,
  executionId: string,
  graphSignatureHash: string,
  executorStates: Map<string, ExecutorState>,
  executionContext: ExecutionContext,
  options?: {
    checkpointId?: string;
    metadata?: Record<string, any>;
  }
): WorkflowCheckpoint {
  return {
    checkpointId: options?.checkpointId ?? generateCheckpointId(),
    workflowId,
    executionId,
    timestamp: new Date(),
    graphSignatureHash,
    executorStates: Object.fromEntries(executorStates),
    pendingMessages: [],
    sharedState: Object.fromEntries(executionContext.sharedState),
    executionContext: {
      workflowId: executionContext.workflowId,
      executionId: executionContext.executionId,
      threadState: executionContext.thread?.serialize(),
      sharedState: Object.fromEntries(executionContext.sharedState),
      executorOutputs: Object.fromEntries(executionContext.executorOutputs)
    },
    metadata: options?.metadata
  };
}

/**
 * Validate checkpoint compatibility with graph
 */
export function validateCheckpointCompatibility(
  checkpoint: WorkflowCheckpoint,
  currentGraphSignature: string
): boolean {
  return checkpoint.graphSignatureHash === currentGraphSignature;
}

/**
 * Generate unique checkpoint ID
 */
function generateCheckpointId(): string {
  return `checkpoint_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Example implementation: In-memory checkpoint storage
 */
export class InMemoryCheckpointStorage implements CheckpointStorage {
  private checkpoints = new Map<string, WorkflowCheckpoint>();

  async saveCheckpoint(checkpointId: string, checkpoint: WorkflowCheckpoint): Promise<void> {
    this.checkpoints.set(checkpointId, checkpoint);
  }

  async loadCheckpoint(checkpointId: string): Promise<WorkflowCheckpoint | null> {
    return this.checkpoints.get(checkpointId) ?? null;
  }

  async listCheckpoints(workflowId: string): Promise<string[]> {
    return Array.from(this.checkpoints.values())
      .filter(cp => cp.workflowId === workflowId)
      .sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime())
      .map(cp => cp.checkpointId);
  }

  async deleteCheckpoint(checkpointId: string): Promise<void> {
    this.checkpoints.delete(checkpointId);
  }

  /**
   * Clear all checkpoints (for testing)
   */
  clear(): void {
    this.checkpoints.clear();
  }
}
```

### Related Tasks
- **Blocked by**: TASK-301 (Graph signature needed for compatibility)
- **Blocked by**: TASK-302 (Execution state needed for checkpoints)
- **Blocks**: TASK-305 (InMemoryCheckpointStorage implementation)
- **Blocks**: TASK-310 (Workflow serialization uses checkpoints)
- **Related**: TASK-306 (State machine creates checkpoints)

---

## Implementation Notes

### Key Architectural Decisions

**Interface-Based Design**:
Provide interface for multiple storage backends:
```typescript
// In-memory for development
const storage = new InMemoryCheckpointStorage();

// Redis for production
const storage = new RedisCheckpointStorage(redisClient);

// File system for debugging
const storage = new FileCheckpointStorage('./checkpoints');
```

**Graph Signature Validation**:
Prevent loading incompatible checkpoints:
```typescript
const checkpoint = await storage.loadCheckpoint(checkpointId);
if (!validateCheckpointCompatibility(checkpoint, graph.getSignatureHash())) {
  throw new Error('Checkpoint incompatible with current graph');
}
```

**Checkpoint Granularity**:
Checkpoint after each executor completion for fine-grained recovery:
```typescript
// Save checkpoint after executor completes
await storage.saveCheckpoint(
  `${executionId}_${executorId}`,
  createCheckpoint(workflowId, executionId, ...)
);
```

### Common Pitfalls

- Always validate graph signature before loading checkpoint
- Don't forget to serialize Date objects properly
- Include all executor internal state, not just outputs
- Remember pending requests for human-in-the-loop
- Handle serialization errors gracefully
