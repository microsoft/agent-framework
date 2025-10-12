# Task: TASK-302 Workflow Executor Base

**Phase**: 4
**Priority**: Critical
**Estimated Effort**: 7 hours
**Dependencies**: TASK-301 (Workflow Graph)

### Objective
Implement the workflow execution engine that traverses the graph, executes nodes, manages state, and handles edge routing for multi-agent orchestration.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-8 (Workflows)
- **Python Reference**: `/python/packages/core/agent_framework/workflows/runner.py` - Workflow runner implementation
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI.Workflows/WorkflowEngine.cs` - Workflow execution engine
- **Standards**: CLAUDE.md § Python Architecture → Async-First Design

### Files to Create/Modify
- `src/workflows/execution/runner.ts` - Workflow runner/executor
- `src/workflows/execution/context.ts` - Execution context
- `src/workflows/execution/state.ts` - Execution state management
- `src/workflows/execution/__tests__/runner.test.ts` - Unit tests
- `src/workflows/index.ts` - Export runner and context types

### Implementation Requirements

**Core Functionality**:
1. Create `WorkflowRunner` class to execute workflow graphs
2. Implement `ExecutionContext` for passing state between executors
3. Implement graph traversal algorithm (topological sort with dependencies)
4. Execute executors in correct order based on edges
5. Handle direct edges (simple sequential execution)
6. Handle conditional edges (branch based on predicate)
7. Handle fan-out edges (parallel execution)
8. Handle fan-in edges (wait for all inputs, merge results)
9. Handle switch-case edges (multi-way branching)
10. Maintain shared state accessible to all executors

**State Management**:
11. Track executor outputs for later access
12. Maintain pending executor queue
13. Track completed executors
14. Handle executor errors and failures
15. Support state snapshots for checkpointing (TASK-304)

**Execution Modes**:
16. Synchronous execution (`run()`) - wait for completion
17. Streaming execution (`runStream()`) - yield events as they occur
18. Resume from checkpoint - restore state and continue

**Error Handling**:
19. Catch executor failures and emit error events
20. Support error propagation vs. graceful degradation
21. Provide detailed error context (executor ID, input, stack trace)
22. Allow retry policies for failed executors

**TypeScript Patterns**:
- Use async/await throughout for executor execution
- Implement async iterators for streaming execution
- Use type-safe execution context
- Provide comprehensive error types
- Export all types with comprehensive JSDoc

**Code Standards**:
- 120 character line length
- JSDoc documentation for all public APIs with `@example` tags
- Strict TypeScript mode enabled
- No `any` types without explicit justification comment

### Test Requirements
- [ ] Test WorkflowRunner creation with valid graph
- [ ] Test sequential execution of direct edges
- [ ] Test conditional edge branching (true and false paths)
- [ ] Test fan-out edge parallel execution
- [ ] Test fan-in edge result merging
- [ ] Test switch-case edge routing to correct branch
- [ ] Test shared state access across executors
- [ ] Test executor error handling and propagation
- [ ] Test execution context passed to executors correctly
- [ ] Test completed executors tracked properly
- [ ] Test pending executor queue management
- [ ] Test synchronous run() returns final result
- [ ] Test streaming runStream() yields events
- [ ] Test workflow execution with nested workflows
- [ ] Test error scenarios (invalid graph, missing executors, etc.)

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] WorkflowRunner executes graphs correctly
- [ ] All edge types handled properly (direct, conditional, fan-out, fan-in, switch-case)
- [ ] Shared state management works across executors
- [ ] Error handling and propagation implemented
- [ ] Synchronous and streaming execution modes work
- [ ] Execution context provides necessary data to executors
- [ ] Tests pass with >85% coverage
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings
- [ ] JSDoc complete for all public APIs with examples
- [ ] Exports added to index.ts files

### Example Code Pattern
```typescript
import { WorkflowGraph, Executor, Edge, ExecutorResult } from '../graph';
import { WorkflowEvent } from '../events';
import { ExecutionContext } from './context';

/**
 * Workflow runner for executing workflow graphs
 *
 * @example
 * ```typescript
 * const graph = new WorkflowGraph();
 * graph.addExecutor('agent1', new AgentExecutor(agent));
 * graph.addExecutor('agent2', new AgentExecutor(agent2));
 * graph.addEdge({ type: 'direct', from: 'agent1', to: 'agent2' });
 * graph.setEntry('agent1');
 *
 * const runner = new WorkflowRunner(graph);
 * const result = await runner.run('Hello');
 * console.log(result.output);
 * ```
 */
export class WorkflowRunner {
  private readonly graph: WorkflowGraph;
  private executionContext?: ExecutionContext;

  constructor(graph: WorkflowGraph) {
    this.graph = graph;
    // Validate graph on construction
    this.graph.validate();
  }

  /**
   * Execute workflow synchronously and return final result
   */
  async run(input: any, options?: WorkflowRunOptions): Promise<WorkflowRunResult> {
    const events: WorkflowEvent[] = [];

    // Collect all events from streaming execution
    for await (const event of this.runStream(input, options)) {
      events.push(event);
    }

    // Extract final output from events
    const outputEvent = events.find(e => e.type === 'workflow_output');
    const failedEvent = events.find(e => e.type === 'workflow_failed');

    if (failedEvent) {
      throw (failedEvent as WorkflowFailedEvent).error;
    }

    return {
      output: outputEvent ? (outputEvent as WorkflowOutputEvent).data : undefined,
      events,
      executionId: this.executionContext!.executionId
    };
  }

  /**
   * Execute workflow with streaming events
   */
  async *runStream(
    input: any,
    options?: WorkflowRunOptions
  ): AsyncIterable<WorkflowEvent> {
    // Initialize execution context
    this.executionContext = this.createExecutionContext(options);

    // Emit workflow started event
    yield {
      type: 'workflow_started',
      timestamp: new Date(),
      workflowId: this.executionContext.workflowId
    } as WorkflowStartedEvent;

    try {
      // Execute graph starting from entry executor
      const entryExecutorId = this.graph.getEntryExecutorId();
      const entryExecutor = this.graph.getExecutor(entryExecutorId);

      // Execute entry executor
      const result = await entryExecutor.execute(input, this.executionContext);

      // Store result
      this.executionContext.setExecutorOutput(entryExecutorId, result.output);

      // Emit executor completion event
      yield* this.emitExecutorEvents(entryExecutorId, result);

      // Process outgoing edges from entry
      yield* this.processExecutor(entryExecutorId, result);

      // Emit workflow completed event
      yield {
        type: 'workflow_output',
        timestamp: new Date(),
        workflowId: this.executionContext.workflowId,
        data: result.output
      } as WorkflowOutputEvent;

    } catch (error) {
      // Emit workflow failed event
      yield {
        type: 'workflow_failed',
        timestamp: new Date(),
        workflowId: this.executionContext.workflowId,
        error: error instanceof Error ? error : new Error(String(error)),
        errorType: error instanceof Error ? error.constructor.name : 'Error',
        errorMessage: error instanceof Error ? error.message : String(error)
      } as WorkflowFailedEvent;
    }
  }

  /**
   * Process executor completion and follow outgoing edges
   */
  private async *processExecutor(
    executorId: string,
    result: ExecutorResult<any>
  ): AsyncIterable<WorkflowEvent> {
    // Get outgoing edges
    const edges = this.graph.getOutgoingEdges(executorId);

    for (const edge of edges) {
      yield* this.processEdge(edge, result.output);
    }
  }

  /**
   * Process an edge based on its type
   */
  private async *processEdge(
    edge: Edge,
    input: any
  ): AsyncIterable<WorkflowEvent> {
    switch (edge.type) {
      case 'direct':
        yield* this.processDirectEdge(edge, input);
        break;

      case 'conditional':
        yield* this.processConditionalEdge(edge, input);
        break;

      case 'fan_out':
        yield* this.processFanOutEdge(edge, input);
        break;

      case 'fan_in':
        yield* this.processFanInEdge(edge, input);
        break;

      case 'switch_case':
        yield* this.processSwitchCaseEdge(edge, input);
        break;
    }
  }

  /**
   * Process direct edge (simple sequential execution)
   */
  private async *processDirectEdge(
    edge: DirectEdge,
    input: any
  ): AsyncIterable<WorkflowEvent> {
    const executor = this.graph.getExecutor(edge.to);
    const result = await executor.execute(input, this.executionContext!);

    this.executionContext!.setExecutorOutput(edge.to, result.output);

    yield* this.emitExecutorEvents(edge.to, result);
    yield* this.processExecutor(edge.to, result);
  }

  /**
   * Process conditional edge (branch based on predicate)
   */
  private async *processConditionalEdge(
    edge: ConditionalEdge,
    input: any
  ): AsyncIterable<WorkflowEvent> {
    const condition = edge.condition(input);
    const conditionResult = condition instanceof Promise ? await condition : condition;

    const targetExecutorId = conditionResult ? edge.trueBranch : edge.falseBranch;

    if (targetExecutorId) {
      const executor = this.graph.getExecutor(targetExecutorId);
      const result = await executor.execute(input, this.executionContext!);

      this.executionContext!.setExecutorOutput(targetExecutorId, result.output);

      yield* this.emitExecutorEvents(targetExecutorId, result);
      yield* this.processExecutor(targetExecutorId, result);
    }
  }

  /**
   * Process fan-out edge (parallel execution)
   */
  private async *processFanOutEdge(
    edge: FanOutEdge,
    input: any
  ): AsyncIterable<WorkflowEvent> {
    // Execute all target executors in parallel
    const promises = edge.to.map(async (executorId) => {
      const executor = this.graph.getExecutor(executorId);
      const result = await executor.execute(input, this.executionContext!);
      this.executionContext!.setExecutorOutput(executorId, result.output);
      return { executorId, result };
    });

    const results = await Promise.all(promises);

    // Emit events for all completed executors
    for (const { executorId, result } of results) {
      yield* this.emitExecutorEvents(executorId, result);
      yield* this.processExecutor(executorId, result);
    }
  }

  /**
   * Process fan-in edge (merge results from multiple executors)
   */
  private async *processFanInEdge(
    edge: FanInEdge,
    input: any
  ): AsyncIterable<WorkflowEvent> {
    // Collect outputs from all source executors
    const outputs = edge.from.map(executorId =>
      this.executionContext!.getExecutorOutput(executorId)
    );

    // Merge outputs
    const mergedOutput = edge.merge(outputs);

    // Execute target executor with merged input
    const executor = this.graph.getExecutor(edge.to);
    const result = await executor.execute(mergedOutput, this.executionContext!);

    this.executionContext!.setExecutorOutput(edge.to, result.output);

    yield* this.emitExecutorEvents(edge.to, result);
    yield* this.processExecutor(edge.to, result);
  }

  /**
   * Process switch-case edge (multi-way branching)
   */
  private async *processSwitchCaseEdge(
    edge: SwitchCaseEdge,
    input: any
  ): AsyncIterable<WorkflowEvent> {
    const caseValue = edge.selector(input);
    const targetExecutorId = edge.cases.get(caseValue) ?? edge.default;

    if (targetExecutorId) {
      const executor = this.graph.getExecutor(targetExecutorId);
      const result = await executor.execute(input, this.executionContext!);

      this.executionContext!.setExecutorOutput(targetExecutorId, result.output);

      yield* this.emitExecutorEvents(targetExecutorId, result);
      yield* this.processExecutor(targetExecutorId, result);
    }
  }

  /**
   * Emit events for executor completion
   */
  private async *emitExecutorEvents(
    executorId: string,
    result: ExecutorResult<any>
  ): AsyncIterable<WorkflowEvent> {
    // Emit executor-specific events based on executor type
    const executor = this.graph.getExecutor(executorId);

    // If it's an agent executor, emit agent events
    if (executor instanceof AgentExecutor) {
      yield {
        type: 'agent_run',
        timestamp: new Date(),
        workflowId: this.executionContext!.workflowId,
        executorId,
        agentId: executor.agent.id,
        response: result.output
      } as AgentRunEvent;
    }
  }

  private createExecutionContext(options?: WorkflowRunOptions): ExecutionContext {
    return {
      workflowId: options?.workflowId ?? this.generateWorkflowId(),
      executionId: this.generateExecutionId(),
      thread: options?.thread,
      sharedState: new Map<string, any>(),
      executorOutputs: new Map<string, any>(),
      getExecutorOutput: (executorId: string) => this.executionContext?.executorOutputs.get(executorId),
      setExecutorOutput: (executorId: string, output: any) => {
        this.executionContext?.executorOutputs.set(executorId, output);
      }
    };
  }

  private generateWorkflowId(): string {
    return `workflow_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private generateExecutionId(): string {
    return `exec_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }
}

export interface WorkflowRunOptions {
  workflowId?: string;
  thread?: AgentThread;
  checkpoint?: string;
}

export interface WorkflowRunResult {
  output: any;
  events: WorkflowEvent[];
  executionId: string;
}
```

### Related Tasks
- **Blocked by**: TASK-301 (Graph structure must exist)
- **Blocks**: TASK-303 (Event system needs runner)
- **Blocks**: TASK-309 (Streaming needs runner implementation)
- **Related**: TASK-304 (Checkpointing needs execution state)

---

## Implementation Notes

### Key Architectural Decisions

**Execution Algorithm**:
Use iterative graph traversal with edge-specific routing:
```typescript
1. Start at entry executor
2. Execute executor with input
3. Store output in execution context
4. Get outgoing edges
5. For each edge:
   - Route based on edge type
   - Execute target executor(s)
   - Repeat from step 3
```

**Parallel Execution**:
Use `Promise.all()` for fan-out edges:
```typescript
const results = await Promise.all(
  targetExecutors.map(exec => exec.execute(input, context))
);
```

**Event Streaming**:
Use async generators to yield events as they occur:
```typescript
async function* runStream() {
  yield { type: 'started' };
  // ... execute ...
  yield { type: 'completed' };
}
```

### Common Pitfalls

- Always validate graph before execution
- Handle executor errors gracefully
- Don't mutate shared state without synchronization
- Remember to emit events for all executor completions
- Track executor outputs for fan-in merging
