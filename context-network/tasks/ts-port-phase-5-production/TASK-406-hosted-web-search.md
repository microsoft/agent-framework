# Task: TASK-406 Hosted Web Search Tool

**Phase**: 5
**Priority**: High
**Estimated Effort**: 5 hours
**Dependencies**: TASK-005 (Tool System)

### Objective
Implement HostedWebSearchTool for web search capabilities via hosted service providers.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-12 (Hosted Tools - Web Search)
- **Python Reference**: `/python/packages/core/agent_framework/hosted_tools.py` - HostedWebSearchTool
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI/Tools/HostedWebSearch.cs`
- **Standards**: CLAUDE.md § Python Architecture

### Files to Create/Modify
- `src/tools/hosted/web-search.ts` - HostedWebSearchTool class
- `src/tools/hosted/__tests__/web-search.test.ts` - Tests
- `src/tools/index.ts` - Exports

### Implementation Requirements

**Core Functionality**:
1. Implement `HostedWebSearchTool` class
2. Support web search queries
3. Configure user location context
4. Handle search result filtering
5. Return search results with snippets and URLs
6. Support result ranking
7. Handle rate limiting
8. Handle search errors

**Test Requirements**: Unit tests for web search, location context, result filtering, error handling

**Acceptance Criteria**: Web search working, location context supported, result filtering, error handling

### Example Code Pattern
```typescript
export class HostedWebSearchTool extends BaseTool {
  constructor(options?: {
    userLocation?: { city: string; country: string };
    description?: string;
  }) {
    super({
      name: 'web_search',
      description: options?.description ?? 'Search the web for information'
    });
    this.userLocation = options?.userLocation;
  }

  toToolDefinition(): ToolDefinition {
    return {
      type: 'web_search',
      user_location: this.userLocation
    };
  }
}
```

### Related Tasks
- **Blocked by**: TASK-005 (Tool system)
- **Related**: TASK-404 (Code interpreter), TASK-405 (File search)
