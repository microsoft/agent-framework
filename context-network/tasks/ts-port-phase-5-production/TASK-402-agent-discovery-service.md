# Task: TASK-402 Agent Discovery Service

**Phase**: 5
**Priority**: Medium
**Estimated Effort**: 7 hours
**Dependencies**: TASK-401 (A2A Protocol Core)

### Objective
Implement agent discovery service for finding and registering agents in distributed systems.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-13 (A2A - Discovery)
- **Python Reference**: `/python/packages/a2a/agent_framework_a2a/discovery.py`
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI.A2A/Discovery/`
- **Standards**: CLAUDE.md § Python Architecture

### Files to Create/Modify
- `src/a2a/discovery/registry.ts` - Agent registry
- `src/a2a/discovery/client.ts` - Discovery client
- `src/a2a/discovery/__tests__/discovery.test.ts` - Tests
- `src/a2a/index.ts` - Exports

### Implementation Requirements

**Core Functionality**:
1. Implement `AgentRegistry` for storing agent metadata
2. Implement `DiscoveryClient` for finding agents
3. Support agent registration and deregistration
4. Support agent health checks
5. Implement query by capability/tag
6. Support TTL and automatic expiration
7. Handle registry updates and notifications
8. Support multiple discovery backends (memory, Redis, etc.)

**Test Requirements**: Unit tests for registry operations, discovery queries, TTL handling

**Acceptance Criteria**: Discovery service working, agent registration/deregistration, health checks, query by capability

### Example Code Pattern
```typescript
export class AgentRegistry {
  private agents = new Map<string, RegisteredAgent>();

  async register(agent: AgentRegistration): Promise<void> {
    this.agents.set(agent.id, {
      ...agent,
      registeredAt: new Date(),
      lastHeartbeat: new Date()
    });
  }

  async discover(query: DiscoveryQuery): Promise<AgentInfo[]> {
    return Array.from(this.agents.values())
      .filter(agent => this.matchesQuery(agent, query))
      .map(agent => agent.info);
  }

  async heartbeat(agentId: string): Promise<void> {
    const agent = this.agents.get(agentId);
    if (agent) {
      agent.lastHeartbeat = new Date();
    }
  }
}
```

### Related Tasks
- **Blocked by**: TASK-401 (A2A protocol)
- **Related**: TASK-403 (Inter-agent messaging uses discovery)
