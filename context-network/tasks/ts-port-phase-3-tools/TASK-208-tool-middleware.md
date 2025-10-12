# Task: TASK-208 Tool Middleware

**Phase**: 3
**Priority**: Medium
**Estimated Effort**: 4 hours
**Dependencies**: TASK-107 (Agent Middleware System), TASK-201 (Tool Execution Engine)

### Objective
Implement middleware system specifically for tool/function invocations, enabling interception, modification, and monitoring of tool calls before and after execution.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-6 (Middleware) → Function Middleware
- **Python Reference**: `/python/packages/core/agent_framework/_middleware.py` - FunctionMiddleware
- **Python Reference**: `/python/packages/core/agent_framework/_tools.py:1010-1039` - Middleware execution in tool calls
- **Standards**: CLAUDE.md § Python Architecture → Middleware

### Files to Create/Modify
- `src/middleware/function-middleware.ts` - FunctionMiddleware interface and pipeline
- `src/middleware/__tests__/function-middleware.test.ts` - Unit tests

### Implementation Requirements

**FunctionMiddleware Interface**:
1. Define `FunctionMiddleware` interface
2. Methods: `onFunctionInvoking()`, `onFunctionInvoked()`
3. Context includes: function, arguments, kwargs, metadata
4. Support async methods
5. Support early termination (skip execution)

**Middleware Pipeline**:
6. Create `FunctionMiddlewarePipeline` class
7. Accept array of middleware in constructor
8. Implement `execute()` method to run pipeline
9. Call middleware invoking in FIFO order
10. Call middleware invoked in LIFO order
11. Pass context through middleware chain

**Integration with Tool Execution**:
12. Extract middleware from chat client or kwargs
13. Pass middleware pipeline to `autoInvokeFunction()`
14. Apply middleware before function execution
15. Apply middleware after function execution
16. Handle middleware errors gracefully

**Common Middleware Implementations**:
17. Logging middleware (log function calls)
18. Timing middleware (measure execution time)
19. Caching middleware (cache results by arguments)
20. Rate limiting middleware (throttle calls)

**TypeScript Patterns**:
- Use interface for middleware contract
- Use pipeline pattern for execution
- Type context strictly

**Code Standards**:
- 120 character line length
- JSDoc with examples
- Strict mode

### Test Requirements
- [ ] Test FunctionMiddleware interface conformance
- [ ] Test middleware pipeline with single middleware
- [ ] Test middleware pipeline with multiple middleware
- [ ] Test invoking called in FIFO order
- [ ] Test invoked called in LIFO order
- [ ] Test middleware can modify context
- [ ] Test middleware can skip execution
- [ ] Test middleware error handling
- [ ] Test logging middleware implementation
- [ ] Test caching middleware implementation

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] FunctionMiddleware interface defined
- [ ] Middleware pipeline executes correctly
- [ ] Integration with tool execution works
- [ ] At least 2 example middleware implementations
- [ ] Tests pass with >85% coverage
- [ ] TypeScript strict mode, ESLint passes
- [ ] JSDoc complete with examples

### Example Code Pattern
```typescript
export interface FunctionInvokingContext {
  function: AIFunction<any, any>;
  arguments: any;
  kwargs: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface FunctionInvokedContext extends FunctionInvokingContext {
  result: any;
  error?: Error;
}

export interface FunctionMiddleware {
  onFunctionInvoking?(context: FunctionInvokingContext): Promise<void | 'skip'>;
  onFunctionInvoked?(context: FunctionInvokedContext): Promise<void>;
}

export class FunctionMiddlewarePipeline {
  constructor(private readonly middleware: FunctionMiddleware[]) {}

  async execute(
    func: AIFunction<any, any>,
    args: any,
    kwargs: Record<string, unknown>,
    finalHandler: (context: FunctionInvokingContext) => Promise<any>
  ): Promise<any> {
    const context: FunctionInvokingContext = {
      function: func,
      arguments: args,
      kwargs,
      metadata: {}
    };

    // Invoking phase (FIFO)
    for (const mw of this.middleware) {
      if (mw.onFunctionInvoking) {
        const result = await mw.onFunctionInvoking(context);
        if (result === 'skip') {
          // Short-circuit execution
          return (context as any).result;
        }
      }
    }

    // Execute function
    let result: any;
    let error: Error | undefined;

    try {
      result = await finalHandler(context);
    } catch (err) {
      error = err as Error;
    }

    const invokedContext: FunctionInvokedContext = {
      ...context,
      result,
      error
    };

    // Invoked phase (LIFO)
    for (const mw of [...this.middleware].reverse()) {
      if (mw.onFunctionInvoked) {
        await mw.onFunctionInvoked(invokedContext);
      }
    }

    if (error) {
      throw error;
    }

    return invokedContext.result;
  }
}

// Example: Logging Middleware
export class LoggingFunctionMiddleware implements FunctionMiddleware {
  async onFunctionInvoking(context: FunctionInvokingContext): Promise<void> {
    console.log(`Calling function: ${context.function.name}`);
    console.log(`Arguments:`, context.arguments);
  }

  async onFunctionInvoked(context: FunctionInvokedContext): Promise<void> {
    if (context.error) {
      console.error(`Function ${context.function.name} failed:`, context.error);
    } else {
      console.log(`Function ${context.function.name} succeeded`);
      console.log(`Result:`, context.result);
    }
  }
}

// Example: Caching Middleware
export class CachingFunctionMiddleware implements FunctionMiddleware {
  private cache = new Map<string, any>();

  async onFunctionInvoking(context: FunctionInvokingContext): Promise<void | 'skip'> {
    const cacheKey = this.getCacheKey(context.function.name, context.arguments);

    if (this.cache.has(cacheKey)) {
      context.metadata.cached = true;
      (context as any).result = this.cache.get(cacheKey);
      return 'skip';  // Skip execution
    }
  }

  async onFunctionInvoked(context: FunctionInvokedContext): Promise<void> {
    if (!context.metadata.cached && !context.error) {
      const cacheKey = this.getCacheKey(context.function.name, context.arguments);
      this.cache.set(cacheKey, context.result);
    }
  }

  private getCacheKey(name: string, args: any): string {
    return `${name}:${JSON.stringify(args)}`;
  }
}

// Usage
const loggingMiddleware = new LoggingFunctionMiddleware();
const cachingMiddleware = new CachingFunctionMiddleware();

const agent = new ChatAgent({
  chatClient: client,
  middleware: [loggingMiddleware, cachingMiddleware],
  tools: [myTool]
});

// Or apply middleware to specific chat client
const clientWithMiddleware = new OpenAIChatClient({
  ...options,
  functionMiddleware: [loggingMiddleware, cachingMiddleware]
});
```

### Related Tasks
- **Blocked by**: TASK-107 (Agent Middleware), TASK-201 (Tool Execution)
- **Related**: TASK-207 (Tool Approval - can be implemented as middleware)
