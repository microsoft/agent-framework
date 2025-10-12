/**
 * Chat Client Protocol
 *
 * Interface definition for LLM provider abstraction with streaming support.
 * All chat client implementations must conform to this protocol.
 *
 * @module chat-client/protocol
 */

import type { ChatMessage } from '../types/chat-message';
import type { ChatCompletionOptions, StreamEvent } from './types';

/**
 * Chat client protocol for LLM providers.
 *
 * Defines the standard interface that all chat client implementations must follow.
 * Implementations must support both blocking and streaming completion modes.
 *
 * This protocol uses structural typing (duck typing), meaning any class that
 * implements these methods is compatible, even without explicitly declaring it.
 *
 * @example
 * ```typescript
 * import { ChatClientProtocol, createUserMessage } from '@microsoft/agent-framework';
 *
 * // Any class implementing these methods is compatible
 * class CustomChatClient implements ChatClientProtocol {
 *   async complete(messages: ChatMessage[], options?: ChatCompletionOptions): Promise<ChatMessage> {
 *     // Implementation
 *   }
 *
 *   async *completeStream(messages: ChatMessage[], options?: ChatCompletionOptions): AsyncIterable<StreamEvent> {
 *     // Implementation
 *   }
 * }
 * ```
 */
export interface ChatClientProtocol {
  /**
   * Complete a chat conversation with the LLM.
   *
   * Sends a sequence of messages to the LLM and returns the assistant's response.
   * This is a blocking operation that waits for the complete response before returning.
   *
   * @param messages - Conversation history as an array of ChatMessage objects
   * @param options - Optional completion settings (model parameters, tools, etc.)
   * @returns Promise resolving to the assistant's response message
   *
   * @example
   * ```typescript
   * const client: ChatClientProtocol = new OpenAIChatClient({
   *   apiKey: 'your-api-key',
   *   modelId: 'gpt-4',
   * });
   *
   * const response = await client.complete([
   *   createUserMessage('What is 2+2?')
   * ]);
   *
   * console.log(getTextContent(response)); // "4"
   * ```
   *
   * @example
   * ```typescript
   * // With options
   * const response = await client.complete(
   *   [
   *     createSystemMessage('You are a helpful math tutor.'),
   *     createUserMessage('Explain the Pythagorean theorem.')
   *   ],
   *   {
   *     temperature: 0.7,
   *     maxTokens: 500,
   *   }
   * );
   * ```
   */
  complete(messages: ChatMessage[], options?: ChatCompletionOptions): Promise<ChatMessage>;

  /**
   * Stream a chat completion with real-time updates.
   *
   * Sends messages to the LLM and returns an async iterable that yields events
   * as they arrive. Events include message deltas (incremental content), usage
   * information (token counts), and metadata (provider info, finish reason).
   *
   * The stream can be consumed using `for await...of` loops. Message deltas
   * typically arrive first, followed by usage info and metadata at the end.
   *
   * @param messages - Conversation history as an array of ChatMessage objects
   * @param options - Optional completion settings (model parameters, tools, etc.)
   * @returns AsyncIterable yielding StreamEvent objects (message_delta, usage, metadata)
   *
   * @example
   * ```typescript
   * const client: ChatClientProtocol = new OpenAIChatClient({
   *   apiKey: 'your-api-key',
   *   modelId: 'gpt-4',
   * });
   *
   * const stream = client.completeStream([
   *   createUserMessage('Tell me a story')
   * ]);
   *
   * for await (const event of stream) {
   *   if (isMessageDelta(event)) {
   *     // Incremental content update
   *     process.stdout.write(getTextContent(event.delta));
   *   } else if (isUsageEvent(event)) {
   *     // Token usage information
   *     console.log(`\nTokens used: ${event.usage.totalTokens}`);
   *   } else if (isMetadataEvent(event)) {
   *     // Provider metadata
   *     console.log(`Model: ${event.metadata.modelId}`);
   *   }
   * }
   * ```
   *
   * @example
   * ```typescript
   * // Collecting full response from stream
   * const stream = client.completeStream([
   *   createUserMessage('What is TypeScript?')
   * ]);
   *
   * let fullContent = '';
   * for await (const event of stream) {
   *   if (isMessageDelta(event)) {
   *     fullContent += getTextContent(event.delta);
   *   }
   * }
   * console.log('Complete response:', fullContent);
   * ```
   */
  completeStream(messages: ChatMessage[], options?: ChatCompletionOptions): AsyncIterable<StreamEvent>;
}
