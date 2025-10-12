/**
 * Mock Chat Client
 *
 * Test implementation of ChatClientProtocol for testing and development.
 * Returns canned responses for both blocking and streaming modes.
 *
 * @module chat-client/mock-client
 */

import type { ChatMessage } from '../types/chat-message';
import { MessageRole, createAssistantMessage, getTextContent } from '../types/chat-message';
import type { ChatClientProtocol } from './protocol';
import type { ChatCompletionOptions, StreamEvent, UsageInfo } from './types';

/**
 * Mock chat client for testing.
 *
 * Provides a simple implementation of ChatClientProtocol that returns
 * canned responses. Useful for testing agent implementations without
 * requiring a real LLM provider.
 *
 * The mock client can be configured with custom responses or will generate
 * default responses based on input messages.
 *
 * @example
 * ```typescript
 * import { MockChatClient, createUserMessage } from '@microsoft/agent-framework';
 *
 * const client = new MockChatClient();
 *
 * // Blocking completion
 * const response = await client.complete([
 *   createUserMessage('Hello')
 * ]);
 * console.log(getTextContent(response)); // "Mock response"
 *
 * // Streaming completion
 * const stream = client.completeStream([
 *   createUserMessage('Hello')
 * ]);
 * for await (const event of stream) {
 *   console.log(event);
 * }
 * ```
 *
 * @example
 * ```typescript
 * // Custom response
 * const client = new MockChatClient({
 *   response: 'Custom mock response'
 * });
 *
 * const response = await client.complete([
 *   createUserMessage('Any question')
 * ]);
 * console.log(getTextContent(response)); // "Custom mock response"
 * ```
 */
export class MockChatClient implements ChatClientProtocol {
  private readonly defaultResponse: string;
  private readonly includeUsage: boolean;
  private readonly includeMetadata: boolean;

  /**
   * Create a new MockChatClient.
   *
   * @param options - Configuration options
   * @param options.response - Custom response text (default: "Mock response")
   * @param options.includeUsage - Whether to include usage events in streams (default: true)
   * @param options.includeMetadata - Whether to include metadata events in streams (default: true)
   */
  constructor(
    options: {
      response?: string;
      includeUsage?: boolean;
      includeMetadata?: boolean;
    } = {},
  ) {
    this.defaultResponse = options.response ?? 'Mock response';
    this.includeUsage = options.includeUsage ?? true;
    this.includeMetadata = options.includeMetadata ?? true;
  }

  /**
   * Complete a chat conversation with a mock response.
   *
   * Returns a canned assistant message. The response text can be customized
   * via constructor options or will default to "Mock response".
   *
   * @param messages - Input messages (used to calculate mock token count)
   * @param options - Completion options (currently unused by mock)
   * @returns Assistant message with mock response
   *
   * @example
   * ```typescript
   * const client = new MockChatClient();
   * const response = await client.complete([
   *   createUserMessage('Hello')
   * ]);
   * ```
   */
  async complete(messages: ChatMessage[], options?: ChatCompletionOptions): Promise<ChatMessage> {
    // Avoid unused parameter warnings
    void options;

    // Calculate mock token count based on input
    const promptTokens = this.estimateTokenCount(messages);

    // Return mock assistant message
    const response = createAssistantMessage(this.defaultResponse);

    // Add mock metadata
    response.metadata = {
      ...(response.metadata || {}),
      mockUsage: {
        promptTokens,
        completionTokens: this.estimateTokenCount([response]),
        totalTokens: promptTokens + this.estimateTokenCount([response]),
      },
      mockProvider: 'mock',
      mockModel: 'mock-model-v1',
    };

    return response;
  }

  /**
   * Stream a chat completion with mock events.
   *
   * Yields message deltas that spell out the response word by word,
   * followed by optional usage and metadata events.
   *
   * @param messages - Input messages (used to calculate mock token count)
   * @param options - Completion options (currently unused by mock)
   * @returns AsyncIterable yielding StreamEvent objects
   *
   * @example
   * ```typescript
   * const client = new MockChatClient();
   * const stream = client.completeStream([
   *   createUserMessage('Hello')
   * ]);
   *
   * for await (const event of stream) {
   *   if (isMessageDelta(event)) {
   *     process.stdout.write(getTextContent(event.delta));
   *   }
   * }
   * ```
   */
  async *completeStream(messages: ChatMessage[], options?: ChatCompletionOptions): AsyncIterable<StreamEvent> {
    // Avoid unused parameter warnings
    void options;

    // Calculate mock token counts
    const promptTokens = this.estimateTokenCount(messages);

    // Split response into words and emit deltas
    const words = this.defaultResponse.split(' ');
    for (let i = 0; i < words.length; i++) {
      const text = i === 0 ? words[i] : ` ${words[i]}`;
      yield {
        type: 'message_delta',
        delta: {
          role: MessageRole.Assistant,
          content: { type: 'text', text },
        },
      };
    }

    // Emit usage event if enabled
    if (this.includeUsage) {
      const completionTokens = Math.ceil(this.defaultResponse.length / 4); // Rough estimate
      const usage: UsageInfo = {
        promptTokens,
        completionTokens,
        totalTokens: promptTokens + completionTokens,
      };
      yield {
        type: 'usage',
        usage,
      };
    }

    // Emit metadata event if enabled
    if (this.includeMetadata) {
      yield {
        type: 'metadata',
        metadata: {
          provider: 'mock',
          modelId: 'mock-model-v1',
          finishReason: 'stop',
        },
      };
    }
  }

  /**
   * Estimate token count for messages (rough approximation).
   *
   * Uses a simple heuristic of ~4 characters per token.
   *
   * @param messages - Messages to count tokens for
   * @returns Estimated token count
   */
  private estimateTokenCount(messages: ChatMessage[]): number {
    const totalChars = messages.reduce((sum, msg) => {
      const text = getTextContent(msg);
      return sum + text.length;
    }, 0);
    // Rough estimate: ~4 characters per token
    return Math.ceil(totalChars / 4);
  }
}
