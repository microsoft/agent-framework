# Phase 2 Groomed Backlog - Agent System

**Status**: Ready for Implementation
**Date**: 2025-10-12
**Objective**: Break down Phase 2 tasks into properly-sized, parallelizable work items

---

## Summary

Phase 2 has been analyzed and broken down into smaller, more manageable tasks. Original 8 tasks (38 hours) have been reorganized into **17 focused work items** averaging 2-3 hours each, enabling better parallelization and progress tracking.

### Key Findings

1. **TASK-101 (ChatAgent) is too large** - 8 hours, blocks most other work
2. **Strong dependencies** - 5 tasks depend on TASK-101 completing
3. **Hidden complexity** - Thread management logic embedded in multiple tasks
4. **Opportunity for parallelization** - Many foundational pieces can be built independently

---

## Breakdown Strategy

### Phase 2A: Foundation (No dependencies on ChatAgent)
These can start immediately:

1. **TASK-101a: ChatAgent Types & Interfaces** (2h)
   - Extract from TASK-101
   - `ChatAgentOptions`, `ChatRunOptions` interfaces
   - `AgentRunResponse`, `AgentRunResponseUpdate` classes
   - No implementation, just contracts
   - **Dependencies**: Phase 1 complete
   - **Enables**: All other Phase 2A tasks

2. **TASK-102: AgentProtocol Type Guards** (3h)
   - Complete as-is
   - Can work in parallel with types
   - **Dependencies**: TASK-101a (types only)

3. **TASK-106a: ContextProvider Lifecycle Interface** (2h)
   - Extract interface definition from TASK-106
   - `invoking()`, `invoked()`, `threadCreated()` signatures
   - **Dependencies**: Phase 1 complete

4. **TASK-107a: Middleware Interfaces** (2h)
   - Extract from TASK-107
   - `Middleware`, `AgentContext`, `FunctionContext` interfaces
   - No decorator implementation yet
   - **Dependencies**: TASK-101a

5. **TASK-103a: Serialization Core** (3h)
   - Extract from TASK-103
   - `SerializationProtocol`, `SerializationMixin`
   - Generic implementation (not agent-specific)
   - **Dependencies**: None (pure utility)

### Phase 2B: Thread Management (Independent of ChatAgent)
Can work in parallel with Phase 2A:

6. **TASK-104a: Service Thread Types** (1.5h)
   - Extract from TASK-104
   - Thread configuration types
   - Validation logic for mutually exclusive options
   - **Dependencies**: TASK-008 (AgentThread from Phase 1)

7. **TASK-105a: Local Thread Types & Store** (2h)
   - Extract from TASK-105
   - `ChatMessageStore` interface
   - `InMemoryMessageStore` implementation
   - **Dependencies**: TASK-010 (MessageStore from Phase 1)

8. **TASK-104-105: Thread Management Logic** (3h)
   - Combine remaining parts of TASK-104 and TASK-105
   - Thread type determination
   - `updateThreadWithConversationId()`
   - **Dependencies**: TASK-104a, TASK-105a

### Phase 2C: ChatAgent Core (Critical Path)
Must complete before Phase 2D:

9. **TASK-101b: ChatAgent Basic Implementation** (4h)
   - Core ChatAgent class
   - Constructor, basic validation
   - Message normalization
   - **Dependencies**: TASK-101a, TASK-104-105
   - **Delivers**: Working ChatAgent (no streaming, no MCP, no middleware)

10. **TASK-101c: ChatAgent run() Method** (2h)
    - Implement `run()` method
    - Thread preparation
    - Context provider integration
    - **Dependencies**: TASK-101b, TASK-106a

11. **TASK-101d: ChatAgent runStream() Method** (2h)
    - Implement `runStream()` method
    - Async iteration
    - Stream handling
    - **Dependencies**: TASK-101c

### Phase 2D: Advanced Features (Parallel after ChatAgent Core)
Can parallelize these 4 work streams:

12. **TASK-101e: MCP Tool Integration** (2h)
    - AsyncExitStack pattern
    - MCP tool connection/disconnection
    - Function resolution
    - **Dependencies**: TASK-101c

13. **TASK-106b: Lifecycle Hook Implementation** (2h)
    - Implement lifecycle calls in ChatAgent
    - Error handling for hooks
    - **Dependencies**: TASK-101c, TASK-106a

14. **TASK-107b: Middleware Decorator Implementation** (3h)
    - `useAgentMiddleware()` decorator
    - Apply to ChatAgent methods
    - Middleware chain execution
    - **Dependencies**: TASK-101c, TASK-107a

15. **TASK-103b: Agent Serialization Implementation** (1.5h)
    - Apply serialization to BaseAgent and ChatAgent
    - Set up INJECTABLE, DEFAULT_EXCLUDE
    - Dependency injection for deserialization
    - **Dependencies**: TASK-103a, TASK-101b

### Phase 2E: Integration & Quality
Final tasks that depend on everything:

16. **TASK-108a: Unit Test Infrastructure** (1.5h)
    - MockChatClient
    - TestMessageStore
    - Test helpers
    - **Dependencies**: TASK-101b

17. **TASK-108b: Phase 2 Integration Tests** (2.5h)
    - All integration scenarios
    - End-to-end validation
    - **Dependencies**: All Phase 2A-2D tasks complete

---

## Dependency Graph

```
Phase 2A (Foundation) - Parallel Group 1
├── TASK-101a (Types) ────────┐
├── TASK-102 (Type Guards) ───┤
├── TASK-106a (Lifecycle IF)  ├──┐
├── TASK-107a (Middleware IF) ├──┤
└── TASK-103a (Serialization) ┘  │
                                  │
Phase 2B (Threads) - Parallel Group 2  │
├── TASK-104a (Service Types) ───┐    │
├── TASK-105a (Local Types) ─────┤    │
└── TASK-104-105 (Thread Logic) ─┴──┐ │
                                     │ │
Phase 2C (ChatAgent Core) - Sequential  │
├── TASK-101b (Basic) ←──────────────┴─┘
├── TASK-101c (run method)
└── TASK-101d (runStream)
    ↓
Phase 2D (Advanced) - Parallel Group 3
├── TASK-101e (MCP Tools)
├── TASK-106b (Lifecycle Impl)
├── TASK-107b (Middleware Impl)
└── TASK-103b (Agent Serialization)
    ↓
Phase 2E (Integration) - Sequential
├── TASK-108a (Test Infrastructure)
└── TASK-108b (Integration Tests)
```

---

## Parallel Work Opportunities

### Wave 1: Foundation + Threads (7 tasks in parallel)
**Duration**: 3 hours (longest task)

- Stream 1: TASK-101a (2h) → Types foundation
- Stream 2: TASK-102 (3h) → Type guards ← **Critical path (longest)**
- Stream 3: TASK-106a (2h) → Lifecycle interfaces
- Stream 4: TASK-107a (2h) → Middleware interfaces
- Stream 5: TASK-103a (3h) → Serialization core
- Stream 6: TASK-104a (1.5h) → Service thread types
- Stream 7: TASK-105a (2h) → Local thread types

**Then**: TASK-104-105 (3h) - Thread logic (depends on 104a, 105a)

**Total Wave 1**: 6 hours (3h parallel + 3h sequential)

### Wave 2: ChatAgent Core (3 tasks sequential)
**Duration**: 8 hours

- TASK-101b: Basic ChatAgent (4h)
- TASK-101c: run() method (2h)
- TASK-101d: runStream() method (2h)

**Total Wave 2**: 8 hours

### Wave 3: Advanced Features (4 tasks in parallel)
**Duration**: 3 hours (longest task)

- Stream 1: TASK-101e (2h) → MCP tools
- Stream 2: TASK-106b (2h) → Lifecycle impl
- Stream 3: TASK-107b (3h) → Middleware impl ← **Critical path**
- Stream 4: TASK-103b (1.5h) → Agent serialization

**Total Wave 3**: 3 hours (parallel)

### Wave 4: Integration (2 tasks sequential)
**Duration**: 4 hours

- TASK-108a: Test infrastructure (1.5h)
- TASK-108b: Integration tests (2.5h)

**Total Wave 4**: 4 hours

---

## Time Estimation

### Original Plan
- 8 tasks, 38 hours total
- Sequential: 38 hours
- Critical path: ~20 hours (with some parallelization)

### Groomed Plan
- 17 tasks, 36.5 hours total (more granular = better estimates)
- **With full parallelization: 21 hours** (6 + 8 + 3 + 4)
- **With 2 parallel workers: ~28 hours**
- **With 4 parallel workers: ~21 hours**

**Time savings**: 47% reduction with 4 workers (38h → 21h)

---

## Risk Assessment

### High Risk
- **TASK-101b/c/d (ChatAgent Core)**: 8 hours on critical path, no parallelization possible
  - Mitigation: Ensure all dependencies (types, threads) are rock solid first

### Medium Risk
- **TASK-104-105 (Thread Logic)**: Complex state machine logic
  - Mitigation: Extensive unit tests, reference Python implementation closely

- **TASK-107b (Middleware)**: TypeScript decorators can be tricky
  - Mitigation: Start with simple function wrappers, add decorators later

### Low Risk
- **Type/Interface tasks**: Straightforward, well-specified
- **Test infrastructure**: Standard mocking patterns

---

## Implementation Order Recommendation

### For Maximum Parallelization (4+ developers)

**Week 1 - Day 1-2** (6 hours):
- All Wave 1 tasks in parallel (7 agents/developers)
- Then TASK-104-105 (1 developer)

**Week 1 - Day 3** (8 hours):
- Wave 2 sequential (1 developer, critical path)
- Others: documentation, code review prep

**Week 1 - Day 4** (3 hours):
- Wave 3 in parallel (4 agents/developers)

**Week 1 - Day 5** (4 hours):
- Wave 4 sequential (1 developer)
- Others: final reviews, documentation

**Total**: 5 days with team of 4-7

### For Small Team (1-2 developers)

**Week 1**:
- Day 1: TASK-101a, TASK-104a, TASK-105a (5.5h)
- Day 2: TASK-104-105, TASK-102 (6h)
- Day 3: TASK-103a, TASK-106a, TASK-107a (7h)
- Day 4-5: TASK-101b/c/d (8h)

**Week 2**:
- Day 1: TASK-101e, TASK-106b, TASK-107b (7h)
- Day 2: TASK-103b, TASK-108a (3h)
- Day 3: TASK-108b (2.5h)

**Total**: ~9 working days for 1 developer

---

## Task Size Distribution

After grooming:

- **< 2 hours**: 5 tasks (29%)
- **2-3 hours**: 9 tasks (53%)  ← **Ideal size**
- **3-4 hours**: 2 tasks (12%)
- **> 4 hours**: 1 task (6%) - TASK-101b

**Improvement**: 82% of tasks are now 2-3 hours (ideal sprint task size)

---

## Next Steps

1. ✅ Review and approve this grooming
2. Create individual task files for new sub-tasks (101a, 101b, etc.)
3. Update Phase 2 index.md with new task structure
4. Assign tasks to parallel work streams
5. Begin Wave 1 implementation

---

## Questions for Product Owner

1. **Priority**: Should we complete ChatAgent basic (101b) before advanced features, or can we deliver a minimal MVP sooner?

2. **Parallelization**: How many parallel work streams can we support? (Determines implementation timeline)

3. **Testing**: Should integration tests (108) be done after each wave or only at the end?

4. **Scope**: Can we defer MCP tool integration (101e) to Phase 3 if time is tight?

---

## Appendix: Detailed Task Cards

### TASK-101a: ChatAgent Types & Interfaces
**Size**: 2h | **Priority**: Critical | **Dependencies**: Phase 1

**Deliverables**:
- [ ] `ChatAgentOptions` interface
- [ ] `ChatRunOptions` interface
- [ ] `AgentRunResponse` class with `.text` getter
- [ ] `AgentRunResponseUpdate` class
- [ ] `ToolChoice` type
- [ ] Export from `src/agents/chat-agent-types.ts`

**Acceptance Criteria**:
- All interfaces compile with strict mode
- JSDoc complete with examples
- No implementation code (interfaces/types only)

---

### TASK-101b: ChatAgent Basic Implementation
**Size**: 4h | **Priority**: Critical | **Dependencies**: 101a, 104-105

**Deliverables**:
- [ ] ChatAgent class extending BaseAgent
- [ ] Constructor with validation
- [ ] `normalizeMessages()` helper
- [ ] `getNewThread()` override
- [ ] Basic error handling

**Acceptance Criteria**:
- Can instantiate ChatAgent with chat client
- Validates conflicting options (conversationId + messageStoreFactory)
- Creates threads correctly
- 100% test coverage for covered methods

---

### TASK-101c: ChatAgent run() Method
**Size**: 2h | **Priority**: Critical | **Dependencies**: 101b, 106a

**Deliverables**:
- [ ] `run()` method implementation
- [ ] `prepareThreadAndMessages()` helper
- [ ] Context provider integration
- [ ] Thread notification

**Acceptance Criteria**:
- Returns AgentRunResponse
- Handles string, ChatMessage, array inputs
- Context provider lifecycle called
- Thread updated after execution

---

### TASK-101d: ChatAgent runStream() Method
**Size**: 2h | **Priority**: Critical | **Dependencies**: 101c

**Deliverables**:
- [ ] `runStream()` method implementation
- [ ] AsyncIterable<AgentRunResponseUpdate>
- [ ] Stream aggregation logic
- [ ] Thread notification after completion

**Acceptance Criteria**:
- Yields AgentRunResponseUpdate objects
- Final update has `isFinal: true`
- Thread notified after stream completes
- Works with async for-await loops

---

### TASK-101e: MCP Tool Integration
**Size**: 2h | **Priority**: High | **Dependencies**: 101c

**Deliverables**:
- [ ] AsyncExitStack implementation or usage
- [ ] MCP tool connection logic
- [ ] Function resolution from MCP servers
- [ ] Cleanup on agent disposal

**Acceptance Criteria**:
- MCP tools connect before first use
- Functions resolved and available
- AsyncExitStack closes all resources
- Symbol.asyncDispose implemented

---

### TASK-104-105: Thread Management Logic
**Size**: 3h | **Priority**: High | **Dependencies**: 104a, 105a

**Deliverables**:
- [ ] Thread type determination logic
- [ ] `updateThreadWithConversationId()` method
- [ ] Service-managed thread flow
- [ ] Local-managed thread flow
- [ ] Undetermined thread handling

**Acceptance Criteria**:
- Thread type determined after first run
- Service-managed when conversation ID returned
- Local-managed when no conversation ID and has factory
- Error when service thread gets no ID
- Tests cover all state transitions

---

*[Additional task cards follow same format...]*
