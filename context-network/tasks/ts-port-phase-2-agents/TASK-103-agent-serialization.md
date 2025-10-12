# Task: TASK-103 Agent Serialization/Deserialization

**Phase**: 2
**Priority**: High
**Estimated Effort**: 4 hours
**Dependencies**: TASK-007 (BaseAgent), TASK-101 (ChatAgent)

### Objective
Implement serialization and deserialization support for agents, enabling agent instances to be converted to/from JSON with dependency injection for non-serializable components like chat clients.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-14 (Serialization)
- **Python Reference**: `/python/packages/core/agent_framework/_serialization.py:1-316` - SerializationMixin and SerializationProtocol
- **Python Reference**: `/python/packages/core/agent_framework/_agents.py:209-210` - BaseAgent extends SerializationMixin
- **Standards**: CLAUDE.md § Python Architecture → Code Quality Standards

### Files to Create/Modify
- `src/core/serialization.ts` - SerializationProtocol and SerializationMixin
- `src/core/__tests__/serialization.test.ts` - Unit tests for serialization
- `src/agents/base-agent.ts` - Implement serialization on BaseAgent
- `src/agents/chat-agent.ts` - Override serialization for ChatAgent
- `src/core/index.ts` - Add serialization exports
- `src/index.ts` - Re-export serialization utilities

### Implementation Requirements

**Core Serialization Protocol**:
1. Define `SerializationProtocol` interface with `toDict()` and `fromDict()` methods
2. Create `isSerializable()` utility to check if value is JSON-compatible
3. Implement `SerializationMixin` class with default serialization logic
4. Support `DEFAULT_EXCLUDE` class property for fields to exclude
5. Support `INJECTABLE` class property for dependencies to inject during deserialization
6. Support `exclude` parameter in `toDict()` for runtime exclusions
7. Support `excludeNone` parameter in `toDict()` to omit null/undefined values

**Serialization Logic**:
8. Include `type` field with class type identifier (snake_case of class name or custom)
9. Recursively serialize nested SerializationProtocol objects
10. Recursively serialize arrays containing SerializationProtocol objects
11. Recursively serialize objects/maps containing SerializationProtocol values
12. Skip non-JSON-serializable values with debug logging
13. Skip private fields (starting with `_`)
14. Combine `DEFAULT_EXCLUDE`, `INJECTABLE`, and runtime `exclude` sets

**Deserialization Logic**:
15. Accept `dependencies` map with format `"<type>.<parameter>"` or `"<type>.<dict-parameter>.<key>"`
16. Filter out `type` field from deserialization kwargs
17. Inject dependencies matching the class type identifier
18. Support simple dependencies: `"chat_agent.chat_client"` → `chatClient` parameter
19. Support dict dependencies: `"chat_agent.additional_options.timeout"` → `additionalOptions.timeout`
20. Log warning if dependency key doesn't match type or isn't in INJECTABLE

**JSON Convenience Methods**:
21. Implement `toJson()` method wrapping `toDict()` + JSON.stringify
22. Implement `fromJson()` class method wrapping JSON.parse + `fromDict()`
23. Pass through JSON.stringify options in `toJson()` (e.g., indent, replacer)

**TypeScript Patterns**:
- Use interface for SerializationProtocol (structural typing)
- Use abstract class for SerializationMixin (provides implementation)
- Use class decorators or mixins for composition
- Use static methods for `fromDict()` and `fromJson()`
- Type the return of `fromDict()` to match the calling class

**Code Standards**:
- 120 character line length
- JSDoc documentation for all public APIs with `@example` tags
- Strict TypeScript mode enabled
- No `any` types without justification (use `unknown` for inputs)

### Test Requirements
- [ ] Test `toDict()` includes all public properties
- [ ] Test `toDict()` excludes properties in `DEFAULT_EXCLUDE`
- [ ] Test `toDict()` excludes properties in `INJECTABLE`
- [ ] Test `toDict()` excludes properties in runtime `exclude` parameter
- [ ] Test `toDict()` excludes private fields (starting with `_`)
- [ ] Test `toDict()` includes `type` field with correct identifier
- [ ] Test `toDict()` with `excludeNone: true` omits null/undefined values
- [ ] Test `toDict()` with `excludeNone: false` includes null/undefined values
- [ ] Test `toDict()` recursively serializes nested SerializationProtocol objects
- [ ] Test `toDict()` recursively serializes arrays of SerializationProtocol objects
- [ ] Test `toDict()` recursively serializes maps with SerializationProtocol values
- [ ] Test `toDict()` skips non-JSON-serializable values
- [ ] Test `fromDict()` creates instance with correct properties
- [ ] Test `fromDict()` filters out `type` field from constructor kwargs
- [ ] Test `fromDict()` injects simple dependencies (e.g., `"chat_agent.chat_client"`)
- [ ] Test `fromDict()` injects dict dependencies (e.g., `"chat_agent.options.timeout"`)
- [ ] Test `fromDict()` ignores dependencies not matching type
- [ ] Test `fromDict()` logs warning for dependency not in INJECTABLE
- [ ] Test `toJson()` produces valid JSON string
- [ ] Test `fromJson()` reconstructs instance from JSON
- [ ] Test round-trip: `fromJson(instance.toJson())` equals original
- [ ] Test ChatAgent serialization excludes `chatClient` (injectable)
- [ ] Test ChatAgent deserialization with injected `chatClient`

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] SerializationProtocol interface defined
- [ ] SerializationMixin class implemented with `toDict()`, `toJson()`, `fromDict()`, `fromJson()`
- [ ] BaseAgent extends/implements serialization support
- [ ] ChatAgent properly excludes `chatClient` and other non-serializable fields
- [ ] Dependency injection works for simple and dict dependencies
- [ ] Type field correctly identifies class (snake_case or custom)
- [ ] Recursive serialization works for nested objects, arrays, and maps
- [ ] Tests pass with >85% coverage
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings
- [ ] JSDoc complete for all public APIs with examples
- [ ] Exports added to index.ts files
- [ ] Code reviewed against Python reference implementation

### Example Code Pattern
```typescript
/**
 * Protocol for objects that support serialization and deserialization.
 *
 * @example
 * ```typescript
 * class MyClass implements SerializationProtocol {
 *   constructor(public value: string) {}
 *
 *   toDict(): Record<string, unknown> {
 *     return { type: 'my_class', value: this.value };
 *   }
 *
 *   static fromDict(data: Record<string, unknown>): MyClass {
 *     return new MyClass(data.value as string);
 *   }
 * }
 * ```
 */
export interface SerializationProtocol {
  /**
   * Convert the instance to a dictionary.
   *
   * @param options - Serialization options
   * @returns Dictionary representation
   */
  toDict(options?: SerializationOptions): Record<string, unknown>;

  /**
   * Create an instance from a dictionary.
   *
   * @param data - Dictionary containing instance data
   * @param options - Deserialization options
   * @returns New instance
   */
  // fromDict is static, so it's not in the protocol interface
  // Classes implement it as a static method
}

export interface SerializationOptions {
  /**
   * Fields to exclude from serialization.
   */
  exclude?: Set<string>;

  /**
   * Whether to exclude null/undefined values.
   * @default true
   */
  excludeNone?: boolean;
}

export interface DeserializationOptions {
  /**
   * Dependencies to inject during deserialization.
   * Keys are in format "<type>.<parameter>" or "<type>.<dict-parameter>.<key>".
   */
  dependencies?: Record<string, unknown>;
}

/**
 * Check if a value is JSON serializable.
 */
export function isSerializable(value: unknown): boolean {
  return (
    value === null ||
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean' ||
    Array.isArray(value) ||
    (typeof value === 'object' && value.constructor === Object)
  );
}

/**
 * Mixin class providing default serialization/deserialization behavior.
 *
 * @example
 * ```typescript
 * class ChatAgent extends SerializationMixin {
 *   static readonly DEFAULT_EXCLUDE = new Set(['additionalProperties']);
 *   static readonly INJECTABLE = new Set(['chatClient']);
 *
 *   constructor(
 *     public chatClient: ChatClientProtocol,
 *     public name: string,
 *     public additionalProperties: Record<string, unknown> = {}
 *   ) {
 *     super();
 *   }
 * }
 *
 * const agent = new ChatAgent(client, 'my-agent');
 * const serialized = agent.toDict(); // excludes chatClient, additionalProperties
 * const json = agent.toJson();
 *
 * const restored = ChatAgent.fromDict(serialized, {
 *   dependencies: { 'chat_agent.chatClient': client }
 * });
 * ```
 */
export abstract class SerializationMixin implements SerializationProtocol {
  /**
   * Fields to always exclude from serialization.
   */
  static readonly DEFAULT_EXCLUDE: Set<string> = new Set();

  /**
   * Fields that are injectable dependencies (excluded from serialization,
   * but can be provided via dependencies parameter in fromDict).
   */
  static readonly INJECTABLE: Set<string> = new Set();

  toDict(options: SerializationOptions = {}): Record<string, unknown> {
    const { exclude = new Set(), excludeNone = true } = options;
    const constructor = this.constructor as typeof SerializationMixin;

    // Combine exclude sets
    const combined = new Set([
      ...constructor.DEFAULT_EXCLUDE,
      ...constructor.INJECTABLE,
      ...exclude,
    ]);

    // Start with type field (unless excluded)
    const result: Record<string, unknown> = combined.has('type')
      ? {}
      : { type: this.getTypeIdentifier() };

    // Serialize all public instance properties
    for (const [key, value] of Object.entries(this)) {
      // Skip if excluded or private
      if (combined.has(key) || key.startsWith('_')) {
        continue;
      }

      // Skip null/undefined if excludeNone
      if (excludeNone && (value === null || value === undefined)) {
        continue;
      }

      // Recursively serialize SerializationProtocol objects
      if (isSerializationProtocol(value)) {
        result[key] = value.toDict(options);
        continue;
      }

      // Handle arrays
      if (Array.isArray(value)) {
        result[key] = value.map((item) =>
          isSerializationProtocol(item) ? item.toDict(options) : item
        ).filter(item => isSerializable(item));
        continue;
      }

      // Handle plain objects/maps
      if (typeof value === 'object' && value !== null && value.constructor === Object) {
        const serializedObj: Record<string, unknown> = {};
        for (const [k, v] of Object.entries(value)) {
          if (isSerializationProtocol(v)) {
            serializedObj[k] = v.toDict(options);
          } else if (isSerializable(v)) {
            serializedObj[k] = v;
          }
        }
        result[key] = serializedObj;
        continue;
      }

      // Include if JSON serializable
      if (isSerializable(value)) {
        result[key] = value;
      }
    }

    return result;
  }

  toJson(options: SerializationOptions & JsonStringifyOptions = {}): string {
    const { indent, replacer, ...serializationOptions } = options;
    return JSON.stringify(
      this.toDict(serializationOptions),
      replacer,
      indent
    );
  }

  static fromDict<T extends SerializationMixin>(
    this: new (...args: any[]) => T,
    data: Record<string, unknown>,
    options: DeserializationOptions = {}
  ): T {
    const { dependencies = {} } = options;
    const typeId = this.getTypeIdentifier();

    // Filter out 'type' field
    const kwargs: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(data)) {
      if (key !== 'type') {
        kwargs[key] = value;
      }
    }

    // Process dependencies
    for (const [depKey, depValue] of Object.entries(dependencies)) {
      const parts = depKey.split('.');
      if (parts.length < 2) continue;

      const [depType, param, ...rest] = parts;

      // Skip if not for this type
      if (depType !== typeId) continue;

      if (rest.length === 0) {
        // Simple dependency: <type>.<parameter>
        kwargs[param] = depValue;
      } else {
        // Dict dependency: <type>.<dict-parameter>.<key>
        const key = rest[0];
        if (!(param in kwargs)) {
          kwargs[param] = {};
        }
        (kwargs[param] as Record<string, unknown>)[key] = depValue;
      }
    }

    return new this(kwargs);
  }

  static fromJson<T extends SerializationMixin>(
    this: new (...args: any[]) => T,
    json: string,
    options: DeserializationOptions = {}
  ): T {
    return this.fromDict(JSON.parse(json), options);
  }

  protected getTypeIdentifier(): string {
    const constructor = this.constructor as typeof SerializationMixin & { type?: string };

    // Use explicit type if defined
    if (constructor.type) {
      return constructor.type;
    }

    // Convert class name to snake_case
    return constructor.name
      .replace(/([A-Z])/g, '_$1')
      .toLowerCase()
      .replace(/^_/, '');
  }

  private static getTypeIdentifier(): string {
    if ((this as any).type) {
      return (this as any).type;
    }
    return this.name
      .replace(/([A-Z])/g, '_$1')
      .toLowerCase()
      .replace(/^_/, '');
  }
}

function isSerializationProtocol(value: unknown): value is SerializationProtocol {
  return (
    value !== null &&
    typeof value === 'object' &&
    typeof (value as any).toDict === 'function'
  );
}
```

### Related Tasks
- **Blocked by**: TASK-007 (BaseAgent must exist)
- **Blocked by**: TASK-101 (ChatAgent for testing serialization)
- **Blocks**: None (utility feature)
- **Related**: TASK-008 (AgentThread serialization)

---

## Implementation Notes

### Key Architectural Decisions

**Dependency Injection Pattern**:
Non-serializable components (like `chatClient`) are excluded and re-injected:
```typescript
// Serialize (excludes chatClient)
const data = agent.toDict();

// Deserialize (inject chatClient)
const restored = ChatAgent.fromDict(data, {
  dependencies: {
    'chat_agent.chatClient': client
  }
});
```

**Type Identifier Strategy**:
- Use explicit `type` class property if defined
- Otherwise convert class name to snake_case
- Examples: `ChatAgent` → `chat_agent`, `MyCustomAgent` → `my_custom_agent`

**Recursive Serialization**:
Automatically handles nested structures:
```typescript
class Parent extends SerializationMixin {
  child: Child; // Child also extends SerializationMixin
}

// Both parent and child are serialized
const data = parent.toDict();
```

### Python/TypeScript Differences

1. **Mixins**: Python uses multiple inheritance, TypeScript may use interfaces + abstract classes
2. **ClassVar**: Python has ClassVar, TypeScript uses static properties
3. **Type Checking**: TypeScript has compile-time types, Python uses runtime protocols
4. **Method Resolution**: Python MRO, TypeScript prototype chain

### Common Pitfalls

- Don't forget to exclude non-JSON-serializable fields (functions, class instances, etc.)
- Always filter out `type` field during deserialization
- Dependency keys must match exact type identifier (snake_case)
- Private fields (`_` prefix) should be excluded automatically
- Constructor must accept kwargs matching serialized property names

### Testing Strategy

Test matrix:
- ✅ Serialization: All public properties included
- ✅ Serialization: DEFAULT_EXCLUDE fields excluded
- ✅ Serialization: INJECTABLE fields excluded
- ✅ Serialization: Private fields excluded
- ✅ Serialization: Nested objects serialized recursively
- ✅ Deserialization: Simple dependencies injected
- ✅ Deserialization: Dict dependencies injected
- ✅ Round-trip: `fromDict(toDict())` preserves data
- ✅ ChatAgent: chatClient excluded and injected correctly
