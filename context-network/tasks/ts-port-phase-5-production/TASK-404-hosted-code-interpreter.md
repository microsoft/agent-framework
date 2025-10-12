# Task: TASK-404 Hosted Code Interpreter Tool

**Phase**: 5
**Priority**: High
**Estimated Effort**: 6 hours
**Dependencies**: TASK-005 (Tool System)

### Objective
Implement HostedCodeInterpreterTool for executing code in sandboxed environments via hosted service providers.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-12 (Hosted Tools - Code Interpreter)
- **Python Reference**: `/python/packages/core/agent_framework/hosted_tools.py` - HostedCodeInterpreterTool
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI/Tools/HostedCodeInterpreter.cs`
- **Standards**: CLAUDE.md § Python Architecture

### Files to Create/Modify
- `src/tools/hosted/code-interpreter.ts` - HostedCodeInterpreterTool class
- `src/tools/hosted/__tests__/code-interpreter.test.ts` - Tests
- `src/tools/index.ts` - Exports

### Implementation Requirements

**Core Functionality**:
1. Implement `HostedCodeInterpreterTool` class
2. Support code execution in sandboxed environment
3. Handle file inputs for code execution
4. Support multiple programming languages (Python, JavaScript)
5. Capture execution output (stdout, stderr)
6. Handle execution errors and timeouts
7. Support session management
8. Return execution results with file outputs

**Test Requirements**: Unit tests for code execution, file inputs, error handling, timeouts

**Acceptance Criteria**: Code interpreter working, multiple languages supported, file I/O, error handling

### Example Code Pattern
```typescript
export class HostedCodeInterpreterTool extends BaseTool {
  constructor(options?: {
    inputs?: Content[];
    description?: string;
    language?: 'python' | 'javascript';
  }) {
    super({
      name: 'code_interpreter',
      description: options?.description ?? 'Execute code in sandboxed environment'
    });
    this.inputs = options?.inputs ?? [];
    this.language = options?.language ?? 'python';
  }

  toToolDefinition(): ToolDefinition {
    return {
      type: 'code_interpreter',
      inputs: this.inputs
    };
  }
}
```

### Related Tasks
- **Blocked by**: TASK-005 (Tool system)
- **Related**: TASK-405 (File search tool), TASK-406 (Web search tool)
