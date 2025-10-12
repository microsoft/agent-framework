# Task: TASK-309 Workflow Streaming

**Phase**: 4
**Priority**: High
**Estimated Effort**: 6 hours
**Dependencies**: TASK-302 (Workflow Executor), TASK-303 (Event System)

### Objective
Implement streaming execution for workflows, yielding real-time events as the workflow progresses for monitoring and user feedback.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-8 (Workflows - Streaming)
- **Python Reference**: `/python/packages/core/agent_framework/workflows/runner.py` - Stream execution
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI.Workflows/WorkflowRunner.cs` - Streaming methods
- **Standards**: CLAUDE.md § Python Architecture → Async-First Design

### Files to Create/Modify
- `src/workflows/execution/streaming.ts` - Streaming utilities and helpers
- `src/workflows/workflow.ts` - Workflow class with runStream() method
- `src/workflows/execution/__tests__/streaming.test.ts` - Unit tests
- `src/workflows/index.ts` - Export streaming types

### Implementation Requirements

**Core Functionality**:
1. Implement `runStream()` method on Workflow class
2. Use async iterators (`AsyncIterable<WorkflowEvent>`) for streaming
3. Yield events in real-time as workflow executes
4. Support all workflow event types (started, status, output, failed, agent_run, etc.)
5. Handle streaming from agent executors (stream agent updates)
6. Emit executor-level events (executor started, completed, failed)
7. Buffer events if consumer is slow
8. Support backpressure handling
9. Implement event filtering for specific event types
10. Allow workflow resumption with streaming

**Event Streaming**:
11. Yield WorkflowStartedEvent at start
12. Yield WorkflowStatusEvent on state changes
13. Yield AgentRunUpdateEvent for streaming agents
14. Yield AgentRunEvent for completed agents
15. Yield RequestInfoEvent for human-in-the-loop
16. Yield WorkflowOutputEvent on completion
17. Yield WorkflowFailedEvent on error

**TypeScript Patterns**:
- Use async generators (`async function*`)
- Implement AsyncIterable interface
- Support for-await-of loops
- Export all types with comprehensive JSDoc
- Strict null checking

**Code Standards**:
- 120 character line length
- JSDoc documentation for all public APIs with `@example` tags
- Strict TypeScript mode enabled
- No `any` types without explicit justification comment

### Test Requirements
- [ ] Test runStream() returns AsyncIterable
- [ ] Test runStream() yields WorkflowStartedEvent first
- [ ] Test runStream() yields events in correct order
- [ ] Test WorkflowStatusEvent emitted on state changes
- [ ] Test AgentRunUpdateEvent for streaming agents
- [ ] Test AgentRunEvent for completed agents
- [ ] Test RequestInfoEvent for human-in-the-loop
- [ ] Test WorkflowOutputEvent on success
- [ ] Test WorkflowFailedEvent on error
- [ ] Test event buffering for slow consumers
- [ ] Test backpressure handling
- [ ] Test event filtering by type
- [ ] Test for-await-of consumption
- [ ] Test workflow resumption with streaming
- [ ] Test concurrent workflow streams

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] runStream() method implemented on Workflow
- [ ] AsyncIterable yields all event types
- [ ] Events emitted in real-time during execution
- [ ] Agent streaming updates forwarded correctly
- [ ] Event buffering and backpressure handled
- [ ] Tests pass with >85% coverage
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings
- [ ] JSDoc complete for all public APIs with examples
- [ ] Exports added to index.ts files

### Example Code Pattern
```typescript
import { WorkflowGraph } from '../graph';
import { WorkflowEvent, WorkflowEventUnion } from '../events';
import { ExecutionContext } from './context';
import { WorkflowRunner } from './runner';

/**
 * Workflow class with streaming execution support
 *
 * @example
 * ```typescript
 * const workflow = new WorkflowBuilder()
 *   .addAgent(researchAgent, 'research')
 *   .addAgent(summaryAgent, 'summary')
 *   .addEdge('research', 'summary')
 *   .setEntry('research')
 *   .build();
 *
 * // Stream workflow execution
 * for await (const event of workflow.runStream('Research AI agents')) {
 *   console.log(`[${event.type}]`, event.timestamp);
 *
 *   if (event.type === 'agent_run_update') {
 *     process.stdout.write(event.update.text ?? '');
 *   }
 *
 *   if (event.type === 'request_info') {
 *     // Pause for user input
 *     const answer = await getUserInput(event.data);
 *     await workflow.sendResponse({ [event.requestId]: answer });
 *   }
 * }
 * ```
 */
export class Workflow {
  private readonly graph: WorkflowGraph;
  private readonly runner: WorkflowRunner;

  constructor(graph: WorkflowGraph) {
    this.graph = graph;
    this.runner = new WorkflowRunner(graph);
  }

  /**
   * Execute workflow synchronously
   */
  async run(input: any, options?: WorkflowRunOptions): Promise<WorkflowRunResult> {
    return await this.runner.run(input, options);
  }

  /**
   * Execute workflow with streaming events
   *
   * Yields real-time events as the workflow executes. Use for-await-of to consume.
   */
  async *runStream(
    input: any,
    options?: WorkflowRunOptions
  ): AsyncIterable<WorkflowEventUnion> {
    // Delegate to runner's streaming execution
    yield* this.runner.runStream(input, options);
  }

  /**
   * Resume workflow from checkpoint with streaming
   */
  async *runFromCheckpointStream(
    checkpointId: string,
    responses?: Record<string, any>
  ): AsyncIterable<WorkflowEventUnion> {
    yield* this.runner.runFromCheckpointStream(checkpointId, responses);
  }

  /**
   * Send responses to pending requests and continue execution
   */
  async *sendResponsesStreaming(
    responses: Record<string, any>
  ): AsyncIterable<WorkflowEventUnion> {
    yield* this.runner.sendResponsesStreaming(responses);
  }

  /**
   * Filter events by type
   */
  async *filterEvents<T extends WorkflowEventUnion>(
    eventType: T['type'],
    source: AsyncIterable<WorkflowEventUnion>
  ): AsyncIterable<T> {
    for await (const event of source) {
      if (event.type === eventType) {
        yield event as T;
      }
    }
  }
}

/**
 * Stream buffer for handling backpressure
 */
export class EventStreamBuffer {
  private queue: WorkflowEventUnion[] = [];
  private waiters: Array<(event: WorkflowEventUnion) => void> = [];
  private ended = false;
  private error?: Error;

  /**
   * Add event to buffer
   */
  push(event: WorkflowEventUnion): void {
    if (this.ended) {
      throw new Error('Cannot push to ended stream');
    }

    if (this.waiters.length > 0) {
      // Immediately resolve waiting consumer
      const waiter = this.waiters.shift()!;
      waiter(event);
    } else {
      // Buffer event
      this.queue.push(event);
    }
  }

  /**
   * Mark stream as ended
   */
  end(error?: Error): void {
    this.ended = true;
    this.error = error;

    // Resolve all waiters
    while (this.waiters.length > 0) {
      const waiter = this.waiters.shift()!;
      if (error) {
        throw error;
      }
    }
  }

  /**
   * Get next event from buffer
   */
  async next(): Promise<WorkflowEventUnion | undefined> {
    // Return buffered event if available
    if (this.queue.length > 0) {
      return this.queue.shift()!;
    }

    // Check if stream ended
    if (this.ended) {
      if (this.error) throw this.error;
      return undefined;
    }

    // Wait for next event
    return new Promise((resolve, reject) => {
      this.waiters.push((event) => {
        resolve(event);
      });
    });
  }

  /**
   * Async iterator implementation
   */
  async *[Symbol.asyncIterator](): AsyncIterator<WorkflowEventUnion> {
    while (true) {
      const event = await this.next();
      if (event === undefined) break;
      yield event;
    }
  }
}

/**
 * Collect all events from stream into array
 */
export async function collectEvents(
  stream: AsyncIterable<WorkflowEventUnion>
): Promise<WorkflowEventUnion[]> {
  const events: WorkflowEventUnion[] = [];
  for await (const event of stream) {
    events.push(event);
  }
  return events;
}

/**
 * Tap into stream without consuming
 */
export async function* tapEvents(
  stream: AsyncIterable<WorkflowEventUnion>,
  callback: (event: WorkflowEventUnion) => void | Promise<void>
): AsyncIterable<WorkflowEventUnion> {
  for await (const event of stream) {
    const result = callback(event);
    if (result instanceof Promise) {
      await result;
    }
    yield event;
  }
}

/**
 * Transform stream events
 */
export async function* mapEvents<T>(
  stream: AsyncIterable<WorkflowEventUnion>,
  mapper: (event: WorkflowEventUnion) => T | Promise<T>
): AsyncIterable<T> {
  for await (const event of stream) {
    const result = mapper(event);
    yield result instanceof Promise ? await result : result;
  }
}
```

### Related Tasks
- **Blocked by**: TASK-302 (Workflow executor implementation)
- **Blocked by**: TASK-303 (Event system)
- **Related**: TASK-308 (RequestInfoExecutor emits events in stream)
- **Related**: TASK-101 (ChatAgent streaming forwards to workflow)

---

## Implementation Notes

### Key Architectural Decisions

**Async Generators**:
Use async generators for natural streaming:
```typescript
async function* runStream() {
  yield { type: 'workflow_started' };
  // ... execute ...
  yield { type: 'agent_run_update', update: ... };
  yield { type: 'workflow_output', data: result };
}
```

**Backpressure Handling**:
Buffer events if consumer is slow:
```typescript
class EventStreamBuffer {
  private queue = [];

  push(event) {
    if (waiters.length > 0) {
      // Immediate delivery
      waiters.shift()(event);
    } else {
      // Buffer
      queue.push(event);
    }
  }
}
```

**Event Forwarding**:
Forward agent streaming updates to workflow stream:
```typescript
if (executor instanceof AgentExecutor) {
  for await (const update of agent.runStream()) {
    yield { type: 'agent_run_update', update };
  }
}
```

### Common Pitfalls

- Don't block on slow consumers (buffer events)
- Always yield WorkflowStartedEvent first
- Remember to yield WorkflowOutputEvent on completion
- Forward agent streaming updates correctly
- Handle async iterator cleanup (try/finally)
