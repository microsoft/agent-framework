# Task: TASK-311 Integration Tests - Phase 4

**Phase**: 4
**Priority**: High
**Estimated Effort**: 6 hours
**Dependencies**: TASK-301 through TASK-310 (All Phase 4 tasks)

### Objective
Implement comprehensive integration tests for the workflow system, validating end-to-end scenarios and cross-component interactions.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-8 (Workflows)
- **Python Reference**: `/python/tests/test_workflows.py` - Workflow integration tests
- **.NET Reference**: `/dotnet/tests/Microsoft.Agents.AI.Workflows.Tests/` - Integration tests
- **Standards**: CLAUDE.md § Testing Strategy

### Files to Create/Modify
- `src/workflows/__tests__/integration/workflow.integration.test.ts` - Main integration tests
- `src/workflows/__tests__/integration/checkpointing.integration.test.ts` - Checkpoint integration tests
- `src/workflows/__tests__/integration/human-in-loop.integration.test.ts` - RequestInfo integration tests
- `src/workflows/__tests__/integration/streaming.integration.test.ts` - Streaming integration tests
- `README.md` - Add workflow examples and documentation

### Implementation Requirements

**Core Integration Tests**:
1. Test sequential workflow (agent1 → agent2 → agent3)
2. Test parallel workflow (fan-out → fan-in)
3. Test conditional workflow (if-then-else routing)
4. Test switch-case workflow (multi-way branching)
5. Test nested workflow (workflow as executor)
6. Test human-in-the-loop workflow (RequestInfoExecutor)
7. Test workflow with context provider and shared state
8. Test workflow error handling and recovery
9. Test workflow streaming execution
10. Test workflow checkpoint and resumption

**Checkpointing Tests**:
11. Test checkpoint creation at executor boundaries
12. Test checkpoint restoration and workflow resumption
13. Test checkpoint compatibility validation
14. Test checkpoint with pending requests
15. Test time-travel debugging (resume from any checkpoint)

**Streaming Tests**:
16. Test event streaming order and completeness
17. Test agent streaming updates forwarded to workflow
18. Test request events emitted correctly
19. Test workflow completion events
20. Test error events on failure

**Human-in-the-Loop Tests**:
21. Test RequestInfoExecutor pauses workflow
22. Test workflow resumes after response
23. Test multiple concurrent requests
24. Test request timeout handling
25. Test request cancellation

**TypeScript Patterns**:
- Use Jest or Vitest for testing
- Mock agents and chat clients
- Use async/await for test execution
- Test with real and mock components
- Comprehensive test coverage

**Code Standards**:
- 120 character line length
- Clear test descriptions
- Arrange-Act-Assert pattern
- No flaky tests
- Fast execution (< 5 seconds total)

### Test Requirements
- [ ] Test sequential workflow execution
- [ ] Test parallel workflow execution (fan-out/fan-in)
- [ ] Test conditional routing (true/false branches)
- [ ] Test switch-case routing
- [ ] Test nested workflows
- [ ] Test RequestInfoExecutor pauses and resumes
- [ ] Test shared state across executors
- [ ] Test context provider integration
- [ ] Test error handling and propagation
- [ ] Test streaming event order and types
- [ ] Test checkpoint creation and restoration
- [ ] Test checkpoint compatibility validation
- [ ] Test workflow resumption from checkpoint
- [ ] Test time-travel debugging
- [ ] Test agent streaming forwarded to workflow stream
- [ ] Test multiple concurrent requests
- [ ] Test request timeout
- [ ] Test graph signature validation
- [ ] Test executor error handling
- [ ] Test workflow state machine transitions

**Minimum Coverage**: 85% (for workflow module)

### Acceptance Criteria
- [ ] All integration test scenarios passing
- [ ] Sequential, parallel, conditional workflows tested
- [ ] Checkpointing and resumption tested
- [ ] Human-in-the-loop tested
- [ ] Streaming tested
- [ ] Error scenarios tested
- [ ] Tests run in < 5 seconds
- [ ] No flaky tests
- [ ] Tests are well-documented
- [ ] README includes workflow examples
- [ ] Coverage report generated

### Example Code Pattern
```typescript
import { describe, it, expect, beforeEach } from '@jest/globals';
import { WorkflowBuilder } from '../builder';
import { AgentExecutor, FunctionExecutor, RequestInfoExecutor } from '../executors';
import { InMemoryCheckpointStorage } from '../checkpoint';
import { ChatAgent } from '../../agents';
import { MockChatClient } from '../../testing/mocks';

describe('Workflow Integration Tests', () => {
  let mockClient: MockChatClient;
  let checkpointStorage: InMemoryCheckpointStorage;

  beforeEach(() => {
    mockClient = new MockChatClient();
    checkpointStorage = new InMemoryCheckpointStorage();
  });

  describe('Sequential Workflow', () => {
    it('should execute agents in sequence', async () => {
      // Arrange
      const agent1 = new ChatAgent({
        chatClient: mockClient,
        name: 'researcher',
        instructions: 'Research the topic'
      });

      const agent2 = new ChatAgent({
        chatClient: mockClient,
        name: 'summarizer',
        instructions: 'Summarize the research'
      });

      const workflow = new WorkflowBuilder()
        .addAgent(agent1, 'research')
        .addAgent(agent2, 'summarize')
        .addEdge('research', 'summarize')
        .setEntry('research')
        .build();

      // Act
      const result = await workflow.run('AI agents');

      // Assert
      expect(result.output).toBeDefined();
      expect(mockClient.callCount).toBe(2); // Both agents called
    });
  });

  describe('Parallel Workflow', () => {
    it('should execute agents in parallel and merge results', async () => {
      // Arrange
      const agent1 = new ChatAgent({
        chatClient: mockClient,
        name: 'researcher1',
        instructions: 'Research topic 1'
      });

      const agent2 = new ChatAgent({
        chatClient: mockClient,
        name: 'researcher2',
        instructions: 'Research topic 2'
      });

      const mergeFunc = (results: any[]) => {
        return { merged: results };
      };

      const workflow = new WorkflowBuilder()
        .addAgent(agent1, 'research1')
        .addAgent(agent2, 'research2')
        .addExecutor('merge', new FunctionExecutor('merge', mergeFunc))
        .addEdge('research1', 'merge', { type: 'fan_in', from: ['research1', 'research2'] })
        .addEdge('research2', 'merge', { type: 'fan_in', from: ['research1', 'research2'] })
        .setEntry('research1') // Both start in parallel
        .build();

      // Act
      const result = await workflow.run('AI agents');

      // Assert
      expect(result.output.merged).toHaveLength(2);
    });
  });

  describe('Human-in-the-Loop Workflow', () => {
    it('should pause for user input and resume', async () => {
      // Arrange
      const agent = new ChatAgent({
        chatClient: mockClient,
        name: 'assistant',
        instructions: 'Answer questions'
      });

      const requestExecutor = new RequestInfoExecutor({
        id: 'user_input',
        name: 'Get user clarification'
      });

      const workflow = new WorkflowBuilder()
        .addAgent(agent, 'agent')
        .addExecutor('request', requestExecutor)
        .addEdge('agent', 'request')
        .setEntry('agent')
        .build();

      // Act
      const events: WorkflowEvent[] = [];
      const streamPromise = (async () => {
        for await (const event of workflow.runStream('Hello')) {
          events.push(event);

          // Simulate user responding to request
          if (event.type === 'request_info') {
            await requestExecutor.handleResponse(event.requestId, 'User response');
          }
        }
      })();

      await streamPromise;

      // Assert
      const requestEvent = events.find(e => e.type === 'request_info');
      expect(requestEvent).toBeDefined();
      expect(events[events.length - 1].type).toBe('workflow_output');
    });
  });

  describe('Checkpointing', () => {
    it('should create checkpoint and resume workflow', async () => {
      // Arrange
      const agent1 = new ChatAgent({
        chatClient: mockClient,
        name: 'step1',
        instructions: 'Step 1'
      });

      const agent2 = new ChatAgent({
        chatClient: mockClient,
        name: 'step2',
        instructions: 'Step 2'
      });

      const workflow = new WorkflowBuilder()
        .addAgent(agent1, 'step1')
        .addAgent(agent2, 'step2')
        .addEdge('step1', 'step2')
        .setEntry('step1')
        .withCheckpointing(checkpointStorage)
        .build();

      // Act - Execute and checkpoint
      const result1 = await workflow.run('Input', {
        checkpoint: true
      });

      const checkpoints = await checkpointStorage.listCheckpoints(workflow.id);
      expect(checkpoints.length).toBeGreaterThan(0);

      // Resume from checkpoint
      const checkpointId = checkpoints[0];
      const result2 = await workflow.runFromCheckpoint(checkpointId);

      // Assert
      expect(result2.output).toBeDefined();
    });
  });

  describe('Streaming', () => {
    it('should stream events in real-time', async () => {
      // Arrange
      const agent = new ChatAgent({
        chatClient: mockClient,
        name: 'assistant',
        instructions: 'Help the user'
      });

      const workflow = new WorkflowBuilder()
        .addAgent(agent, 'agent')
        .setEntry('agent')
        .build();

      // Act
      const events: WorkflowEvent[] = [];
      for await (const event of workflow.runStream('Hello')) {
        events.push(event);
      }

      // Assert
      expect(events[0].type).toBe('workflow_started');
      expect(events[events.length - 1].type).toBe('workflow_output');

      const agentEvent = events.find(e => e.type === 'agent_run');
      expect(agentEvent).toBeDefined();
    });
  });
});
```

### Related Tasks
- **Blocked by**: All Phase 4 tasks (TASK-301 through TASK-310)
- **Validates**: Complete Phase 4 implementation

---

## Implementation Notes

### Key Test Scenarios

**Sequential Execution**:
Test simplest case - agents in sequence:
```typescript
A → B → C
```

**Parallel Execution**:
Test concurrent execution with fan-out/fan-in:
```typescript
     → B →
A →      → D
     → C →
```

**Conditional Routing**:
Test branching based on predicate:
```typescript
     → B (if true)
A →
     → C (if false)
```

**Human-in-the-Loop**:
Test workflow pause and resume:
```typescript
A → [Request] → B
    (pause for user input)
```

### Common Test Pitfalls

- Always use mock chat clients for speed
- Clean up checkpoints between tests
- Use deterministic agent responses for reliability
- Test both synchronous and streaming execution
- Verify event order and types in streaming tests
- Handle async properly (await all promises)
