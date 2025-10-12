# Task: TASK-007 BaseAgent Class

**Phase**: 1
**Priority**: Critical
**Estimated Effort**: 6 hours
**Dependencies**: TASK-002, TASK-003, TASK-004, TASK-005, TASK-008, TASK-012

## Objective
Implement BaseAgent abstract class with lifecycle hooks, streaming support, and context provider integration.

## Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-1 (Agents), § FR-3 (Streaming), § FR-9 (Context Providers)
- **Python Reference**: `/python/packages/core/agent_framework/_agents.py:100-400`
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI/Agent.cs`
- **Standards**: CLAUDE.md § Async-first design

## Files to Create/Modify
- `src/core/agents/base-agent.ts` - BaseAgent abstract class
- `src/core/agents/__tests__/base-agent.test.ts` - Tests
- `src/core/agents/index.ts` - Re-exports
- `src/core/index.ts` - Add agents exports

## Implementation Requirements

### Core Functionality

1. **Define AgentProtocol interface**:
   ```typescript
   export interface AgentProtocol {
     readonly info: AgentInfo;
     readonly chatClient: ChatClientProtocol;
     readonly tools: AITool[];
     readonly contextProvider?: ContextProvider;

     invoke(messages: ChatMessage[], options?: AISettings): Promise<ChatMessage>;
     invokeStream(messages: ChatMessage[], options?: AISettings): AsyncIterable<ChatMessage>;
   }
   ```

2. **Implement BaseAgent abstract class**:
   ```typescript
   export abstract class BaseAgent implements AgentProtocol {
     public readonly info: AgentInfo;
     protected chatClient: ChatClientProtocol;
     protected tools: AITool[] = [];
     protected contextProvider?: ContextProvider;

     constructor(config: {
       info: AgentInfo;
       chatClient: ChatClientProtocol;
       tools?: AITool[];
       contextProvider?: ContextProvider;
     });

     async invoke(messages: ChatMessage[], options?: AISettings): Promise<ChatMessage>;
     async *invokeStream(messages: ChatMessage[], options?: AISettings): AsyncIterable<ChatMessage>;

     // Lifecycle hooks
     protected async beforeInvoke(messages: ChatMessage[]): Promise<ChatMessage[]>;
     protected async afterInvoke(request: ChatMessage[], response: ChatMessage): Promise<void>;
   }
   ```

3. **Implement context provider lifecycle**:
   - Call `contextProvider.invoking()` before LLM call
   - Apply returned context (instructions, messages, tools)
   - Call `contextProvider.invoked()` after LLM call

4. **Support tool execution** (placeholder for Phase 3):
   - Detect function_call content in response
   - Return response (tool execution will be in Phase 3)

### TypeScript Patterns
- Use abstract class for BaseAgent
- Use async/await throughout
- Use AsyncIterable for streaming
- Protected methods for hooks
- Support method override in subclasses

### Code Standards
- JSDoc explaining lifecycle and hooks
- Examples showing subclass creation
- Async-first design
- Proper error handling

## Test Requirements

- [ ] Test BaseAgent cannot be instantiated directly (abstract)
- [ ] Test BaseAgent subclass creation
- [ ] Test invoke() calls chatClient.complete()
- [ ] Test invokeStream() calls chatClient.completeStream()
- [ ] Test beforeInvoke hook is called
- [ ] Test afterInvoke hook is called
- [ ] Test context provider invoking() is called
- [ ] Test context provider invoked() is called
- [ ] Test context from provider is applied
- [ ] Test tools are passed to chat client
- [ ] Test with no context provider works
- [ ] Test with no tools works

**Minimum Coverage**: 85%

## Acceptance Criteria
- [ ] AgentProtocol interface defined
- [ ] BaseAgent abstract class implemented
- [ ] Lifecycle hooks (beforeInvoke, afterInvoke)
- [ ] Context provider integration
- [ ] Streaming support
- [ ] JSDoc complete with examples
- [ ] Tests achieve >85% coverage
- [ ] TypeScript compiles with no errors

## Example Code Pattern

```typescript
export abstract class BaseAgent implements AgentProtocol {
  public readonly info: AgentInfo;
  protected chatClient: ChatClientProtocol;
  protected tools: AITool[] = [];
  protected contextProvider?: ContextProvider;

  constructor(config: {
    info: AgentInfo;
    chatClient: ChatClientProtocol;
    tools?: AITool[];
    contextProvider?: ContextProvider;
  }) {
    this.info = config.info;
    this.chatClient = config.chatClient;
    this.tools = config.tools || [];
    this.contextProvider = config.contextProvider;
  }

  async invoke(messages: ChatMessage[], options?: AISettings): Promise<ChatMessage> {
    // Apply before hook
    messages = await this.beforeInvoke(messages);

    // Get context
    let contextInstructions: string | undefined;
    let contextMessages: ChatMessage[] | undefined;
    let contextTools: AITool[] | undefined;

    if (this.contextProvider) {
      const context = await this.contextProvider.invoking(messages, options);
      contextInstructions = context.instructions;
      contextMessages = context.messages;
      contextTools = context.tools;
    }

    // Merge context
    if (contextInstructions && this.info.instructions) {
      // Combine instructions
    }
    const allMessages = [...(contextMessages || []), ...messages];
    const allTools = [...this.tools, ...(contextTools || [])];

    // Call LLM
    const response = await this.chatClient.complete(allMessages, {
      ...options,
      tools: allTools,
    });

    // Apply after hook
    await this.afterInvoke(messages, response);

    // Notify context provider
    if (this.contextProvider) {
      await this.contextProvider.invoked(messages, [response]);
    }

    return response;
  }

  protected async beforeInvoke(messages: ChatMessage[]): Promise<ChatMessage[]> {
    return messages;
  }

  protected async afterInvoke(request: ChatMessage[], response: ChatMessage): Promise<void> {
    // Override in subclass
  }
}
```

## Related Tasks
- **Blocks**: Phase 2 tasks (ChatAgent extends BaseAgent)
- **Blocked by**: TASK-002, TASK-003, TASK-004, TASK-005, TASK-008, TASK-012
