# Task: TASK-301 Workflow Graph Data Structure

**Phase**: 4
**Priority**: Critical
**Estimated Effort**: 6 hours
**Dependencies**: TASK-002 (ChatMessage), TASK-007 (BaseAgent), TASK-101 (ChatAgent)

### Objective
Implement the core workflow graph data structures including nodes (executors), edges (connections), and graph representation for multi-agent orchestration.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-8 (Workflows)
- **Python Reference**: `/python/packages/core/agent_framework/workflows/` - Workflow graph implementation
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI.Workflows/Graph/` - Workflow graph structure
- **Standards**: CLAUDE.md § Python Architecture → Async-First Design

### Files to Create/Modify
- `src/workflows/graph/executor.ts` - Base Executor interface and implementations
- `src/workflows/graph/edge.ts` - Edge types and interfaces
- `src/workflows/graph/graph.ts` - WorkflowGraph class
- `src/workflows/graph/__tests__/graph.test.ts` - Unit tests
- `src/workflows/index.ts` - Export workflow types
- `src/index.ts` - Re-export workflows from workflows module

### Implementation Requirements

**Core Functionality**:
1. Create `Executor<TInput, TOutput>` base interface for workflow nodes
2. Implement `AgentExecutor` that wraps an AgentProtocol instance
3. Implement `FunctionExecutor` that wraps a function
4. Implement `WorkflowExecutor` for nested workflows
5. Create `Edge` interface with source, target, and optional condition
6. Implement edge types: direct, conditional, fan-out, fan-in, switch-case
7. Create `WorkflowGraph` class to represent the graph structure
8. Implement graph validation (connectivity, cycles, entry/exit nodes)
9. Support graph signature hashing for checkpoint compatibility
10. Implement graph serialization/deserialization

**Executor Types**:
11. `AgentExecutor`: Execute an agent with input messages
12. `FunctionExecutor`: Execute a function with input data
13. `WorkflowExecutor`: Execute a nested workflow
14. `RequestInfoExecutor`: Human-in-the-loop (Phase 4 TASK-308)
15. All executors return `Promise<ExecutorResult<TOutput>>`

**Edge Types**:
16. Direct edge: Simple connection from one executor to another
17. Conditional edge: Route based on predicate function
18. Fan-out edge: Split execution to multiple parallel executors
19. Fan-in edge: Merge results from multiple executors
20. Switch-case edge: Multi-way branching based on output value

**TypeScript Patterns**:
- Use generic types for type-safe executor inputs/outputs
- Implement discriminated unions for edge types
- Use structural typing for executor protocol
- Provide fluent API for graph construction
- Export all types with comprehensive JSDoc
- Use strict null checking

**Code Standards**:
- 120 character line length
- JSDoc documentation for all public APIs with `@example` tags
- Strict TypeScript mode enabled
- No `any` types without explicit justification comment

### Test Requirements
- [ ] Test Executor interface implementation
- [ ] Test AgentExecutor with mock agent
- [ ] Test FunctionExecutor with sync and async functions
- [ ] Test WorkflowExecutor with nested workflow
- [ ] Test direct edge creation and validation
- [ ] Test conditional edge with predicate
- [ ] Test fan-out edge splitting to multiple executors
- [ ] Test fan-in edge merging results
- [ ] Test switch-case edge routing
- [ ] Test WorkflowGraph creation and validation
- [ ] Test graph connectivity validation (detect disconnected nodes)
- [ ] Test graph cycle detection
- [ ] Test graph signature hashing for same/different graphs
- [ ] Test graph serialization and deserialization
- [ ] Test error handling for invalid graph configurations

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] Executor interface and implementations created
- [ ] All edge types implemented with proper validation
- [ ] WorkflowGraph class with validation and serialization
- [ ] Graph signature hashing for checkpoint compatibility
- [ ] Type-safe generic executor interfaces
- [ ] Comprehensive validation for graph structure
- [ ] Tests pass with >85% coverage
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings
- [ ] JSDoc complete for all public APIs with examples
- [ ] Exports added to index.ts files

### Example Code Pattern
```typescript
/**
 * Base interface for workflow executors
 */
export interface Executor<TInput = any, TOutput = any> {
  readonly id: string;
  readonly name?: string;

  /**
   * Execute the node with given input
   */
  execute(input: TInput, context: ExecutionContext): Promise<ExecutorResult<TOutput>>;

  /**
   * Get input signature for type compatibility checking
   */
  getInputSignature(): string;

  /**
   * Get output signature for type compatibility checking
   */
  getOutputSignature(): string;
}

/**
 * Result from executor execution
 */
export interface ExecutorResult<TOutput> {
  output: TOutput;
  metadata?: Record<string, any>;
  error?: Error;
}

/**
 * Executor that wraps an agent
 */
export class AgentExecutor<TInput = string, TOutput = AgentRunResponse> implements Executor<TInput, TOutput> {
  public readonly id: string;
  public readonly name?: string;
  private readonly agent: AgentProtocol;

  constructor(agent: AgentProtocol, options?: { id?: string; name?: string }) {
    this.id = options?.id ?? `agent_${agent.id}`;
    this.name = options?.name ?? agent.name;
    this.agent = agent;
  }

  async execute(
    input: TInput,
    context: ExecutionContext
  ): Promise<ExecutorResult<TOutput>> {
    try {
      // Convert input to messages
      const messages = this.convertInputToMessages(input);

      // Execute agent
      const response = await this.agent.run(messages, {
        thread: context.thread
      });

      return {
        output: response as TOutput,
        metadata: {
          agentId: this.agent.id,
          tokensUsed: response.usageDetails?.totalTokens
        }
      };
    } catch (error) {
      return {
        output: undefined as any,
        error: error instanceof Error ? error : new Error(String(error))
      };
    }
  }

  getInputSignature(): string {
    return 'string | ChatMessage | ChatMessage[]';
  }

  getOutputSignature(): string {
    return 'AgentRunResponse';
  }

  private convertInputToMessages(input: TInput): string | ChatMessage | ChatMessage[] {
    // Implementation
    if (typeof input === 'string') return input;
    if (Array.isArray(input)) return input as ChatMessage[];
    return String(input);
  }
}

/**
 * Executor that wraps a function
 */
export class FunctionExecutor<TInput, TOutput> implements Executor<TInput, TOutput> {
  public readonly id: string;
  public readonly name?: string;
  private readonly func: (input: TInput, context: ExecutionContext) => Promise<TOutput> | TOutput;

  constructor(
    id: string,
    func: (input: TInput, context: ExecutionContext) => Promise<TOutput> | TOutput,
    options?: { name?: string }
  ) {
    this.id = id;
    this.name = options?.name ?? id;
    this.func = func;
  }

  async execute(
    input: TInput,
    context: ExecutionContext
  ): Promise<ExecutorResult<TOutput>> {
    try {
      const result = this.func(input, context);
      const output = result instanceof Promise ? await result : result;

      return {
        output,
        metadata: {
          functionName: this.name
        }
      };
    } catch (error) {
      return {
        output: undefined as any,
        error: error instanceof Error ? error : new Error(String(error))
      };
    }
  }

  getInputSignature(): string {
    return 'any'; // Could be enhanced with reflection
  }

  getOutputSignature(): string {
    return 'any'; // Could be enhanced with reflection
  }
}

/**
 * Edge connecting executors in the workflow graph
 */
export type Edge =
  | DirectEdge
  | ConditionalEdge
  | FanOutEdge
  | FanInEdge
  | SwitchCaseEdge;

export interface DirectEdge {
  type: 'direct';
  from: string;
  to: string;
}

export interface ConditionalEdge {
  type: 'conditional';
  from: string;
  condition: (output: any) => boolean | Promise<boolean>;
  trueBranch: string;
  falseBranch?: string;
}

export interface FanOutEdge {
  type: 'fan_out';
  from: string;
  to: string[];
}

export interface FanInEdge {
  type: 'fan_in';
  from: string[];
  to: string;
  merge: (outputs: any[]) => any;
}

export interface SwitchCaseEdge {
  type: 'switch_case';
  from: string;
  cases: Map<string | number, string>;
  default?: string;
  selector: (output: any) => string | number;
}

/**
 * Workflow graph structure
 */
export class WorkflowGraph {
  private executors: Map<string, Executor<any, any>>;
  private edges: Edge[];
  private entryExecutorId?: string;

  constructor(options?: {
    executors?: Map<string, Executor<any, any>>;
    edges?: Edge[];
    entryExecutorId?: string;
  }) {
    this.executors = options?.executors ?? new Map();
    this.edges = options?.edges ?? [];
    this.entryExecutorId = options?.entryExecutorId;
  }

  addExecutor(id: string, executor: Executor<any, any>): void {
    this.executors.set(id, executor);
  }

  addEdge(edge: Edge): void {
    this.edges.push(edge);
  }

  setEntry(executorId: string): void {
    if (!this.executors.has(executorId)) {
      throw new Error(`Entry executor '${executorId}' not found`);
    }
    this.entryExecutorId = executorId;
  }

  /**
   * Validate graph structure
   */
  validate(): void {
    if (!this.entryExecutorId) {
      throw new WorkflowValidationError('Entry executor must be set');
    }

    // Check entry exists
    if (!this.executors.has(this.entryExecutorId)) {
      throw new WorkflowValidationError(`Entry executor '${this.entryExecutorId}' not found`);
    }

    // Check all edge references exist
    for (const edge of this.edges) {
      this.validateEdgeReferences(edge);
    }

    // Check for cycles
    if (this.hasCycles()) {
      throw new GraphConnectivityError('Graph contains cycles');
    }

    // Check connectivity
    if (!this.isConnected()) {
      throw new GraphConnectivityError('Graph has disconnected nodes');
    }
  }

  /**
   * Compute graph signature hash for checkpoint compatibility
   */
  getSignatureHash(): string {
    const signature = {
      executors: Array.from(this.executors.entries()).map(([id, executor]) => ({
        id,
        inputSig: executor.getInputSignature(),
        outputSig: executor.getOutputSignature()
      })),
      edges: this.edges,
      entry: this.entryExecutorId
    };

    return this.hashObject(signature);
  }

  private validateEdgeReferences(edge: Edge): void {
    // Implementation
  }

  private hasCycles(): boolean {
    // Implement cycle detection (DFS)
    return false;
  }

  private isConnected(): boolean {
    // Implement connectivity check
    return true;
  }

  private hashObject(obj: any): string {
    // Simple hash implementation (use crypto in production)
    return JSON.stringify(obj);
  }
}

/**
 * Execution context passed to executors
 */
export interface ExecutionContext {
  workflowId: string;
  executionId: string;
  thread?: AgentThread;
  sharedState: Map<string, any>;
  getExecutorOutput(executorId: string): any;
}
```

### Related Tasks
- **Blocked by**: TASK-007 (BaseAgent must exist)
- **Blocked by**: TASK-101 (ChatAgent needed for AgentExecutor)
- **Blocks**: TASK-302 (Workflow executor needs graph structure)
- **Blocks**: TASK-306 (State machine needs graph structure)
- **Blocks**: TASK-307 (Signature validation needs graph signature)

---

## Implementation Notes

### Key Architectural Decisions

**Generic Type Safety**:
Use generic types to maintain type safety across the workflow:
```typescript
interface Executor<TInput, TOutput> {
  execute(input: TInput): Promise<ExecutorResult<TOutput>>;
}

const stringToNumber: Executor<string, number> = ...;
const numberToBoolean: Executor<number, boolean> = ...;
```

**Edge Type Discrimination**:
Use discriminated unions for different edge types:
```typescript
type Edge =
  | { type: 'direct'; from: string; to: string }
  | { type: 'conditional'; from: string; condition: Predicate; ... };

function processEdge(edge: Edge) {
  switch (edge.type) {
    case 'direct': // TypeScript knows all direct fields
    case 'conditional': // TypeScript knows all conditional fields
  }
}
```

**Graph Signature**:
Hash graph structure for checkpoint compatibility validation:
```typescript
// Same graph → same hash
const hash1 = graph.getSignatureHash();
// Modified graph → different hash
graph.addExecutor('new', executor);
const hash2 = graph.getSignatureHash();
// hash1 !== hash2
```

### Python/TypeScript Differences

1. **Generics**: TypeScript generics are structural, not nominal like Python typing
2. **Edge Types**: Use discriminated unions instead of Python class hierarchy
3. **Hash Function**: TypeScript needs explicit hashing (use crypto or simple JSON hash)
4. **Validation**: TypeScript can validate at compile time with proper generics

### Common Pitfalls

- Don't use `any` for executor inputs/outputs (use generics)
- Always validate edge references point to existing executors
- Remember to check for cycles in graph validation
- Graph signature must be deterministic (sort keys in JSON)
- Handle both sync and async functions in FunctionExecutor
