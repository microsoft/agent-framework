# Task: TASK-008 AgentThread & ThreadState

**Phase**: 1  
**Priority**: High  
**Estimated Effort**: 5 hours  
**Dependencies**: TASK-002, TASK-010

## Objective
Implement AgentThread class supporting both service-managed and local-managed conversation threads with serialization.

## Context References
- **Spec**: 002-typescript-feature-parity.md § FR-5 (Thread Management)
- **Python**: `/python/packages/core/agent_framework/_agents.py:500-700`

## Files to Create/Modify
- `src/core/agents/agent-thread.ts`
- `src/core/agents/__tests__/agent-thread.test.ts`

## Implementation Requirements
1. AgentThread class with serviceThreadId OR messageStore
2. ThreadState interface for serialization
3. serialize()/deserialize() methods
4. Support for both thread modes

## Test Requirements
- Service-managed thread creation
- Local-managed thread creation
- Serialization/deserialization
- Mixed mode prevention

**Coverage**: >85%
