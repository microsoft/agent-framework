# Task: TASK-005 AITool & Function Decorator System

**Phase**: 1
**Priority**: Critical
**Estimated Effort**: 6 hours
**Dependencies**: TASK-001, TASK-002

## Objective
Implement AITool interface, function decorator system for tool registration, and Zod schema integration for runtime validation.

## Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-7 (Tools and Function Calling)
- **Python Reference**: `/python/packages/core/agent_framework/_tools.py:1-300`
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI.Abstractions/AIFunction.cs`
- **Standards**: CLAUDE.md § Code Quality Standards

## Files to Create/Modify
- `src/core/tools/base-tool.ts` - AITool interface and BaseTool class
- `src/core/tools/decorators.ts` - Function decorator (@aiFunction)
- `src/core/tools/schema.ts` - Zod schema utilities
- `src/core/tools/__tests__/base-tool.test.ts` - Base tool tests
- `src/core/tools/__tests__/decorators.test.ts` - Decorator tests
- `src/core/tools/index.ts` - Re-exports
- `src/core/index.ts` - Add tools exports

## Implementation Requirements

### Core Functionality

1. **Define AITool interface**:
   ```typescript
   export interface AITool {
     name: string;
     description: string;
     schema: z.ZodSchema;                // Zod schema for parameters
     execute(params: unknown): Promise<unknown>;
     metadata?: Record<string, unknown>;
   }
   ```

2. **Create BaseTool abstract class**:
   ```typescript
   export abstract class BaseTool implements AITool {
     public readonly name: string;
     public readonly description: string;
     public readonly schema: z.ZodSchema;
     public readonly metadata?: Record<string, unknown>;

     constructor(config: {
       name: string;
       description: string;
       schema: z.ZodSchema;
       metadata?: Record<string, unknown>;
     });

     abstract execute(params: unknown): Promise<unknown>;

     // Validate params against schema
     protected validate(params: unknown): unknown;
   }
   ```

3. **Create @aiFunction decorator**:
   ```typescript
   export function aiFunction(config: {
     name?: string;
     description: string;
     schema: z.ZodSchema;
   }): MethodDecorator;
   ```

4. **Create FunctionTool class** (wraps functions as tools):
   ```typescript
   export class FunctionTool extends BaseTool {
     private fn: (params: unknown) => Promise<unknown>;

     constructor(config: {
       name: string;
       description: string;
       schema: z.ZodSchema;
       fn: (params: unknown) => Promise<unknown>;
     });

     async execute(params: unknown): Promise<unknown>;
   }
   ```

5. **Create schema utility functions**:
   ```typescript
   // Convert Zod schema to JSON Schema for LLM
   export function zodToJsonSchema(schema: z.ZodSchema): Record<string, unknown>;

   // Create tool schema from function signature
   export function createToolSchema<T>(schema: z.ZodSchema<T>): AIToolSchema;

   export interface AIToolSchema {
     type: 'function';
     function: {
       name: string;
       description: string;
       parameters: Record<string, unknown>; // JSON Schema
     };
   }
   ```

6. **Create helper function for tool registration**:
   ```typescript
   export function createTool<T>(
     name: string,
     description: string,
     schema: z.ZodSchema<T>,
     fn: (params: T) => Promise<unknown>
   ): AITool;
   ```

### TypeScript Patterns
- Use Zod for runtime validation and type inference
- Use decorators (experimental) for method annotation
- Use generics for type-safe tool creation
- Export interfaces and base classes for extension
- Use abstract class for BaseTool to enforce implementation

### Code Standards
- JSDoc for all public APIs
- Include `@example` showing tool creation and usage
- Validate all input parameters
- Throw descriptive errors on validation failure
- Support both class-based and function-based tools

## Test Requirements

### AITool Interface Tests
- [ ] Test interface can be implemented by custom tool
- [ ] Test tool with all required fields
- [ ] Test tool with optional metadata field

### BaseTool Tests
- [ ] Test BaseTool cannot be instantiated directly (abstract)
- [ ] Test BaseTool subclass with execute implementation
- [ ] Test validate() method validates against schema
- [ ] Test validate() throws ZodError for invalid params
- [ ] Test validate() returns parsed/coerced params

### FunctionTool Tests
- [ ] Test FunctionTool creation with function
- [ ] Test FunctionTool execute calls wrapped function
- [ ] Test FunctionTool validates params before execution
- [ ] Test FunctionTool with async function
- [ ] Test FunctionTool with sync function (auto-wrapped)

### Decorator Tests
- [ ] Test @aiFunction decorator attaches metadata to method
- [ ] Test @aiFunction with explicit name
- [ ] Test @aiFunction infers name from method name
- [ ] Test decorated method can be called normally
- [ ] Test metadata can be retrieved from decorated method

### Schema Utility Tests
- [ ] Test zodToJsonSchema converts simple types (string, number, boolean)
- [ ] Test zodToJsonSchema converts object schemas
- [ ] Test zodToJsonSchema converts array schemas
- [ ] Test zodToJsonSchema handles optional fields
- [ ] Test zodToJsonSchema handles default values
- [ ] Test createToolSchema produces correct AIToolSchema structure

### Helper Function Tests
- [ ] Test createTool creates valid AITool
- [ ] Test createTool function executes correctly
- [ ] Test createTool validates params
- [ ] Test createTool with type inference from Zod schema

### Integration Tests
- [ ] Test tool creation and execution end-to-end
- [ ] Test tool with complex nested schema
- [ ] Test tool error handling (validation errors, execution errors)

**Minimum Coverage**: 85%

## Acceptance Criteria
- [ ] AITool interface defined
- [ ] BaseTool abstract class with validation
- [ ] FunctionTool for wrapping functions
- [ ] @aiFunction decorator functional
- [ ] Zod schema integration working
- [ ] zodToJsonSchema converts Zod to JSON Schema
- [ ] createTool helper function
- [ ] All validation errors are descriptive
- [ ] JSDoc complete with examples
- [ ] Tests achieve >85% coverage
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings
- [ ] Type inference works (params typed from Zod schema)

## Example Code Pattern

```typescript
import { z } from 'zod';
import { BaseTool, createTool, aiFunction } from '@microsoft/agent-framework-ts';

/**
 * Base tool class for creating custom tools.
 *
 * @example
 * ```typescript
 * class CalculatorTool extends BaseTool {
 *   constructor() {
 *     super({
 *       name: 'calculator',
 *       description: 'Perform basic math operations',
 *       schema: z.object({
 *         operation: z.enum(['add', 'subtract', 'multiply', 'divide']),
 *         a: z.number(),
 *         b: z.number(),
 *       }),
 *     });
 *   }
 *
 *   async execute(params: unknown): Promise<number> {
 *     const { operation, a, b } = this.validate(params);
 *     switch (operation) {
 *       case 'add': return a + b;
 *       case 'subtract': return a - b;
 *       case 'multiply': return a * b;
 *       case 'divide': return a / b;
 *     }
 *   }
 * }
 * ```
 */
export abstract class BaseTool implements AITool {
  public readonly name: string;
  public readonly description: string;
  public readonly schema: z.ZodSchema;
  public readonly metadata?: Record<string, unknown>;

  constructor(config: {
    name: string;
    description: string;
    schema: z.ZodSchema;
    metadata?: Record<string, unknown>;
  }) {
    this.name = config.name;
    this.description = config.description;
    this.schema = config.schema;
    this.metadata = config.metadata;
  }

  abstract execute(params: unknown): Promise<unknown>;

  protected validate(params: unknown): unknown {
    return this.schema.parse(params);
  }
}

/**
 * Create a tool from a function.
 *
 * @example
 * ```typescript
 * const weatherTool = createTool(
 *   'get_weather',
 *   'Get current weather for a location',
 *   z.object({
 *     location: z.string(),
 *     units: z.enum(['celsius', 'fahrenheit']).default('celsius'),
 *   }),
 *   async ({ location, units }) => {
 *     // Fetch weather data
 *     return { location, temp: 72, units };
 *   }
 * );
 * ```
 */
export function createTool<T>(
  name: string,
  description: string,
  schema: z.ZodSchema<T>,
  fn: (params: T) => Promise<unknown>
): AITool {
  return new FunctionTool({
    name,
    description,
    schema,
    fn: async (params: unknown) => {
      const validated = schema.parse(params) as T;
      return fn(validated);
    },
  });
}

/**
 * Decorator for marking methods as AI functions.
 *
 * @example
 * ```typescript
 * class MyAgent {
 *   @aiFunction({
 *     description: 'Search the web',
 *     schema: z.object({ query: z.string() }),
 *   })
 *   async search(params: { query: string }) {
 *     return { results: [] };
 *   }
 * }
 * ```
 */
export function aiFunction(config: {
  name?: string;
  description: string;
  schema: z.ZodSchema;
}): MethodDecorator {
  return (target: any, propertyKey: string | symbol, descriptor: PropertyDescriptor) => {
    const originalMethod = descriptor.value;

    // Attach metadata
    Reflect.defineMetadata('ai:function', {
      name: config.name || String(propertyKey),
      description: config.description,
      schema: config.schema,
    }, target, propertyKey);

    return descriptor;
  };
}
```

## Related Tasks
- **Blocks**: TASK-007 (BaseAgent needs tools), TASK-011 (OpenAI client tool calling)
- **Blocked by**: TASK-001 (Scaffolding), TASK-002 (ChatMessage for function calls)
- **Related**: TASK-004 (ChatCompletionOptions references AITool)

## Notes

### Zod Dependency
Add to package.json:
```json
{
  "dependencies": {
    "zod": "^3.22.0"
  }
}
```

### Decorator Support
Add to tsconfig.json:
```json
{
  "compilerOptions": {
    "experimentalDecorators": true,
    "emitDecoratorMetadata": true
  }
}
```

### Reflection Support
For decorator metadata, add:
```bash
npm install reflect-metadata
```
