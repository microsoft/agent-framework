# Task: TASK-108 Integration Tests - Phase 2

**Phase**: 2
**Priority**: High
**Estimated Effort**: 4 hours
**Dependencies**: All Phase 2 tasks (TASK-101 through TASK-107)

### Objective
Create comprehensive integration tests for Phase 2 agent system, validating that all components work together correctly in real-world scenarios.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § All Phase 2 features
- **Python Reference**: `/python/tests/` - Integration test patterns
- **Standards**: CLAUDE.md § Testing → Integration Tests

### Files to Create/Modify
- `src/agents/__tests__/integration/phase-2.test.ts` - Main integration tests
- `test/fixtures/mock-chat-client.ts` - Mock chat client for testing
- `test/fixtures/test-helpers.ts` - Test utility functions

### Implementation Requirements

**Test Scenarios**:
1. Create ChatAgent with minimal configuration
2. Send message and receive response
3. Stream responses with AsyncIterable
4. Maintain conversation history across multiple runs
5. Use service-managed threads with conversation ID
6. Use local-managed threads with message store
7. Apply middleware to agent invocations
8. Use context providers to inject context
9. Serialize and deserialize agents
10. Use tools during agent execution

**Integration Test Coverage**:
11. End-to-end agent creation and execution
12. Thread management (service and local)
13. Middleware chains with multiple middleware
14. Context provider lifecycle
15. Agent serialization round-trips
16. Error handling in production scenarios
17. Streaming with real async iteration
18. Tool calls with function execution

**Test Infrastructure**:
19. Create MockChatClient implementing ChatClientProtocol
20. Create TestMessageStore implementing ChatMessageStore
21. Create test middleware for validation
22. Create test context provider
23. Use realistic test data (not minimal stubs)

**Code Standards**:
- Use Jest/Vitest for testing
- Use async/await for all tests
- Clean up resources (using, finally blocks)

### Test Requirements
- [ ] Test: Create ChatAgent and run with string message
- [ ] Test: Create ChatAgent and run with ChatMessage array
- [ ] Test: Stream responses and collect all updates
- [ ] Test: Maintain history across multiple runs (service thread)
- [ ] Test: Maintain history across multiple runs (local thread)
- [ ] Test: Apply logging middleware and verify calls
- [ ] Test: Apply context provider and verify context injection
- [ ] Test: Serialize agent and deserialize with dependencies
- [ ] Test: Use tools during execution and verify results
- [ ] Test: Handle errors gracefully
- [ ] Test: Thread type determination (undetermined → determined)
- [ ] Test: Custom agent implementation passes AgentProtocol checks

**Minimum Coverage**: 100% of integration paths

### Acceptance Criteria
- [ ] All Phase 2 integration tests pass
- [ ] Tests use realistic scenarios (not just happy path)
- [ ] Mock infrastructure robust and reusable
- [ ] Tests run quickly (<5s for full suite)
- [ ] Tests are deterministic (no flaky tests)
- [ ] TypeScript strict mode, ESLint passes

### Example Code Pattern
```typescript
import { describe, it, expect } from 'vitest';
import { ChatAgent } from '../chat-agent';
import { MockChatClient } from '@test/fixtures/mock-chat-client';

describe('Phase 2 Integration Tests', () => {
  it('should create agent and get response', async () => {
    const client = new MockChatClient({
      responses: [{ text: 'Hello!' }]
    });

    const agent = new ChatAgent({
      chatClient: client,
      name: 'test-agent',
      instructions: 'You are helpful'
    });

    const response = await agent.run('Hi there');

    expect(response.text).toBe('Hello!');
    expect(response.messages).toHaveLength(1);
  });

  it('should maintain conversation history with service thread', async () => {
    const client = new MockChatClient({
      supportsConversationId: true,
      responses: [
        { text: 'Nice to meet you!', conversationId: 'conv-123' },
        { text: 'I remember you said your name is Alice.' }
      ]
    });

    const agent = new ChatAgent({
      chatClient: client,
      conversationId: 'conv-123'
    });

    const thread = agent.getNewThread();

    // First message
    const response1 = await agent.run('My name is Alice', { thread });
    expect(response1.text).toBe('Nice to meet you!');
    expect(thread.serviceThreadId).toBe('conv-123');

    // Second message - history maintained by service
    const response2 = await agent.run('What did I tell you?', { thread });
    expect(response2.text).toContain('Alice');
  });

  it('should apply middleware chain correctly', async () => {
    const calls: string[] = [];

    const middleware1 = {
      async onAgentInvoking(ctx) {
        calls.push('m1-invoking');
      },
      async onAgentInvoked(ctx) {
        calls.push('m1-invoked');
      }
    };

    const middleware2 = {
      async onAgentInvoking(ctx) {
        calls.push('m2-invoking');
      },
      async onAgentInvoked(ctx) {
        calls.push('m2-invoked');
      }
    };

    const client = new MockChatClient();
    const agent = new ChatAgent({
      chatClient: client,
      middleware: [middleware1, middleware2]
    });

    await agent.run('test');

    expect(calls).toEqual([
      'm1-invoking',
      'm2-invoking',
      'm2-invoked',
      'm1-invoked'
    ]);
  });

  it('should serialize and deserialize agent', async () => {
    const client = new MockChatClient();
    const agent = new ChatAgent({
      chatClient: client,
      name: 'original-agent',
      temperature: 0.7,
      maxTokens: 100
    });

    const serialized = agent.toDict();

    expect(serialized.name).toBe('original-agent');
    expect(serialized.chatClient).toBeUndefined(); // Excluded

    const restored = ChatAgent.fromDict(serialized, {
      dependencies: {
        'chat_agent.chatClient': client
      }
    });

    expect(restored.name).toBe('original-agent');
    expect(restored.chatClient).toBe(client);

    // Restored agent should work
    const response = await restored.run('test');
    expect(response).toBeDefined();
  });
});
```

### Related Tasks
- **Blocked by**: All Phase 2 tasks (TASK-101 through TASK-107)
- **Blocks**: Phase 3 (validates Phase 2 completion)
