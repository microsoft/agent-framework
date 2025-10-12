# Task: TASK-205 AggregateContextProvider

**Phase**: 3
**Priority**: High
**Estimated Effort**: 4 hours
**Dependencies**: TASK-012 (ContextProvider), TASK-204 (Context Provider Implementations)

### Objective
Implement AggregateContextProvider that combines multiple context providers, calling each in parallel and merging their contexts into a single unified context for agent execution.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-9 (Context Providers) → Aggregation
- **Python Reference**: `/python/packages/core/agent_framework/_memory.py:189-310` - AggregateContextProvider
- **Standards**: CLAUDE.md § Python Architecture → Async-First

### Files to Create/Modify
- `src/context/aggregate-context-provider.ts` - AggregateContextProvider class
- `src/context/__tests__/aggregate-context-provider.test.ts` - Unit tests

### Implementation Requirements

**Core Functionality**:
1. Extend ContextProvider abstract class
2. Accept single provider or array of providers in constructor
3. Store providers in internal array
4. Implement `add()` method to add providers dynamically
5. Call all providers' `threadCreated()` in parallel
6. Call all providers' `invoking()` in parallel
7. Merge contexts from all providers
8. Call all providers' `invoked()` in parallel

**Context Merging**:
9. Concatenate all instructions (separated by newlines)
10. Combine all messages into single array
11. Combine all tools into single array
12. Maintain order of providers for deterministic merging

**Async Context Manager**:
13. Implement `__aenter__` to enter all providers
14. Use AsyncExitStack to manage provider lifecycles
15. Implement `__aexit__` to exit all providers
16. Ensure cleanup even on errors

**TypeScript Patterns**:
- Use Promise.all() for parallel execution
- Use AsyncExitStack or similar for resource management
- Type provider array properly

**Code Standards**:
- 120 character line length
- JSDoc with examples
- Strict mode

### Test Requirements
- [ ] Test AggregateContextProvider with single provider
- [ ] Test AggregateContextProvider with multiple providers
- [ ] Test `add()` method adds provider
- [ ] Test `threadCreated()` called on all providers
- [ ] Test `invoking()` called on all providers in parallel
- [ ] Test context merging (instructions, messages, tools)
- [ ] Test `invoked()` called on all providers
- [ ] Test async context manager enters all providers
- [ ] Test async context manager exits all providers
- [ ] Test cleanup on error

**Minimum Coverage**: 90%

### Acceptance Criteria
- [ ] AggregateContextProvider combines multiple providers
- [ ] All lifecycle methods called in parallel
- [ ] Contexts merged correctly
- [ ] Async context manager works correctly
- [ ] Tests pass with >90% coverage
- [ ] TypeScript strict mode, ESLint passes
- [ ] JSDoc complete with examples

### Example Code Pattern
```typescript
export class AggregateContextProvider extends ContextProvider {
  private providers: ContextProvider[];
  private exitStack?: AsyncExitStack;

  constructor(providers?: ContextProvider | ContextProvider[]) {
    super();

    if (providers === undefined) {
      this.providers = [];
    } else if (Array.isArray(providers)) {
      this.providers = providers;
    } else {
      this.providers = [providers];
    }
  }

  add(provider: ContextProvider): void {
    this.providers.push(provider);
  }

  async threadCreated(threadId: string): Promise<void> {
    await Promise.all(
      this.providers.map(p => p.threadCreated(threadId))
    );
  }

  async invoking(messages: ChatMessage[]): Promise<Context> {
    const contexts = await Promise.all(
      this.providers.map(p => p.invoking(messages))
    );

    // Merge all contexts
    let instructions = '';
    const allMessages: ChatMessage[] = [];
    const allTools: ToolProtocol[] = [];

    for (const ctx of contexts) {
      if (ctx.instructions) {
        instructions += (instructions ? '\n' : '') + ctx.instructions;
      }
      if (ctx.messages) {
        allMessages.push(...ctx.messages);
      }
      if (ctx.tools) {
        allTools.push(...ctx.tools);
      }
    }

    return new Context({
      instructions: instructions || undefined,
      messages: allMessages,
      tools: allTools
    });
  }

  async invoked(
    requestMessages: ChatMessage[],
    responseMessages: ChatMessage[]
  ): Promise<void> {
    await Promise.all(
      this.providers.map(p => p.invoked(requestMessages, responseMessages))
    );
  }

  async [Symbol.asyncDispose](): Promise<void> {
    if (this.exitStack) {
      await this.exitStack[Symbol.asyncDispose]();
      this.exitStack = undefined;
    }
  }

  // Note: TypeScript doesn't have exact equivalent of Python's __aenter__/__aexit__
  // This would be handled via explicit enter/exit methods or Symbol.asyncDispose
}

// Usage
const provider1 = new SimpleContextProvider({ instructions: 'Be helpful' });
const provider2 = new RAGContextProvider(vectorStore);
const provider3 = new SessionContextProvider();

const aggregate = new AggregateContextProvider([provider1, provider2, provider3]);

// Or add dynamically
const aggregate2 = new AggregateContextProvider();
aggregate2.add(provider1);
aggregate2.add(provider2);

const agent = new ChatAgent({
  chatClient: client,
  contextProviders: aggregate
});
```

### Related Tasks
- **Blocked by**: TASK-012 (ContextProvider), TASK-204 (Implementations)
- **Related**: TASK-101 (ChatAgent uses aggregate provider)
