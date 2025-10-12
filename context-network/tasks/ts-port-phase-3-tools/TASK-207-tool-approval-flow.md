# Task: TASK-207 Tool Approval Flow

**Phase**: 3
**Priority**: High
**Estimated Effort**: 5 hours
**Dependencies**: TASK-005 (Tool System), TASK-201 (Tool Execution Engine)

### Objective
Implement tool approval flow that allows human-in-the-loop approval before executing sensitive tools, preventing unauthorized actions and enabling safety guardrails.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-7 (Tools) → Approval Mode
- **Python Reference**: `/python/packages/core/agent_framework/_tools.py:966-978` - Approval check logic
- **Python Reference**: `/python/packages/core/agent_framework/_types.py` - FunctionApprovalRequestContent, FunctionApprovalResponseContent
- **Standards**: CLAUDE.md § Python Architecture → Tool Approval

### Files to Create/Modify
- `src/tools/approval-flow.ts` - Approval request/response handling
- `src/types/function-approval.ts` - Approval content types
- `src/tools/__tests__/approval-flow.test.ts` - Unit tests

### Implementation Requirements

**Approval Content Types**:
1. Define `FunctionApprovalRequestContent` extending BaseContent
2. Properties: `id`, `functionCall` (reference to original call)
3. Define `FunctionApprovalResponseContent` extending BaseContent
4. Properties: `id`, `functionCall`, `approved` (boolean)

**AIFunction Approval Mode**:
5. Add `approvalMode` property to AIFunction
6. Values: `"always_require"`, `"never_require"`
7. Default to `"never_require"`
8. Check approval mode before execution

**Execution Flow with Approval**:
9. In `autoInvokeFunction()`, check if tool requires approval
10. If yes, return FunctionApprovalRequestContent instead of executing
11. Add approval requests to assistant message contents
12. Halt execution and return response to user
13. User provides approval (approved/rejected) via new message
14. On next run, detect approval responses in messages
15. Execute approved tools, skip rejected tools
16. For rejected tools, create FunctionResultContent with error

**Multi-Tool Approval**:
17. If ANY tool in batch requires approval, request approval for ALL
18. Simplifies UX: single approval prompt for multiple tools
19. Execute all approved tools concurrently
20. Handle partial approvals correctly

**TypeScript Patterns**:
- Use discriminated union for approval content types
- Use boolean flag for approval status
- Type approval requests/responses strictly

**Code Standards**:
- 120 character line length
- JSDoc with examples
- Strict mode

### Test Requirements
- [ ] Test AIFunction with `approvalMode: "always_require"`
- [ ] Test FunctionApprovalRequestContent created for approval-required tools
- [ ] Test execution halts when approval needed
- [ ] Test FunctionApprovalResponseContent with `approved: true`
- [ ] Test FunctionApprovalResponseContent with `approved: false`
- [ ] Test approved tool executes correctly
- [ ] Test rejected tool returns error
- [ ] Test batch approval when one tool needs approval
- [ ] Test partial approval (some approved, some rejected)
- [ ] Test multiple approval iterations

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] Approval request content types defined
- [ ] AIFunction supports approval mode
- [ ] Approval flow halts execution correctly
- [ ] Approved tools execute, rejected tools skip
- [ ] Multi-tool approval works correctly
- [ ] Tests pass with >85% coverage
- [ ] TypeScript strict mode, ESLint passes
- [ ] JSDoc complete with examples

### Example Code Pattern
```typescript
export interface FunctionApprovalRequestContent extends BaseContent {
  type: 'function_approval_request';
  id: string;
  functionCall: FunctionCallContent;
}

export interface FunctionApprovalResponseContent extends BaseContent {
  type: 'function_approval_response';
  id: string;
  functionCall: FunctionCallContent;
  approved: boolean;
}

// In AIFunction
export class AIFunction<ArgsT, ReturnT> extends BaseTool {
  approvalMode: 'always_require' | 'never_require';

  constructor(options: AIFunctionOptions<ArgsT, ReturnT>) {
    super(options);
    this.approvalMode = options.approvalMode ?? 'never_require';
  }
}

// In autoInvokeFunction
export async function autoInvokeFunction(
  functionCall: FunctionCallContent,
  toolMap: Map<string, AIFunction<any, any>>
): Promise<FunctionResultContent | FunctionApprovalRequestContent> {
  const tool = toolMap.get(functionCall.name);

  if (!tool) {
    throw new Error(`Function '${functionCall.name}' not found`);
  }

  // Check if approval required
  if (tool.approvalMode === 'always_require') {
    return {
      type: 'function_approval_request',
      id: functionCall.callId,
      functionCall
    };
  }

  // Execute normally
  try {
    const result = await tool.invoke(functionCall.arguments);
    return {
      type: 'function_result',
      callId: functionCall.callId,
      result
    };
  } catch (error) {
    return {
      type: 'function_result',
      callId: functionCall.callId,
      exception: error as Error
    };
  }
}

// In executeFunctionCalls
export async function executeFunctionCalls(
  functionCalls: FunctionCallContent[],
  tools: ToolProtocol[]
): Promise<(FunctionResultContent | FunctionApprovalRequestContent)[]> {
  const toolMap = buildToolMap(tools);

  // Check if any tool requires approval
  const approvalNeeded = functionCalls.some(fc => {
    const tool = toolMap.get(fc.name);
    return tool?.approvalMode === 'always_require';
  });

  if (approvalNeeded) {
    // Return approval requests for all tools
    return functionCalls.map(fc => ({
      type: 'function_approval_request',
      id: fc.callId,
      functionCall: fc
    }));
  }

  // Execute all tools
  return await Promise.all(
    functionCalls.map(fc => autoInvokeFunction(fc, toolMap))
  );
}

// In chat client decorator (handle approval responses)
async function handleApprovalResponses(messages: ChatMessage[]) {
  const approvalResponses: FunctionApprovalResponseContent[] = [];

  for (const msg of messages) {
    for (const content of msg.contents) {
      if (content.type === 'function_approval_response') {
        approvalResponses.push(content);
      }
    }
  }

  if (approvalResponses.length > 0) {
    // Execute approved tools
    const approvedCalls = approvalResponses
      .filter(r => r.approved)
      .map(r => r.functionCall);

    const rejectedCalls = approvalResponses
      .filter(r => !r.approved)
      .map(r => r.functionCall);

    // Execute approved
    const approvedResults = await executeFunctionCalls(approvedCalls, tools);

    // Create error results for rejected
    const rejectedResults = rejectedCalls.map(fc => ({
      type: 'function_result',
      callId: fc.callId,
      result: 'Error: Tool call invocation was rejected by user.'
    }));

    return [...approvedResults, ...rejectedResults];
  }

  return [];
}

// Usage
const dangerousTool = new AIFunction({
  name: 'delete_database',
  description: 'Delete entire database',
  approvalMode: 'always_require',  // Requires approval
  func: async () => {
    // Dangerous operation
  },
  inputModel: DeleteDatabaseArgs
});

const agent = new ChatAgent({
  chatClient: client,
  tools: [dangerousTool]
});

// First run - approval requested
const response1 = await agent.run('Delete the database');
// response1.messages contains FunctionApprovalRequestContent

// User approves
const approval = new ChatMessage({
  role: 'user',
  contents: [{
    type: 'function_approval_response',
    id: approvalRequest.id,
    functionCall: approvalRequest.functionCall,
    approved: true  // or false to reject
  }]
});

// Second run - tool executes
const response2 = await agent.run([approval]);
```

### Related Tasks
- **Blocked by**: TASK-005 (Tool System), TASK-201 (Tool Execution)
- **Related**: TASK-208 (Tool Middleware can also control approval)
