# Task: TASK-310 Workflow Serialization

**Phase**: 4
**Priority**: High
**Estimated Effort**: 5 hours
**Dependencies**: TASK-301 (Workflow Graph), TASK-304 (Checkpoint Storage), TASK-306 (State Machine)

### Objective
Implement workflow and execution state serialization/deserialization for persistence, checkpointing, and cross-process communication.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-8 (Workflows - Checkpointing)
- **Python Reference**: `/python/packages/core/agent_framework/workflows/serialization.py` - Workflow serialization
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI.Workflows/Serialization/` - Workflow state serialization
- **Standards**: CLAUDE.md § Python Architecture → Serialization Patterns

### Files to Create/Modify
- `src/workflows/serialization/serializer.ts` - Serialization utilities
- `src/workflows/serialization/deserializer.ts` - Deserialization utilities
- `src/workflows/serialization/__tests__/serialization.test.ts` - Unit tests
- `src/workflows/index.ts` - Export serialization types

### Implementation Requirements

**Core Functionality**:
1. Implement `serializeWorkflow()` - serialize workflow graph to JSON
2. Implement `deserializeWorkflow()` - deserialize JSON to workflow graph
3. Implement `serializeExecutionState()` - serialize execution state
4. Implement `deserializeExecutionState()` - deserialize execution state
5. Handle executor serialization (agent references, function closures)
6. Handle edge serialization (including condition functions)
7. Serialize thread state and agent thread references
8. Serialize shared state and executor outputs
9. Support custom serializers for complex types
10. Validate deserialized data before creating objects

**Serialization Format**:
11. JSON-based format for portability
12. Include version information for compatibility
13. Include graph signature hash for validation
14. Executor definitions with type information
15. Edge definitions with serialized conditions
16. Execution state (outputs, pending requests, shared state)

**TypeScript Patterns**:
- Use type-safe serialization helpers
- Implement custom serializers for complex types
- Support dependency injection for agents
- Export all types with comprehensive JSDoc
- Strict null checking

**Code Standards**:
- 120 character line length
- JSDoc documentation for all public APIs with `@example` tags
- Strict TypeScript mode enabled
- No `any` types without explicit justification comment

### Test Requirements
- [ ] Test serializeWorkflow() produces valid JSON
- [ ] Test deserializeWorkflow() reconstructs graph correctly
- [ ] Test serialization includes version information
- [ ] Test serialization includes graph signature
- [ ] Test executor serialization preserves configuration
- [ ] Test edge serialization handles all edge types
- [ ] Test condition function serialization (or replacement)
- [ ] Test serializeExecutionState() captures all state
- [ ] Test deserializeExecutionState() restores state correctly
- [ ] Test thread state serialization/deserialization
- [ ] Test shared state serialization
- [ ] Test executor output serialization
- [ ] Test pending request serialization
- [ ] Test custom serializer integration
- [ ] Test validation on deserialization

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] Workflow serialization to JSON implemented
- [ ] Workflow deserialization from JSON implemented
- [ ] Execution state serialization implemented
- [ ] All workflow components serializable
- [ ] Custom serializer support for complex types
- [ ] Validation on deserialization
- [ ] Tests pass with >85% coverage
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings
- [ ] JSDoc complete for all public APIs with examples
- [ ] Exports added to index.ts files

### Example Code Pattern
```typescript
import { WorkflowGraph, Executor, Edge } from '../graph';
import { ExecutionContext } from '../execution/context';
import { WorkflowCheckpoint } from '../checkpoint';

/**
 * Serialized workflow format
 */
export interface SerializedWorkflow {
  version: string;
  graphSignatureHash: string;
  executors: SerializedExecutor[];
  edges: SerializedEdge[];
  entryExecutorId: string;
  metadata?: Record<string, any>;
}

/**
 * Serialized executor format
 */
export interface SerializedExecutor {
  id: string;
  type: string; // 'agent' | 'function' | 'workflow' | 'request_info'
  name?: string;
  config?: Record<string, any>;
  // Agent-specific
  agentId?: string;
  // Function-specific
  functionName?: string;
}

/**
 * Serialized edge format
 */
export interface SerializedEdge {
  type: 'direct' | 'conditional' | 'fan_out' | 'fan_in' | 'switch_case';
  from: string | string[];
  to?: string | string[];
  // Conditional-specific
  trueBranch?: string;
  falseBranch?: string;
  conditionName?: string; // Reference to named condition
  // Switch-case-specific
  cases?: Array<[string | number, string]>;
  default?: string;
  selectorName?: string; // Reference to named selector
}

/**
 * Serialized execution state
 */
export interface SerializedExecutionState {
  workflowId: string;
  executionId: string;
  timestamp: Date;
  graphSignatureHash: string;
  executorOutputs: Record<string, any>;
  sharedState: Record<string, any>;
  pendingRequests: Array<{
    requestId: string;
    executorId: string;
    data: any;
    timestamp: Date;
  }>;
  threadState?: any;
}

/**
 * Serialize workflow graph to JSON
 *
 * @example
 * ```typescript
 * const workflow = new WorkflowBuilder()
 *   .addAgent(agent, 'research')
 *   .addEdge('research', 'summary')
 *   .build();
 *
 * const serialized = serializeWorkflow(workflow.graph);
 * const json = JSON.stringify(serialized, null, 2);
 * ```
 */
export function serializeWorkflow(
  graph: WorkflowGraph,
  options?: {
    agentRegistry?: Map<string, AgentProtocol>;
  }
): SerializedWorkflow {
  return {
    version: '1.0',
    graphSignatureHash: graph.getSignatureHash(),
    executors: serializeExecutors(graph.getExecutors(), options),
    edges: serializeEdges(graph.getEdges()),
    entryExecutorId: graph.getEntryExecutorId()
  };
}

/**
 * Deserialize workflow graph from JSON
 *
 * @example
 * ```typescript
 * const json = fs.readFileSync('workflow.json', 'utf-8');
 * const serialized = JSON.parse(json);
 *
 * const graph = deserializeWorkflow(serialized, {
 *   agentRegistry: new Map([
 *     ['agent-123', myAgent]
 *   ])
 * });
 * ```
 */
export function deserializeWorkflow(
  serialized: SerializedWorkflow,
  options: {
    agentRegistry: Map<string, AgentProtocol>;
    functionRegistry?: Map<string, Function>;
    conditionRegistry?: Map<string, (output: any) => boolean>;
  }
): WorkflowGraph {
  // Validate version
  if (serialized.version !== '1.0') {
    throw new Error(`Unsupported workflow version: ${serialized.version}`);
  }

  const graph = new WorkflowGraph();

  // Deserialize executors
  for (const execData of serialized.executors) {
    const executor = deserializeExecutor(execData, options);
    graph.addExecutor(execData.id, executor);
  }

  // Deserialize edges
  for (const edgeData of serialized.edges) {
    const edge = deserializeEdge(edgeData, options);
    graph.addEdge(edge);
  }

  // Set entry
  graph.setEntry(serialized.entryExecutorId);

  // Validate graph signature
  const currentSignature = graph.getSignatureHash();
  if (currentSignature !== serialized.graphSignatureHash) {
    console.warn('Graph signature mismatch after deserialization');
  }

  return graph;
}

/**
 * Serialize executors
 */
function serializeExecutors(
  executors: Map<string, Executor<any, any>>,
  options?: { agentRegistry?: Map<string, AgentProtocol> }
): SerializedExecutor[] {
  return Array.from(executors.entries()).map(([id, executor]) => {
    if (executor instanceof AgentExecutor) {
      return {
        id,
        type: 'agent',
        name: executor.name,
        agentId: executor.agent.id
      };
    } else if (executor instanceof FunctionExecutor) {
      return {
        id,
        type: 'function',
        name: executor.name,
        functionName: executor.func.name
      };
    } else if (executor instanceof RequestInfoExecutor) {
      return {
        id,
        type: 'request_info',
        name: executor.name,
        config: {
          timeoutMs: executor.timeoutMs
        }
      };
    }

    throw new Error(`Cannot serialize executor type: ${executor.constructor.name}`);
  });
}

/**
 * Deserialize executor from serialized data
 */
function deserializeExecutor(
  data: SerializedExecutor,
  options: {
    agentRegistry: Map<string, AgentProtocol>;
    functionRegistry?: Map<string, Function>;
  }
): Executor<any, any> {
  switch (data.type) {
    case 'agent': {
      if (!data.agentId) {
        throw new Error('Agent executor missing agentId');
      }

      const agent = options.agentRegistry.get(data.agentId);
      if (!agent) {
        throw new Error(`Agent not found in registry: ${data.agentId}`);
      }

      return new AgentExecutor(agent, { id: data.id, name: data.name });
    }

    case 'function': {
      if (!data.functionName) {
        throw new Error('Function executor missing functionName');
      }

      const func = options.functionRegistry?.get(data.functionName);
      if (!func) {
        throw new Error(`Function not found in registry: ${data.functionName}`);
      }

      return new FunctionExecutor(data.id, func, { name: data.name });
    }

    case 'request_info': {
      return new RequestInfoExecutor({
        id: data.id,
        name: data.name,
        timeoutMs: data.config?.timeoutMs
      });
    }

    default:
      throw new Error(`Unknown executor type: ${data.type}`);
  }
}

/**
 * Serialize edges
 */
function serializeEdges(edges: Edge[]): SerializedEdge[] {
  return edges.map(edge => {
    switch (edge.type) {
      case 'direct':
        return {
          type: 'direct',
          from: edge.from,
          to: edge.to
        };

      case 'conditional':
        return {
          type: 'conditional',
          from: edge.from,
          trueBranch: edge.trueBranch,
          falseBranch: edge.falseBranch,
          conditionName: 'condition' // Function name/reference
        };

      case 'fan_out':
        return {
          type: 'fan_out',
          from: edge.from,
          to: edge.to
        };

      case 'fan_in':
        return {
          type: 'fan_in',
          from: edge.from,
          to: edge.to
        };

      case 'switch_case':
        return {
          type: 'switch_case',
          from: edge.from,
          cases: Array.from(edge.cases.entries()),
          default: edge.default,
          selectorName: 'selector' // Function name/reference
        };
    }
  });
}

/**
 * Deserialize edge from serialized data
 */
function deserializeEdge(
  data: SerializedEdge,
  options: {
    conditionRegistry?: Map<string, (output: any) => boolean>;
  }
): Edge {
  switch (data.type) {
    case 'direct':
      return {
        type: 'direct',
        from: data.from as string,
        to: data.to as string
      };

    case 'conditional': {
      const condition = options.conditionRegistry?.get(data.conditionName ?? '');
      if (!condition) {
        throw new Error(`Condition not found: ${data.conditionName}`);
      }

      return {
        type: 'conditional',
        from: data.from as string,
        condition,
        trueBranch: data.trueBranch!,
        falseBranch: data.falseBranch
      };
    }

    case 'fan_out':
      return {
        type: 'fan_out',
        from: data.from as string,
        to: data.to as string[]
      };

    case 'fan_in':
      return {
        type: 'fan_in',
        from: data.from as string[],
        to: data.to as string,
        merge: (outputs) => outputs // Default merge
      };

    case 'switch_case':
      return {
        type: 'switch_case',
        from: data.from as string,
        cases: new Map(data.cases),
        default: data.default,
        selector: (output) => output // Default selector
      };

    default:
      throw new Error(`Unknown edge type: ${(data as any).type}`);
  }
}

/**
 * Serialize execution state for checkpointing
 */
export function serializeExecutionState(
  context: ExecutionContext
): SerializedExecutionState {
  return {
    workflowId: context.workflowId,
    executionId: context.executionId,
    timestamp: new Date(),
    graphSignatureHash: '', // Would come from graph
    executorOutputs: Object.fromEntries(context.executorOutputs),
    sharedState: Object.fromEntries(context.sharedState),
    pendingRequests: [],
    threadState: context.thread?.serialize()
  };
}

/**
 * Deserialize execution state from checkpoint
 */
export function deserializeExecutionState(
  serialized: SerializedExecutionState
): Partial<ExecutionContext> {
  return {
    workflowId: serialized.workflowId,
    executionId: serialized.executionId,
    executorOutputs: new Map(Object.entries(serialized.executorOutputs)),
    sharedState: new Map(Object.entries(serialized.sharedState))
    // Note: Thread would be deserialized separately
  };
}
```

### Related Tasks
- **Blocked by**: TASK-301 (Graph structure)
- **Blocked by**: TASK-304 (Checkpoint storage)
- **Blocked by**: TASK-306 (State machine)
- **Related**: TASK-307 (Graph signature validation)

---

## Implementation Notes

### Key Architectural Decisions

**Registry Pattern**:
Use registries for agent/function lookup:
```typescript
const graph = deserializeWorkflow(json, {
  agentRegistry: new Map([
    ['agent-123', myAgent]
  ]),
  functionRegistry: new Map([
    ['myFunc', myFunction]
  ])
});
```

**Function Serialization**:
Functions cannot be serialized, use named references:
```typescript
// Serialize: store function name
{ conditionName: 'isPositive' }

// Deserialize: lookup in registry
const condition = conditionRegistry.get('isPositive');
```

**Version Management**:
Include version for future compatibility:
```typescript
{
  version: '1.0',
  // ... workflow data
}
```

### Common Pitfalls

- Cannot serialize functions directly - use registries
- Always validate version on deserialization
- Don't forget graph signature validation
- Handle missing registry entries gracefully
- Remember to serialize Date objects correctly
