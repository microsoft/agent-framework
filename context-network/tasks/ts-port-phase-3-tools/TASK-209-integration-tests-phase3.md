# Task: TASK-209 Integration Tests - Phase 3

**Phase**: 3
**Priority**: High
**Estimated Effort**: 5 hours
**Dependencies**: All Phase 3 tasks (TASK-201 through TASK-208)

### Objective
Create comprehensive integration tests for Phase 3 tools and context system, validating that all components work together correctly in real-world scenarios involving tool execution, context providers, and memory.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § All Phase 3 features
- **Python Reference**: `/python/tests/` - Integration test patterns
- **Standards**: CLAUDE.md § Testing → Integration Tests

### Files to Create/Modify
- `src/tools/__tests__/integration/phase-3.test.ts` - Main integration tests
- `test/fixtures/mock-tools.ts` - Mock tools for testing
- `test/fixtures/mock-vector-store.ts` - Mock vector store

### Implementation Requirements

**Test Scenarios**:
1. Agent with tools executes function calls
2. Agent with multiple tools calls them concurrently
3. Tool requiring approval triggers approval flow
4. MCP tool connects and executes
5. OpenAPI tool calls REST API
6. Context provider injects context before execution
7. Multiple context providers aggregate correctly
8. Memory context provider stores and retrieves memories
9. Tool middleware intercepts calls
10. Function middleware modifies execution

**Integration Test Coverage**:
11. End-to-end tool execution flow
12. Tool approval request and response cycle
13. MCP server connection and tool discovery
14. Context provider lifecycle (threadCreated, invoking, invoked)
15. Aggregate context provider merging
16. Memory storage and retrieval
17. Middleware pipeline execution
18. Error handling in tool execution
19. Max iterations limit for tools
20. Tool execution with streaming responses

**Test Infrastructure**:
21. Create mock AIFunctions for testing
22. Create mock MCP server
23. Create mock REST API for OpenAPI tools
24. Create mock vector store for memory tests
25. Use realistic test data

**Code Standards**:
- Use Jest/Vitest
- Use async/await
- Clean up resources

### Test Requirements
- [ ] Test: Agent executes simple tool
- [ ] Test: Agent executes multiple tools concurrently
- [ ] Test: Tool approval request generated
- [ ] Test: Approved tool executes
- [ ] Test: Rejected tool returns error
- [ ] Test: MCP tool connects and lists tools
- [ ] Test: MCP tool executes via tools/call
- [ ] Test: OpenAPI tool parses spec and calls API
- [ ] Test: SimpleContextProvider injects static context
- [ ] Test: RAGContextProvider queries and formats results
- [ ] Test: MemoryContextProvider stores memories
- [ ] Test: MemoryContextProvider retrieves relevant memories
- [ ] Test: AggregateContextProvider merges contexts
- [ ] Test: FunctionMiddleware logs calls
- [ ] Test: FunctionMiddleware caches results
- [ ] Test: Tool execution with max iterations limit
- [ ] Test: Tool execution in streaming mode
- [ ] Test: Error handling in tool calls

**Minimum Coverage**: 100% of integration paths

### Acceptance Criteria
- [ ] All Phase 3 integration tests pass
- [ ] Tests cover realistic scenarios
- [ ] Mock infrastructure robust and reusable
- [ ] Tests run quickly (<10s for full suite)
- [ ] Tests are deterministic
- [ ] TypeScript strict mode, ESLint passes

### Example Code Pattern
```typescript
import { describe, it, expect } from 'vitest';
import { ChatAgent } from '../agents/chat-agent';
import { AIFunction } from '../tools/ai-function';
import { MockChatClient } from '@test/fixtures/mock-chat-client';

describe('Phase 3 Integration Tests', () => {
  it('should execute tool and return result', async () => {
    const weatherTool = new AIFunction({
      name: 'get_weather',
      description: 'Get weather for location',
      func: async (args: { location: string }) => {
        return `Weather in ${args.location}: Sunny, 72°F`;
      },
      inputModel: WeatherArgs
    });

    const client = new MockChatClient({
      responses: [
        {
          role: 'assistant',
          contents: [{
            type: 'function_call',
            callId: 'call-1',
            name: 'get_weather',
            arguments: '{"location":"Seattle"}'
          }]
        },
        {
          role: 'assistant',
          text: 'The weather in Seattle is sunny and 72°F.'
        }
      ]
    });

    const agent = new ChatAgent({
      chatClient: client,
      tools: [weatherTool]
    });

    const response = await agent.run('What is the weather in Seattle?');

    expect(response.text).toContain('sunny');
    expect(response.text).toContain('72°F');
  });

  it('should handle tool approval flow', async () => {
    const dangerousTool = new AIFunction({
      name: 'delete_database',
      description: 'Delete database',
      approvalMode: 'always_require',
      func: async () => 'Database deleted',
      inputModel: DeleteArgs
    });

    const client = new MockChatClient({
      responses: [{
        role: 'assistant',
        contents: [{
          type: 'function_call',
          callId: 'call-1',
          name: 'delete_database',
          arguments: '{}'
        }]
      }]
    });

    const agent = new ChatAgent({
      chatClient: client,
      tools: [dangerousTool]
    });

    // First run - approval requested
    const response1 = await agent.run('Delete the database');

    const approvalRequest = response1.messages[0].contents.find(
      c => c.type === 'function_approval_request'
    );
    expect(approvalRequest).toBeDefined();

    // User approves
    const approval = new ChatMessage({
      role: 'user',
      contents: [{
        type: 'function_approval_response',
        id: approvalRequest!.id,
        functionCall: approvalRequest!.functionCall,
        approved: true
      }]
    });

    // Second run - tool executes
    client.addResponse({
      role: 'assistant',
      text: 'Database has been deleted.'
    });

    const response2 = await agent.run([approval]);
    expect(response2.text).toContain('deleted');
  });

  it('should aggregate context from multiple providers', async () => {
    const provider1 = new SimpleContextProvider({
      instructions: 'Be helpful.'
    });

    const provider2 = new SimpleContextProvider({
      instructions: 'Be concise.'
    });

    const aggregate = new AggregateContextProvider([provider1, provider2]);

    const client = new MockChatClient();
    const agent = new ChatAgent({
      chatClient: client,
      contextProviders: aggregate
    });

    await agent.run('Hello');

    // Verify context was injected
    const lastCall = client.getLastCall();
    expect(lastCall.messages.some(m =>
      m.text?.includes('Be helpful') && m.text?.includes('Be concise')
    )).toBe(true);
  });

  it('should store and retrieve memories', async () => {
    const vectorStore = new MockVectorStore();
    const embeddingService = new MockEmbeddingService();
    const memoryProvider = new MemoryContextProvider(vectorStore, embeddingService);

    const client = new MockChatClient();
    const agent = new ChatAgent({
      chatClient: client,
      contextProviders: memoryProvider
    });

    // First conversation - store memory
    await agent.run('My name is Alice');
    expect(vectorStore.size()).toBeGreaterThan(0);

    // Second conversation - retrieve memory
    await agent.run('What is my name?');

    const context = await memoryProvider.invoking([
      new ChatMessage({ role: 'user', text: 'What is my name?' })
    ]);

    expect(context.instructions).toContain('Alice');
  });
});
```

### Related Tasks
- **Blocked by**: All Phase 3 tasks (TASK-201 through TASK-208)
- **Blocks**: Phase 4 (validates Phase 3 completion)
