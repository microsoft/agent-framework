# Task: TASK-202 MCP Tool Integration

**Phase**: 3
**Priority**: Critical
**Estimated Effort**: 8 hours
**Dependencies**: TASK-005 (Tool System), TASK-201 (Tool Execution Engine)

### Objective
Implement Model Context Protocol (MCP) tool integration, enabling agents to connect to MCP servers, discover their tools, and execute them as part of agent workflows.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-11 (MCP Integration)
- **Python Reference**: `/python/packages/core/agent_framework/_mcp.py` - MCPTool class
- **Python Reference**: `/python/packages/core/agent_framework/_agents.py:642-803` - MCP integration in ChatAgent
- **MCP Spec**: https://modelcontextprotocol.io/

### Files to Create/Modify
- `src/tools/mcp-tool.ts` - MCPTool class
- `src/tools/mcp-client.ts` - MCP client wrapper
- `src/tools/__tests__/mcp-tool.test.ts` - Unit tests

### Implementation Requirements

**MCPTool Class**:
1. Create MCPTool extending BaseTool
2. Accept MCP server connection details (stdio, SSE, or WebSocket)
3. Connect to MCP server on demand
4. List available tools from server via `tools/list` request
5. Convert MCP tool schemas to AIFunction instances
6. Store functions for later invocation
7. Support `isConnected` property
8. Implement AsyncDisposable for cleanup

**MCP Server Connection**:
9. Support stdio transport (spawn child process)
10. Support SSE transport (HTTP Server-Sent Events)
11. Support WebSocket transport
12. Handle connection errors gracefully
13. Maintain connection during agent lifetime
14. Close connection on disposal

**Tool Discovery**:
15. Call MCP `tools/list` to get available tools
16. Parse MCP tool schema (name, description, inputSchema)
17. Create AIFunction wrapper for each MCP tool
18. Map MCP parameters to Pydantic models
19. Store tool map (name → function)

**Tool Execution**:
20. Intercept calls to MCP tools
21. Convert arguments to MCP `tools/call` format
22. Send `tools/call` request to server
23. Parse response and extract result
24. Handle MCP errors and exceptions

**ChatAgent Integration**:
25. Separate MCPTool instances from regular tools
26. Connect MCP tools via AsyncExitStack
27. Resolve MCP functions before execution
28. Include MCP functions in final tool list

**TypeScript Patterns**:
- Use Symbol.asyncDispose for resource management
- Use factory pattern for different transports
- Type MCP protocol messages properly

**Code Standards**:
- 120 character line length
- JSDoc with examples
- Strict mode

### Test Requirements
- [ ] Test MCPTool creation with stdio transport
- [ ] Test MCPTool creation with SSE transport
- [ ] Test MCPTool connection to MCP server
- [ ] Test tool discovery via `tools/list`
- [ ] Test AIFunction generation from MCP schemas
- [ ] Test tool execution via `tools/call`
- [ ] Test error handling for connection failures
- [ ] Test error handling for execution failures
- [ ] Test AsyncDisposable cleanup
- [ ] Test integration with ChatAgent
- [ ] Test multiple MCP servers simultaneously

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] MCPTool connects to MCP servers
- [ ] Tools discovered and converted to AIFunctions
- [ ] Tool execution works via MCP protocol
- [ ] Multiple transports supported (stdio, SSE, WS)
- [ ] Resource cleanup via AsyncDisposable
- [ ] Tests pass with >85% coverage
- [ ] TypeScript strict mode, ESLint passes

### Example Code Pattern
```typescript
export class MCPTool extends BaseTool implements AsyncDisposable {
  private client?: MCPClient;
  private _functions: AIFunction[] = [];

  constructor(options: MCPToolOptions) {
    super({
      name: options.name,
      description: options.description || 'MCP Server Tools'
    });
    this.transport = options.transport;
    this.serverConfig = options.config;
  }

  get isConnected(): boolean {
    return this.client?.isConnected ?? false;
  }

  get functions(): AIFunction[] {
    return this._functions;
  }

  async connect(): Promise<void> {
    if (this.isConnected) return;

    this.client = await MCPClient.connect(this.transport, this.serverConfig);
    await this.discoverTools();
  }

  private async discoverTools(): Promise<void> {
    const toolsResponse = await this.client!.request('tools/list', {});

    for (const mcpTool of toolsResponse.tools) {
      const aiFunction = this.createAIFunctionFromMCPTool(mcpTool);
      this._functions.push(aiFunction);
    }
  }

  private createAIFunctionFromMCPTool(mcpTool: MCPToolSchema): AIFunction {
    // Convert MCP inputSchema to Pydantic model
    const inputModel = createModelFromSchema(mcpTool.inputSchema);

    return new AIFunction({
      name: mcpTool.name,
      description: mcpTool.description,
      inputModel,
      func: async (args) => {
        const result = await this.client!.request('tools/call', {
          name: mcpTool.name,
          arguments: args
        });
        return result.content;
      }
    });
  }

  async [Symbol.asyncDispose](): Promise<void> {
    if (this.client) {
      await this.client.close();
      this.client = undefined;
    }
  }
}

// In ChatAgent
async run(...) {
  // Separate MCP tools
  this.localMcpTools = tools.filter(t => t instanceof MCPTool);

  // Connect MCP tools
  for (const mcpTool of this.localMcpTools) {
    if (!mcpTool.isConnected) {
      await this.asyncExitStack.enterAsyncContext(mcpTool);
      await mcpTool.connect();
    }
    finalTools.push(...mcpTool.functions);
  }
}
```

### Related Tasks
- **Blocked by**: TASK-005 (Tool System), TASK-201 (Tool Execution)
- **Related**: TASK-101 (ChatAgent integrates MCP tools)
