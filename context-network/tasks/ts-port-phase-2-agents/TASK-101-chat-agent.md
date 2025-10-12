# Task: TASK-101 ChatAgent Implementation

**Phase**: 2
**Priority**: Critical
**Estimated Effort**: 8 hours
**Dependencies**: TASK-007 (BaseAgent), TASK-004 (ChatClientProtocol), TASK-005 (Tool System)

### Objective
Implement the ChatAgent class that extends BaseAgent to provide chat client-based agent functionality with support for tools, context providers, middleware, and both streaming and non-streaming responses.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-2 (Chat Agents)
- **Python Reference**: `/python/packages/core/agent_framework/_agents.py:471-1231` - ChatAgent class
- **Python Reference**: `/python/packages/core/agent_framework/_types.py:250-350` - ChatOptions, AgentRunResponse
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI/Agent.cs` lines 50-300
- **Standards**: CLAUDE.md § Python Architecture → Async-First Design

### Files to Create/Modify
- `src/agents/chat-agent.ts` - ChatAgent class implementation
- `src/agents/__tests__/chat-agent.test.ts` - Unit tests for ChatAgent
- `src/agents/index.ts` - Add ChatAgent export
- `src/index.ts` - Re-export ChatAgent from agents module

### Implementation Requirements

**Core Functionality**:
1. Create `ChatAgent` class extending `BaseAgent`
2. Implement constructor accepting `ChatClientProtocol` and configuration options
3. Implement `run()` method returning `Promise<AgentRunResponse>`
4. Implement `runStream()` method returning `AsyncIterable<AgentRunResponseUpdate>`
5. Implement `getNewThread()` override with service-managed and local-managed logic
6. Support both service-managed threads (with `conversationId`) and local-managed threads (with `chatMessageStoreFactory`)
7. Implement MCP tool integration (connect MCP servers and resolve their functions)
8. Implement context provider integration during message preparation
9. Implement middleware support via decorators/wrappers
10. Handle message normalization (string | ChatMessage | array conversions)

**ChatOptions Support**:
11. Support all standard chat options: `modelId`, `temperature`, `maxTokens`, `topP`, etc.
12. Support `toolChoice` with auto/required/none modes
13. Support `responseFormat` for structured outputs
14. Support `additionalChatOptions` for provider-specific parameters
15. Merge constructor-level options with runtime options (runtime takes precedence)

**Thread Management**:
16. Create service-managed threads when `conversationId` is provided
17. Create local-managed threads when `chatMessageStoreFactory` is provided
18. Update thread with conversation ID from chat client response
19. Raise error if both `conversationId` and `chatMessageStoreFactory` provided
20. Notify threads of new messages after successful execution

**Context Provider Integration**:
21. Call `contextProvider.invoking()` before chat client invocation
22. Merge context messages into thread messages
23. Merge context tools into runtime tool list
24. Append context instructions to chat options instructions
25. Call `contextProvider.invoked()` after successful execution

**MCP Tool Integration**:
26. Separate MCPTool instances from regular tools during initialization
27. Connect MCP servers using AsyncExitStack for lifecycle management
28. Resolve MCP server functions and merge into final tool list
29. Support runtime-provided MCP tools in addition to constructor tools

**TypeScript Patterns**:
- Use async/await throughout (never use callbacks or promises without await)
- Implement async context manager pattern using Symbol.asyncDispose (if available)
- Use discriminated unions for options (not classes)
- Provide fluent builder pattern for complex configuration
- Export all types with comprehensive JSDoc
- Use strict null checking (no `!` assertions without justification)

**Code Standards**:
- 120 character line length
- JSDoc documentation for all public APIs with `@example` tags
- Strict TypeScript mode enabled
- No `any` types without explicit justification comment

### Test Requirements
- [ ] Test ChatAgent instantiation with minimal config (chat_client only)
- [ ] Test ChatAgent with all constructor options
- [ ] Test `run()` method with string message
- [ ] Test `run()` method with ChatMessage object
- [ ] Test `run()` method with array of messages
- [ ] Test `runStream()` yields AgentRunResponseUpdate objects
- [ ] Test `runStream()` completes with final response
- [ ] Test service-managed thread creation with conversationId
- [ ] Test local-managed thread creation with chatMessageStoreFactory
- [ ] Test error when both conversationId and chatMessageStoreFactory provided
- [ ] Test thread notification after successful run
- [ ] Test context provider invoking/invoked lifecycle
- [ ] Test context messages merged into thread messages
- [ ] Test context tools merged into runtime tools
- [ ] Test context instructions appended to chat options
- [ ] Test MCP tool connection and function resolution
- [ ] Test runtime options override constructor options
- [ ] Test message normalization for all input types
- [ ] Test async cleanup with AsyncExitStack pattern
- [ ] Test error handling for chat client failures

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] ChatAgent class implemented with all required methods
- [ ] Constructor validates conflicting options (conversationId + chatMessageStoreFactory)
- [ ] `run()` returns AgentRunResponse with messages and metadata
- [ ] `runStream()` yields updates and notifies thread after completion
- [ ] Thread management works for both service-managed and local-managed modes
- [ ] Context provider lifecycle (invoking/invoked) implemented correctly
- [ ] MCP tools connected via AsyncExitStack and functions resolved
- [ ] Message normalization handles string, ChatMessage, and arrays
- [ ] Runtime options override constructor options correctly
- [ ] Tests pass with >85% coverage
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings
- [ ] JSDoc complete for all public APIs with examples
- [ ] Exports added to index.ts files
- [ ] Code reviewed against Python reference implementation

### Example Code Pattern
```typescript
import { BaseAgent } from '../core/base-agent';
import { ChatClientProtocol } from '../core/chat-client-protocol';
import { AgentRunResponse, AgentRunResponseUpdate } from '../types';
import { ChatOptions } from '../types/chat-options';

/**
 * A chat client-based agent implementation.
 *
 * Supports tools, context providers, middleware, and both streaming and non-streaming responses.
 *
 * @example
 * ```typescript
 * import { ChatAgent } from 'agent-framework';
 * import { OpenAIChatClient } from 'agent-framework/openai';
 *
 * const client = new OpenAIChatClient({ modelId: 'gpt-4' });
 * const agent = new ChatAgent({
 *   chatClient: client,
 *   name: 'assistant',
 *   instructions: 'You are a helpful assistant.',
 *   tools: [myTool],
 *   temperature: 0.7
 * });
 *
 * // Non-streaming
 * const response = await agent.run('Hello!');
 * console.log(response.text);
 *
 * // Streaming
 * for await (const update of agent.runStream('Hello!')) {
 *   console.log(update.text);
 * }
 * ```
 */
export class ChatAgent extends BaseAgent {
  private readonly chatClient: ChatClientProtocol;
  private readonly chatOptions: ChatOptions;
  private readonly chatMessageStoreFactory?: () => ChatMessageStore;
  private readonly localMcpTools: MCPTool[];
  private readonly asyncExitStack: AsyncExitStack;

  constructor(options: ChatAgentOptions) {
    // Validate conflicting options
    if (options.conversationId && options.chatMessageStoreFactory) {
      throw new AgentInitializationError(
        'Cannot specify both conversationId and chatMessageStoreFactory'
      );
    }

    super({
      id: options.id,
      name: options.name,
      description: options.description,
      contextProviders: options.contextProviders,
      middleware: options.middleware,
      additionalProperties: options.additionalProperties
    });

    this.chatClient = options.chatClient;
    this.chatMessageStoreFactory = options.chatMessageStoreFactory;

    // Separate MCP tools from regular tools
    const tools = Array.isArray(options.tools) ? options.tools : [options.tools];
    this.localMcpTools = tools.filter(isMCPTool);
    const regularTools = tools.filter(t => !isMCPTool(t));

    this.chatOptions = {
      modelId: options.modelId,
      conversationId: options.conversationId,
      instructions: options.instructions,
      temperature: options.temperature,
      maxTokens: options.maxTokens,
      tools: regularTools,
      toolChoice: options.toolChoice ?? 'auto',
      // ... other options
      additionalProperties: options.additionalChatOptions ?? {}
    };

    this.asyncExitStack = new AsyncExitStack();
  }

  async run(
    messages?: string | ChatMessage | (string | ChatMessage)[],
    options?: Partial<ChatRunOptions>
  ): Promise<AgentRunResponse> {
    const inputMessages = this.normalizeMessages(messages);
    const { thread, mergedOptions, threadMessages } =
      await this.prepareThreadAndMessages(options?.thread, inputMessages);

    // Connect MCP tools and resolve functions
    const finalTools = await this.resolveFinalTools(
      mergedOptions.tools,
      options?.tools
    );

    // Merge runtime options (override constructor)
    const finalOptions = { ...this.chatOptions, ...options, tools: finalTools };

    // Call chat client
    const response = await this.chatClient.getResponse(threadMessages, finalOptions);

    // Update thread and notify
    await this.updateThreadWithConversationId(thread, response.conversationId);
    await this.notifyThreadOfNewMessages(thread, inputMessages, response.messages);

    return new AgentRunResponse({
      messages: response.messages,
      responseId: response.responseId,
      // ... other fields
    });
  }

  async *runStream(
    messages?: string | ChatMessage | (string | ChatMessage)[],
    options?: Partial<ChatRunOptions>
  ): AsyncIterable<AgentRunResponseUpdate> {
    // Similar to run() but with streaming
    // ...
  }

  override getNewThread(options?: { serviceThreadId?: string }): AgentThread {
    // Service-managed thread
    if (options?.serviceThreadId) {
      return new AgentThread({
        serviceThreadId: options.serviceThreadId,
        contextProvider: this.contextProvider
      });
    }

    // Agent has conversation ID
    if (this.chatOptions.conversationId) {
      return new AgentThread({
        serviceThreadId: this.chatOptions.conversationId,
        contextProvider: this.contextProvider
      });
    }

    // Agent has message store factory
    if (this.chatMessageStoreFactory) {
      return new AgentThread({
        messageStore: this.chatMessageStoreFactory(),
        contextProvider: this.contextProvider
      });
    }

    // Default (will be determined during run)
    return new AgentThread({ contextProvider: this.contextProvider });
  }

  private normalizeMessages(
    messages?: string | ChatMessage | (string | ChatMessage)[]
  ): ChatMessage[] {
    // Implementation
  }

  private async prepareThreadAndMessages(
    thread: AgentThread | undefined,
    inputMessages: ChatMessage[]
  ): Promise<{ thread: AgentThread; mergedOptions: ChatOptions; threadMessages: ChatMessage[] }> {
    // Invoke context provider, merge context, etc.
  }

  private async resolveFinalTools(
    ...toolSets: (Tool | MCPTool)[][]
  ): Promise<Tool[]> {
    // Connect MCP servers and resolve functions
  }

  async [Symbol.asyncDispose](): Promise<void> {
    await this.asyncExitStack.aclose();
  }
}
```

### Related Tasks
- **Blocked by**: TASK-007 (BaseAgent must exist)
- **Blocked by**: TASK-004 (ChatClientProtocol must exist)
- **Blocked by**: TASK-005 (Tool system must exist)
- **Blocks**: TASK-104 (Service-managed thread support needs ChatAgent)
- **Blocks**: TASK-105 (Local-managed thread support needs ChatAgent)
- **Related**: TASK-011 (OpenAI client will be used for testing)

---

## Implementation Notes

### Key Architectural Decisions

**Async Context Management**:
Use Symbol.asyncDispose (TC39 Explicit Resource Management) for cleanup:
```typescript
class ChatAgent implements AsyncDisposable {
  async [Symbol.asyncDispose]() {
    await this.asyncExitStack.aclose();
  }
}
```

**Options Merging Strategy**:
Constructor options < Runtime options (runtime wins):
```typescript
const finalOptions = {
  ...this.chatOptions,
  ...runtimeOptions,
  tools: mergedTools // Special handling for tools
};
```

**MCP Tool Resolution**:
Separate MCP tools early, connect lazily:
```typescript
// Constructor
this.localMcpTools = tools.filter(isMCPTool);

// Runtime
for (const mcpTool of this.localMcpTools) {
  if (!mcpTool.isConnected) {
    await this.asyncExitStack.enterAsyncContext(mcpTool);
  }
  finalTools.push(...mcpTool.functions);
}
```

**Thread Type Detection**:
Thread type is determined by presence of conversationId or messageStore:
```typescript
// Service-managed if has service thread ID
if (thread.serviceThreadId) { /* service managed */ }
// Local-managed if has message store
else if (thread.messageStore) { /* local managed */ }
// Undetermined (will be set during run)
else { /* create default */ }
```

### Python/TypeScript Differences

1. **Decorators**: Python uses `@use_agent_middleware`, TypeScript may use higher-order functions or method decorators
2. **Context Managers**: Python uses `async with`, TypeScript uses Symbol.asyncDispose
3. **Type Guards**: TypeScript has structural typing, use `is` predicates for runtime checks
4. **Async Iterables**: Both support, but TypeScript syntax is `async *funcName()`

### Common Pitfalls

- Don't mutate `this.chatOptions` during run (create copies)
- Always await context provider lifecycle methods
- Connect MCP servers before resolving their functions
- Notify thread only after successful execution (not on error)
- Update thread conversation ID even if context provider is null
