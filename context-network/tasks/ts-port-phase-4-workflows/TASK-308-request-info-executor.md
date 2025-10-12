# Task: TASK-308 RequestInfoExecutor (Human-in-the-Loop)

**Phase**: 4
**Priority**: High
**Estimated Effort**: 6 hours
**Dependencies**: TASK-301 (Workflow Graph), TASK-302 (Workflow Executor), TASK-303 (Event System)

### Objective
Implement the RequestInfoExecutor for human-in-the-loop workflows, allowing workflows to pause and request information from external systems or users.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-8 (Workflows - Human-in-the-Loop)
- **Python Reference**: `/python/packages/core/agent_framework/workflows/executors.py` - RequestInfoExecutor
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI.Workflows/Executors/RequestInfoExecutor.cs`
- **Standards**: CLAUDE.md § Python Architecture → Async-First Design

### Files to Create/Modify
- `src/workflows/executors/request-info-executor.ts` - RequestInfoExecutor class
- `src/workflows/executors/__tests__/request-info-executor.test.ts` - Unit tests
- `src/workflows/index.ts` - Export RequestInfoExecutor

### Implementation Requirements

**Core Functionality**:
1. Implement `RequestInfoExecutor` class extending `Executor`
2. Generate unique request IDs for each request
3. Emit `RequestInfoEvent` when executed
4. Store pending requests in execution context
5. Provide `handleResponse()` method to resolve requests
6. Support typed request/response data
7. Handle request timeouts
8. Support request cancellation
9. Emit events for request lifecycle (requested, responded, timeout)
10. Integrate with workflow state machine for pending state

**Request Management**:
11. Track pending requests with IDs
12. Store request metadata (timestamp, data, executor ID)
13. Validate responses match pending requests
14. Handle multiple concurrent requests
15. Clean up resolved requests

**TypeScript Patterns**:
- Implement Executor interface
- Use generic types for request/response data
- Use Promise-based API for responses
- Export all types with comprehensive JSDoc
- Strict null checking

**Code Standards**:
- 120 character line length
- JSDoc documentation for all public APIs with `@example` tags
- Strict TypeScript mode enabled
- No `any` types without explicit justification comment

### Test Requirements
- [ ] Test RequestInfoExecutor creation
- [ ] Test execute() emits RequestInfoEvent
- [ ] Test unique request ID generation
- [ ] Test pending request storage
- [ ] Test handleResponse() resolves pending request
- [ ] Test handleResponse() rejects invalid request ID
- [ ] Test multiple concurrent requests
- [ ] Test request timeout handling
- [ ] Test request cancellation
- [ ] Test typed request/response data
- [ ] Test execution context integration
- [ ] Test workflow state machine integration
- [ ] Test request metadata (timestamp, data)
- [ ] Test error handling for missing requests
- [ ] Test cleanup of resolved requests

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] RequestInfoExecutor class implemented
- [ ] RequestInfoEvent emitted on execution
- [ ] Pending request management working
- [ ] handleResponse() resolves requests correctly
- [ ] Request timeout and cancellation supported
- [ ] Typed request/response data
- [ ] Tests pass with >85% coverage
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings
- [ ] JSDoc complete for all public APIs with examples
- [ ] Exports added to index.ts files

### Example Code Pattern
```typescript
import { Executor, ExecutorResult } from '../graph/executor';
import { ExecutionContext } from '../execution/context';
import { RequestInfoEvent } from '../events';

/**
 * Request data structure
 */
export interface RequestInfo<TData = any> {
  requestId: string;
  executorId: string;
  data: TData;
  timestamp: Date;
  timeoutMs?: number;
}

/**
 * Response data structure
 */
export interface RequestResponse<TResponse = any> {
  requestId: string;
  data: TResponse;
  timestamp: Date;
}

/**
 * Executor for human-in-the-loop workflows
 *
 * Emits a RequestInfoEvent and waits for external response via handleResponse()
 *
 * @example
 * ```typescript
 * // In workflow definition
 * const requestExecutor = new RequestInfoExecutor<QuestionData, AnswerData>({
 *   id: 'user_input',
 *   name: 'Request user input'
 * });
 *
 * workflow.addExecutor('request', requestExecutor);
 *
 * // During workflow execution
 * for await (const event of workflow.runStream(input)) {
 *   if (event.type === 'request_info') {
 *     // Pause and get user input
 *     const answer = await promptUser(event.data);
 *
 *     // Resume workflow with response
 *     await workflow.sendResponse({
 *       [event.requestId]: answer
 *     });
 *   }
 * }
 * ```
 */
export class RequestInfoExecutor<TInput = any, TOutput = any> implements Executor<TInput, TOutput> {
  public readonly id: string;
  public readonly name?: string;
  private pendingRequests = new Map<string, {
    request: RequestInfo<TInput>;
    resolve: (value: TOutput) => void;
    reject: (error: Error) => void;
    timeout?: NodeJS.Timeout;
  }>();
  private readonly timeoutMs?: number;

  constructor(options: {
    id: string;
    name?: string;
    timeoutMs?: number;
  }) {
    this.id = options.id;
    this.name = options.name;
    this.timeoutMs = options.timeoutMs;
  }

  /**
   * Execute the request info node
   */
  async execute(input: TInput, context: ExecutionContext): Promise<ExecutorResult<TOutput>> {
    // Generate unique request ID
    const requestId = this.generateRequestId();

    // Create request
    const request: RequestInfo<TInput> = {
      requestId,
      executorId: this.id,
      data: input,
      timestamp: new Date(),
      timeoutMs: this.timeoutMs
    };

    // Emit request event
    const event: RequestInfoEvent = {
      type: 'request_info',
      timestamp: new Date(),
      workflowId: context.workflowId,
      executionId: context.executionId,
      requestId,
      data: input,
      executorId: this.id
    };

    // Store event in context (so it can be yielded)
    context.addPendingEvent(event);

    // Create promise for response
    const responsePromise = new Promise<TOutput>((resolve, reject) => {
      // Setup timeout if configured
      let timeout: NodeJS.Timeout | undefined;
      if (this.timeoutMs) {
        timeout = setTimeout(() => {
          this.pendingRequests.delete(requestId);
          reject(new Error(`Request ${requestId} timed out after ${this.timeoutMs}ms`));
        }, this.timeoutMs);
      }

      // Store pending request
      this.pendingRequests.set(requestId, {
        request,
        resolve,
        reject,
        timeout
      });
    });

    try {
      // Wait for response
      const output = await responsePromise;

      return {
        output,
        metadata: {
          requestId,
          respondedAt: new Date()
        }
      };
    } catch (error) {
      return {
        output: undefined as any,
        error: error instanceof Error ? error : new Error(String(error)),
        metadata: {
          requestId,
          timedOut: true
        }
      };
    }
  }

  /**
   * Handle response to a pending request
   */
  async handleResponse(requestId: string, data: TOutput): Promise<void> {
    const pending = this.pendingRequests.get(requestId);

    if (!pending) {
      throw new Error(`No pending request found with ID: ${requestId}`);
    }

    // Clear timeout if set
    if (pending.timeout) {
      clearTimeout(pending.timeout);
    }

    // Remove from pending
    this.pendingRequests.delete(requestId);

    // Resolve promise
    pending.resolve(data);
  }

  /**
   * Cancel a pending request
   */
  cancelRequest(requestId: string): void {
    const pending = this.pendingRequests.get(requestId);

    if (!pending) {
      throw new Error(`No pending request found with ID: ${requestId}`);
    }

    // Clear timeout if set
    if (pending.timeout) {
      clearTimeout(pending.timeout);
    }

    // Remove from pending
    this.pendingRequests.delete(requestId);

    // Reject promise
    pending.reject(new Error(`Request ${requestId} was cancelled`));
  }

  /**
   * Get all pending request IDs
   */
  getPendingRequestIds(): string[] {
    return Array.from(this.pendingRequests.keys());
  }

  /**
   * Check if a request is pending
   */
  isRequestPending(requestId: string): boolean {
    return this.pendingRequests.has(requestId);
  }

  getInputSignature(): string {
    return 'any';
  }

  getOutputSignature(): string {
    return 'any';
  }

  private generateRequestId(): string {
    return `request_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }
}
```

### Related Tasks
- **Blocked by**: TASK-301 (Executor interface)
- **Blocked by**: TASK-302 (Execution context)
- **Blocked by**: TASK-303 (RequestInfoEvent)
- **Related**: TASK-306 (State machine tracks pending requests)
- **Related**: TASK-309 (Streaming workflows emit request events)

---

## Implementation Notes

### Key Architectural Decisions

**Promise-Based Waiting**:
Use Promise to block execution until response:
```typescript
const responsePromise = new Promise((resolve, reject) => {
  this.pendingRequests.set(requestId, { resolve, reject });
});

const output = await responsePromise; // Blocks until handleResponse()
```

**Timeout Handling**:
Automatically reject promise on timeout:
```typescript
const timeout = setTimeout(() => {
  pending.reject(new Error('Timeout'));
  this.pendingRequests.delete(requestId);
}, timeoutMs);
```

**Event Integration**:
Emit RequestInfoEvent through workflow event system:
```typescript
context.addPendingEvent({
  type: 'request_info',
  requestId,
  data: input
});
```

### Common Pitfalls

- Always clear timeout when resolving/rejecting
- Validate request ID exists before handling response
- Remove from pending map after resolution
- Handle concurrent requests properly
- Don't forget to emit RequestInfoEvent
