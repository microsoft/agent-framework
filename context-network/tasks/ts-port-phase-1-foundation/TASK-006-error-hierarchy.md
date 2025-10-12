# Task: TASK-006 Error Hierarchy

**Phase**: 1
**Priority**: High
**Estimated Effort**: 3 hours
**Dependencies**: TASK-001

## Objective
Implement AgentFrameworkError base class and 7 specific error types with cause chaining and proper stack traces.

## Context References
- **Spec Section**: 002-typescript-feature-parity.md § Error Handling & Exception Hierarchy
- **Python Reference**: `/python/packages/core/agent_framework/_exceptions.py:1-150`
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI/Exceptions/`
- **Standards**: CLAUDE.md § Code Quality Standards

## Files to Create/Modify
- `src/core/errors/base-error.ts` - Base error class
- `src/core/errors/agent-errors.ts` - Agent-specific errors
- `src/core/errors/tool-errors.ts` - Tool-specific errors
- `src/core/errors/workflow-errors.ts` - Workflow-specific errors
- `src/core/errors/__tests__/errors.test.ts` - Error tests
- `src/core/errors/index.ts` - Re-exports
- `src/core/index.ts` - Add error exports

## Implementation Requirements

### Core Functionality

1. **Define AgentFrameworkError base class**:
   ```typescript
   export class AgentFrameworkError extends Error {
     public readonly cause?: Error;
     public readonly code?: string;

     constructor(message: string, cause?: Error, code?: string) {
       super(message);
       this.name = this.constructor.name;
       this.cause = cause;
       this.code = code;
       Error.captureStackTrace?.(this, this.constructor);
     }
   }
   ```

2. **Define 7 specific error classes**:
   - `AgentExecutionError` - Errors during agent execution
   - `AgentInitializationError` - Errors during agent setup
   - `ToolExecutionError` - Errors during tool execution
   - `ChatClientError` - Errors from chat client
   - `WorkflowValidationError` - Workflow validation failures
   - `GraphConnectivityError extends WorkflowValidationError` - Graph connectivity issues
   - `TypeCompatibilityError extends WorkflowValidationError` - Type mismatch errors

3. **All errors should**:
   - Extend AgentFrameworkError
   - Support cause chaining (Error wrapping)
   - Support optional error codes
   - Capture proper stack traces
   - Include descriptive messages

### TypeScript Patterns
- Use proper Error inheritance
- Capture stack traces with Error.captureStackTrace
- Support cause chaining for debugging
- Export all error types

### Code Standards
- JSDoc for each error class explaining when to use
- Include `@example` showing error creation and catching
- Descriptive error messages
- Error codes as constants where useful

## Test Requirements

- [ ] Test AgentFrameworkError creation
- [ ] Test AgentFrameworkError with cause
- [ ] Test AgentFrameworkError with code
- [ ] Test stack trace is captured
- [ ] Test error name matches class name
- [ ] Test each specific error type creation
- [ ] Test error inheritance (instanceof checks)
- [ ] Test cause chaining (wrapped errors)
- [ ] Test error serialization (toJSON)

**Minimum Coverage**: 85%

## Acceptance Criteria
- [ ] AgentFrameworkError base class with cause and code
- [ ] 7 specific error types defined
- [ ] All errors extend AgentFrameworkError
- [ ] Stack traces captured correctly
- [ ] Cause chaining works
- [ ] JSDoc complete with examples
- [ ] Tests achieve >85% coverage
- [ ] TypeScript compiles with no errors (strict mode)

## Example Code Pattern

```typescript
export class AgentFrameworkError extends Error {
  public readonly cause?: Error;
  public readonly code?: string;

  constructor(message: string, cause?: Error, code?: string) {
    super(message);
    this.name = this.constructor.name;
    this.cause = cause;
    this.code = code;
    Error.captureStackTrace?.(this, this.constructor);
  }
}

export class AgentExecutionError extends AgentFrameworkError {}
export class ToolExecutionError extends AgentFrameworkError {}

// Usage
try {
  await tool.execute(params);
} catch (error) {
  throw new ToolExecutionError('Failed to execute tool', error as Error, 'TOOL_EXEC_001');
}
```

## Related Tasks
- **Blocks**: All subsequent tasks (used throughout)
- **Blocked by**: TASK-001 (Scaffolding)
