/**
 * OpenAI Chat Client
 *
 * Implementation of ChatClientProtocol for OpenAI's Chat Completions API.
 * Supports both blocking and streaming completions, tool calling, and full
 * OpenAI API parameter configuration.
 *
 * @module providers/openai/chat-client
 */

import OpenAI from 'openai';
import type {
  ChatCompletion,
  ChatCompletionMessageParam,
  ChatCompletionTool,
  ChatCompletionCreateParamsNonStreaming,
  ChatCompletionCreateParamsStreaming,
} from 'openai/resources/chat/completions';
import type { ChatClientProtocol } from '../../core/chat-client/protocol.js';
import type { ChatCompletionOptions, StreamEvent } from '../../core/chat-client/types.js';
import type {
  ChatMessage,
  Content,
  FunctionCallContent,
} from '../../core/types/chat-message.js';
import { MessageRole } from '../../core/types/chat-message.js';
import { createToolSchema } from '../../core/tools/schema.js';
import type { AITool } from '../../core/tools/base-tool.js';

/**
 * Configuration options for OpenAIChatClient.
 *
 * @example
 * ```typescript
 * const config: OpenAIChatClientConfig = {
 *   apiKey: process.env.OPENAI_API_KEY,
 *   modelId: 'gpt-4',
 *   organization: 'org-123',
 *   baseURL: 'https://api.openai.com/v1',
 * };
 * ```
 */
export interface OpenAIChatClientConfig {
  /**
   * OpenAI API key. Required unless client is provided.
   * Can also be set via OPENAI_API_KEY environment variable.
   */
  apiKey?: string;

  /**
   * Default model ID to use for completions.
   * Can be overridden in ChatCompletionOptions.
   * Examples: 'gpt-4', 'gpt-4-turbo', 'gpt-3.5-turbo'
   */
  modelId?: string;

  /**
   * OpenAI organization ID (optional).
   * Can also be set via OPENAI_ORG_ID environment variable.
   */
  organization?: string;

  /**
   * Base URL for the OpenAI API (optional).
   * Defaults to https://api.openai.com/v1
   */
  baseURL?: string;

  /**
   * Pre-configured OpenAI client instance (optional).
   * If provided, apiKey and other options are ignored.
   */
  client?: OpenAI;

  /**
   * Default headers to include in all requests (optional).
   */
  defaultHeaders?: Record<string, string>;

  /**
   * Request timeout in milliseconds (optional).
   * Defaults to 60000 (60 seconds).
   */
  timeout?: number;

  /**
   * Maximum number of retries for failed requests (optional).
   * Defaults to 2.
   */
  maxRetries?: number;
}

/**
 * OpenAI Chat Client implementing ChatClientProtocol.
 *
 * Provides a standardized interface to OpenAI's Chat Completions API with support
 * for both blocking and streaming completions, tool calling, and comprehensive
 * error handling.
 *
 * @example
 * ```typescript
 * import { OpenAIChatClient, createUserMessage } from '@microsoft/agent-framework';
 *
 * // Initialize with API key
 * const client = new OpenAIChatClient({
 *   apiKey: process.env.OPENAI_API_KEY,
 *   modelId: 'gpt-4',
 * });
 *
 * // Simple completion
 * const response = await client.complete([
 *   createUserMessage('What is 2+2?')
 * ]);
 * console.log(response.content); // "4"
 *
 * // Streaming completion
 * const stream = client.completeStream([
 *   createUserMessage('Tell me a story')
 * ]);
 *
 * for await (const event of stream) {
 *   if (event.type === 'message_delta') {
 *     process.stdout.write(getTextContent(event.delta));
 *   }
 * }
 * ```
 *
 * @example
 * ```typescript
 * // With tools
 * import { createTool } from '@microsoft/agent-framework';
 * import { z } from 'zod';
 *
 * const weatherTool = createTool(
 *   'get_weather',
 *   'Get current weather for a location',
 *   z.object({ location: z.string() }),
 *   async ({ location }) => ({ temp: 72, location })
 * );
 *
 * const response = await client.complete(
 *   [createUserMessage('What is the weather in Seattle?')],
 *   { tools: [weatherTool] }
 * );
 * ```
 */
export class OpenAIChatClient implements ChatClientProtocol {
  private readonly client: OpenAI;
  private readonly defaultModelId?: string;

  /**
   * Create a new OpenAI chat client.
   *
   * @param config - Configuration options for the client
   * @throws {Error} If neither apiKey nor client is provided
   * @throws {Error} If apiKey is invalid
   *
   * @example
   * ```typescript
   * // Using API key from environment
   * const client = new OpenAIChatClient({
   *   modelId: 'gpt-4',
   * });
   *
   * // Using explicit API key
   * const client = new OpenAIChatClient({
   *   apiKey: 'sk-...',
   *   modelId: 'gpt-4',
   *   organization: 'org-123',
   * });
   *
   * // Using custom client
   * const customClient = new OpenAI({ apiKey: 'sk-...' });
   * const client = new OpenAIChatClient({
   *   client: customClient,
   *   modelId: 'gpt-4',
   * });
   * ```
   */
  constructor(config: OpenAIChatClientConfig = {}) {
    if (config.client) {
      this.client = config.client;
    } else {
      const apiKey = config.apiKey || process.env.OPENAI_API_KEY;
      if (!apiKey) {
        throw new Error(
          'OpenAI API key is required. Provide via config.apiKey or OPENAI_API_KEY environment variable.'
        );
      }

      this.client = new OpenAI({
        apiKey,
        organization: config.organization || process.env.OPENAI_ORG_ID,
        baseURL: config.baseURL,
        defaultHeaders: config.defaultHeaders,
        timeout: config.timeout ?? 60000,
        maxRetries: config.maxRetries ?? 2,
      });
    }

    this.defaultModelId = config.modelId;
  }

  /**
   * Complete a chat conversation with the OpenAI API.
   *
   * Sends messages to OpenAI and returns the complete assistant response.
   * This is a blocking operation that waits for the full response.
   *
   * @param messages - Conversation history
   * @param options - Optional completion settings (model, temperature, tools, etc.)
   * @returns Promise resolving to the assistant's response message
   * @throws {Error} If the API request fails or returns an error
   *
   * @example
   * ```typescript
   * const response = await client.complete([
   *   createSystemMessage('You are a helpful assistant.'),
   *   createUserMessage('What is TypeScript?')
   * ], {
   *   temperature: 0.7,
   *   maxTokens: 500,
   * });
   * ```
   */
  async complete(messages: ChatMessage[], options?: ChatCompletionOptions): Promise<ChatMessage> {
    try {
      const params = this.buildCompletionParams(messages, options, false);
      const completion = await this.client.chat.completions.create(
        params as unknown as ChatCompletionCreateParamsNonStreaming
      );
      return this.convertCompletionToMessage(completion as ChatCompletion);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  /**
   * Stream a chat completion with real-time updates.
   *
   * Sends messages to OpenAI and returns an async iterable that yields events
   * as they arrive. Events include message deltas, usage info, and metadata.
   *
   * @param messages - Conversation history
   * @param options - Optional completion settings (model, temperature, tools, etc.)
   * @returns AsyncIterable yielding StreamEvent objects
   * @throws {Error} If the API request fails or returns an error
   *
   * @example
   * ```typescript
   * const stream = client.completeStream([
   *   createUserMessage('Tell me a story')
   * ]);
   *
   * for await (const event of stream) {
   *   if (event.type === 'message_delta') {
   *     process.stdout.write(getTextContent(event.delta));
   *   } else if (event.type === 'usage') {
   *     console.log(`\nTokens: ${event.usage.totalTokens}`);
   *   }
   * }
   * ```
   */
  async *completeStream(
    messages: ChatMessage[],
    options?: ChatCompletionOptions
  ): AsyncIterable<StreamEvent> {
    try {
      const params = this.buildCompletionParams(messages, options, true);
      const stream = await this.client.chat.completions.create(
        params as unknown as ChatCompletionCreateParamsStreaming
      );

      // Track accumulated content for delta calculation
      const accumulatedContent: Map<number, string> = new Map();
      const accumulatedToolCalls: Map<number, Map<number, Partial<FunctionCallContent>>> = new Map();

      for await (const chunk of stream) {
        // Handle usage information (typically at the end)
        if (chunk.usage) {
          yield {
            type: 'usage',
            usage: {
              promptTokens: chunk.usage.prompt_tokens,
              completionTokens: chunk.usage.completion_tokens,
              totalTokens: chunk.usage.total_tokens,
            },
          };
        }

        // Process each choice in the chunk
        for (const choice of chunk.choices) {
          const delta = choice.delta;
          const index = choice.index;

          // Build message delta
          const messageDelta: Partial<ChatMessage> = {
            role: delta.role as MessageRole | undefined,
            content: [],
          };

          // Handle text content delta
          if (delta.content) {
            const previousContent = accumulatedContent.get(index) || '';
            accumulatedContent.set(index, previousContent + delta.content);

            (messageDelta.content as Content[]).push({
              type: 'text',
              text: delta.content,
            });
          }

          // Handle tool calls delta
          if (delta.tool_calls) {
            if (!accumulatedToolCalls.has(index)) {
              accumulatedToolCalls.set(index, new Map());
            }
            const toolCallsMap = accumulatedToolCalls.get(index)!;

            for (const toolCallDelta of delta.tool_calls) {
              const toolIndex = toolCallDelta.index;

              if (!toolCallsMap.has(toolIndex)) {
                toolCallsMap.set(toolIndex, {
                  callId: toolCallDelta.id || '',
                  name: '',
                  arguments: '',
                });
              }

              const accumulated = toolCallsMap.get(toolIndex)!;

              if (toolCallDelta.id) {
                accumulated.callId = toolCallDelta.id;
              }
              if (toolCallDelta.function?.name) {
                accumulated.name = toolCallDelta.function.name;
              }
              if (toolCallDelta.function?.arguments) {
                accumulated.arguments = (accumulated.arguments || '') + toolCallDelta.function.arguments;
              }

              // Only yield complete tool calls
              if (accumulated.callId && accumulated.name) {
                (messageDelta.content as Content[]).push({
                  type: 'function_call',
                  callId: accumulated.callId,
                  name: accumulated.name,
                  arguments: accumulated.arguments || '',
                });
              }
            }
          }

          // Yield message delta if there's any content
          if ((messageDelta.content as Content[]).length > 0 || messageDelta.role) {
            yield {
              type: 'message_delta',
              delta: messageDelta,
            };
          }

          // Yield metadata when the stream finishes
          if (choice.finish_reason) {
            yield {
              type: 'metadata',
              metadata: {
                provider: 'openai',
                modelId: chunk.model,
                finishReason: choice.finish_reason,
              },
            };
          }
        }
      }
    } catch (error) {
      throw this.handleError(error);
    }
  }

  /**
   * Build OpenAI API request parameters from messages and options.
   *
   * @param messages - Chat messages to send
   * @param options - Optional completion settings
   * @param stream - Whether to enable streaming
   * @returns OpenAI API request parameters
   * @throws {Error} If no model ID is specified
   */
  private buildCompletionParams(
    messages: ChatMessage[],
    options?: ChatCompletionOptions,
    stream = false
  ): Record<string, unknown> {
    const modelId = options?.modelId || this.defaultModelId;
    if (!modelId) {
      throw new Error('Model ID is required. Provide via config.modelId or options.modelId.');
    }

    // Convert messages to OpenAI format
    const openaiMessages = this.convertMessagesToOpenAI(messages);

    // Build base parameters
    const params: Record<string, unknown> = {
      model: modelId,
      messages: openaiMessages,
      stream,
    };

    // Add stream options for usage tracking
    if (stream) {
      params.stream_options = { include_usage: true };
    }

    // Add optional parameters
    if (options) {
      if (options.temperature !== undefined) params.temperature = options.temperature;
      if (options.maxTokens !== undefined) params.max_tokens = options.maxTokens;
      if (options.topP !== undefined) params.top_p = options.topP;
      if (options.frequencyPenalty !== undefined) params.frequency_penalty = options.frequencyPenalty;
      if (options.presencePenalty !== undefined) params.presence_penalty = options.presencePenalty;
      if (options.stopSequences !== undefined) params.stop = options.stopSequences;
      if (options.seed !== undefined) params.seed = options.seed;

      // Add tools if provided
      if (options.tools && options.tools.length > 0) {
        params.tools = this.convertToolsToOpenAI(options.tools);
        if (options.parallelToolCalls !== undefined) {
          params.parallel_tool_calls = options.parallelToolCalls;
        }
      }

      // Add metadata
      if (options.metadata) {
        params.metadata = options.metadata;
      }
    }

    return params;
  }

  /**
   * Convert framework messages to OpenAI message format.
   *
   * @param messages - Framework chat messages
   * @returns OpenAI API message format
   */
  private convertMessagesToOpenAI(messages: ChatMessage[]): ChatCompletionMessageParam[] {
    return messages.map((message): ChatCompletionMessageParam => {
      const contents = Array.isArray(message.content) ? message.content : [message.content];

      // Handle tool role messages
      if (message.role === 'tool') {
        const functionResult = contents.find((c) => c.type === 'function_result');
        if (functionResult && functionResult.type === 'function_result') {
          return {
            role: 'tool',
            tool_call_id: functionResult.callId,
            content: functionResult.error
              ? `Error: ${functionResult.error.message}`
              : JSON.stringify(functionResult.result),
          };
        }
      }

      // Check if message contains tool calls
      const toolCalls = contents.filter((c) => c.type === 'function_call');
      if (toolCalls.length > 0) {
        return {
          role: 'assistant',
          tool_calls: toolCalls.map((tc) => {
            if (tc.type !== 'function_call') throw new Error('Invalid tool call content');
            return {
              id: tc.callId,
              type: 'function' as const,
              function: {
                name: tc.name,
                arguments: tc.arguments,
              },
            };
          }),
        };
      }

      // Handle regular messages
      const textContents = contents.filter((c) => c.type === 'text');
      const imageContents = contents.filter((c) => c.type === 'image');

      // Multi-modal message
      if (textContents.length > 0 && imageContents.length > 0) {
        const content = [
          ...textContents.map((c) => {
            if (c.type !== 'text') throw new Error('Invalid text content');
            return {
              type: 'text' as const,
              text: c.text,
            };
          }),
          ...imageContents.map((c) => {
            if (c.type !== 'image') throw new Error('Invalid image content');
            return {
              type: 'image_url' as const,
              image_url: {
                url: c.url,
                detail: c.detail,
              },
            };
          }),
        ];

        return {
          role: message.role as 'user' | 'assistant' | 'system',
          content,
          ...(message.name && { name: message.name }),
        } as ChatCompletionMessageParam;
      }

      // Text-only message
      const textContent = textContents.map((c) => {
        if (c.type !== 'text') throw new Error('Invalid text content');
        return c.text;
      }).join('\n');

      return {
        role: message.role as 'user' | 'assistant' | 'system',
        content: textContent,
        ...(message.name && { name: message.name }),
      } as ChatCompletionMessageParam;
    });
  }

  /**
   * Convert framework tools to OpenAI tool format.
   *
   * @param tools - Framework AI tools
   * @returns OpenAI tool format
   */
  private convertToolsToOpenAI(tools: readonly AITool[]): ChatCompletionTool[] {
    return tools.map((tool) => {
      const schema = createToolSchema(tool as AITool);
      return {
        type: 'function',
        function: {
          name: schema.function.name,
          description: schema.function.description,
          parameters: schema.function.parameters,
        },
      };
    });
  }

  /**
   * Convert OpenAI completion response to framework ChatMessage.
   *
   * @param completion - OpenAI completion response
   * @returns Framework chat message
   */
  private convertCompletionToMessage(completion: ChatCompletion): ChatMessage {
    const choice = completion.choices[0];
    if (!choice) {
      throw new Error('No choices returned from OpenAI API');
    }

    const message = choice.message;
    const contents: Content[] = [];

    // Add text content
    if (message.content) {
      contents.push({
        type: 'text',
        text: message.content,
      });
    }

    // Add tool calls
    if (message.tool_calls && message.tool_calls.length > 0) {
      for (const toolCall of message.tool_calls) {
        if (toolCall.type === 'function') {
          contents.push({
            type: 'function_call',
            callId: toolCall.id,
            name: toolCall.function.name,
            arguments: toolCall.function.arguments,
          });
        }
      }
    }

    return {
      role: MessageRole.Assistant,
      content: contents,
      timestamp: new Date(),
      metadata: {
        modelId: completion.model,
        finishReason: choice.finish_reason,
        usage: {
          promptTokens: completion.usage?.prompt_tokens,
          completionTokens: completion.usage?.completion_tokens,
          totalTokens: completion.usage?.total_tokens,
        },
      },
    };
  }

  /**
   * Handle and transform OpenAI API errors.
   *
   * @param error - Error from OpenAI API
   * @returns Transformed error with descriptive message
   */
  private handleError(error: unknown): Error {
    if (error instanceof OpenAI.APIError) {
      return new Error(
        `OpenAI API error (${error.status}): ${error.message}\n` +
          `Type: ${error.type}\n` +
          `Code: ${error.code || 'N/A'}`
      );
    }

    if (error instanceof Error) {
      return new Error(`OpenAI client error: ${error.message}`);
    }

    return new Error(`Unknown error: ${String(error)}`);
  }
}
