# Task: TASK-105 Local-Managed Thread Support

**Phase**: 2
**Priority**: High
**Estimated Effort**: 4 hours
**Dependencies**: TASK-008 (AgentThread), TASK-010 (MessageStore), TASK-101 (ChatAgent)

### Objective
Implement local-managed conversation thread support where thread state (message history) is stored client-side using a message store, enabling full control over conversation persistence.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-5 (Thread Management) → Local-Managed
- **Python Reference**: `/python/packages/core/agent_framework/_threads.py:200-400` - AgentThread with message_store
- **Python Reference**: `/python/packages/core/agent_framework/_agents.py:1158-1163` - Local storage creation
- **Standards**: CLAUDE.md § Python Architecture → Thread Management

### Files to Create/Modify
- `src/threads/agent-thread.ts` - Add messageStore support
- `src/agents/chat-agent.ts` - Local thread creation and management
- `src/threads/__tests__/local-threads.test.ts` - Unit tests

### Implementation Requirements

**AgentThread Enhancements**:
1. Add `messageStore` property (optional ChatMessageStore)
2. Ensure `messageStore` and `serviceThreadId` are mutually exclusive
3. Implement `onNewMessages()` to store messages in message store
4. Implement `getMessages()` to retrieve from message store
5. Create default in-memory message store if none provided and needed

**ChatAgent Integration**:
6. Accept `chatMessageStoreFactory` in constructor
7. Create threads with message store when factory provided
8. If thread is undetermined and service doesn't return conversation ID, create message store
9. Use message store factory to create store instances
10. Load existing messages from store before each run

**Message Store Protocol**:
11. Define `ChatMessageStore` interface with `add()`, `list()`, `clear()` methods
12. Implement `InMemoryMessageStore` as default implementation
13. Support async operations for all store methods

**TypeScript Patterns**:
- Use factory pattern for message store creation
- Use async operations for store methods (future-proof for DB stores)
- Validate thread configuration in constructor

**Code Standards**:
- 120 character line length
- JSDoc with examples
- Strict mode, no `any`

### Test Requirements
- [ ] Test AgentThread creation with messageStore
- [ ] Test `isLocalManaged` returns true when messageStore set
- [ ] Test error when both serviceThreadId and messageStore provided
- [ ] Test `onNewMessages()` adds messages to store
- [ ] Test `getMessages()` retrieves messages from store
- [ ] Test ChatAgent creates thread with message store when factory provided
- [ ] Test thread becomes local-managed when service has no conversation ID
- [ ] Test message store factory called to create store instances
- [ ] Test messages loaded from store before each run
- [ ] Test InMemoryMessageStore implements ChatMessageStore correctly

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] AgentThread supports messageStore property
- [ ] ChatMessageStore interface defined
- [ ] InMemoryMessageStore implemented
- [ ] Local-managed threads persist messages across runs
- [ ] Thread type determination works for local storage
- [ ] Tests pass with >85% coverage
- [ ] TypeScript strict mode, ESLint passes
- [ ] JSDoc complete with examples

### Example Code Pattern
```typescript
export interface ChatMessageStore {
  add(message: ChatMessage | ChatMessage[]): Promise<void>;
  list(): Promise<ChatMessage[]>;
  clear(): Promise<void>;
}

export class InMemoryMessageStore implements ChatMessageStore {
  private messages: ChatMessage[] = [];

  async add(message: ChatMessage | ChatMessage[]): Promise<void> {
    const msgs = Array.isArray(message) ? message : [message];
    this.messages.push(...msgs);
  }

  async list(): Promise<ChatMessage[]> {
    return [...this.messages];
  }

  async clear(): Promise<void> {
    this.messages = [];
  }
}

export class AgentThread {
  async onNewMessages(messages: ChatMessage | ChatMessage[]): Promise<void> {
    if (this.messageStore) {
      await this.messageStore.add(messages);
    }
  }

  async getMessages(): Promise<ChatMessage[]> {
    if (this.messageStore) {
      return await this.messageStore.list();
    }
    return [];
  }
}

// In ChatAgent
constructor(options: ChatAgentOptions) {
  // ...
  this.chatMessageStoreFactory = options.chatMessageStoreFactory;
}

override getNewThread(options?: ThreadOptions): AgentThread {
  if (this.chatMessageStoreFactory) {
    return new AgentThread({
      messageStore: this.chatMessageStoreFactory(),
      contextProvider: this.contextProvider
    });
  }
  return super.getNewThread(options);
}

private async updateThreadWithConversationId(
  thread: AgentThread,
  conversationId?: string
): Promise<void> {
  // ...
  if (!conversationId && !thread.messageStore && this.chatMessageStoreFactory) {
    // Thread becomes local-managed
    thread.messageStore = this.chatMessageStoreFactory();
  }
}
```

### Related Tasks
- **Blocked by**: TASK-008 (AgentThread), TASK-010 (MessageStore), TASK-101 (ChatAgent)
- **Blocks**: TASK-108 (Integration tests)
- **Related**: TASK-104 (Service-managed - complementary)
