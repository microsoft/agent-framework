# Task: TASK-010 ChatMessageStore Interface

**Phase**: 1  
**Priority**: High  
**Estimated Effort**: 3 hours  
**Dependencies**: TASK-002

## Objective
Define ChatMessageStore interface for message persistence with in-memory implementation.

## Context References
- **Spec**: 002-typescript-feature-parity.md § FR-5 (Thread Management)
- **Python**: `/python/packages/core/agent_framework/_memory.py:300-400`

## Files to Create/Modify
- `src/core/storage/message-store.ts`
- `src/core/storage/in-memory-store.ts`
- `src/core/storage/__tests__/message-store.test.ts`

## Implementation Requirements
1. ChatMessageStore interface (add, get, list, clear)
2. InMemoryMessageStore implementation
3. Support for filtering/querying
4. Thread-safe operations

## Test Requirements
- CRUD operations
- Multiple threads
- Edge cases (empty, large)

**Coverage**: >85%
