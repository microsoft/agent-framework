# Task Granularity Guidelines

How to size tasks appropriately for autonomous agent or developer execution.

## The 2-8 Hour Rule

Each task should be completable in a single focused work session:
- **2-3 hours**: Simple types, interfaces, utilities
- **4-6 hours**: Core classes with moderate complexity
- **6-8 hours**: Complex systems (workflow engine, checkpoint storage)

**If a task exceeds 8 hours**, split it into sub-tasks.
**If a task takes less than 2 hours**, consider merging with related work.

## Single Responsibility Principle

Each task should implement **one coherent feature or component**.

### Good Examples ✅
- "Implement ChatMessage discriminated union with type guards"
- "Create AISettings builder with validation"
- "Implement InMemoryCheckpointStorage with CRUD operations"

### Too Broad ❌
- "Implement all core types"
- "Build the entire workflow system"
- "Create all chat client implementations"

### Too Narrow ❌
- "Add text property to ChatMessage"
- "Write one test for AISettings"
- "Export types from index.ts"

## Self-Contained Context

Task descriptions should include everything needed to complete the work without searching or asking questions.

### Required Context
- ✅ Exact spec section references with § markers
- ✅ Reference implementation file paths with line numbers
- ✅ Explicit code patterns and examples
- ✅ Specific test cases to implement
- ✅ Standards references from CLAUDE.md

### Agent Should NOT Need To
- ❌ Search for related code
- ❌ Infer architectural patterns
- ❌ Ask clarifying questions about structure
- ❌ Guess at naming conventions
- ❌ Figure out what tests to write

## Testable Completion

Every task must have objective pass/fail criteria.

### Objective Criteria ✅
- "Tests pass with >80% coverage"
- "TypeScript compiles with no errors in strict mode"
- "ESLint passes with no warnings"
- "All 9 content types defined with discriminators"

### Subjective Criteria ❌
- "Code is clean and maintainable"
- "Implementation is efficient"
- "Tests are comprehensive"
- "Documentation is good"

## Dependency Clarity

Explicitly state what must exist before this task can start.

### Types of Dependencies

**Hard Dependencies (Blocks Execution)**:
```markdown
**Blocked by**: TASK-001 (Project scaffolding must exist)
```

**Soft Dependencies (Provides Context)**:
```markdown
**Related**: TASK-003 (Similar pattern used for AgentInfo)
```

**Forward Dependencies (What This Enables)**:
```markdown
**Blocks**: TASK-007 (BaseAgent needs these types)
```

## When to Split a Task

Split when:
1. **Estimated time exceeds 8 hours**
2. **Task has multiple independent components** (e.g., "Implement A and B" → split into "Implement A" and "Implement B")
3. **Different skill sets required** (e.g., backend + frontend)
4. **Useful checkpoint needed** (e.g., implement core, then add advanced features)

### Splitting Strategies

**By Component**:
- Original: "Implement ChatMessage types and content types"
- Split into:
  - TASK-002A: ChatMessage interface and roles
  - TASK-002B: Content discriminated union
  - TASK-002C: Type guards and utilities

**By Complexity Layer**:
- Original: "Implement Workflow system"
- Split into:
  - TASK-301: Workflow graph data structure
  - TASK-302: Basic executor
  - TASK-303: Event system
  - TASK-304: Checkpoint storage

**By Phase**:
- Original: "Implement feature X completely"
- Split into:
  - TASK-XXX: Core functionality
  - TASK-YYY: Advanced features
  - TASK-ZZZ: Optimizations

## When to Merge Tasks

Merge when:
1. **Both tasks under 2 hours each**
2. **Tasks are tightly coupled** (one doesn't make sense without the other)
3. **Same files modified** and no intermediate checkpoint needed
4. **Sequential dependency** with no other tasks between them

### Merging Strategies

**Tightly Coupled Features**:
- Original: "Define AgentInfo interface" + "Define AISettings interface"
- Merged: TASK-003: Core Type Definitions - AgentInfo & AISettings

**Utility Functions**:
- Original: "Create isTextContent guard" + "Create isFunctionCall guard" + ...
- Merged: Include all type guards in TASK-002: ChatMessage types

## Task Size Examples

### 2-Hour Task: Simple Interface
```markdown
### Task: TASK-010 ChatMessageStore Interface

**Objective**: Define ChatMessageStore interface for message persistence

**Implementation**:
- 4 methods: add, get, list, clear
- TypeScript interface with JSDoc
- No implementation (interface only)
```

### 4-Hour Task: Moderate Class
```markdown
### Task: TASK-006 Error Hierarchy

**Objective**: Implement AgentFrameworkError base class and 7 specific error types

**Implementation**:
- Base error class with cause chaining
- 7 specific error classes extending base
- Constructor patterns for all
- Tests for error creation and inheritance
```

### 6-Hour Task: Complex System
```markdown
### Task: TASK-007 BaseAgent Class

**Objective**: Implement BaseAgent abstract class with lifecycle hooks and streaming

**Implementation**:
- Abstract class with 5 core methods
- Streaming support with AsyncIterable
- Integration with ChatClientProtocol
- Context provider lifecycle
- Comprehensive tests for all paths
```

### 8-Hour Task: Complete Feature
```markdown
### Task: TASK-301 Workflow Graph Data Structure

**Objective**: Implement workflow graph with executors, edges, and validation

**Implementation**:
- Graph data structure (nodes, edges)
- Executor abstraction
- Edge conditions and routing
- Graph connectivity validation
- Type compatibility checking
- Comprehensive test suite
```

## Checklist for Task Granularity

Before finalizing a task, verify:
- [ ] Estimated time is 2-8 hours
- [ ] Single, clear objective stated
- [ ] All context provided inline (no searching needed)
- [ ] Specific, testable acceptance criteria
- [ ] Dependencies explicitly listed
- [ ] Not coupled with other tasks (can complete independently)
- [ ] Clear checkpoint/milestone when complete

## Red Flags

Watch out for these signs of poor granularity:

**Too Large**:
- 🚩 "Implement X, Y, and Z systems"
- 🚩 Task spans multiple phases
- 🚩 More than 3 major components
- 🚩 Estimate exceeds 8 hours

**Too Small**:
- 🚩 "Add one property to interface"
- 🚩 Task is just exporting from index
- 🚩 Single function with no tests
- 🚩 Estimate under 1 hour

**Poorly Defined**:
- 🚩 Vague objective: "Improve performance"
- 🚩 Missing context references
- 🚩 No specific acceptance criteria
- 🚩 Subjective completion: "make it good"
