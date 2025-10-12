# Task: TASK-106 Agent Lifecycle Hooks

**Phase**: 2
**Priority**: Medium
**Estimated Effort**: 4 hours
**Dependencies**: TASK-007 (BaseAgent), TASK-012 (ContextProvider)

### Objective
Implement agent lifecycle hooks that allow context providers and other components to react to key agent events during execution (invoking, invoked, thread created).

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-9 (Context Providers) → Lifecycle
- **Python Reference**: `/python/packages/core/agent_framework/_memory.py:50-150` - ContextProvider lifecycle methods
- **Python Reference**: `/python/packages/core/agent_framework/_agents.py:296-316` - notify_thread_of_new_messages
- **Standards**: CLAUDE.md § Python Architecture → Async-First

### Files to Create/Modify
- `src/core/context-provider.ts` - Add lifecycle methods
- `src/agents/base-agent.ts` - Implement lifecycle calls
- `src/agents/chat-agent.ts` - Call lifecycle hooks
- `src/core/__tests__/lifecycle.test.ts` - Unit tests

### Implementation Requirements

**ContextProvider Lifecycle Methods**:
1. Define `invoking(messages)` method called before agent execution
2. Define `invoked(inputMessages, responseMessages)` method called after execution
3. Define `threadCreated(threadId)` method called when service thread is created
4. Make all lifecycle methods async
5. Support returning Context from `invoking()` to modify execution

**BaseAgent Integration**:
6. Implement `notifyThreadOfNewMessages()` calling thread and context provider
7. Call `contextProvider.invoking()` in `prepareThreadAndMessages()`
8. Call `contextProvider.invoked()` after successful execution
9. Call `threadCreated()` when service thread ID is set
10. Wrap lifecycle calls in AsyncContextManager (`using` pattern)

**Error Handling**:
11. Lifecycle errors should not fail agent execution
12. Log warnings for lifecycle hook failures
13. Continue execution if lifecycle hook throws

**TypeScript Patterns**:
- Use async methods for all lifecycle hooks
- Use optional chaining for provider checks
- Use Symbol.asyncDispose for context manager pattern

**Code Standards**:
- 120 character line length
- JSDoc with examples
- Strict mode

### Test Requirements
- [ ] Test `invoking()` called before agent execution
- [ ] Test `invoked()` called after successful execution
- [ ] Test `threadCreated()` called when service thread set
- [ ] Test Context returned from `invoking()` modifies execution
- [ ] Test lifecycle hooks not called if no context provider
- [ ] Test agent continues if lifecycle hook throws
- [ ] Test lifecycle hook errors are logged
- [ ] Test multiple context providers (via AggregateContextProvider)

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] Lifecycle methods defined on ContextProvider
- [ ] All lifecycle hooks called at correct times
- [ ] Error handling for failing hooks
- [ ] Tests pass with >85% coverage
- [ ] TypeScript strict mode, ESLint passes

### Example Code Pattern
```typescript
export abstract class ContextProvider {
  async invoking(messages: ChatMessage[]): Promise<Context | null> {
    return null;
  }

  async invoked(
    inputMessages: ChatMessage[],
    responseMessages: ChatMessage[]
  ): Promise<void> {
    // Override in subclass
  }

  async threadCreated(threadId: string): Promise<void> {
    // Override in subclass
  }
}

// In ChatAgent
private async prepareThreadAndMessages(...) {
  // ...
  if (this.contextProvider) {
    try {
      using _ = await this.contextProvider[Symbol.asyncDispose]();
      const context = await this.contextProvider.invoking(inputMessages);
      if (context) {
        // Merge context into options
      }
    } catch (error) {
      logger.warn('Context provider invoking failed:', error);
    }
  }
}

private async notifyThreadOfNewMessages(
  thread: AgentThread,
  inputMessages: ChatMessage[],
  responseMessages: ChatMessage[]
): Promise<void> {
  await thread.onNewMessages(inputMessages);
  await thread.onNewMessages(responseMessages);

  if (thread.contextProvider) {
    try {
      await thread.contextProvider.invoked(inputMessages, responseMessages);
    } catch (error) {
      logger.warn('Context provider invoked failed:', error);
    }
  }
}
```

### Related Tasks
- **Blocked by**: TASK-007 (BaseAgent), TASK-012 (ContextProvider)
- **Related**: TASK-101 (ChatAgent calls hooks)
