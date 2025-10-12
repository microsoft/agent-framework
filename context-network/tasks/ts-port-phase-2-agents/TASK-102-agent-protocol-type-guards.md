# Task: TASK-102 AgentProtocol Type Guards

**Phase**: 2
**Priority**: High
**Estimated Effort**: 3 hours
**Dependencies**: TASK-007 (BaseAgent), TASK-101 (ChatAgent)

### Objective
Implement type guard functions and utilities for runtime validation of AgentProtocol conformance, enabling structural subtyping checks and safe type narrowing in TypeScript.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-2 (Chat Agents) → Protocol Pattern
- **Python Reference**: `/python/packages/core/agent_framework/_agents.py:57-203` - AgentProtocol definition with @runtime_checkable
- **TypeScript Pattern**: Structural typing with type guards
- **Standards**: CLAUDE.md § Python Architecture → Protocols use structural subtyping

### Files to Create/Modify
- `src/agents/protocol.ts` - AgentProtocol interface and type guards
- `src/agents/__tests__/protocol.test.ts` - Unit tests for type guards
- `src/agents/index.ts` - Add exports for protocol utilities
- `src/index.ts` - Re-export protocol utilities

### Implementation Requirements

**Core Functionality**:
1. Define `AgentProtocol` interface with all required properties and methods
2. Create `isAgentProtocol(value: unknown): value is AgentProtocol` type guard
3. Create `assertAgentProtocol(value: unknown): asserts value is AgentProtocol` assertion
4. Validate all required properties: `id`, `name`, `displayName`, `description`
5. Validate all required methods: `run()`, `runStream()`, `getNewThread()`
6. Support partial protocol checks: `hasRunMethod()`, `hasStreamMethod()`, etc.
7. Provide detailed error messages when validation fails

**AgentProtocol Interface**:
8. Define `id` property as `string` (required)
9. Define `name` property as `string | null` (required, can be null)
10. Define `displayName` property as `string` (computed, required)
11. Define `description` property as `string | null` (required, can be null)
12. Define `run()` method signature matching agent execution pattern
13. Define `runStream()` method signature returning AsyncIterable
14. Define `getNewThread()` method signature returning AgentThread

**TypeScript Patterns**:
- Use type predicates (`value is Type`) for type guards
- Use assertion signatures (`asserts value is Type`) for throwing guards
- Use structural typing (interface, not class)
- Provide both narrow checks (single property) and broad checks (full protocol)
- Export const namespace for utility functions

**Code Standards**:
- 120 character line length
- JSDoc documentation for all public APIs with `@example` tags
- Strict TypeScript mode enabled
- No `any` types (use `unknown` for inputs)

### Test Requirements
- [ ] Test `isAgentProtocol()` returns true for conforming objects
- [ ] Test `isAgentProtocol()` returns false for null/undefined
- [ ] Test `isAgentProtocol()` returns false for objects missing `id`
- [ ] Test `isAgentProtocol()` returns false for objects missing `run()` method
- [ ] Test `isAgentProtocol()` returns false for objects missing `runStream()` method
- [ ] Test `isAgentProtocol()` returns false for objects missing `getNewThread()` method
- [ ] Test `isAgentProtocol()` validates method signatures (not just presence)
- [ ] Test `assertAgentProtocol()` throws for non-conforming objects
- [ ] Test `assertAgentProtocol()` includes helpful error messages
- [ ] Test partial protocol checks work independently
- [ ] Test ChatAgent instances pass `isAgentProtocol()` check
- [ ] Test BaseAgent instances fail `isAgentProtocol()` check (missing run methods)
- [ ] Test custom agent implementations pass `isAgentProtocol()` check
- [ ] Test type narrowing works after `isAgentProtocol()` check
- [ ] Test edge case: object with all properties but wrong types

**Minimum Coverage**: 90%

### Acceptance Criteria
- [ ] `AgentProtocol` interface defined with all required members
- [ ] `isAgentProtocol()` type guard correctly validates protocol conformance
- [ ] `assertAgentProtocol()` throws with descriptive errors for non-conforming objects
- [ ] Partial protocol checks (e.g., `hasRunMethod()`) work independently
- [ ] TypeScript correctly narrows types after guard checks
- [ ] Tests pass with >90% coverage
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings
- [ ] JSDoc complete for all public APIs with examples
- [ ] Exports added to index.ts files
- [ ] Code reviewed against Python reference implementation

### Example Code Pattern
```typescript
/**
 * Protocol interface for agent implementations.
 *
 * This interface defines the contract that all agents must implement.
 * Uses structural subtyping - classes don't need to explicitly implement this interface.
 *
 * @example
 * ```typescript
 * import { AgentProtocol, isAgentProtocol } from 'agent-framework';
 *
 * // Custom agent that structurally conforms to AgentProtocol
 * class MyCustomAgent {
 *   id = 'custom-001';
 *   name = 'Custom Agent';
 *   get displayName() { return this.name || this.id; }
 *   description = 'A custom agent';
 *
 *   async run(messages, options) {
 *     return { messages: [], responseId: 'response-001' };
 *   }
 *
 *   async *runStream(messages, options) {
 *     yield { text: 'chunk' };
 *   }
 *
 *   getNewThread(options) {
 *     return new AgentThread();
 *   }
 * }
 *
 * const agent = new MyCustomAgent();
 * if (isAgentProtocol(agent)) {
 *   // TypeScript knows agent conforms to AgentProtocol
 *   const response = await agent.run('Hello');
 * }
 * ```
 */
export interface AgentProtocol {
  /**
   * The unique identifier of the agent.
   */
  readonly id: string;

  /**
   * The name of the agent (can be null).
   */
  readonly name: string | null;

  /**
   * The display name of the agent.
   * Should return name if available, otherwise id.
   */
  readonly displayName: string;

  /**
   * The description of the agent (can be null).
   */
  readonly description: string | null;

  /**
   * Execute the agent with the given messages.
   *
   * @param messages - The message(s) to send to the agent
   * @param options - Optional execution options including thread
   * @returns A promise resolving to the agent's response
   */
  run(
    messages?: string | ChatMessage | (string | ChatMessage)[],
    options?: AgentRunOptions
  ): Promise<AgentRunResponse>;

  /**
   * Execute the agent with streaming responses.
   *
   * @param messages - The message(s) to send to the agent
   * @param options - Optional execution options including thread
   * @returns An async iterable of response updates
   */
  runStream(
    messages?: string | ChatMessage | (string | ChatMessage)[],
    options?: AgentRunOptions
  ): AsyncIterable<AgentRunResponseUpdate>;

  /**
   * Create a new conversation thread for the agent.
   *
   * @param options - Optional thread creation options
   * @returns A new agent thread instance
   */
  getNewThread(options?: unknown): AgentThread;
}

/**
 * Type guard to check if a value conforms to AgentProtocol.
 *
 * This performs runtime validation of the protocol contract using structural typing.
 *
 * @param value - The value to check
 * @returns True if value conforms to AgentProtocol
 *
 * @example
 * ```typescript
 * function processAgent(agent: unknown) {
 *   if (isAgentProtocol(agent)) {
 *     // TypeScript knows agent has run(), runStream(), etc.
 *     const response = await agent.run('Hello');
 *   }
 * }
 * ```
 */
export function isAgentProtocol(value: unknown): value is AgentProtocol {
  if (value === null || value === undefined) {
    return false;
  }

  if (typeof value !== 'object') {
    return false;
  }

  const obj = value as Record<string, unknown>;

  // Check required properties
  if (typeof obj.id !== 'string') {
    return false;
  }

  if (obj.name !== null && typeof obj.name !== 'string') {
    return false;
  }

  if (typeof obj.displayName !== 'string') {
    return false;
  }

  if (obj.description !== null && typeof obj.description !== 'string') {
    return false;
  }

  // Check required methods
  if (typeof obj.run !== 'function') {
    return false;
  }

  if (typeof obj.runStream !== 'function') {
    return false;
  }

  if (typeof obj.getNewThread !== 'function') {
    return false;
  }

  return true;
}

/**
 * Assert that a value conforms to AgentProtocol, throwing if it doesn't.
 *
 * @param value - The value to check
 * @param name - Optional name for error messages
 * @throws {TypeError} If value doesn't conform to AgentProtocol
 *
 * @example
 * ```typescript
 * function requireAgent(value: unknown): AgentProtocol {
 *   assertAgentProtocol(value, 'agent parameter');
 *   return value; // TypeScript knows this is AgentProtocol
 * }
 * ```
 */
export function assertAgentProtocol(
  value: unknown,
  name = 'value'
): asserts value is AgentProtocol {
  if (!isAgentProtocol(value)) {
    const reasons: string[] = [];

    if (value === null || value === undefined) {
      throw new TypeError(`${name} is ${value}, expected AgentProtocol`);
    }

    if (typeof value !== 'object') {
      throw new TypeError(`${name} is ${typeof value}, expected object`);
    }

    const obj = value as Record<string, unknown>;

    if (typeof obj.id !== 'string') {
      reasons.push('missing or invalid property "id" (expected string)');
    }

    if (obj.name !== null && typeof obj.name !== 'string') {
      reasons.push('invalid property "name" (expected string | null)');
    }

    if (typeof obj.displayName !== 'string') {
      reasons.push('missing or invalid property "displayName" (expected string)');
    }

    if (obj.description !== null && typeof obj.description !== 'string') {
      reasons.push('invalid property "description" (expected string | null)');
    }

    if (typeof obj.run !== 'function') {
      reasons.push('missing method "run"');
    }

    if (typeof obj.runStream !== 'function') {
      reasons.push('missing method "runStream"');
    }

    if (typeof obj.getNewThread !== 'function') {
      reasons.push('missing method "getNewThread"');
    }

    throw new TypeError(
      `${name} does not conform to AgentProtocol:\n  - ${reasons.join('\n  - ')}`
    );
  }
}

/**
 * Partial protocol checks for granular validation.
 */
export namespace AgentProtocolGuards {
  /**
   * Check if value has a valid run() method.
   */
  export function hasRunMethod(value: unknown): value is { run: AgentProtocol['run'] } {
    return (
      value !== null &&
      typeof value === 'object' &&
      typeof (value as Record<string, unknown>).run === 'function'
    );
  }

  /**
   * Check if value has a valid runStream() method.
   */
  export function hasStreamMethod(
    value: unknown
  ): value is { runStream: AgentProtocol['runStream'] } {
    return (
      value !== null &&
      typeof value === 'object' &&
      typeof (value as Record<string, unknown>).runStream === 'function'
    );
  }

  /**
   * Check if value has agent identity properties.
   */
  export function hasAgentIdentity(
    value: unknown
  ): value is Pick<AgentProtocol, 'id' | 'name' | 'displayName' | 'description'> {
    if (value === null || typeof value !== 'object') {
      return false;
    }

    const obj = value as Record<string, unknown>;
    return (
      typeof obj.id === 'string' &&
      (obj.name === null || typeof obj.name === 'string') &&
      typeof obj.displayName === 'string' &&
      (obj.description === null || typeof obj.description === 'string')
    );
  }
}
```

### Related Tasks
- **Blocked by**: TASK-007 (BaseAgent class must exist)
- **Blocked by**: TASK-101 (ChatAgent for testing protocol conformance)
- **Blocks**: None (utility task)
- **Related**: TASK-002 (ChatMessage types for method signatures)
- **Related**: TASK-008 (AgentThread for method signatures)

---

## Implementation Notes

### Key Architectural Decisions

**Structural Typing over Nominal**:
TypeScript uses structural typing, so AgentProtocol works without explicit `implements`:
```typescript
// This class conforms to AgentProtocol without declaring it
class MyAgent {
  id = 'agent-001';
  name = 'My Agent';
  // ... all required members
}

// Type guard confirms conformance at runtime
if (isAgentProtocol(myAgent)) {
  // Works!
}
```

**Runtime Validation Strategy**:
- Check property presence first
- Check property types second
- Provide detailed error messages listing all violations
- Use assertion functions for throwing variants

**Partial Checks Pattern**:
Allow checking specific capabilities:
```typescript
if (AgentProtocolGuards.hasRunMethod(value)) {
  // Can call run() but may not be full protocol
  await value.run('test');
}
```

### Python/TypeScript Differences

1. **@runtime_checkable**: Python uses decorator, TypeScript uses type guards manually
2. **Protocol**: Python has Protocol class from typing module, TypeScript has interface
3. **isinstance()**: Python runtime check, TypeScript uses custom type guard functions
4. **Duck Typing**: Both support structural typing, but TypeScript is more explicit

### Common Pitfalls

- Don't use `instanceof` for protocol checking (works only for classes)
- Don't forget to check method presence AND type (some properties might be non-function)
- TypeScript doesn't validate method signatures at runtime (only presence)
- Remember `displayName` is often a getter, check as property not method
- Null checks must allow `null` for `name` and `description` (not just undefined)

### Testing Strategy

Test matrix:
- ✅ Valid: ChatAgent instance
- ✅ Valid: Custom object with all properties/methods
- ❌ Invalid: Missing `id`
- ❌ Invalid: Missing `run()` method
- ❌ Invalid: `run` is not a function (e.g., string)
- ❌ Invalid: `name` is number (not string | null)
- ❌ Invalid: Null/undefined input
- ❌ Invalid: Primitive value (string, number)
