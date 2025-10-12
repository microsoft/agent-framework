# Context Minimization Strategies

How to write self-contained tasks that require minimal additional context for autonomous execution.

## Goal

An agent or developer should be able to:
1. Read the task file
2. Read referenced spec sections and code examples
3. Complete the task successfully

**Without needing to:**
- Search for additional context
- Infer patterns or conventions
- Ask clarifying questions
- Guess at implementation details

## Strategy 1: Self-Contained References

### Exact File Paths with Line Numbers

**Good ✅**:
```markdown
**Python Reference**: `/python/packages/core/agent_framework/_types.py:50-150`
```

**Bad ❌**:
```markdown
**Python Reference**: See the types file in the core package
```

### Why This Works
- Agent can read exactly those lines without searching
- No ambiguity about which file or section
- Clear boundary of what to read

### Spec Section References

**Good ✅**:
```markdown
**Spec Section**: 002-typescript-feature-parity.md § FR-4 (Content Types)
```

**Bad ❌**:
```markdown
**Spec Section**: See the content types section
```

## Strategy 2: Inline Code Patterns

Instead of saying "follow existing patterns," show the pattern directly:

### Example Pattern Inclusion

```markdown
### Example Code Pattern
```typescript
// Discriminated union pattern
export type Content =
  | { type: 'text'; text: string }
  | { type: 'function_call'; callId: string; name: string; arguments: string };

// Factory function pattern
export function createUserMessage(content: string | Content[]): ChatMessage {
  return {
    role: 'user',
    content: typeof content === 'string' ? { type: 'text', text: content } : content,
    timestamp: new Date()
  };
}

// Type guard pattern
export function isTextContent(content: Content): content is { type: 'text'; text: string } {
  return content.type === 'text';
}
```
\```
```

### Why This Works
- Agent sees exactly what style to use
- No need to search for similar code
- Pattern is demonstrated, not described

## Strategy 3: Explicit Standards References

Link to specific standard sections, not entire documents:

**Good ✅**:
```markdown
**Standards**: CLAUDE.md § Code Quality Standards → Prefer Attributes Over Inheritance
```

**Bad ❌**:
```markdown
**Standards**: Follow the standards in CLAUDE.md
```

### Implementation
Create anchors in standards documents:
```markdown
## Code Quality Standards

### Prefer Attributes Over Inheritance
```

Then reference: `CLAUDE.md § Prefer Attributes Over Inheritance`

## Strategy 4: Pre-Made Decisions

Don't make agents choose architectural patterns. State decisions explicitly:

### Architectural Decisions

**Good ✅**:
```markdown
**Pattern Decision**: Use discriminated unions (not class hierarchy) for message types.
This matches TypeScript idioms and provides better type safety.
```

**Bad ❌**:
```markdown
**Implementation**: Create message types using appropriate TypeScript patterns.
```

### Why This Works
- No ambiguity about approach
- Agent doesn't waste time evaluating options
- Consistency across codebase

## Strategy 5: Specified Test Cases

List exact test scenarios, not general guidance:

### Test Specification

**Good ✅**:
```markdown
### Test Requirements
- [ ] Test factory function creates user message with text content
- [ ] Test factory function creates user message with array of content
- [ ] Test type guard correctly identifies text content
- [ ] Test type guard returns false for non-text content
- [ ] Test edge case: empty string in text content
- [ ] Test edge case: undefined content field
```

**Bad ❌**:
```markdown
### Test Requirements
- Write comprehensive tests for all functionality
- Include edge cases
- Ensure good coverage
```

### Why This Works
- Agent knows exactly what tests to write
- No guessing about "comprehensive"
- Clear completion criteria

## Strategy 6: File Path Templates

Provide exact file paths to create/modify:

### File Path Specification

**Good ✅**:
```markdown
### Files to Create/Modify
- `src/core/types/chat-message.ts` - ChatMessage types and factories
- `src/core/types/__tests__/chat-message.test.ts` - Unit tests
- `src/core/types/index.ts` - Add exports for ChatMessage types
- `src/core/index.ts` - Re-export from types/index.ts
```

**Bad ❌**:
```markdown
### Files to Create/Modify
- Create the types file
- Add tests
- Update exports
```

### Why This Works
- Agent knows exact file structure
- No decisions about file naming or location
- Clear what to export and from where

## Strategy 7: Numbered Requirements

Use numbered lists with specific, actionable items:

### Implementation Requirements

**Good ✅**:
```markdown
**Core Functionality**:
1. Define `MessageRole` enum with 4 values: 'user', 'assistant', 'system', 'tool'
2. Define `Content` discriminated union with 9 types (text, function_call, etc.)
3. Define `ChatMessage` interface with role, content, name?, timestamp?, metadata?
4. Create factory function `createUserMessage(content: string | Content[]): ChatMessage`
5. Create type guard `isTextContent(content: Content): content is TextContent`
```

**Bad ❌**:
```markdown
**Core Functionality**:
- Implement message types
- Add helper functions
- Support different content types
```

### Why This Works
- Each item is atomic and testable
- Clear count of what needs to be done
- No ambiguity about requirements

## Strategy 8: Dependency Graphs

Visualize dependencies so agents understand order:

### Visual Dependencies

```markdown
### Task Dependencies

```
TASK-001 (Scaffolding)
    ↓
TASK-002 (ChatMessage) ──→ TASK-005 (Tools)
    ↓                           ↓
TASK-004 (ChatClient)      TASK-007 (BaseAgent)
    ↓                           ↓
TASK-011 (OpenAI Client)   TASK-013 (Integration)
```
\```

**Critical Path**: TASK-001 → TASK-002 → TASK-004 → TASK-011
```

### Why This Works
- Agent understands what must complete first
- Clear critical path
- Visual representation is quick to parse

## Strategy 9: Acceptance Criteria as Checkboxes

Make completion objective and verifiable:

### Checkbox Criteria

**Good ✅**:
```markdown
### Acceptance Criteria
- [ ] All 9 content types defined with 'type' discriminator
- [ ] Factory functions create correct message structure
- [ ] Type guards have correct TypeScript signature with type predicate
- [ ] Tests achieve >90% coverage
- [ ] TypeScript compiles with no errors in strict mode
- [ ] ESLint passes with no warnings
```

**Bad ❌**:
```markdown
### Acceptance Criteria
- Implementation is complete
- Code quality is high
- Tests are adequate
```

### Why This Works
- Each item is objectively verifiable
- No subjective judgment needed
- Clear when task is done

## Strategy 10: Context Budget

Explicitly state what context is needed:

### Context Declaration

```markdown
### Required Reading (30 minutes)
1. Spec section § FR-4 (10 min)
2. Python reference code (15 min)
3. Task file (5 min)

### No Additional Context Needed
- ✅ All patterns shown inline
- ✅ All decisions pre-made
- ✅ All file paths specified
```

### Why This Works
- Agent knows time investment upfront
- Confirms nothing else needs to be searched
- Sets clear boundaries

## Anti-Patterns to Avoid

### Vague References ❌
```markdown
See the implementation in the Python codebase
```

**Better**:
```markdown
`/python/packages/core/agent_framework/_agents.py:100-250` - BaseAgent implementation
```

### Implied Patterns ❌
```markdown
Follow the same pattern used elsewhere
```

**Better**:
```markdown
Use builder pattern with fluent interface (see example below)
```

### General Instructions ❌
```markdown
Write good tests with edge cases
```

**Better**:
```markdown
- Test null input throws TypeError
- Test empty array returns empty result
- Test undefined field defaults to system value
```

### Ambiguous Scope ❌
```markdown
Implement the agent system
```

**Better**:
```markdown
Implement BaseAgent abstract class with invoke() and invokeStream() methods
```

## Validation Checklist

Before publishing a task, verify:
- [ ] All file paths include line numbers or are complete
- [ ] Code patterns shown inline (not described)
- [ ] Architectural decisions stated explicitly
- [ ] Test cases listed specifically
- [ ] File paths are complete and exact
- [ ] Requirements are numbered and atomic
- [ ] Dependencies visualized or clearly listed
- [ ] Acceptance criteria are checkboxes
- [ ] No vague words: "appropriate", "good", "comprehensive", "etc."

## Context Minimization Score

Score your task:
- 1 point for each exact file reference (with line numbers)
- 1 point for each inline code pattern
- 1 point for each specific standard reference
- 1 point for each pre-made decision
- 1 point for each specific test case
- 1 point for exact file paths to create
- 1 point for numbered requirements
- 1 point for dependency visualization
- 1 point for checkbox acceptance criteria

**Target Score**: >8 out of 9 for good self-containment

## Example: Low Context Score (3/9)

```markdown
### Task: Implement Message Types

Create the message types following best practices. Write tests and documentation.

**Reference**: See Python implementation
**Files**: Create types file and tests
**Requirements**: Support different message roles and content types
**Tests**: Write comprehensive tests
```

**Score**: 3/9
- No exact file paths with line numbers
- No inline patterns
- No specific standards
- No pre-made decisions
- No specific test cases
- Vague file paths
- Non-numbered requirements
- No dependency info
- No checkbox criteria

## Example: High Context Score (9/9)

```markdown
### Task: TASK-002 ChatMessage Types

**Objective**: Implement ChatMessage discriminated union with all message roles and content types

**Context References**:
- **Spec**: 002-typescript-feature-parity.md § FR-1 (Agents and Chat Messages)
- **Python**: `/python/packages/core/agent_framework/_types.py:50-150`
- **Standards**: CLAUDE.md § Prefer Attributes Over Inheritance

**Files to Create**:
- `src/core/types/chat-message.ts` - ChatMessage types
- `src/core/types/__tests__/chat-message.test.ts` - Tests
- `src/core/types/index.ts` - Exports

**Implementation Requirements**:
1. Define `MessageRole` enum: 'user', 'assistant', 'system', 'tool'
2. Define `Content` discriminated union with 'type' discriminator
3. Create factory: `createUserMessage(content: string | Content[]): ChatMessage`

**Pattern Decision**: Use discriminated unions (not class hierarchy)

**Test Requirements**:
- [ ] Test createUserMessage with string creates { type: 'text', text: string }
- [ ] Test createUserMessage with Content[] preserves array
- [ ] Test edge case: empty string

**Acceptance Criteria**:
- [ ] All 9 content types defined
- [ ] Tests >90% coverage
- [ ] TypeScript strict mode passes

**Example Pattern**:
\```typescript
export type Content = { type: 'text'; text: string } | ...;
\```

**Dependencies**: TASK-001 (Scaffolding)
```

**Score**: 9/9 ✅
