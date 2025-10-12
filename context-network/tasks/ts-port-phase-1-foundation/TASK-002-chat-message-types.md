# Task: TASK-002 Core Type Definitions - ChatMessage

**Phase**: 1
**Priority**: Critical
**Estimated Effort**: 4 hours
**Dependencies**: TASK-001

## Objective
Implement ChatMessage discriminated union with all message roles, content types, and type guards following TypeScript best practices.

## Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-1 (Agents and Chat Messages), § FR-4 (Content Types)
- **Python Reference**: `/python/packages/core/agent_framework/_types.py:50-200`
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI.Abstractions/ChatMessage.cs`
- **Standards**: CLAUDE.md § Prefer Attributes Over Inheritance

## Files to Create/Modify
- `src/core/types/chat-message.ts` - ChatMessage types and factory functions
- `src/core/types/__tests__/chat-message.test.ts` - Comprehensive tests
- `src/core/types/index.ts` - Re-exports
- `src/core/index.ts` - Top-level exports

## Implementation Requirements

### Core Functionality

1. **Define MessageRole enum**:
   ```typescript
   export enum MessageRole {
     User = 'user',
     Assistant = 'assistant',
     System = 'system',
     Tool = 'tool'
   }
   ```

2. **Define Content discriminated union** with 9 types:
   - `{ type: 'text'; text: string }`
   - `{ type: 'function_call'; callId: string; name: string; arguments: string }`
   - `{ type: 'function_result'; callId: string; result: unknown; error?: Error }`
   - `{ type: 'function_approval_request'; id: string; functionCall: FunctionCallContent }`
   - `{ type: 'function_approval_response'; id: string; approved: boolean; functionCall: FunctionCallContent }`
   - `{ type: 'image'; url: string; detail?: 'low' | 'high' | 'auto' }`
   - `{ type: 'audio'; data: Buffer; format: 'wav' | 'mp3' }`
   - `{ type: 'file'; fileId: string; purpose?: string }`
   - `{ type: 'vector_store'; vectorStoreId: string }`

3. **Define ChatMessage interface**:
   ```typescript
   export interface ChatMessage {
     role: MessageRole;
     content: Content | Content[];
     name?: string;
     timestamp?: Date;
     metadata?: Record<string, unknown>;
   }
   ```

4. **Create factory functions** for each message type:
   - `createUserMessage(content: string | Content[]): ChatMessage`
   - `createAssistantMessage(content: string | Content[]): ChatMessage`
   - `createSystemMessage(content: string): ChatMessage`
   - `createToolMessage(callId: string, result: unknown, error?: Error): ChatMessage`

5. **Create type guard functions** for each content type:
   - `isTextContent(content: Content): content is TextContent`
   - `isFunctionCallContent(content: Content): content is FunctionCallContent`
   - `isFunctionResultContent(content: Content): content is FunctionResultContent`
   - `isFunctionApprovalRequest(content: Content): content is FunctionApprovalRequestContent`
   - `isFunctionApprovalResponse(content: Content): content is FunctionApprovalResponseContent`
   - `isImageContent(content: Content): content is ImageContent`
   - `isAudioContent(content: Content): content is AudioContent`
   - `isFileContent(content: Content): content is FileContent`
   - `isVectorStoreContent(content: Content): content is VectorStoreContent`

6. **Create utility functions**:
   - `getTextContent(message: ChatMessage): string` - Extract all text from message
   - `getFunctionCalls(message: ChatMessage): FunctionCallContent[]` - Extract function calls
   - `getFunctionResults(message: ChatMessage): FunctionResultContent[]` - Extract function results
   - `hasContent(message: ChatMessage, type: string): boolean` - Check if message contains content type

### TypeScript Patterns
- Use `type` for discriminated unions (not interfaces)
- Use `enum` for MessageRole with string values
- Use type predicates (`content is TextContent`) in type guards
- Export all types and functions from index.ts
- Use JSDoc with `@example` for all public functions

### Code Standards
- 120 character line length
- JSDoc documentation for all public APIs
- Strict TypeScript mode enabled
- No `any` types (use `unknown` for result field)
- Readonly arrays where applicable

## Test Requirements

### Factory Function Tests
- [ ] Test `createUserMessage` with string creates `{ type: 'text', text: string }` content
- [ ] Test `createUserMessage` with `Content[]` preserves array
- [ ] Test `createAssistantMessage` with function call content
- [ ] Test `createSystemMessage` creates message with system role
- [ ] Test `createToolMessage` with result creates function_result content
- [ ] Test `createToolMessage` with error includes error in content
- [ ] Test all factory functions set `timestamp` automatically

### Type Guard Tests
- [ ] Test `isTextContent` returns true for text content
- [ ] Test `isTextContent` returns false for non-text content
- [ ] Test `isFunctionCallContent` correctly identifies function calls
- [ ] Test each type guard with all content types (9 × 9 = 81 cases, can sample)
- [ ] Test type guards enable TypeScript type narrowing

### Utility Function Tests
- [ ] Test `getTextContent` extracts text from single text content
- [ ] Test `getTextContent` extracts and joins multiple text contents
- [ ] Test `getTextContent` returns empty string when no text content
- [ ] Test `getFunctionCalls` extracts all function calls from content array
- [ ] Test `getFunctionCalls` returns empty array when no function calls
- [ ] Test `hasContent` returns true when content type present
- [ ] Test `hasContent` returns false when content type absent

### Edge Case Tests
- [ ] Test message with empty string content
- [ ] Test message with empty content array
- [ ] Test message with undefined optional fields (name, timestamp, metadata)
- [ ] Test message with multiple content types in array
- [ ] Test type inference works without explicit type assertions

**Minimum Coverage**: 90% (core types are critical)

## Acceptance Criteria
- [ ] All 9 content types defined with 'type' discriminator
- [ ] MessageRole enum with 4 roles
- [ ] ChatMessage interface with all required and optional fields
- [ ] Factory functions for user, assistant, system, tool messages
- [ ] Type guards for all 9 content types with type predicates
- [ ] Utility functions for common operations
- [ ] JSDoc complete with `@example` for all public functions
- [ ] Tests cover all content types and edge cases
- [ ] Tests achieve >90% coverage
- [ ] TypeScript inference works without type assertions
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings
- [ ] Exports available from `src/core/index.ts`

## Example Code Pattern

```typescript
/**
 * Content types for chat messages using discriminated unions.
 */
export type TextContent = { type: 'text'; text: string };
export type FunctionCallContent = { type: 'function_call'; callId: string; name: string; arguments: string };
export type FunctionResultContent = { type: 'function_result'; callId: string; result: unknown; error?: Error };
// ... other content types

export type Content =
  | TextContent
  | FunctionCallContent
  | FunctionResultContent
  | FunctionApprovalRequestContent
  | FunctionApprovalResponseContent
  | ImageContent
  | AudioContent
  | FileContent
  | VectorStoreContent;

/**
 * Create a user message.
 *
 * @param content - Text string or array of content objects
 * @returns ChatMessage with user role
 *
 * @example
 * ```typescript
 * const msg = createUserMessage('Hello, world!');
 * // { role: 'user', content: { type: 'text', text: 'Hello, world!' }, timestamp: Date }
 * ```
 */
export function createUserMessage(content: string | Content[]): ChatMessage {
  return {
    role: MessageRole.User,
    content: typeof content === 'string' ? { type: 'text', text: content } : content,
    timestamp: new Date(),
  };
}

/**
 * Type guard for text content.
 *
 * @param content - Content to check
 * @returns True if content is TextContent
 */
export function isTextContent(content: Content): content is TextContent {
  return content.type === 'text';
}

/**
 * Extract all text content from a message.
 *
 * @param message - Chat message
 * @returns Concatenated text from all text contents
 */
export function getTextContent(message: ChatMessage): string {
  const contents = Array.isArray(message.content) ? message.content : [message.content];
  return contents.filter(isTextContent).map((c) => c.text).join('\n');
}
```

## Related Tasks
- **Blocks**: TASK-004 (ChatClientProtocol), TASK-005 (Tools), TASK-007 (BaseAgent)
- **Blocked by**: TASK-001 (Project scaffolding)
- **Related**: TASK-003 (AgentInfo uses similar patterns)
