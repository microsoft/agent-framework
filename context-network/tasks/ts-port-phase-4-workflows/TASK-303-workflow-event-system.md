# Task: TASK-303 Workflow Event System

**Phase**: 4
**Priority**: High
**Estimated Effort**: 5 hours
**Dependencies**: TASK-301 (Workflow Graph), TASK-302 (Workflow Executor)

### Objective
Implement the workflow event system for real-time monitoring of workflow execution, including event types, event emitters, and event handlers.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-8 (Workflows - Events)
- **Python Reference**: `/python/packages/core/agent_framework/workflows/events.py` - Workflow event types
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI.Workflows/Events/` - Workflow events
- **Standards**: CLAUDE.md § Python Architecture → Async-First Design

### Files to Create/Modify
- `src/workflows/events/types.ts` - Event type definitions
- `src/workflows/events/emitter.ts` - Event emitter implementation
- `src/workflows/events/__tests__/events.test.ts` - Unit tests
- `src/workflows/index.ts` - Export event types

### Implementation Requirements

**Core Functionality**:
1. Create base `WorkflowEvent` interface with common fields (type, timestamp, workflowId)
2. Implement `WorkflowStartedEvent` - workflow execution begins
3. Implement `WorkflowStatusEvent` - workflow state changes
4. Implement `WorkflowOutputEvent` - workflow produces output
5. Implement `WorkflowFailedEvent` - workflow execution fails
6. Implement `RequestInfoEvent` - human-in-the-loop request emitted
7. Implement `AgentRunEvent` - agent executor completes
8. Implement `AgentRunUpdateEvent` - agent executor streams update
9. Create `WorkflowRunState` enum (IN_PROGRESS, IDLE, FAILED, etc.)
10. Implement event emitter for publishing events

**Event Types**:
11. Use discriminated unions for type-safe event handling
12. Include execution context in all events (workflowId, executionId, timestamp)
13. Support custom event metadata
14. Implement event filtering and subscription

**TypeScript Patterns**:
- Use discriminated unions for event types
- Implement type guards for event type checking
- Use async iterables for event streams
- Export all types with comprehensive JSDoc
- Strict null checking

**Code Standards**:
- 120 character line length
- JSDoc documentation for all public APIs with `@example` tags
- Strict TypeScript mode enabled
- No `any` types without explicit justification comment

### Test Requirements
- [ ] Test WorkflowEvent base interface
- [ ] Test WorkflowStartedEvent creation
- [ ] Test WorkflowStatusEvent with all states
- [ ] Test WorkflowOutputEvent with data
- [ ] Test WorkflowFailedEvent with error details
- [ ] Test RequestInfoEvent with request ID
- [ ] Test AgentRunEvent with agent response
- [ ] Test AgentRunUpdateEvent with streaming update
- [ ] Test event type guards (isWorkflowStartedEvent, etc.)
- [ ] Test WorkflowRunState enum values
- [ ] Test event emitter publish/subscribe
- [ ] Test event filtering by type
- [ ] Test event metadata inclusion
- [ ] Test event timestamp generation
- [ ] Test discriminated union exhaustiveness

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] All workflow event types implemented
- [ ] WorkflowRunState enum with all states
- [ ] Type-safe event discriminated union
- [ ] Type guards for all event types
- [ ] Event emitter for publishing events
- [ ] Tests pass with >85% coverage
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings
- [ ] JSDoc complete for all public APIs with examples
- [ ] Exports added to index.ts files

### Example Code Pattern
```typescript
/**
 * Base workflow event interface
 */
export interface WorkflowEvent {
  type: string;
  timestamp: Date;
  workflowId: string;
  executionId?: string;
  metadata?: Record<string, any>;
}

/**
 * Workflow execution states
 */
export enum WorkflowRunState {
  IN_PROGRESS = 'IN_PROGRESS',
  IN_PROGRESS_PENDING_REQUESTS = 'IN_PROGRESS_PENDING_REQUESTS',
  IDLE = 'IDLE',
  IDLE_WITH_PENDING_REQUESTS = 'IDLE_WITH_PENDING_REQUESTS',
  FAILED = 'FAILED'
}

/**
 * Workflow started event
 */
export interface WorkflowStartedEvent extends WorkflowEvent {
  type: 'workflow_started';
}

/**
 * Workflow status changed event
 */
export interface WorkflowStatusEvent extends WorkflowEvent {
  type: 'workflow_status';
  state: WorkflowRunState;
  previousState?: WorkflowRunState;
}

/**
 * Workflow output event
 */
export interface WorkflowOutputEvent extends WorkflowEvent {
  type: 'workflow_output';
  data: any;
  executorId?: string;
}

/**
 * Workflow failed event
 */
export interface WorkflowFailedEvent extends WorkflowEvent {
  type: 'workflow_failed';
  error: Error;
  errorType: string;
  errorMessage: string;
  executorId?: string;
  stackTrace?: string;
}

/**
 * Request info event (human-in-the-loop)
 */
export interface RequestInfoEvent extends WorkflowEvent {
  type: 'request_info';
  requestId: string;
  data: any;
  executorId: string;
}

/**
 * Agent run completed event
 */
export interface AgentRunEvent extends WorkflowEvent {
  type: 'agent_run';
  executorId: string;
  agentId: string;
  response: AgentRunResponse;
}

/**
 * Agent run update event (streaming)
 */
export interface AgentRunUpdateEvent extends WorkflowEvent {
  type: 'agent_run_update';
  executorId: string;
  agentId: string;
  update: AgentRunResponseUpdate;
}

/**
 * Union type for all workflow events
 */
export type WorkflowEventUnion =
  | WorkflowStartedEvent
  | WorkflowStatusEvent
  | WorkflowOutputEvent
  | WorkflowFailedEvent
  | RequestInfoEvent
  | AgentRunEvent
  | AgentRunUpdateEvent;

/**
 * Type guards for workflow events
 */
export function isWorkflowStartedEvent(event: WorkflowEvent): event is WorkflowStartedEvent {
  return event.type === 'workflow_started';
}

export function isWorkflowStatusEvent(event: WorkflowEvent): event is WorkflowStatusEvent {
  return event.type === 'workflow_status';
}

export function isWorkflowOutputEvent(event: WorkflowEvent): event is WorkflowOutputEvent {
  return event.type === 'workflow_output';
}

export function isWorkflowFailedEvent(event: WorkflowEvent): event is WorkflowFailedEvent {
  return event.type === 'workflow_failed';
}

export function isRequestInfoEvent(event: WorkflowEvent): event is RequestInfoEvent {
  return event.type === 'request_info';
}

export function isAgentRunEvent(event: WorkflowEvent): event is AgentRunEvent {
  return event.type === 'agent_run';
}

export function isAgentRunUpdateEvent(event: WorkflowEvent): event is AgentRunUpdateEvent {
  return event.type === 'agent_run_update';
}

/**
 * Event emitter for workflow events
 *
 * @example
 * ```typescript
 * const emitter = new WorkflowEventEmitter();
 *
 * // Subscribe to events
 * for await (const event of emitter.events()) {
 *   if (isWorkflowStartedEvent(event)) {
 *     console.log('Workflow started:', event.workflowId);
 *   }
 * }
 *
 * // Emit event
 * emitter.emit({
 *   type: 'workflow_started',
 *   timestamp: new Date(),
 *   workflowId: 'workflow-123'
 * });
 * ```
 */
export class WorkflowEventEmitter {
  private listeners: Array<(event: WorkflowEventUnion) => void> = [];

  /**
   * Emit an event to all subscribers
   */
  emit(event: WorkflowEventUnion): void {
    for (const listener of this.listeners) {
      listener(event);
    }
  }

  /**
   * Subscribe to workflow events
   */
  on(listener: (event: WorkflowEventUnion) => void): () => void {
    this.listeners.push(listener);

    // Return unsubscribe function
    return () => {
      const index = this.listeners.indexOf(listener);
      if (index > -1) {
        this.listeners.splice(index, 1);
      }
    };
  }

  /**
   * Get async iterable of events
   */
  async *events(): AsyncIterable<WorkflowEventUnion> {
    const queue: WorkflowEventUnion[] = [];
    let resolve: ((value: WorkflowEventUnion) => void) | null = null;

    const listener = (event: WorkflowEventUnion) => {
      if (resolve) {
        resolve(event);
        resolve = null;
      } else {
        queue.push(event);
      }
    };

    const unsubscribe = this.on(listener);

    try {
      while (true) {
        if (queue.length > 0) {
          yield queue.shift()!;
        } else {
          yield await new Promise<WorkflowEventUnion>(r => {
            resolve = r;
          });
        }
      }
    } finally {
      unsubscribe();
    }
  }

  /**
   * Filter events by type
   */
  async *filterEvents<T extends WorkflowEventUnion>(
    typeName: T['type']
  ): AsyncIterable<T> {
    for await (const event of this.events()) {
      if (event.type === typeName) {
        yield event as T;
      }
    }
  }
}

/**
 * Create a workflow event with default fields
 */
export function createWorkflowEvent<T extends WorkflowEventUnion>(
  event: Omit<T, 'timestamp'>
): T {
  return {
    ...event,
    timestamp: new Date()
  } as T;
}
```

### Related Tasks
- **Blocked by**: TASK-301 (Graph structure for event context)
- **Blocked by**: TASK-302 (Executor for emitting events)
- **Blocks**: TASK-309 (Streaming needs event system)
- **Related**: TASK-306 (State machine uses workflow states)

---

## Implementation Notes

### Key Architectural Decisions

**Discriminated Union Pattern**:
Use TypeScript discriminated unions for type-safe event handling:
```typescript
type WorkflowEventUnion =
  | { type: 'workflow_started'; ... }
  | { type: 'workflow_failed'; error: Error; ... };

function handleEvent(event: WorkflowEventUnion) {
  switch (event.type) {
    case 'workflow_started':
      // TypeScript knows all 'workflow_started' fields
      break;
    case 'workflow_failed':
      // TypeScript knows 'error' field exists
      console.error(event.error);
      break;
  }
}
```

**Type Guards**:
Provide type guard functions for runtime type checking:
```typescript
if (isWorkflowFailedEvent(event)) {
  // event is WorkflowFailedEvent
  console.error(event.error);
}
```

**Event Streaming**:
Use async iterables for consuming events:
```typescript
for await (const event of emitter.events()) {
  console.log(event.type, event.timestamp);
}
```

### Common Pitfalls

- Always include timestamp in events
- Don't forget workflowId in all events
- Type guards must check exact type string
- Event emitter should handle unsubscribe properly
- Async iterables need cleanup on exit
