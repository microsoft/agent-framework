# Task: TASK-104 Service-Managed Thread Support

**Phase**: 2
**Priority**: High
**Estimated Effort**: 5 hours
**Dependencies**: TASK-008 (AgentThread), TASK-101 (ChatAgent)

### Objective
Implement service-managed conversation thread support where thread state is managed server-side by the chat service provider using a conversation ID, enabling stateless client applications.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-5 (Thread Management) → Service-Managed
- **Python Reference**: `/python/packages/core/agent_framework/_threads.py:1-300` - AgentThread with service_thread_id
- **Python Reference**: `/python/packages/core/agent_framework/_agents.py:1132-1163` - Thread update logic
- **Standards**: CLAUDE.md § Python Architecture → Thread Management

### Files to Create/Modify
- `src/threads/agent-thread.ts` - Add serviceThreadId support
- `src/agents/chat-agent.ts` - Service thread creation and management
- `src/threads/__tests__/service-threads.test.ts` - Unit tests
- `src/index.ts` - Ensure exports

### Implementation Requirements

**AgentThread Enhancements**:
1. Add `serviceThreadId` property (optional string)
2. Add `isServiceManaged` computed property (true if serviceThreadId exists)
3. Ensure `serviceThreadId` and `messageStore` are mutually exclusive
4. Update `getNewThread()` to accept `serviceThreadId` parameter
5. Implement `updateThreadWithConversationId()` method to set service ID from response

**ChatAgent Integration**:
6. Check if chat client returns conversation ID in response
7. Update thread's `serviceThreadId` from chat response
8. Raise error if thread is service-managed but service doesn't return conversation ID
9. Notify context provider of thread creation with `threadCreated(serviceThreadId)`
10. Pass `conversationId` to chat client via ChatOptions

**Thread Lifecycle**:
11. Thread starts as undetermined (no serviceThreadId, no messageStore)
12. After first run, thread type is determined by service response
13. If service returns conversation ID, thread becomes service-managed
14. If service doesn't return ID, thread becomes local-managed (next task)
15. Once determined, thread type cannot change

**TypeScript Patterns**:
- Use discriminated union for thread type (service vs local vs undetermined)
- Use readonly properties for immutable thread state
- Validate mutually exclusive properties in constructor

**Code Standards**:
- 120 character line length
- JSDoc with examples
- Strict mode, no `any`

### Test Requirements
- [ ] Test AgentThread creation with serviceThreadId
- [ ] Test `isServiceManaged` returns true when serviceThreadId set
- [ ] Test error when both serviceThreadId and messageStore provided
- [ ] Test ChatAgent updates thread with conversation ID from response
- [ ] Test ChatAgent raises error if service-managed thread gets no conversation ID
- [ ] Test context provider notified with `threadCreated(serviceThreadId)`
- [ ] Test conversation ID passed to chat client in ChatOptions
- [ ] Test undetermined thread becomes service-managed after first run
- [ ] Test subsequent runs use existing serviceThreadId
- [ ] Test thread type doesn't change after determination

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] AgentThread supports serviceThreadId property
- [ ] Service-managed threads work with chat clients that return conversation IDs
- [ ] Error handling for incompatible thread configurations
- [ ] Thread type determination logic implemented
- [ ] Context provider lifecycle hooks called correctly
- [ ] Tests pass with >85% coverage
- [ ] TypeScript strict mode, ESLint passes
- [ ] JSDoc complete with examples

### Example Code Pattern
```typescript
export interface AgentThreadOptions {
  serviceThreadId?: string;
  messageStore?: ChatMessageStore;
  contextProvider?: ContextProvider;
}

export class AgentThread {
  readonly serviceThreadId?: string;
  readonly messageStore?: ChatMessageStore;
  readonly contextProvider?: ContextProvider;

  constructor(options: AgentThreadOptions = {}) {
    if (options.serviceThreadId && options.messageStore) {
      throw new AgentInitializationError(
        'Cannot specify both serviceThreadId and messageStore'
      );
    }

    this.serviceThreadId = options.serviceThreadId;
    this.messageStore = options.messageStore;
    this.contextProvider = options.contextProvider;
  }

  get isServiceManaged(): boolean {
    return this.serviceThreadId !== undefined;
  }

  get isLocalManaged(): boolean {
    return this.messageStore !== undefined;
  }

  get isUndetermined(): boolean {
    return !this.isServiceManaged && !this.isLocalManaged;
  }
}

// In ChatAgent
async run(...): Promise<AgentRunResponse> {
  // ... prepare thread and messages

  const response = await this.chatClient.getResponse(messages, options);

  // Update thread type based on response
  await this.updateThreadWithConversationId(thread, response.conversationId);

  // ...
}

private async updateThreadWithConversationId(
  thread: AgentThread,
  conversationId?: string
): Promise<void> {
  if (!conversationId && thread.isServiceManaged) {
    throw new AgentExecutionException(
      'Service did not return conversation ID for service-managed thread'
    );
  }

  if (conversationId) {
    // Thread becomes service-managed
    thread.serviceThreadId = conversationId;
    if (thread.contextProvider) {
      await thread.contextProvider.threadCreated(conversationId);
    }
  }
}
```

### Related Tasks
- **Blocked by**: TASK-008 (AgentThread), TASK-101 (ChatAgent)
- **Blocks**: TASK-108 (Integration tests need this)
- **Related**: TASK-105 (Local-managed threads - complementary)
