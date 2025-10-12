# Task: TASK-004 ChatClientProtocol Interface

**Phase**: 1
**Priority**: Critical
**Estimated Effort**: 3 hours
**Dependencies**: TASK-002, TASK-003

## Objective
Define ChatClientProtocol interface for LLM provider abstraction with streaming support and usage tracking.

## Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-2 (Chat Client Protocol)
- **Python Reference**: `/python/packages/core/agent_framework/_chat_client.py:1-150`
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI.Abstractions/IChatClient.cs`
- **Standards**: CLAUDE.md § Async-first design

## Files to Create/Modify
- `src/core/chat-client/protocol.ts` - ChatClientProtocol interface
- `src/core/chat-client/types.ts` - Request/response types
- `src/core/chat-client/__tests__/protocol.test.ts` - Tests with mock
- `src/core/chat-client/index.ts` - Re-exports
- `src/core/index.ts` - Add chat-client exports

## Implementation Requirements

### Core Functionality

1. **Define ChatClientProtocol interface**:
   ```typescript
   export interface ChatClientProtocol {
     complete(
       messages: ChatMessage[],
       options?: ChatCompletionOptions
     ): Promise<ChatMessage>;

     completeStream(
       messages: ChatMessage[],
       options?: ChatCompletionOptions
     ): AsyncIterable<StreamEvent>;
   }
   ```

2. **Define ChatCompletionOptions interface**:
   ```typescript
   export interface ChatCompletionOptions extends AISettings {
     tools?: AITool[];                    // Available tools (forward reference)
     parallelToolCalls?: boolean;         // Allow parallel tool calls
     serviceThreadId?: string;            // Service-managed thread ID
     additionalInstructions?: string;     // Additional instructions
     metadata?: Record<string, unknown>;  // Custom metadata
   }
   ```

3. **Define UsageInfo interface**:
   ```typescript
   export interface UsageInfo {
     promptTokens: number;
     completionTokens: number;
     totalTokens: number;
   }
   ```

4. **Define ProviderMetadata interface**:
   ```typescript
   export interface ProviderMetadata {
     provider: string;                    // e.g., 'openai', 'azure-openai', 'anthropic'
     modelId: string;                     // Actual model used
     finishReason?: string;               // 'stop', 'length', 'tool_calls', etc.
     [key: string]: unknown;              // Provider-specific fields
   }
   ```

5. **Define StreamEvent discriminated union**:
   ```typescript
   export type StreamEvent =
     | { type: 'message_delta'; delta: Partial<ChatMessage> }
     | { type: 'usage'; usage: UsageInfo }
     | { type: 'metadata'; metadata: ProviderMetadata };
   ```

6. **Create type guards for stream events**:
   ```typescript
   export function isMessageDelta(event: StreamEvent): event is MessageDeltaEvent;
   export function isUsageEvent(event: StreamEvent): event is UsageEvent;
   export function isMetadataEvent(event: StreamEvent): event is MetadataEvent;
   ```

7. **Create mock implementation for testing**:
   ```typescript
   export class MockChatClient implements ChatClientProtocol {
     async complete(messages: ChatMessage[], options?: ChatCompletionOptions): Promise<ChatMessage>;
     async *completeStream(messages: ChatMessage[], options?: ChatCompletionOptions): AsyncIterable<StreamEvent>;
   }
   ```

### TypeScript Patterns
- Use `AsyncIterable<T>` for streaming (not Observable or Promise<Stream>)
- Use discriminated union for stream events
- Use interface extension for ChatCompletionOptions
- Use type predicates for event type guards
- Forward reference AITool (will be defined in TASK-005)

### Code Standards
- JSDoc explaining protocol contract
- Document async iterator requirements for streaming
- Include streaming examples in JSDoc
- Use strict typing (no `any`)

## Test Requirements

### Protocol Interface Tests
- [ ] Test MockChatClient implements ChatClientProtocol (type check)
- [ ] Test MockChatClient.complete returns ChatMessage
- [ ] Test MockChatClient.completeStream returns AsyncIterable
- [ ] Test mock can be used in place of real client (duck typing)

### Options Tests
- [ ] Test ChatCompletionOptions extends AISettings (type check)
- [ ] Test options with all fields
- [ ] Test options with only AISettings fields
- [ ] Test options with only chat-specific fields

### Stream Event Tests
- [ ] Test stream event type guards correctly identify event types
- [ ] Test isMessageDelta returns true for message_delta events
- [ ] Test isMessageDelta returns false for other events
- [ ] Test isUsageEvent correctly identifies usage events
- [ ] Test isMetadataEvent correctly identifies metadata events

### Mock Implementation Tests
- [ ] Test mock complete returns assistant message
- [ ] Test mock completeStream yields message deltas
- [ ] Test mock completeStream yields usage info
- [ ] Test mock completeStream can be consumed with for-await-of
- [ ] Test mock handles empty message array
- [ ] Test mock handles options parameter

### Usage Info Tests
- [ ] Test UsageInfo creation with all fields
- [ ] Test totalTokens equals sum of prompt and completion tokens

**Minimum Coverage**: 80%

## Acceptance Criteria
- [ ] ChatClientProtocol interface with complete() and completeStream()
- [ ] Streaming support with AsyncIterable<StreamEvent>
- [ ] ChatCompletionOptions interface extending AISettings
- [ ] UsageInfo for token tracking
- [ ] ProviderMetadata for provider-specific info
- [ ] StreamEvent discriminated union with 3 event types
- [ ] Type guards for all stream event types
- [ ] MockChatClient implementation for testing
- [ ] JSDoc with streaming examples
- [ ] Tests cover all types and mock implementation
- [ ] Tests achieve >80% coverage
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings

## Example Code Pattern

```typescript
/**
 * Chat client protocol for LLM providers.
 *
 * Implementations must support both blocking and streaming completion.
 */
export interface ChatClientProtocol {
  /**
   * Complete a chat conversation with the LLM.
   *
   * @param messages - Conversation history
   * @param options - Completion options (model settings, tools, etc.)
   * @returns Assistant response message
   *
   * @example
   * ```typescript
   * const client: ChatClientProtocol = new OpenAIChatClient(...);
   * const response = await client.complete([
   *   createUserMessage('What is 2+2?')
   * ]);
   * console.log(getTextContent(response)); // "4"
   * ```
   */
  complete(
    messages: ChatMessage[],
    options?: ChatCompletionOptions
  ): Promise<ChatMessage>;

  /**
   * Stream a chat completion with real-time updates.
   *
   * @param messages - Conversation history
   * @param options - Completion options
   * @returns Async iterable of message chunks, usage info, and metadata
   *
   * @example
   * ```typescript
   * const client: ChatClientProtocol = new OpenAIChatClient(...);
   * const stream = client.completeStream([
   *   createUserMessage('Tell me a story')
   * ]);
   *
   * for await (const event of stream) {
   *   if (isMessageDelta(event)) {
   *     process.stdout.write(getTextContent(event.delta));
   *   } else if (isUsageEvent(event)) {
   *     console.log(`Tokens used: ${event.usage.totalTokens}`);
   *   }
   * }
   * ```
   */
  completeStream(
    messages: ChatMessage[],
    options?: ChatCompletionOptions
  ): AsyncIterable<StreamEvent>;
}

/**
 * Stream event types.
 */
export type MessageDeltaEvent = { type: 'message_delta'; delta: Partial<ChatMessage> };
export type UsageEvent = { type: 'usage'; usage: UsageInfo };
export type MetadataEvent = { type: 'metadata'; metadata: ProviderMetadata };

export type StreamEvent = MessageDeltaEvent | UsageEvent | MetadataEvent;

/**
 * Type guard for message delta events.
 */
export function isMessageDelta(event: StreamEvent): event is MessageDeltaEvent {
  return event.type === 'message_delta';
}

/**
 * Mock chat client for testing.
 *
 * Returns canned responses for testing agent implementations.
 */
export class MockChatClient implements ChatClientProtocol {
  async complete(messages: ChatMessage[]): Promise<ChatMessage> {
    return createAssistantMessage('Mock response');
  }

  async *completeStream(messages: ChatMessage[]): AsyncIterable<StreamEvent> {
    yield { type: 'message_delta', delta: { content: { type: 'text', text: 'Mock' } } };
    yield { type: 'message_delta', delta: { content: { type: 'text', text: ' response' } } };
    yield { type: 'usage', usage: { promptTokens: 10, completionTokens: 2, totalTokens: 12 } };
  }
}
```

## Related Tasks
- **Blocks**: TASK-007 (BaseAgent), TASK-011 (OpenAI client)
- **Blocked by**: TASK-002 (ChatMessage), TASK-003 (AISettings)
- **Related**: TASK-005 (AITool will be used in ChatCompletionOptions)
