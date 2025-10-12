# Task: TASK-407 Hosted MCP Tool with Approval

**Phase**: 5
**Priority**: High
**Estimated Effort**: 7 hours
**Dependencies**: TASK-005 (Tool System), TASK-202 (MCP Integration)

### Objective
Implement HostedMCPTool for connecting to hosted MCP services with configurable approval flows.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-12 (Hosted Tools - MCP)
- **Python Reference**: `/python/packages/core/agent_framework/hosted_tools.py` - HostedMCPTool
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI/Tools/HostedMCP.cs`
- **Standards**: CLAUDE.md § Python Architecture

### Files to Create/Modify
- `src/tools/hosted/mcp-tool.ts` - HostedMCPTool class
- `src/tools/hosted/__tests__/mcp-tool.test.ts` - Tests
- `src/tools/index.ts` - Exports

### Implementation Requirements

**Core Functionality**:
1. Implement `HostedMCPTool` class
2. Support MCP service URL configuration
3. Implement approval modes: `always_require`, `never_require`, specific per-tool
4. Support authentication headers
5. Implement tool filtering via `allowedTools`
6. Handle MCP tool discovery
7. Execute MCP tools with approval checks
8. Support streaming responses

**Test Requirements**: Unit tests for MCP connection, approval flows, tool filtering, authentication

**Acceptance Criteria**: MCP tool working, all approval modes supported, authentication, tool filtering

### Example Code Pattern
```typescript
export class HostedMCPTool extends BaseTool {
  public readonly url: string;
  public readonly approvalMode?: 'always_require' | 'never_require' | HostedMCPSpecificApproval;
  public readonly allowedTools?: Set<string>;

  constructor(options: {
    name: string;
    url: string;
    description?: string;
    approvalMode?: 'always_require' | 'never_require' | HostedMCPSpecificApproval;
    allowedTools?: string[];
    headers?: Record<string, string>;
  }) {
    super({
      name: options.name,
      description: options.description ?? `MCP tool: ${options.name}`
    });
    this.url = options.url;
    this.approvalMode = options.approvalMode;
    this.allowedTools = options.allowedTools ? new Set(options.allowedTools) : undefined;
  }

  toToolDefinition(): ToolDefinition {
    return {
      type: 'mcp',
      url: this.url,
      approval_mode: this.approvalMode,
      allowed_tools: this.allowedTools ? Array.from(this.allowedTools) : undefined
    };
  }
}
```

### Related Tasks
- **Blocked by**: TASK-005 (Tool system)
- **Blocked by**: TASK-202 (MCP integration)
- **Related**: TASK-404-406 (Other hosted tools)
