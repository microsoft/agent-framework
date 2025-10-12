# Task: TASK-405 Hosted File Search Tool

**Phase**: 5
**Priority**: High
**Estimated Effort**: 5 hours
**Dependencies**: TASK-005 (Tool System)

### Objective
Implement HostedFileSearchTool for vector-based search through uploaded files via hosted service providers.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-12 (Hosted Tools - File Search)
- **Python Reference**: `/python/packages/core/agent_framework/hosted_tools.py` - HostedFileSearchTool
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI/Tools/HostedFileSearch.cs`
- **Standards**: CLAUDE.md § Python Architecture

### Files to Create/Modify
- `src/tools/hosted/file-search.ts` - HostedFileSearchTool class
- `src/tools/hosted/__tests__/file-search.test.ts` - Tests
- `src/tools/index.ts` - Exports

### Implementation Requirements

**Core Functionality**:
1. Implement `HostedFileSearchTool` class
2. Support vector store-based file search
3. Configure max results
4. Support multiple vector store inputs
5. Handle file upload and indexing
6. Return search results with relevance scores
7. Support result filtering and ranking
8. Handle search errors

**Test Requirements**: Unit tests for file search, vector stores, result ranking, error handling

**Acceptance Criteria**: File search working, vector stores supported, configurable results, error handling

### Example Code Pattern
```typescript
export class HostedFileSearchTool extends BaseTool {
  constructor(options?: {
    inputs?: Content[];
    maxResults?: number;
    description?: string;
  }) {
    super({
      name: 'file_search',
      description: options?.description ?? 'Search through uploaded files'
    });
    this.inputs = options?.inputs ?? [];
    this.maxResults = options?.maxResults ?? 10;
  }

  toToolDefinition(): ToolDefinition {
    return {
      type: 'file_search',
      max_num_results: this.maxResults,
      inputs: this.inputs
    };
  }
}
```

### Related Tasks
- **Blocked by**: TASK-005 (Tool system)
- **Related**: TASK-404 (Code interpreter), TASK-406 (Web search)
