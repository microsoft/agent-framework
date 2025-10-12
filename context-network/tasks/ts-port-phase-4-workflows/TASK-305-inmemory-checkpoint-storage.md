# Task: TASK-305 InMemoryCheckpointStorage

**Phase**: 4
**Priority**: High
**Estimated Effort**: 4 hours
**Dependencies**: TASK-304 (Checkpoint Storage Interface)

### Objective
Implement an in-memory checkpoint storage implementation for development, testing, and simple workflow scenarios.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-8 (Workflows - Checkpointing)
- **Python Reference**: `/python/packages/core/agent_framework/workflows/checkpoint.py` - InMemoryCheckpointStorage
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI.Workflows/Checkpointing/InMemoryCheckpointStorage.cs`
- **Standards**: CLAUDE.md § Python Architecture → Async-First Design

### Files to Create/Modify
- `src/workflows/checkpoint/in-memory-storage.ts` - InMemoryCheckpointStorage class
- `src/workflows/checkpoint/__tests__/in-memory-storage.test.ts` - Unit tests
- `src/workflows/index.ts` - Export InMemoryCheckpointStorage

### Implementation Requirements

**Core Functionality**:
1. Implement `InMemoryCheckpointStorage` class implementing `CheckpointStorage`
2. Use `Map<string, WorkflowCheckpoint>` for storage
3. Implement `saveCheckpoint()` - store checkpoint in map
4. Implement `loadCheckpoint()` - retrieve checkpoint from map
5. Implement `listCheckpoints()` - filter and sort by workflow ID and timestamp
6. Implement `deleteCheckpoint()` - remove checkpoint from map
7. Support concurrent access (no race conditions)
8. Provide `clear()` method for testing
9. Provide `getAll()` method for debugging
10. Implement deep cloning to prevent mutation

**TypeScript Patterns**:
- Implement CheckpointStorage interface
- Use Map for efficient lookups
- Deep clone checkpoints on save/load
- Export class with comprehensive JSDoc
- Strict null checking

**Code Standards**:
- 120 character line length
- JSDoc documentation for all public APIs with `@example` tags
- Strict TypeScript mode enabled
- No `any` types without explicit justification comment

### Test Requirements
- [ ] Test saveCheckpoint() stores checkpoint
- [ ] Test loadCheckpoint() retrieves correct checkpoint
- [ ] Test loadCheckpoint() returns null for missing checkpoint
- [ ] Test listCheckpoints() returns checkpoints for workflow
- [ ] Test listCheckpoints() sorts by timestamp (newest first)
- [ ] Test deleteCheckpoint() removes checkpoint
- [ ] Test deleteCheckpoint() for non-existent checkpoint (no error)
- [ ] Test clear() removes all checkpoints
- [ ] Test getAll() returns all checkpoints
- [ ] Test deep cloning prevents external mutation
- [ ] Test concurrent save operations
- [ ] Test concurrent load operations
- [ ] Test checkpoint overwrite with same ID
- [ ] Test empty storage scenarios
- [ ] Test large checkpoint storage

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] InMemoryCheckpointStorage class implemented
- [ ] All CheckpointStorage methods implemented
- [ ] Deep cloning prevents mutation
- [ ] Concurrent access handled safely
- [ ] Tests pass with >85% coverage
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings
- [ ] JSDoc complete for all public APIs with examples
- [ ] Exports added to index.ts files

### Example Code Pattern
```typescript
import { CheckpointStorage, WorkflowCheckpoint } from './storage';

/**
 * In-memory checkpoint storage for development and testing
 *
 * @example
 * ```typescript
 * const storage = new InMemoryCheckpointStorage();
 *
 * // Save checkpoint
 * await storage.saveCheckpoint('checkpoint-1', checkpoint);
 *
 * // Load checkpoint
 * const loaded = await storage.loadCheckpoint('checkpoint-1');
 *
 * // List checkpoints for workflow
 * const checkpoints = await storage.listCheckpoints('workflow-123');
 * ```
 */
export class InMemoryCheckpointStorage implements CheckpointStorage {
  private checkpoints = new Map<string, WorkflowCheckpoint>();

  /**
   * Save a checkpoint (deep clones to prevent mutation)
   */
  async saveCheckpoint(checkpointId: string, checkpoint: WorkflowCheckpoint): Promise<void> {
    // Deep clone to prevent external mutation
    const cloned = this.deepClone(checkpoint);
    this.checkpoints.set(checkpointId, cloned);
  }

  /**
   * Load a checkpoint (deep clones to prevent mutation)
   */
  async loadCheckpoint(checkpointId: string): Promise<WorkflowCheckpoint | null> {
    const checkpoint = this.checkpoints.get(checkpointId);
    if (!checkpoint) {
      return null;
    }

    // Deep clone to prevent external mutation
    return this.deepClone(checkpoint);
  }

  /**
   * List all checkpoint IDs for a workflow, sorted by timestamp (newest first)
   */
  async listCheckpoints(workflowId: string): Promise<string[]> {
    const checkpoints = Array.from(this.checkpoints.values())
      .filter(cp => cp.workflowId === workflowId)
      .sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());

    return checkpoints.map(cp => cp.checkpointId);
  }

  /**
   * Delete a checkpoint
   */
  async deleteCheckpoint(checkpointId: string): Promise<void> {
    this.checkpoints.delete(checkpointId);
  }

  /**
   * Clear all checkpoints (useful for testing)
   */
  clear(): void {
    this.checkpoints.clear();
  }

  /**
   * Get all checkpoints (useful for debugging)
   */
  getAll(): WorkflowCheckpoint[] {
    return Array.from(this.checkpoints.values()).map(cp => this.deepClone(cp));
  }

  /**
   * Get checkpoint count
   */
  size(): number {
    return this.checkpoints.size;
  }

  /**
   * Deep clone an object to prevent mutation
   */
  private deepClone<T>(obj: T): T {
    return JSON.parse(JSON.stringify(obj));
  }
}
```

### Related Tasks
- **Blocked by**: TASK-304 (CheckpointStorage interface)
- **Blocks**: TASK-310 (Workflow serialization needs storage)
- **Related**: TASK-306 (State machine uses checkpoint storage)

---

## Implementation Notes

### Key Architectural Decisions

**Deep Cloning**:
Always deep clone checkpoints to prevent external mutation:
```typescript
// Save: clone to prevent external changes affecting stored checkpoint
const cloned = JSON.parse(JSON.stringify(checkpoint));
this.checkpoints.set(id, cloned);

// Load: clone to prevent external changes affecting stored checkpoint
return JSON.parse(JSON.stringify(this.checkpoints.get(id)));
```

**Sorting**:
Sort checkpoints by timestamp (newest first) for time-travel debugging:
```typescript
.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime())
```

**Thread Safety**:
JavaScript is single-threaded, but async operations can interleave. Use Map which is safe for concurrent reads and single writes.

### Common Pitfalls

- Don't forget to deep clone on both save and load
- Remember to convert Date objects properly in JSON serialization
- Handle null/undefined checkpoints gracefully
- Sort by timestamp descending (newest first)
- Clear() should be synchronous for testing
