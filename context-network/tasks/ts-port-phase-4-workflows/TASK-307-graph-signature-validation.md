# Task: TASK-307 Graph Signature Validation

**Phase**: 4
**Priority**: High
**Estimated Effort**: 5 hours
**Dependencies**: TASK-301 (Workflow Graph), TASK-304 (Checkpoint Storage)

### Objective
Implement graph signature generation and validation to ensure checkpoint compatibility when resuming workflows.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-8 (Workflows - Checkpointing)
- **Python Reference**: `/python/packages/core/agent_framework/workflows/signature.py` - Graph signature validation
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI.Workflows/GraphSignature.cs`
- **Standards**: CLAUDE.md § Python Architecture → Type Safety

### Files to Create/Modify
- `src/workflows/graph/signature.ts` - Graph signature generation and validation
- `src/workflows/graph/__tests__/signature.test.ts` - Unit tests
- `src/workflows/index.ts` - Export signature utilities

### Implementation Requirements

**Core Functionality**:
1. Implement `computeGraphSignature()` function to generate deterministic hash
2. Include executor signatures (ID, input type, output type)
3. Include edge connections and types
4. Include entry/exit point information
5. Implement deterministic serialization (sorted keys)
6. Use cryptographic hash (SHA-256) for signature
7. Implement `validateGraphCompatibility()` function
8. Compare checkpoint signature with current graph signature
9. Provide detailed error messages for incompatibility
10. Support signature versioning for future compatibility

**Signature Components**:
11. Executor definitions (ID, name, type, input/output signatures)
12. Edge definitions (type, from, to, conditions)
13. Entry executor ID
14. Graph metadata (version, schema)
15. Tool signatures if applicable

**Validation Logic**:
16. Exact match validation (strict mode)
17. Backward compatibility validation (lenient mode)
18. Provide incompatibility details (what changed)
19. Support whitelist of allowed changes

**TypeScript Patterns**:
- Use crypto for hashing (Node.js crypto module)
- Implement deterministic object serialization
- Export validation utilities
- Comprehensive JSDoc
- Strict null checking

**Code Standards**:
- 120 character line length
- JSDoc documentation for all public APIs with `@example` tags
- Strict TypeScript mode enabled
- No `any` types without explicit justification comment

### Test Requirements
- [ ] Test computeGraphSignature() generates deterministic hash
- [ ] Test same graph produces same signature
- [ ] Test different graphs produce different signatures
- [ ] Test signature includes all executor information
- [ ] Test signature includes all edge information
- [ ] Test signature includes entry executor
- [ ] Test deterministic serialization (key order doesn't matter)
- [ ] Test validateGraphCompatibility() with matching signatures
- [ ] Test validateGraphCompatibility() with different signatures
- [ ] Test incompatibility error messages
- [ ] Test signature versioning
- [ ] Test hash algorithm (SHA-256)
- [ ] Test signature for complex graphs (nested workflows)
- [ ] Test backward compatibility mode
- [ ] Test whitelist allowed changes

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] Graph signature generation implemented
- [ ] Deterministic hash for identical graphs
- [ ] Validation function for compatibility checking
- [ ] Detailed incompatibility error messages
- [ ] Signature versioning support
- [ ] Tests pass with >85% coverage
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings
- [ ] JSDoc complete for all public APIs with examples
- [ ] Exports added to index.ts files

### Example Code Pattern
```typescript
import { createHash } from 'crypto';
import { WorkflowGraph } from './graph';
import { WorkflowCheckpoint } from '../checkpoint';

/**
 * Graph signature for checkpoint compatibility validation
 */
export interface GraphSignature {
  version: string;
  hash: string;
  timestamp: Date;
  metadata?: Record<string, any>;
}

/**
 * Incompatibility details
 */
export interface GraphIncompatibility {
  type: 'executor_added' | 'executor_removed' | 'executor_modified' | 'edge_added' | 'edge_removed' | 'entry_changed';
  message: string;
  details?: any;
}

/**
 * Compute deterministic signature for a workflow graph
 *
 * @example
 * ```typescript
 * const graph = new WorkflowGraph();
 * // ... build graph ...
 * const signature = computeGraphSignature(graph);
 * console.log(signature.hash); // SHA-256 hash
 * ```
 */
export function computeGraphSignature(graph: WorkflowGraph): GraphSignature {
  // Build deterministic representation
  const representation = {
    version: '1.0',
    executors: getExecutorSignatures(graph),
    edges: getEdgeSignatures(graph),
    entry: graph.getEntryExecutorId()
  };

  // Serialize deterministically (sorted keys)
  const serialized = JSON.stringify(representation, sortKeys);

  // Compute hash
  const hash = createHash('sha256')
    .update(serialized)
    .digest('hex');

  return {
    version: '1.0',
    hash,
    timestamp: new Date()
  };
}

/**
 * Get executor signatures for deterministic hashing
 */
function getExecutorSignatures(graph: WorkflowGraph): any[] {
  const executors = Array.from(graph.getExecutors().entries())
    .map(([id, executor]) => ({
      id,
      type: executor.constructor.name,
      inputSignature: executor.getInputSignature(),
      outputSignature: executor.getOutputSignature()
    }))
    .sort((a, b) => a.id.localeCompare(b.id)); // Deterministic order

  return executors;
}

/**
 * Get edge signatures for deterministic hashing
 */
function getEdgeSignatures(graph: WorkflowGraph): any[] {
  const edges = graph.getEdges()
    .map(edge => {
      const base = { type: edge.type };

      switch (edge.type) {
        case 'direct':
          return { ...base, from: edge.from, to: edge.to };
        case 'conditional':
          return { ...base, from: edge.from, trueBranch: edge.trueBranch, falseBranch: edge.falseBranch };
        case 'fan_out':
          return { ...base, from: edge.from, to: edge.to.sort() };
        case 'fan_in':
          return { ...base, from: edge.from.sort(), to: edge.to };
        case 'switch_case':
          return { ...base, from: edge.from, cases: Array.from(edge.cases.entries()).sort(), default: edge.default };
      }
    })
    .sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b))); // Deterministic order

  return edges;
}

/**
 * Sort object keys for deterministic serialization
 */
function sortKeys(key: string, value: any): any {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return Object.keys(value)
      .sort()
      .reduce((sorted: any, key) => {
        sorted[key] = value[key];
        return sorted;
      }, {});
  }
  return value;
}

/**
 * Validate graph compatibility with checkpoint
 *
 * @example
 * ```typescript
 * const checkpoint = await storage.loadCheckpoint('checkpoint-123');
 * const currentGraph = buildWorkflowGraph();
 *
 * const result = validateGraphCompatibility(
 *   checkpoint.graphSignatureHash,
 *   computeGraphSignature(currentGraph).hash
 * );
 *
 * if (!result.compatible) {
 *   console.error('Incompatible:', result.incompatibilities);
 * }
 * ```
 */
export function validateGraphCompatibility(
  checkpointSignature: string,
  currentSignature: string,
  options?: { strict?: boolean }
): {
  compatible: boolean;
  incompatibilities?: GraphIncompatibility[];
} {
  const strict = options?.strict ?? true;

  if (checkpointSignature === currentSignature) {
    return { compatible: true };
  }

  if (strict) {
    return {
      compatible: false,
      incompatibilities: [
        {
          type: 'executor_modified',
          message: 'Graph signature mismatch. Checkpoint is incompatible with current graph.',
          details: {
            checkpointSignature,
            currentSignature
          }
        }
      ]
    };
  }

  // Lenient mode: could implement backward compatibility logic here
  return { compatible: false };
}

/**
 * Detailed graph compatibility check with specific incompatibilities
 */
export function validateDetailedGraphCompatibility(
  checkpoint: WorkflowCheckpoint,
  currentGraph: WorkflowGraph
): {
  compatible: boolean;
  incompatibilities: GraphIncompatibility[];
} {
  const incompatibilities: GraphIncompatibility[] = [];

  // Compare checkpoint signature with current graph
  const currentSignature = computeGraphSignature(currentGraph);

  if (checkpoint.graphSignatureHash === currentSignature.hash) {
    return { compatible: true, incompatibilities: [] };
  }

  // Detailed analysis would go here
  // For now, return generic incompatibility
  incompatibilities.push({
    type: 'executor_modified',
    message: 'Graph structure has changed since checkpoint was created',
    details: {
      checkpointHash: checkpoint.graphSignatureHash,
      currentHash: currentSignature.hash
    }
  });

  return {
    compatible: false,
    incompatibilities
  };
}

/**
 * Compare two graph signatures for compatibility
 */
export function compareGraphSignatures(
  signature1: GraphSignature,
  signature2: GraphSignature
): boolean {
  return signature1.hash === signature2.hash;
}
```

### Related Tasks
- **Blocked by**: TASK-301 (Graph structure needed)
- **Blocked by**: TASK-304 (Checkpoint storage interface)
- **Blocks**: TASK-310 (Workflow serialization needs validation)
- **Related**: TASK-306 (State machine validates compatibility)

---

## Implementation Notes

### Key Architectural Decisions

**Deterministic Serialization**:
Always serialize in the same order:
```typescript
// Sort executor IDs
executors.sort((a, b) => a.id.localeCompare(b.id))

// Sort object keys
JSON.stringify(obj, sortKeys)
```

**Cryptographic Hash**:
Use SHA-256 for collision resistance:
```typescript
const hash = createHash('sha256')
  .update(serialized)
  .digest('hex');
```

**Strict vs Lenient Mode**:
```typescript
// Strict: exact match required
if (strict && sig1 !== sig2) return false;

// Lenient: allow backward-compatible changes
if (!strict) {
  // Check if changes are backward compatible
}
```

### Common Pitfalls

- Object key order matters for hashing - always sort
- Include all relevant graph information in signature
- Don't include runtime-specific data (timestamps, IDs)
- Use deterministic serialization for arrays too
- Remember to version signatures for future changes
