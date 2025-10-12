# Quality Gates

Phase completion criteria and quality standards that must be met before proceeding to the next phase.

## Phase Completion Checklist

Before marking a phase as complete and proceeding to the next phase, verify all items:

### Critical Requirements
- [ ] All **Critical** priority tasks completed
- [ ] All **High** priority tasks completed
- [ ] Medium/Low priority tasks completed OR explicitly deferred with justification
- [ ] Test coverage >80% for all phase packages
- [ ] TypeScript strict mode passes with no errors
- [ ] ESLint passes with no warnings
- [ ] All exports available from package entry points

### Quality Standards
- [ ] JSDoc documentation complete for all public APIs
- [ ] Integration tests pass for phase functionality
- [ ] No `any` types without explicit justification comments
- [ ] Code reviewed by at least one other person
- [ ] All acceptance criteria met for completed tasks

### Phase-Specific Gates
- [ ] Phase-specific integration tests pass (see below)
- [ ] Performance benchmarks meet targets (if applicable)
- [ ] Breaking changes documented (if any)

## Per-Task Quality Standards

Every task must meet these standards before being marked complete:

### Code Quality
- **Line Length**: Max 120 characters
- **Formatting**: Prettier formatted
- **Linting**: ESLint passes with no warnings
- **Type Safety**: Strict TypeScript mode, no errors
- **No Any**: `any` types only with explicit justification

### Documentation
- **JSDoc**: All public APIs documented
- **Examples**: At least one `@example` in JSDoc for major features
- **Inline Comments**: Complex logic explained
- **README Updates**: If creating new package/module

### Testing
- **Coverage**: >80% line coverage (>90% for critical paths)
- **Unit Tests**: All public methods tested
- **Edge Cases**: Null, undefined, empty inputs tested
- **Error Cases**: Error handling paths tested
- **Integration**: Integration tests for external interactions

### Code Review
- **Self-Review**: Executor reviews own code against acceptance criteria
- **Peer Review**: Another developer/agent reviews code
- **Standards Check**: Verified against CLAUDE.md standards
- **Reference Check**: Compared to Python/.NET reference implementations

## Phase-Specific Integration Tests

Each phase has specific integration tests that must pass:

### Phase 1: Core Foundation
```typescript
// Must be able to:
- Create ChatMessage objects of all types
- Instantiate chat client with protocol
- Create agent with minimal config
- Add tools to agent
- Store and retrieve messages
- Log events
```

**Integration Test File**: `src/core/__tests__/integration/phase-1.test.ts`

### Phase 2: Agent System
```typescript
// Must be able to:
- Create ChatAgent with all options
- Send message and get response
- Stream responses
- Maintain conversation history
- Handle service-managed threads
- Handle local-managed threads
- Apply middleware
```

**Integration Test File**: `src/agents/__tests__/integration/phase-2.test.ts`

### Phase 3: Tools & Context
```typescript
// Must be able to:
- Register tools with agent
- Execute tool calls from LLM
- Handle MCP tool invocations
- Apply context providers
- Aggregate multiple context providers
- Handle tool approval flow
```

**Integration Test File**: `src/tools/__tests__/integration/phase-3.test.ts`

### Phase 4: Workflows
```typescript
// Must be able to:
- Create workflow graph
- Execute workflow with multiple agents
- Stream workflow events
- Save and restore checkpoints
- Handle human-in-the-loop
- Route conditionally between executors
```

**Integration Test File**: `src/workflows/__tests__/integration/phase-4.test.ts`

### Phase 5: Advanced Features
```typescript
// Must be able to:
- Discover agents via A2A
- Send messages between agents
- Use hosted tools (code interpreter, file search, web search, MCP)
- Track with OpenTelemetry
```

**Integration Test File**: `src/advanced/__tests__/integration/phase-5.test.ts`

## Coverage Requirements

### Overall Coverage Targets
- **Line Coverage**: >80%
- **Branch Coverage**: >75%
- **Function Coverage**: >85%

### Critical Path Coverage
Core functionality must have higher coverage:
- **ChatMessage types**: >90%
- **Agent execution**: >85%
- **Tool execution**: >85%
- **Workflow engine**: >85%

### Allowed Lower Coverage
Some areas can have lower coverage with justification:
- **Error edge cases**: May be difficult to trigger
- **Provider-specific code**: When mocked in tests
- **Dev utilities**: Non-production code

## Performance Benchmarks

### Phase 1-2: Agent Response Time
- Single message: <100ms overhead (excluding LLM call)
- With tools: <50ms per tool call overhead
- Message serialization: <10ms per message

### Phase 3: Context Provider
- Context loading: <50ms per provider
- Context aggregation: <100ms for 5 providers

### Phase 4: Workflows
- Graph validation: <100ms for 20-node graph
- Checkpoint save: <200ms for typical workflow state
- Checkpoint restore: <150ms

### Phase 5: A2A
- Agent discovery: <500ms
- Inter-agent message: <100ms overhead

## Breaking Change Policy

### Allowed in Early Phases (1-2)
- API changes are acceptable as we stabilize design
- Document all changes in phase README

### Restricted in Later Phases (3-5)
- Minimize breaking changes
- Provide migration path if breaking change needed
- Deprecate before removing

## Review Process

### Self-Review Checklist
Before requesting review:
- [ ] All acceptance criteria met
- [ ] Tests pass locally
- [ ] Coverage meets minimum
- [ ] Linting passes
- [ ] Type checking passes
- [ ] Code compared against reference implementations
- [ ] JSDoc complete

### Peer Review Focus
Reviewer should verify:
- [ ] Code matches specification
- [ ] Patterns consistent with existing code
- [ ] Edge cases handled
- [ ] Tests are meaningful (not just coverage padding)
- [ ] Documentation clear
- [ ] No security issues (injection, XSS, etc.)

## Failure Handling

### When Quality Gates Fail

**If coverage <80%**:
1. Identify untested paths
2. Add tests for critical paths first
3. Document why some paths remain untested (if valid)

**If type checking fails**:
1. Fix type errors (don't use `any` as quick fix)
2. Add proper type definitions
3. Use type assertions only when absolutely necessary with comment explaining why

**If integration tests fail**:
1. Debug the specific failing scenario
2. Fix implementation or test as appropriate
3. Re-run full test suite

**If review finds issues**:
1. Address all feedback
2. Re-submit for review
3. Don't proceed to next task until approved

## Phase Sign-Off

Each phase requires sign-off before proceeding:

### Required Approvals
- [ ] Lead developer/architect review
- [ ] All quality gates passed
- [ ] Phase integration tests pass
- [ ] Documentation updated

### Sign-Off Template
```markdown
## Phase [X] Sign-Off

**Date**: YYYY-MM-DD
**Reviewer**: [Name]

**Quality Gates**:
- Coverage: [X]%
- Type Safety: ✅ Pass
- Linting: ✅ Pass
- Integration Tests: ✅ Pass

**Deferred Items**:
- [TASK-XXX]: [Reason for deferral]

**Notes**:
[Any important notes about the phase completion]

**Approved**: ✅ / ❌
```

## Continuous Quality

### During Development
- Run tests after each change
- Run linter on save (IDE integration)
- Type check continuously (IDE integration)
- Run coverage locally before pushing

### Before Commit
- All tests pass
- Linting clean
- Type checking clean
- Coverage checked

### CI/CD Pipeline
- Automated test runs
- Coverage reporting
- Type checking in strict mode
- Linting enforcement
- Integration test runs

## Quality Metrics Dashboard

Track these metrics throughout implementation:

```markdown
| Phase | Coverage | Type Errors | Lint Warnings | Test Failures | Status |
|-------|----------|-------------|---------------|---------------|--------|
| 1     | 85%      | 0           | 0             | 0             | ✅     |
| 2     | 78%      | 3           | 2             | 1             | 🟨     |
| 3     | -        | -           | -             | -             | ⬜     |
| 4     | -        | -           | -             | -             | ⬜     |
| 5     | -        | -           | -             | -             | ⬜     |
```

Legend:
- ✅ Meets all quality gates
- 🟨 In progress / has minor issues
- ⬜ Not started
- ❌ Failing quality gates
