# Task: TASK-204 ContextProvider Implementations

**Phase**: 3
**Priority**: High
**Estimated Effort**: 6 hours
**Dependencies**: TASK-012 (ContextProvider Abstract Class)

### Objective
Implement concrete ContextProvider classes for common use cases, demonstrating the context provider pattern and providing ready-to-use implementations for memory, RAG, and custom context injection.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-9 (Context Providers)
- **Python Reference**: `/python/packages/core/agent_framework/_memory.py:74-184` - ContextProvider base class
- **Python Reference**: Python packages (mem0, redis) for specific implementations
- **Standards**: CLAUDE.md § Python Architecture → Context Providers

### Files to Create/Modify
- `src/context/simple-context-provider.ts` - Simple static context provider
- `src/context/rag-context-provider.ts` - RAG-based context provider
- `src/context/session-context-provider.ts` - Session-based context provider
- `src/context/__tests__/context-providers.test.ts` - Unit tests

### Implementation Requirements

**SimpleContextProvider**:
1. Accept static instructions, messages, or tools
2. Return same context for every `invoking()` call
3. No-op for `invoked()` and `threadCreated()`
4. Use case: static instructions or system messages

**RAGContextProvider** (conceptual):
5. Accept vector store interface
6. On `invoking()`, query vector store with recent messages
7. Retrieve relevant documents/memories
8. Format as Context with instructions or messages
9. Use case: retrieval-augmented generation

**SessionContextProvider**:
10. Maintain session state in memory
11. Store conversation metadata per thread
12. Inject session info into context
13. Use case: tracking user preferences, session data

**Base Implementation Pattern**:
14. Extend ContextProvider abstract class
15. Implement `invoking()` method (required)
16. Optionally implement `invoked()` for state updates
17. Optionally implement `threadCreated()` for initialization
18. Support async context manager protocol

**TypeScript Patterns**:
- Use class inheritance for ContextProvider
- Use async/await for all lifecycle methods
- Type Context return values strictly

**Code Standards**:
- 120 character line length
- JSDoc with examples
- Strict mode

### Test Requirements
- [ ] Test SimpleContextProvider returns static context
- [ ] Test RAGContextProvider queries vector store
- [ ] Test RAGContextProvider formats results as Context
- [ ] Test SessionContextProvider maintains state
- [ ] Test SessionContextProvider per-thread isolation
- [ ] Test `threadCreated()` lifecycle hook
- [ ] Test `invoked()` lifecycle hook
- [ ] Test async context manager cleanup

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] At least 3 concrete ContextProvider implementations
- [ ] Each demonstrates different use case
- [ ] All lifecycle methods implemented correctly
- [ ] Tests pass with >85% coverage
- [ ] TypeScript strict mode, ESLint passes
- [ ] JSDoc complete with examples

### Example Code Pattern
```typescript
/**
 * Simple context provider that returns static context.
 */
export class SimpleContextProvider extends ContextProvider {
  constructor(
    private readonly context: Partial<Context>
  ) {
    super();
  }

  async invoking(messages: ChatMessage[]): Promise<Context> {
    return new Context({
      instructions: this.context.instructions,
      messages: this.context.messages || [],
      tools: this.context.tools || []
    });
  }
}

/**
 * RAG-based context provider using vector store.
 */
export class RAGContextProvider extends ContextProvider {
  constructor(
    private readonly vectorStore: VectorStore,
    private readonly topK: number = 5
  ) {
    super();
  }

  async invoking(messages: ChatMessage[]): Promise<Context> {
    const query = messages[messages.length - 1]?.text || '';
    const results = await this.vectorStore.search(query, this.topK);

    const instructions = this.formatResults(results);

    return new Context({
      instructions,
      messages: [],
      tools: []
    });
  }

  private formatResults(results: VectorSearchResult[]): string {
    const memories = results.map(r => r.content).join('\n\n');
    return `${ContextProvider.DEFAULT_CONTEXT_PROMPT}\n\n${memories}`;
  }
}

/**
 * Session-based context provider.
 */
export class SessionContextProvider extends ContextProvider {
  private sessions = new Map<string, SessionData>();

  async threadCreated(threadId: string): Promise<void> {
    if (!this.sessions.has(threadId)) {
      this.sessions.set(threadId, {
        createdAt: new Date(),
        metadata: {}
      });
    }
  }

  async invoking(messages: ChatMessage[]): Promise<Context> {
    const threadId = this.getCurrentThreadId(); // from context
    const session = this.sessions.get(threadId);

    if (!session) {
      return new Context({});
    }

    const instructions = `Session started at: ${session.createdAt.toISOString()}`;

    return new Context({ instructions });
  }

  async invoked(
    requestMessages: ChatMessage[],
    responseMessages: ChatMessage[]
  ): Promise<void> {
    const threadId = this.getCurrentThreadId();
    const session = this.sessions.get(threadId);

    if (session) {
      session.lastActivity = new Date();
    }
  }
}

// Usage
const simpleContext = new SimpleContextProvider({
  instructions: 'Always be helpful and concise.'
});

const ragContext = new RAGContextProvider(vectorStore, 5);

const sessionContext = new SessionContextProvider();

const agent = new ChatAgent({
  chatClient: client,
  contextProviders: [simpleContext, ragContext, sessionContext]
});
```

### Related Tasks
- **Blocked by**: TASK-012 (ContextProvider abstract class)
- **Related**: TASK-205 (AggregateContextProvider)
- **Related**: TASK-206 (Memory Context Provider - advanced)
