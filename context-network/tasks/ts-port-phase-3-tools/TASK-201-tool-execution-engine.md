# Task: TASK-201 Tool Execution Engine

**Phase**: 3
**Priority**: Critical
**Estimated Effort**: 6 hours
**Dependencies**: TASK-005 (AITool & Function Decorator System)

### Objective
Implement the tool execution engine that handles automatic function invocation during agent execution, including function call detection, argument validation, execution, and result handling with support for multiple iterations.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-7 (Tools & Function Calling)
- **Python Reference**: `/python/packages/core/agent_framework/_tools.py:925-1143` - Function invocation logic
- **Python Reference**: `/python/packages/core/agent_framework/_tools.py:1214-1357` - get_response decorator
- **Standards**: CLAUDE.md § Python Architecture → Async-First

### Files to Create/Modify
- `src/tools/execution-engine.ts` - Core tool execution logic
- `src/tools/function-invoking-client.ts` - Decorator for chat clients
- `src/tools/__tests__/execution-engine.test.ts` - Unit tests

### Implementation Requirements

**Core Execution Logic**:
1. Implement `autoInvokeFunction()` to execute single function calls
2. Implement `executeFunctionCalls()` to execute multiple calls concurrently
3. Parse function arguments from FunctionCallContent
4. Validate arguments against AIFunction input model
5. Return FunctionResultContent with result or exception
6. Support max iterations to prevent infinite loops (default: 10)
7. Handle FunctionApprovalRequestContent for approval-required tools

**ChatClient Decoration**:
8. Create `useFunctionInvocation()` decorator for chat client classes
9. Wrap `getResponse()` method to handle function calls automatically
10. Wrap `getStreamingResponse()` method for streaming support
11. Detect function calls in chat response
12. Execute functions and append results to messages
13. Re-invoke chat client with function results
14. Continue until no more function calls or max iterations reached

**Function Call Flow**:
15. Extract tools from kwargs or chat_options
16. Build tool map (name → AIFunction)
17. For each function call in response:
    - Parse arguments
    - Validate with Pydantic model
    - Check if approval required
    - Execute function via `invoke()`
    - Create FunctionResultContent
18. Add function results as new message with role="tool"
19. Call chat client again with updated messages
20. Repeat until completion or max iterations

**Error Handling**:
21. Catch and wrap validation errors in FunctionResultContent
22. Catch and wrap execution errors in FunctionResultContent
23. Handle missing tools gracefully with error result
24. Failsafe: after max iterations, force tool_choice="none"

**TypeScript Patterns**:
- Use higher-order functions for decorators
- Use async/await for all operations
- Use Promise.all() for concurrent function execution
- Type return values properly

**Code Standards**:
- 120 character line length
- JSDoc with examples
- Strict mode, no `any`

### Test Requirements
- [ ] Test `autoInvokeFunction()` with valid function call
- [ ] Test `autoInvokeFunction()` with invalid arguments (validation error)
- [ ] Test `autoInvokeFunction()` with function throwing error
- [ ] Test `autoInvokeFunction()` with approval-required tool
- [ ] Test `executeFunctionCalls()` executes multiple calls concurrently
- [ ] Test `useFunctionInvocation()` decorator applies to chat client
- [ ] Test decorated client detects and executes function calls
- [ ] Test decorated client handles multiple iterations
- [ ] Test decorated client respects max iterations limit
- [ ] Test decorated client failsafe disables tools after max iterations
- [ ] Test function results appended correctly to messages
- [ ] Test conversation_id updated between iterations
- [ ] Test streaming response handles function calls

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] Tool execution engine handles single and multiple function calls
- [ ] Arguments validated before execution
- [ ] Errors wrapped in FunctionResultContent
- [ ] useFunctionInvocation decorator works on chat clients
- [ ] Max iterations prevents infinite loops
- [ ] Tests pass with >85% coverage
- [ ] TypeScript strict mode, ESLint passes
- [ ] JSDoc complete with examples

### Example Code Pattern
```typescript
import { AIFunction } from '../core/ai-function';
import { FunctionCallContent, FunctionResultContent } from '../types';

/**
 * Execute a single function call automatically.
 */
export async function autoInvokeFunction(
  functionCall: FunctionCallContent,
  toolMap: Map<string, AIFunction<any, any>>,
  customArgs?: Record<string, unknown>
): Promise<FunctionResultContent> {
  const tool = toolMap.get(functionCall.name);

  if (!tool) {
    return new FunctionResultContent({
      callId: functionCall.callId,
      exception: new Error(`Function '${functionCall.name}' not found`)
    });
  }

  if (tool.approvalMode === 'always_require') {
    return new FunctionApprovalRequestContent({
      id: functionCall.callId,
      functionCall
    });
  }

  try {
    const parsedArgs = functionCall.parseArguments();
    const mergedArgs = { ...customArgs, ...parsedArgs };
    const validatedArgs = tool.inputModel.parse(mergedArgs);
    const result = await tool.invoke({ arguments: validatedArgs });

    return new FunctionResultContent({
      callId: functionCall.callId,
      result
    });
  } catch (error) {
    return new FunctionResultContent({
      callId: functionCall.callId,
      exception: error as Error
    });
  }
}

/**
 * Execute multiple function calls concurrently.
 */
export async function executeFunctionCalls(
  functionCalls: FunctionCallContent[],
  tools: ToolProtocol[],
  customArgs?: Record<string, unknown>
): Promise<FunctionResultContent[]> {
  const toolMap = buildToolMap(tools);

  return await Promise.all(
    functionCalls.map(fc => autoInvokeFunction(fc, toolMap, customArgs))
  );
}

/**
 * Decorator to enable automatic function calling on a chat client.
 */
export function useFunctionInvocation<T extends ChatClientProtocol>(
  ChatClientClass: new (...args: any[]) => T
): new (...args: any[]) => T {
  const originalGetResponse = ChatClientClass.prototype.getResponse;

  ChatClientClass.prototype.getResponse = async function(
    this: T,
    messages: ChatMessage[],
    options?: ChatOptions
  ): Promise<ChatResponse> {
    const maxIterations = options?.maxIterations ?? 10;
    let preparedMessages = [...messages];

    for (let i = 0; i < maxIterations; i++) {
      const response = await originalGetResponse.call(this, preparedMessages, options);

      const functionCalls = extractFunctionCalls(response);
      if (functionCalls.length === 0) {
        return response;
      }

      const tools = options?.tools || [];
      const results = await executeFunctionCalls(functionCalls, tools);

      // Add function results as tool message
      preparedMessages.push(
        new ChatMessage({
          role: 'tool',
          contents: results
        })
      );

      if (response.conversationId) {
        // Service-managed: clear messages, service has history
        preparedMessages = [];
        options = { ...options, conversationId: response.conversationId };
      }
    }

    // Failsafe: disable tools and get final response
    return await originalGetResponse.call(this, preparedMessages, {
      ...options,
      toolChoice: 'none'
    });
  };

  return ChatClientClass;
}
```

### Related Tasks
- **Blocked by**: TASK-005 (AITool & Function Decorator)
- **Blocks**: TASK-202 (MCP tool integration), TASK-207 (Tool approval)
- **Related**: TASK-101 (ChatAgent uses tool execution)
