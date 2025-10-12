# Task: TASK-409 Integration Tests - Phase 5

**Phase**: 5
**Priority**: High
**Estimated Effort**: 5 hours
**Dependencies**: TASK-401 through TASK-408 (All Phase 5 tasks)

### Objective
Implement comprehensive integration tests for Phase 5 advanced features including A2A, hosted tools, and observability.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § Phase 5 Features
- **Python Reference**: `/python/tests/test_a2a.py`, `/python/tests/test_hosted_tools.py`
- **.NET Reference**: `/dotnet/tests/Microsoft.Agents.AI.Tests/`
- **Standards**: CLAUDE.md § Testing Strategy

### Files to Create/Modify
- `src/__tests__/integration/a2a.integration.test.ts` - A2A integration tests
- `src/__tests__/integration/hosted-tools.integration.test.ts` - Hosted tools tests
- `src/__tests__/integration/telemetry.integration.test.ts` - Telemetry tests
- `README.md` - Add Phase 5 examples

### Implementation Requirements

**A2A Tests**:
1. Test agent registration and discovery
2. Test remote agent invocation
3. Test inter-agent messaging
4. Test authentication and authorization
5. Test streaming responses
6. Test error handling

**Hosted Tools Tests**:
7. Test HostedCodeInterpreterTool integration
8. Test HostedFileSearchTool integration
9. Test HostedWebSearchTool integration
10. Test HostedMCPTool with approval flows
11. Test tool error handling

**Telemetry Tests**:
12. Test span creation for agent invocations
13. Test span creation for tool executions
14. Test metrics recording (tokens, latency)
15. Test trace context propagation
16. Test @traced decorator

**Test Requirements**: All integration scenarios, error handling, authentication, observability

**Acceptance Criteria**: All integration tests passing, examples documented, coverage >85%

### Example Code Pattern
```typescript
describe('A2A Integration Tests', () => {
  it('should register and discover agents', async () => {
    const server = new A2AServer({ port: 3000 });
    const agent = new ChatAgent({ chatClient, name: 'test' });

    server.registerAgent(agent);
    await server.start();

    const client = new A2AClient({ baseUrl: 'http://localhost:3000' });
    const agents = await client.discoverAgents();

    expect(agents).toContainEqual(
      expect.objectContaining({ id: agent.id })
    );

    await server.stop();
  });

  it('should invoke remote agent', async () => {
    const server = new A2AServer({ port: 3001 });
    const agent = new ChatAgent({ chatClient, name: 'remote' });

    server.registerAgent(agent);
    await server.start();

    const client = new A2AClient({ baseUrl: 'http://localhost:3001' });
    const response = await client.callAgent({
      targetAgentId: agent.id,
      sourceAgentId: 'caller',
      content: 'Hello'
    });

    expect(response.response).toBeDefined();
    await server.stop();
  });
});

describe('Hosted Tools Integration Tests', () => {
  it('should use HostedCodeInterpreterTool', async () => {
    const tool = new HostedCodeInterpreterTool({
      language: 'python'
    });

    const agent = new ChatAgent({
      chatClient,
      tools: [tool]
    });

    const response = await agent.run('Calculate 2 + 2');
    expect(response.text).toContain('4');
  });
});

describe('Telemetry Integration Tests', () => {
  it('should create spans for agent invocations', async () => {
    const { tracer, spans } = setupTestTracer();

    const agent = new ChatAgent({ chatClient, name: 'traced' });
    await agent.run('Hello');

    const agentSpan = spans.find(s => s.name.includes('ChatAgent'));
    expect(agentSpan).toBeDefined();
    expect(agentSpan?.attributes['agent.id']).toBe(agent.id);
  });
});
```

### Related Tasks
- **Blocked by**: All Phase 5 tasks (TASK-401 through TASK-408)
- **Validates**: Complete Phase 5 implementation
