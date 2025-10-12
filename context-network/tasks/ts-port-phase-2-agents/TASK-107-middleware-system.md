# Task: TASK-107 Agent Middleware System

**Phase**: 2
**Priority**: High
**Estimated Effort**: 6 hours
**Dependencies**: TASK-007 (BaseAgent), TASK-101 (ChatAgent)

### Objective
Implement middleware system for intercepting and modifying agent and function invocations, enabling cross-cutting concerns like logging, caching, rate limiting, and custom behavior injection.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-6 (Middleware)
- **Python Reference**: `/python/packages/core/agent_framework/_middleware.py:1-400` - Middleware definition and decorators
- **Python Reference**: `/python/packages/core/agent_framework/_agents.py:471-472` - @use_agent_middleware decorator
- **Standards**: CLAUDE.md § Python Architecture → Middleware Support

### Files to Create/Modify
- `src/middleware/middleware.ts` - Middleware interface and utilities
- `src/middleware/agent-middleware.ts` - Agent-specific middleware
- `src/middleware/function-middleware.ts` - Function-specific middleware
- `src/agents/base-agent.ts` - Middleware registration
- `src/agents/chat-agent.ts` - Apply middleware via decorators
- `src/middleware/__tests__/middleware.test.ts` - Unit tests

### Implementation Requirements

**Middleware Protocol**:
1. Define `Middleware` interface with `onAgentInvoking()`, `onAgentInvoked()` methods
2. Define `FunctionMiddleware` with `onFunctionInvoking()`, `onFunctionInvoked()` methods
3. Support async middleware methods
4. Support middleware chains (multiple middleware applied in order)
5. Support early termination (middleware can short-circuit execution)

**Middleware Context**:
6. Define `AgentContext` with agent, messages, options, result
7. Define `FunctionContext` with function, arguments, result
8. Allow middleware to modify context before/after execution
9. Support metadata passing between middleware

**BaseAgent Integration**:
10. Accept `middleware` in constructor (single or array)
11. Store middleware chain in agent
12. Apply middleware decorators to `run()` and `runStream()` methods
13. Call middleware in correct order (FIFO for invoking, LIFO for invoked)

**Decorator Pattern**:
14. Implement `useAgentMiddleware()` higher-order function
15. Wrap agent methods with middleware calls
16. Preserve method signatures and return types
17. Support both class decorators and function wrappers

**TypeScript Patterns**:
- Use higher-order functions for middleware
- Use method decorators for applying middleware
- Support async middleware chains

**Code Standards**:
- 120 character line length
- JSDoc with examples
- Strict mode

### Test Requirements
- [ ] Test single middleware applied correctly
- [ ] Test multiple middleware applied in correct order
- [ ] Test middleware can modify input before execution
- [ ] Test middleware can modify output after execution
- [ ] Test middleware can short-circuit execution
- [ ] Test middleware errors are handled gracefully
- [ ] Test function middleware applied to tool calls
- [ ] Test metadata passing between middleware
- [ ] Test middleware with streaming responses

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] Middleware interface defined
- [ ] Middleware chains work correctly
- [ ] Agent and function middleware both supported
- [ ] Decorators apply middleware correctly
- [ ] Tests pass with >85% coverage
- [ ] TypeScript strict mode, ESLint passes

### Example Code Pattern
```typescript
export interface AgentInvokingContext {
  agent: AgentProtocol;
  messages: ChatMessage[];
  options: AgentRunOptions;
  metadata: Record<string, unknown>;
}

export interface AgentInvokedContext extends AgentInvokingContext {
  result: AgentRunResponse;
}

export interface Middleware {
  onAgentInvoking?(context: AgentInvokingContext): Promise<void | 'skip'>;
  onAgentInvoked?(context: AgentInvokedContext): Promise<void>;
}

export function useAgentMiddleware<T extends AgentProtocol>(
  middleware: Middleware[]
) {
  return function (target: T): T {
    const originalRun = target.run.bind(target);

    target.run = async function (...args) {
      const context: AgentInvokingContext = {
        agent: target,
        messages: args[0],
        options: args[1] || {},
        metadata: {}
      };

      // Call middleware invoking in order
      for (const mw of middleware) {
        if (mw.onAgentInvoking) {
          const result = await mw.onAgentInvoking(context);
          if (result === 'skip') {
            return context.result!; // Short-circuit
          }
        }
      }

      // Execute original method
      const result = await originalRun(...args);

      const invokedContext: AgentInvokedContext = { ...context, result };

      // Call middleware invoked in reverse order
      for (const mw of [...middleware].reverse()) {
        if (mw.onAgentInvoked) {
          await mw.onAgentInvoked(invokedContext);
        }
      }

      return invokedContext.result;
    };

    return target;
  };
}

// Usage
class LoggingMiddleware implements Middleware {
  async onAgentInvoking(context: AgentInvokingContext): Promise<void> {
    console.log('Agent invoking:', context.agent.name);
  }

  async onAgentInvoked(context: AgentInvokedContext): Promise<void> {
    console.log('Agent invoked:', context.result.text);
  }
}

@useAgentMiddleware([new LoggingMiddleware()])
class ChatAgent extends BaseAgent {
  // ...
}
```

### Related Tasks
- **Blocked by**: TASK-007 (BaseAgent), TASK-101 (ChatAgent)
- **Related**: TASK-005 (Tool system for function middleware)
