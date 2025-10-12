---
description: Identify next implementable tasks, assign to parallel subagents in worktrees, and create PRs
---

You are coordinating the TypeScript port implementation using multiple parallel subagents.

## Your Role

Analyze the task dependency graph, identify tasks ready for implementation, spawn subagents to work on them in parallel worktrees, and manage the PR workflow.

## Process

### 1. Analyze Current State

First, check what phase tasks exist and their status:

```bash
# Check all phase task files
find context-network/tasks/ts-port-phase-* -name "TASK-*.md" -type f | sort

# Check git status to see what's already in progress
git branch -a | grep -E "task-|TASK-"

# Check for existing PRs
gh pr list --state open
```

### 2. Identify Ready Tasks

A task is "ready" if:
- All dependencies (listed in "Blocked by") are completed
- Not currently being worked on (no worktree branch exists)
- Not already merged
- Has priority Critical or High

Read the relevant phase index.md file to understand:
- The dependency graph
- The critical path
- Parallel work opportunities

### 3. Select Tasks for Parallel Implementation

Choose 2-4 tasks that:
- Are independent (can be worked on in parallel)
- Form a logical group from "Parallel Work Opportunities"
- Maximize parallel progress without conflicts

### 4. For Each Selected Task

Create a worktree and spawn a subagent:

```bash
# Create worktree branch
TASK_ID="TASK-XXX"
BRANCH_NAME="task-${TASK_ID,,}-implementation"
git worktree add -b "$BRANCH_NAME" "../worktrees/$BRANCH_NAME" context-dev

# In the worktree, spawn task-implementer agent
cd "../worktrees/$BRANCH_NAME"

# Use Task tool to spawn implementation agent
```

For each task, use the Task tool with subagent_type "task-implementer" and provide this prompt:

```
Implement {{TASK_ID}} from the TypeScript port project.

Task file: context-network/tasks/{{PHASE_DIR}}/{{TASK_ID}}-{{task-name}}.md

Requirements:
1. Read the task file completely to understand requirements
2. Read referenced Python/C# implementations for guidance
3. Implement all files listed in "Files to Create/Modify"
4. Write comprehensive tests meeting coverage requirements
5. Ensure all acceptance criteria are met
6. Follow TypeScript patterns specified in task
7. Add JSDoc documentation to all public APIs
8. Update index.ts exports

When complete:
1. Run tests: npm test (or appropriate test command)
2. Run linting: npm run lint
3. Commit with message: "feat: implement {{TASK_ID}} - {{Task Title}}"
4. Push to origin: git push -u origin {{BRANCH_NAME}}
5. Create PR with gh CLI:
   - Repo: jwynia/ms-agent-framework
   - Base: context-dev
   - Title: "{{TASK_ID}}: {{Task Title}}"
   - Body: Include task summary, implementation notes, testing done
   - Labels: typescript-port, {{phase-label}}

Important: Do not merge the PR. The coordinator will review and merge.
```

### 5. Monitor Progress

As agents work:
- Check for completion signals
- Monitor for errors or blockers
- Be ready to assist if an agent gets stuck

### 6. Coordinate PR Reviews

Once PRs are created:
```bash
# List PRs created
gh pr list --repo jwynia/ms-agent-framework --label typescript-port --state open

# Review each PR
gh pr view {{PR_NUMBER}} --repo jwynia/ms-agent-framework
gh pr checks {{PR_NUMBER}} --repo jwynia/ms-agent-framework

# If all checks pass and implementation looks good, merge
gh pr merge {{PR_NUMBER}} --repo jwynia/ms-agent-framework --squash --delete-branch
```

### 7. Update Task Tracking

After successful merges:
- Update the phase index.md to mark tasks as completed
- Identify the next batch of ready tasks
- Repeat the process

## Example Execution

Let's say Phase 1 is starting fresh:

**Step 1**: Identify ready tasks from phase-1-foundation/index.md

Critical path: TASK-001 → TASK-002 → TASK-004 → TASK-007 → TASK-013

After TASK-001 completes, parallel opportunities:
- Group A: TASK-003, TASK-006, TASK-009, TASK-010

**Step 2**: Start with TASK-001 (must go first)

```bash
git worktree add -b task-001-implementation ../worktrees/task-001-implementation context-dev
cd ../worktrees/task-001-implementation
```

Spawn agent with Task tool for TASK-001.

**Step 3**: Once TASK-001 is merged, spawn 4 parallel agents for Group A:
- Agent 1: TASK-003 (AgentInfo types)
- Agent 2: TASK-006 (Error hierarchy)
- Agent 3: TASK-009 (Logger)
- Agent 4: TASK-010 (MessageStore)

All work in separate worktrees simultaneously.

## Task Implementer Prompt Template

When spawning each task-implementer agent, provide this detailed prompt:

```
You are implementing {{TASK_ID}}: {{TASK_TITLE}} for the Microsoft Agent Framework TypeScript port.

**Task File**: context-network/tasks/{{PHASE_DIR}}/{{TASK_FILE}}

**Your Mission**:
1. Read and understand the complete task specification
2. Review Python reference: {{PYTHON_REF}} (if specified)
3. Review .NET reference: {{DOTNET_REF}} (if specified)
4. Implement all required files with full functionality
5. Write comprehensive tests (>85% coverage target)
6. Ensure all acceptance criteria are met
7. Create PR for review

**Implementation Steps**:

1. **Setup** (DO THIS FIRST):
   ```bash
   # Verify you're in the correct worktree
   pwd
   git branch --show-current

   # Install dependencies if needed
   npm install
   ```

2. **Read Task Specification**:
   Read the task file completely. Pay attention to:
   - Implementation Requirements (numbered list)
   - TypeScript Patterns section
   - Example Code Pattern
   - Test Requirements
   - Acceptance Criteria

3. **Study Reference Implementations**:
   If Python or .NET references are provided, read those files to understand:
   - API design
   - Edge cases handled
   - Error handling patterns
   - Test coverage

4. **Implement Core Functionality**:
   Create all files listed in "Files to Create/Modify":
   - Follow the Example Code Pattern
   - Use TypeScript patterns specified
   - Include comprehensive JSDoc
   - Handle all edge cases
   - Follow coding standards (120 char lines, strict mode, no `any`)

5. **Write Tests**:
   Create test files with:
   - All test cases from "Test Requirements"
   - Edge case coverage
   - Error handling tests
   - Aim for >85% coverage

6. **Update Exports**:
   Add exports to index.ts files as specified

7. **Verify Quality**:
   ```bash
   # Run tests
   npm test

   # Run linting
   npm run lint

   # Run type checking
   npx tsc --noEmit

   # Check coverage
   npm run test:coverage
   ```

8. **Commit and Push**:
   ```bash
   git add .
   git commit -m "feat: implement {{TASK_ID}} - {{TASK_TITLE}}

   - Implemented all required functionality
   - Added comprehensive tests (>85% coverage)
   - Updated exports and documentation
   - All acceptance criteria met

   Refs: {{TASK_ID}}"

   git push -u origin {{BRANCH_NAME}}
   ```

9. **Create Pull Request**:
   ```bash
   gh pr create \
     --repo jwynia/ms-agent-framework \
     --base context-dev \
     --title "{{TASK_ID}}: {{TASK_TITLE}}" \
     --body "## Summary

   Implements {{TASK_ID}} as specified in context-network/tasks/{{PHASE_DIR}}/{{TASK_FILE}}

   ## Implementation

   - [List key implementation details]
   - [Highlight any design decisions]
   - [Note any deviations from spec with justification]

   ## Testing

   - Coverage: [X]%
   - All test requirements met
   - Edge cases covered

   ## Acceptance Criteria

   - [ ] All implementation requirements completed
   - [ ] Tests pass with >85% coverage
   - [ ] TypeScript strict mode passes
   - [ ] ESLint passes with no warnings
   - [ ] JSDoc complete for all public APIs
   - [ ] Exports added to index.ts

   ## References

   - Task Spec: context-network/tasks/{{PHASE_DIR}}/{{TASK_FILE}}
   - Python Ref: {{PYTHON_REF}}
   - .NET Ref: {{DOTNET_REF}}" \
     --label "typescript-port,{{phase-label}},automated-implementation"
   ```

10. **Report Completion**:
    Output a summary:
    ```
    ✅ {{TASK_ID}} Implementation Complete

    Branch: {{BRANCH_NAME}}
    PR: #{{PR_NUMBER}}
    Files Created: [list]
    Tests Added: [count]
    Coverage: [X]%

    Ready for review and merge.
    ```

**Important Notes**:
- Do NOT merge the PR yourself
- If you encounter blockers, report them clearly
- If dependencies are missing, note what's needed
- Follow the task specification exactly
- When in doubt, reference Python/C# implementations
```

## Output Format

After spawning all agents, provide a summary:

```
🚀 Parallel Task Implementation Started

Phase: {{PHASE_NUMBER}}
Tasks in Progress: {{COUNT}}

{{TASK_ID_1}}: {{TITLE_1}}
  Branch: {{BRANCH_1}}
  Worktree: ../worktrees/{{BRANCH_1}}
  Agent: Spawned
  Status: In Progress

{{TASK_ID_2}}: {{TITLE_2}}
  Branch: {{BRANCH_2}}
  Worktree: ../worktrees/{{BRANCH_2}}
  Agent: Spawned
  Status: In Progress

[... more tasks ...]

Next Steps:
1. Monitor agent progress
2. Review PRs as they're created
3. Merge approved PRs
4. Identify next batch of ready tasks

Run this command again after current batch completes.
```

## Error Handling

If an agent encounters issues:
1. Check the worktree for error messages
2. Review task dependencies - are they actually complete?
3. Check if the task spec is clear enough
4. Provide additional guidance to the agent
5. If needed, reassign the task to a new agent

## Notes

- Each agent works in isolation in its own worktree
- No conflicts between parallel agents
- PRs are reviewed before merging to ensure quality
- Failed tasks can be retried without affecting others
- The coordinator (you) maintains the overall project state
