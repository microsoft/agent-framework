# Task: TASK-012 ContextProvider Abstract Class

**Phase**: 1  
**Priority**: High  
**Estimated Effort**: 5 hours  
**Dependencies**: TASK-002, TASK-005

## Objective
Implement ContextProvider abstract class with lifecycle hooks and AggregateContextProvider.

## Context References
- **Spec**: 002-typescript-feature-parity.md § FR-9 (Memory & Context)
- **Python**: `/python/packages/core/agent_framework/_memory.py:1-200`

## Files to Create/Modify
- `src/core/context/context-provider.ts`
- `src/core/context/aggregate-provider.ts`
- `src/core/context/__tests__/context-provider.test.ts`

## Implementation Requirements
1. ContextProvider abstract class
2. threadCreated(), invoking(), invoked() lifecycle methods
3. AIContext interface
4. AggregateContextProvider for combining providers
5. Base memory context provider example

## Test Requirements
- Lifecycle method calls
- Context merging
- Aggregate provider
- Multiple providers

**Coverage**: >85%
