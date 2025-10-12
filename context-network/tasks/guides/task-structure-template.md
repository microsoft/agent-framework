# Task Structure Template

This template defines the standard format for all task files. Copy this structure when creating new tasks.

---

## Task: [TASK-XXX] [Short Title]

**Phase**: [1-5]
**Priority**: [Critical/High/Medium/Low]
**Estimated Effort**: [2-8 hours]
**Dependencies**: [List of TASK-XXX IDs, or "None"]

### Objective
[One clear sentence describing what this task accomplishes]

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § [section name/number]
- **Python Reference**: `/python/packages/core/agent_framework/[file].py` lines [X-Y]
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI/[file].cs` lines [X-Y]
- **Standards**: CLAUDE.md § [relevant section]

### Files to Create/Modify
- `src/core/[filename].ts` - [Purpose]
- `src/core/__tests__/[filename].test.ts` - [Test coverage]
- `src/core/index.ts` - [Export additions]

### Implementation Requirements

**Core Functionality**:
1. [Specific requirement 1]
2. [Specific requirement 2]
3. [Specific requirement 3]

**TypeScript Patterns**:
- [Pattern 1: e.g., "Use discriminated unions for content types"]
- [Pattern 2: e.g., "Export all types from index.ts with JSDoc"]
- [Pattern 3: e.g., "Follow async-first design patterns"]

**Code Standards**:
- 120 character line length
- JSDoc documentation for all public APIs
- Strict TypeScript mode enabled
- No `any` types without explicit justification

### Test Requirements
- [Specific test case 1]
- [Specific test case 2]
- [Edge case tests: null, undefined, empty inputs]
- [Error handling tests]

**Minimum Coverage**: [80-90%]

### Acceptance Criteria
- [ ] All implementation requirements met
- [ ] Tests pass with >[X]% coverage
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings
- [ ] JSDoc complete for all public APIs
- [ ] Exports added to index.ts
- [ ] Code reviewed against Python/.NET reference implementations

### Example Code Pattern
```typescript
// Show minimal example of expected pattern
// This helps the executor understand the style and approach
```

### Related Tasks
- **Blocks**: [TASK-XXX] - [Why this must complete first]
- **Blocked by**: [TASK-XXX] - [What must complete before this]
- **Related**: [TASK-XXX] - [Related work for context]

---

## Template Notes

### Objective
- **Purpose**: One-sentence summary for quick understanding
- **Guidelines**: Start with action verb, state concrete outcome
- **Example**: "Implement ChatMessage discriminated union with all message roles and content types"

### Context References
- **Purpose**: Direct pointers to source material, no searching required
- **Guidelines**: Include file paths with line numbers, specific section markers
- **Example**: `/python/packages/core/agent_framework/_types.py:50-150`

### Implementation Requirements
- **Purpose**: Numbered, specific requirements that define "done"
- **Guidelines**: Break into Core Functionality, TypeScript Patterns, Code Standards
- **Avoid**: Vague requirements like "implement well" or "make it good"

### Test Requirements
- **Purpose**: Explicit test cases so executor knows exactly what to test
- **Guidelines**: List specific scenarios, edge cases, error conditions
- **Include**: Minimum coverage percentage

### Acceptance Criteria
- **Purpose**: Checkbox list for objective pass/fail verification
- **Guidelines**: All items must be verifiable without subjective judgment
- **Example**: "Tests pass with >80% coverage" (objective) not "Code is clean" (subjective)

### Example Code Pattern
- **Purpose**: Show the expected code style so executor doesn't need to infer
- **Guidelines**: Keep minimal, focus on pattern not full implementation
- **Include**: TypeScript-specific idioms (discriminated unions, type guards, etc.)

### Related Tasks
- **Purpose**: Make dependencies crystal clear
- **Guidelines**:
  - "Blocks" = other tasks waiting on this one
  - "Blocked by" = this task can't start until others complete
  - "Related" = provides context but not a hard dependency
