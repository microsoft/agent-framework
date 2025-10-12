# Task: TASK-403 Inter-Agent Messaging

**Phase**: 5
**Priority**: High
**Estimated Effort**: 6 hours
**Dependencies**: TASK-401 (A2A Protocol), TASK-402 (Discovery)

### Objective
Implement inter-agent messaging patterns including direct messaging, publish-subscribe, and request-response.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-13 (A2A - Messaging)
- **Python Reference**: `/python/packages/a2a/agent_framework_a2a/messaging.py`
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI.A2A/Messaging/`
- **Standards**: CLAUDE.md § Python Architecture

### Files to Create/Modify
- `src/a2a/messaging/patterns.ts` - Messaging patterns
- `src/a2a/messaging/pubsub.ts` - Publish-subscribe
- `src/a2a/messaging/__tests__/messaging.test.ts` - Tests
- `src/a2a/index.ts` - Exports

### Implementation Requirements

**Core Functionality**:
1. Implement direct agent-to-agent messaging
2. Implement publish-subscribe pattern
3. Implement request-response pattern
4. Support message routing
5. Handle message delivery guarantees
6. Support message queuing
7. Implement retry logic
8. Support message acknowledgment

**Test Requirements**: Unit tests for all messaging patterns, delivery guarantees, retry logic

**Acceptance Criteria**: All messaging patterns working, reliable delivery, retry logic, acknowledgments

### Example Code Pattern
```typescript
export class InterAgentMessaging {
  async sendMessage(
    from: string,
    to: string,
    content: any
  ): Promise<void> {
    const message: A2AMessage = {
      messageId: generateId(),
      sourceAgentId: from,
      targetAgentId: to,
      content
    };

    await this.client.callAgent({
      targetAgentId: to,
      content,
      sourceAgentId: from
    });
  }

  async publish(topic: string, content: any): Promise<void> {
    const subscribers = await this.discovery.findSubscribers(topic);
    await Promise.all(
      subscribers.map(sub =>
        this.sendMessage(this.agentId, sub.id, content)
      )
    );
  }
}
```

### Related Tasks
- **Blocked by**: TASK-401 (A2A protocol)
- **Blocked by**: TASK-402 (Discovery for routing)
