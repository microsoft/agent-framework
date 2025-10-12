# Phase 2 Quick Start Guide

**Ready to implement?** Use this guide to pick up groomed tasks and start coding.

---

## TL;DR - Start Here

### For Parallel Team (4+ developers)
1. **Pick a Wave 1 task** from the list below (all can run in parallel)
2. Create a worktree: `git worktree add -b task-<ID> ../worktrees/task-<ID> context-dev`
3. Implement following the task card in GROOMED-BACKLOG.md
4. Create PR when done

### For Solo Developer
1. Start with **TASK-101a** (Types - foundation for everything)
2. Then do Wave 1 tasks in any order
3. Proceed to ChatAgent core (sequential)

---

## Wave 1: Foundation Tasks (START HERE)

All these can be done **in parallel** - pick any one to start:

| Task | Size | What You'll Build | Files to Create |
|------|------|-------------------|-----------------|
| **TASK-101a** | 2h | ChatAgent types & interfaces | `src/agents/chat-agent-types.ts` |
| **TASK-102** | 3h | Agent Protocol type guards | `src/agents/protocol.ts` |
| **TASK-106a** | 2h | Lifecycle hook interfaces | `src/core/lifecycle.ts` |
| **TASK-107a** | 2h | Middleware interfaces | `src/middleware/types.ts` |
| **TASK-103a** | 3h | Serialization core (generic) | `src/core/serialization.ts` |
| **TASK-104a** | 1.5h | Service thread types | `src/threads/service-thread-types.ts` |
| **TASK-105a** | 2h | Local thread + message store | `src/storage/message-store.ts` |

**After Wave 1**, one person does **TASK-104-105** (Thread Logic, 3h)

---

## Wave 2: ChatAgent Core (Sequential, 1 developer)

**Prerequisites**: Wave 1 complete

| Task | Size | What You'll Build |
|------|------|-------------------|
| **TASK-101b** | 4h | ChatAgent class, constructor, validation |
| **TASK-101c** | 2h | `run()` method, thread preparation |
| **TASK-101d** | 2h | `runStream()` method, async iteration |

---

## Wave 3: Advanced Features (Parallel after Wave 2)

**Prerequisites**: Wave 2 complete

Pick any one to start:

| Task | Size | What You'll Build |
|------|------|-------------------|
| **TASK-101e** | 2h | MCP tool integration |
| **TASK-106b** | 2h | Lifecycle hook implementation |
| **TASK-107b** | 3h | Middleware decorator system |
| **TASK-103b** | 1.5h | Agent serialization |

---

## Wave 4: Integration (Sequential)

**Prerequisites**: All Wave 3 complete

| Task | Size | What You'll Build |
|------|------|-------------------|
| **TASK-108a** | 1.5h | Test infrastructure (mocks, helpers) |
| **TASK-108b** | 2.5h | Full integration tests |

---

## How to Pick Up a Task

### 1. Check Dependencies
```bash
# See what's blocking your task
cat context-network/tasks/ts-port-phase-2-agents/GROOMED-BACKLOG.md | grep "TASK-<ID>"
```

### 2. Create Worktree
```bash
cd /Users/jwynia/Projects/github/ms-agent-framework
git worktree add -b task-<ID>-implementation ../worktrees/task-<ID>-implementation context-dev
cd ../worktrees/task-<ID>-implementation
```

### 3. Review Task Details
- Open `GROOMED-BACKLOG.md`
- Find your task card (detailed specs at bottom)
- Review deliverables and acceptance criteria

### 4. Implement
- Follow TypeScript patterns from Phase 1
- Write tests alongside code
- Keep strict mode enabled
- Add JSDoc to all public APIs

### 5. Test & Commit
```bash
# Run tests
npm test

# Lint
npm run lint

# Type check
npx tsc --noEmit

# Commit
git add .
git commit -m "feat: implement TASK-<ID> - <description>"
git push -u origin task-<ID>-implementation
```

### 6. Create PR
```bash
gh pr create \
  --title "TASK-<ID>: <Title>" \
  --body "See GROOMED-BACKLOG.md for task details" \
  --base context-dev \
  --label "typescript-port,phase-2-agents"
```

---

## Task Status Tracking

### Wave 1 (Foundation)
- [ ] TASK-101a - ChatAgent Types
- [ ] TASK-102 - Agent Protocol Type Guards
- [ ] TASK-106a - Lifecycle Interfaces
- [ ] TASK-107a - Middleware Interfaces
- [ ] TASK-103a - Serialization Core
- [ ] TASK-104a - Service Thread Types
- [ ] TASK-105a - Local Thread Store
- [ ] TASK-104-105 - Thread Management Logic

### Wave 2 (ChatAgent Core)
- [ ] TASK-101b - ChatAgent Basic
- [ ] TASK-101c - run() Method
- [ ] TASK-101d - runStream() Method

### Wave 3 (Advanced)
- [ ] TASK-101e - MCP Tools
- [ ] TASK-106b - Lifecycle Implementation
- [ ] TASK-107b - Middleware Decorators
- [ ] TASK-103b - Agent Serialization

### Wave 4 (Integration)
- [ ] TASK-108a - Test Infrastructure
- [ ] TASK-108b - Integration Tests

---

## Reference Implementations

When implementing, reference these Python files:

| Task | Python Reference |
|------|------------------|
| TASK-101* | `/python/packages/core/agent_framework/_agents.py:471-762` |
| TASK-102 | `/python/packages/core/agent_framework/_agents.py:57-203` |
| TASK-103* | `/python/packages/core/agent_framework/_serialization.py` |
| TASK-104* | `/python/packages/core/agent_framework/_threads.py:1-300` |
| TASK-105* | `/python/packages/core/agent_framework/_threads.py:200-400` |
| TASK-106* | `/python/packages/core/agent_framework/_memory.py:50-150` |
| TASK-107* | `/python/packages/core/agent_framework/_middleware.py` |

---

## Common Patterns

### Type Definition Pattern
```typescript
/**
 * Options for creating a ChatAgent.
 *
 * @example
 * ```typescript
 * const options: ChatAgentOptions = {
 *   chatClient: myClient,
 *   name: 'assistant'
 * };
 * ```
 */
export interface ChatAgentOptions {
  // ...
}
```

### Implementation Pattern
```typescript
export class ChatAgent extends BaseAgent {
  constructor(options: ChatAgentOptions) {
    // Validate
    if (options.conflictingA && options.conflictingB) {
      throw new AgentInitializationError('Cannot use both A and B');
    }

    super({...});
    // Initialize
  }
}
```

### Test Pattern
```typescript
describe('TASK-XXX: Feature Name', () => {
  it('should handle happy path', async () => {
    // Arrange
    const instance = new MyClass();

    // Act
    const result = await instance.method();

    // Assert
    expect(result).toBeDefined();
  });

  it('should handle error case', async () => {
    // ...
  });
});
```

---

## Getting Help

### Blocked on Dependencies?
- Check if prerequisite PRs are merged
- Coordinate with team on Slack/Discord
- Can implement with mocked dependencies if needed

### Technical Questions?
- Review Python implementation for guidance
- Check Phase 1 implementations for patterns
- Consult CLAUDE.md for coding standards

### Ready to Start?
1. Pick a Wave 1 task from the table above
2. Create your worktree
3. Start coding!

---

## Progress Dashboard

**Total Tasks**: 17
**Completed**: 0
**In Progress**: 0
**Ready**: 7 (Wave 1)

**Estimated Completion**:
- With 4 parallel workers: ~21 hours (5 days)
- With 2 parallel workers: ~28 hours (7 days)
- Solo developer: ~36 hours (9 days)

---

**Questions?** See GROOMED-BACKLOG.md for full details or ask in the team channel.

**Ready to code?** Pick a Wave 1 task and create your worktree! 🚀
