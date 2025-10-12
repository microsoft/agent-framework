# Phase 2: Agent System

Implement agent protocols, base classes, and chat agents with thread management.

## Overview

**Goal**: Build the core agent system with support for both service-managed and local-managed conversation threads.

**Estimated Total Effort**: 36.5 hours (groomed into 17 focused tasks)

**Status**: 🔄 Groomed & Ready for Implementation

**📋 See**:
- [GROOMED-BACKLOG.md](./GROOMED-BACKLOG.md) - Detailed task breakdown with 17 sub-tasks
- [QUICK-START-GUIDE.md](./QUICK-START-GUIDE.md) - How to pick up and implement tasks

## Task List (Original - see GROOMED-BACKLOG.md for breakdown)

| ID | Task | Priority | Effort | Status | Assignee |
|----|------|----------|--------|--------|----------|
| [TASK-101](./TASK-101-chat-agent.md) | ChatAgent Implementation | Critical | 8h → 12h (4 subtasks) | ⬜ | - |
| [TASK-102](./TASK-102-agent-protocol-type-guards.md) | AgentProtocol Type Guards | High | 3h | ⬜ | - |
| [TASK-103](./TASK-103-agent-serialization.md) | Agent Serialization/Deserialization | High | 4h → 4.5h (2 subtasks) | ⬜ | - |
| [TASK-104](./TASK-104-service-managed-threads.md) | Service-Managed Thread Support | High | 5h → 4.5h (2 subtasks) | ⬜ | - |
| [TASK-105](./TASK-105-local-managed-threads.md) | Local-Managed Thread Support | High | 4h → (merged with 104) | ⬜ | - |
| [TASK-106](./TASK-106-lifecycle-hooks.md) | Agent Lifecycle Hooks | Medium | 4h (2 subtasks) | ⬜ | - |
| [TASK-107](./TASK-107-middleware-system.md) | Agent Middleware System | High | 6h → 5h (2 subtasks) | ⬜ | - |
| [TASK-108](./TASK-108-integration-tests.md) | Integration Tests - Phase 2 | High | 4h (2 subtasks) | ⬜ | - |

### Groomed Subtasks (17 total)

**Wave 1 - Foundation** (can run in parallel):
- TASK-101a: ChatAgent Types (2h)
- TASK-102: Type Guards (3h)
- TASK-103a: Serialization Core (3h)
- TASK-104a: Service Thread Types (1.5h)
- TASK-105a: Local Thread Store (2h)
- TASK-106a: Lifecycle Interfaces (2h)
- TASK-107a: Middleware Interfaces (2h)
- TASK-104-105: Thread Logic (3h)

**Wave 2 - ChatAgent Core** (sequential):
- TASK-101b: Basic Implementation (4h)
- TASK-101c: run() Method (2h)
- TASK-101d: runStream() Method (2h)

**Wave 3 - Advanced** (can run in parallel):
- TASK-101e: MCP Tools (2h)
- TASK-103b: Agent Serialization (1.5h)
- TASK-106b: Lifecycle Implementation (2h)
- TASK-107b: Middleware Decorators (3h)

**Wave 4 - Integration** (sequential):
- TASK-108a: Test Infrastructure (1.5h)
- TASK-108b: Integration Tests (2.5h)

## Dependency Graph (Groomed)

```
Phase 2A (Foundation) - Parallel Wave 1
├── TASK-101a (Types) ────────┐
├── TASK-102 (Type Guards) ───┤
├── TASK-106a (Lifecycle IF)  ├──┐
├── TASK-107a (Middleware IF) ├──┤
├── TASK-103a (Serialization) ┘  │
├── TASK-104a (Service Types) ───┤
└── TASK-105a (Local Types) ─────┤
                                 │
    TASK-104-105 (Thread Logic) ─┘
                ↓
Phase 2B (ChatAgent Core) - Sequential Wave 2
├── TASK-101b (Basic) ←──────────────────
├── TASK-101c (run method)
└── TASK-101d (runStream)
                ↓
Phase 2C (Advanced) - Parallel Wave 3
├── TASK-101e (MCP Tools)
├── TASK-106b (Lifecycle Impl)
├── TASK-107b (Middleware Impl)
└── TASK-103b (Agent Serialization)
                ↓
Phase 2D (Integration) - Sequential Wave 4
├── TASK-108a (Test Infrastructure)
└── TASK-108b (Integration Tests)
```

## Critical Path (Groomed)

**Wave 1**: 3h (longest parallel task: TASK-102, TASK-103a)
**Sequential**: TASK-104-105 (3h)
**Wave 2**: 8h (sequential: TASK-101b→c→d)
**Wave 3**: 3h (longest parallel task: TASK-107b)
**Wave 4**: 4h (sequential: TASK-108a→b)

**Critical Path Total**: 21 hours (with full parallelization)
**Solo Developer**: 36.5 hours (all tasks sequential)

## Parallel Work Opportunities (Updated)

**Wave 1 - 7 tasks in parallel** (3h duration):
- TASK-101a, TASK-102, TASK-103a, TASK-104a, TASK-105a, TASK-106a, TASK-107a

**Wave 2 - Sequential** (8h duration):
- TASK-101b → TASK-101c → TASK-101d

**Wave 3 - 4 tasks in parallel** (3h duration):
- TASK-101e, TASK-103b, TASK-106b, TASK-107b

**Wave 4 - Sequential** (4h duration):
- TASK-108a → TASK-108b

## Phase Completion Criteria

Before proceeding to Phase 3, verify:

### Critical Requirements
- [ ] All Critical priority tasks completed (TASK-101)
- [ ] All High priority tasks completed (TASK-102, 103, 104, 105, 107, 108)
- [ ] Test coverage >85% for all phase 2 modules
- [ ] TypeScript strict mode passes with no errors
- [ ] ESLint passes with no warnings

### Integration Tests (TASK-108)
- [ ] Can create ChatAgent with minimal config
- [ ] Can send message and get response
- [ ] Can stream responses
- [ ] Can maintain conversation history (service-managed threads)
- [ ] Can maintain conversation history (local-managed threads)
- [ ] Can apply middleware
- [ ] Can use context providers
- [ ] Can serialize/deserialize agents

### Documentation
- [ ] All public APIs have JSDoc with examples
- [ ] README examples work as documented
- [ ] Migration guide from Phase 1 to Phase 2

### Code Review
- [ ] All tasks peer reviewed
- [ ] Patterns consistent across codebase
- [ ] No security issues identified

## Related Documentation

- [TypeScript Feature Parity Specification](../../specs/002-typescript-feature-parity.md) § FR-2, FR-5, FR-6, FR-14
- [Phase 1 Tasks](../ts-port-phase-1-foundation/index.md)
- [Phase 3 Tasks](../ts-port-phase-3-tools/index.md)
- [Task Structure Template](../guides/task-structure-template.md)
- [Quality Gates](../guides/quality-gates.md)

## Phase Sign-Off

**Date**: _____________
**Reviewer**: _____________
**Status**: ⬜ Not Started / 🟦 In Progress / ✅ Completed

**Notes**:
[To be filled upon phase completion]
