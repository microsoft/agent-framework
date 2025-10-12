/**
 * Chat Message Types
 *
 * Core types for representing chat messages with discriminated union content types.
 * Follows the TypeScript port specification for the Microsoft Agent Framework.
 *
 * @module chat-message
 */

/**
 * Message roles for chat interactions
 */
export enum MessageRole {
  User = 'user',
  Assistant = 'assistant',
  System = 'system',
  Tool = 'tool',
}

/**
 * Text content in a message
 */
export type TextContent = {
  type: 'text';
  text: string;
};

/**
 * Function call request content
 */
export type FunctionCallContent = {
  type: 'function_call';
  callId: string;
  name: string;
  arguments: string;
};

/**
 * Function call result content
 */
export type FunctionResultContent = {
  type: 'function_result';
  callId: string;
  result: unknown;
  error?: Error;
};

/**
 * Function approval request content
 */
export type FunctionApprovalRequestContent = {
  type: 'function_approval_request';
  id: string;
  functionCall: FunctionCallContent;
};

/**
 * Function approval response content
 */
export type FunctionApprovalResponseContent = {
  type: 'function_approval_response';
  id: string;
  approved: boolean;
  functionCall: FunctionCallContent;
};

/**
 * Image content with optional detail level
 */
export type ImageContent = {
  type: 'image';
  url: string;
  detail?: 'low' | 'high' | 'auto';
};

/**
 * Audio content with format specification
 */
export type AudioContent = {
  type: 'audio';
  data: Buffer;
  format: 'wav' | 'mp3';
};

/**
 * Hosted file content reference
 */
export type FileContent = {
  type: 'file';
  fileId: string;
  purpose?: string;
};

/**
 * Hosted vector store content reference
 */
export type VectorStoreContent = {
  type: 'vector_store';
  vectorStoreId: string;
};

/**
 * Discriminated union of all content types
 */
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
 * A chat message with role, content, and optional metadata
 */
export interface ChatMessage {
  role: MessageRole;
  content: Content | Content[];
  name?: string;
  timestamp?: Date;
  metadata?: Record<string, unknown>;
}

// Factory Functions

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
 * Create an assistant message.
 *
 * @param content - Text string or array of content objects
 * @returns ChatMessage with assistant role
 *
 * @example
 * ```typescript
 * const msg = createAssistantMessage('How can I help you?');
 * // { role: 'assistant', content: { type: 'text', text: 'How can I help you?' }, timestamp: Date }
 * ```
 */
export function createAssistantMessage(content: string | Content[]): ChatMessage {
  return {
    role: MessageRole.Assistant,
    content: typeof content === 'string' ? { type: 'text', text: content } : content,
    timestamp: new Date(),
  };
}

/**
 * Create a system message.
 *
 * @param content - Text string for system instructions
 * @returns ChatMessage with system role
 *
 * @example
 * ```typescript
 * const msg = createSystemMessage('You are a helpful assistant.');
 * // { role: 'system', content: { type: 'text', text: 'You are a helpful assistant.' }, timestamp: Date }
 * ```
 */
export function createSystemMessage(content: string): ChatMessage {
  return {
    role: MessageRole.System,
    content: { type: 'text', text: content },
    timestamp: new Date(),
  };
}

/**
 * Create a tool message with function result.
 *
 * @param callId - The function call identifier
 * @param result - The result of the function call
 * @param error - Optional error if the function call failed
 * @returns ChatMessage with tool role
 *
 * @example
 * ```typescript
 * const msg = createToolMessage('call_123', { temperature: 72 });
 * // { role: 'tool', content: { type: 'function_result', callId: 'call_123', result: {...} }, timestamp: Date }
 * ```
 */
export function createToolMessage(callId: string, result: unknown, error?: Error): ChatMessage {
  return {
    role: MessageRole.Tool,
    content: { type: 'function_result', callId, result, error },
    timestamp: new Date(),
  };
}

// Type Guard Functions

/**
 * Type guard for text content.
 *
 * @param content - Content to check
 * @returns True if content is TextContent
 *
 * @example
 * ```typescript
 * if (isTextContent(content)) {
 *   console.log(content.text); // TypeScript knows content is TextContent
 * }
 * ```
 */
export function isTextContent(content: Content): content is TextContent {
  return content.type === 'text';
}

/**
 * Type guard for function call content.
 *
 * @param content - Content to check
 * @returns True if content is FunctionCallContent
 */
export function isFunctionCallContent(content: Content): content is FunctionCallContent {
  return content.type === 'function_call';
}

/**
 * Type guard for function result content.
 *
 * @param content - Content to check
 * @returns True if content is FunctionResultContent
 */
export function isFunctionResultContent(content: Content): content is FunctionResultContent {
  return content.type === 'function_result';
}

/**
 * Type guard for function approval request content.
 *
 * @param content - Content to check
 * @returns True if content is FunctionApprovalRequestContent
 */
export function isFunctionApprovalRequest(content: Content): content is FunctionApprovalRequestContent {
  return content.type === 'function_approval_request';
}

/**
 * Type guard for function approval response content.
 *
 * @param content - Content to check
 * @returns True if content is FunctionApprovalResponseContent
 */
export function isFunctionApprovalResponse(content: Content): content is FunctionApprovalResponseContent {
  return content.type === 'function_approval_response';
}

/**
 * Type guard for image content.
 *
 * @param content - Content to check
 * @returns True if content is ImageContent
 */
export function isImageContent(content: Content): content is ImageContent {
  return content.type === 'image';
}

/**
 * Type guard for audio content.
 *
 * @param content - Content to check
 * @returns True if content is AudioContent
 */
export function isAudioContent(content: Content): content is AudioContent {
  return content.type === 'audio';
}

/**
 * Type guard for file content.
 *
 * @param content - Content to check
 * @returns True if content is FileContent
 */
export function isFileContent(content: Content): content is FileContent {
  return content.type === 'file';
}

/**
 * Type guard for vector store content.
 *
 * @param content - Content to check
 * @returns True if content is VectorStoreContent
 */
export function isVectorStoreContent(content: Content): content is VectorStoreContent {
  return content.type === 'vector_store';
}

// Utility Functions

/**
 * Extract all text content from a message.
 *
 * @param message - Chat message
 * @returns Concatenated text from all text contents, joined with newlines
 *
 * @example
 * ```typescript
 * const msg = createUserMessage('Hello world');
 * console.log(getTextContent(msg)); // "Hello world"
 * ```
 */
export function getTextContent(message: ChatMessage): string {
  const contents = Array.isArray(message.content) ? message.content : [message.content];
  return contents
    .filter(isTextContent)
    .map((c) => c.text)
    .join('\n');
}

/**
 * Extract all function calls from a message.
 *
 * @param message - Chat message
 * @returns Array of function call contents
 *
 * @example
 * ```typescript
 * const calls = getFunctionCalls(message);
 * calls.forEach(call => console.log(call.name));
 * ```
 */
export function getFunctionCalls(message: ChatMessage): FunctionCallContent[] {
  const contents = Array.isArray(message.content) ? message.content : [message.content];
  return contents.filter(isFunctionCallContent);
}

/**
 * Extract all function results from a message.
 *
 * @param message - Chat message
 * @returns Array of function result contents
 *
 * @example
 * ```typescript
 * const results = getFunctionResults(message);
 * results.forEach(result => console.log(result.result));
 * ```
 */
export function getFunctionResults(message: ChatMessage): FunctionResultContent[] {
  const contents = Array.isArray(message.content) ? message.content : [message.content];
  return contents.filter(isFunctionResultContent);
}

/**
 * Check if a message contains content of a specific type.
 *
 * @param message - Chat message
 * @param type - Content type to check for
 * @returns True if message contains the specified content type
 *
 * @example
 * ```typescript
 * if (hasContent(message, 'text')) {
 *   console.log('Message has text content');
 * }
 * ```
 */
export function hasContent(message: ChatMessage, type: string): boolean {
  const contents = Array.isArray(message.content) ? message.content : [message.content];
  return contents.some((c) => c.type === type);
}
