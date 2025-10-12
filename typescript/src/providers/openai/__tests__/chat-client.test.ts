/**
 * Tests for OpenAIChatClient
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import OpenAI from 'openai';
import { OpenAIChatClient } from '../chat-client.js';
import { createUserMessage, createSystemMessage, createToolMessage } from '../../../core/types/chat-message.js';
import { createTool } from '../../../core/tools/base-tool.js';
import { z } from 'zod';
import type { ChatCompletion, ChatCompletionChunk } from 'openai/resources/chat/completions';

describe('OpenAIChatClient', () => {
  let mockClient: OpenAI;

  beforeEach(() => {
    // Clear environment variables
    delete process.env.OPENAI_API_KEY;
    delete process.env.OPENAI_ORG_ID;

    // Create mock OpenAI client
    mockClient = {
      chat: {
        completions: {
          create: vi.fn(),
        },
      },
    } as unknown as OpenAI;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('constructor', () => {
    it('should create client with API key', () => {
      const client = new OpenAIChatClient({
        apiKey: 'sk-test-key',
        modelId: 'gpt-4',
      });

      expect(client).toBeInstanceOf(OpenAIChatClient);
    });

    it('should create client with environment variable API key', () => {
      process.env.OPENAI_API_KEY = 'sk-env-key';

      const client = new OpenAIChatClient({
        modelId: 'gpt-4',
      });

      expect(client).toBeInstanceOf(OpenAIChatClient);
    });

    it('should create client with provided OpenAI client', () => {
      const client = new OpenAIChatClient({
        client: mockClient,
        modelId: 'gpt-4',
      });

      expect(client).toBeInstanceOf(OpenAIChatClient);
    });

    it('should throw error when no API key is provided', () => {
      expect(() => {
        new OpenAIChatClient({ modelId: 'gpt-4' });
      }).toThrow('OpenAI API key is required');
    });

    it('should respect organization from config', () => {
      const client = new OpenAIChatClient({
        apiKey: 'sk-test-key',
        modelId: 'gpt-4',
        organization: 'org-123',
      });

      expect(client).toBeInstanceOf(OpenAIChatClient);
    });

    it('should respect organization from environment', () => {
      process.env.OPENAI_API_KEY = 'sk-env-key';
      process.env.OPENAI_ORG_ID = 'org-env';

      const client = new OpenAIChatClient({
        modelId: 'gpt-4',
      });

      expect(client).toBeInstanceOf(OpenAIChatClient);
    });

    it('should respect custom baseURL', () => {
      const client = new OpenAIChatClient({
        apiKey: 'sk-test-key',
        modelId: 'gpt-4',
        baseURL: 'https://custom.openai.com/v1',
      });

      expect(client).toBeInstanceOf(OpenAIChatClient);
    });

    it('should respect timeout and maxRetries', () => {
      const client = new OpenAIChatClient({
        apiKey: 'sk-test-key',
        modelId: 'gpt-4',
        timeout: 30000,
        maxRetries: 5,
      });

      expect(client).toBeInstanceOf(OpenAIChatClient);
    });
  });

  describe('complete', () => {
    it('should complete a simple text message', async () => {
      const mockCompletion: ChatCompletion = {
        id: 'chatcmpl-123',
        object: 'chat.completion',
        created: Math.floor(Date.now() / 1000),
        model: 'gpt-4',
        choices: [
          {
            index: 0,
            message: {
              role: 'assistant',
              content: 'Hello! How can I help you today?',
              refusal: null,
            },
            finish_reason: 'stop',
            logprobs: null,
          },
        ],
        usage: {
          prompt_tokens: 10,
          completion_tokens: 20,
          total_tokens: 30,
        },
      };

      vi.mocked(mockClient.chat.completions.create).mockResolvedValue(mockCompletion);

      const client = new OpenAIChatClient({
        client: mockClient,
        modelId: 'gpt-4',
      });

      const response = await client.complete([createUserMessage('Hello')]);

      expect(response.role).toBe('assistant');
      expect(response.content).toHaveLength(1);
      const contents = Array.isArray(response.content) ? response.content : [response.content];
      expect(contents[0]).toEqual({
        type: 'text',
        text: 'Hello! How can I help you today?',
      });
      expect(response.metadata?.finishReason).toBe('stop');
      expect(response.metadata?.usage).toEqual({
        promptTokens: 10,
        completionTokens: 20,
        totalTokens: 30,
      });
    });

    it('should complete with tool calls', async () => {
      const mockCompletion: ChatCompletion = {
        id: 'chatcmpl-456',
        object: 'chat.completion',
        created: Math.floor(Date.now() / 1000),
        model: 'gpt-4',
        choices: [
          {
            index: 0,
            message: {
              role: 'assistant',
              content: null,
              refusal: null,
              tool_calls: [
                {
                  id: 'call_123',
                  type: 'function',
                  function: {
                    name: 'get_weather',
                    arguments: '{"location":"Seattle"}',
                  },
                },
              ],
            },
            finish_reason: 'tool_calls',
            logprobs: null,
          },
        ],
        usage: {
          prompt_tokens: 15,
          completion_tokens: 25,
          total_tokens: 40,
        },
      };

      vi.mocked(mockClient.chat.completions.create).mockResolvedValue(mockCompletion);

      const weatherTool = createTool(
        'get_weather',
        'Get current weather',
        z.object({ location: z.string() }),
        async () => ({ temp: 72 })
      );

      const client = new OpenAIChatClient({
        client: mockClient,
        modelId: 'gpt-4',
      });

      const response = await client.complete(
        [createUserMessage('What is the weather in Seattle?')],
        { tools: [weatherTool] }
      );

      expect(response.role).toBe('assistant');
      expect(response.content).toHaveLength(1);
      const contents = Array.isArray(response.content) ? response.content : [response.content];
      expect(contents[0]).toEqual({
        type: 'function_call',
        callId: 'call_123',
        name: 'get_weather',
        arguments: '{"location":"Seattle"}',
      });
      expect(response.metadata?.finishReason).toBe('tool_calls');
    });

    it('should send tool messages correctly', async () => {
      const mockCompletion: ChatCompletion = {
        id: 'chatcmpl-789',
        object: 'chat.completion',
        created: Math.floor(Date.now() / 1000),
        model: 'gpt-4',
        choices: [
          {
            index: 0,
            message: {
              role: 'assistant',
              content: 'The temperature in Seattle is 72°F.',
              refusal: null,
            },
            finish_reason: 'stop',
            logprobs: null,
          },
        ],
        usage: {
          prompt_tokens: 20,
          completion_tokens: 10,
          total_tokens: 30,
        },
      };

      vi.mocked(mockClient.chat.completions.create).mockResolvedValue(mockCompletion);

      const client = new OpenAIChatClient({
        client: mockClient,
        modelId: 'gpt-4',
      });

      const response = await client.complete([
        createUserMessage('What is the weather?'),
        createToolMessage('call_123', { temp: 72, location: 'Seattle' }),
      ]);

      const contents = Array.isArray(response.content) ? response.content : [response.content];
      expect(contents[0]).toEqual({
        type: 'text',
        text: 'The temperature in Seattle is 72°F.',
      });

      // Verify that tool message was formatted correctly
      expect(mockClient.chat.completions.create).toHaveBeenCalledWith(
        expect.objectContaining({
          messages: expect.arrayContaining([
            expect.objectContaining({
              role: 'tool',
              tool_call_id: 'call_123',
              content: expect.stringContaining('temp'),
            }),
          ]),
        })
      );
    });

    it('should handle completion options', async () => {
      const mockCompletion: ChatCompletion = {
        id: 'chatcmpl-options',
        object: 'chat.completion',
        created: Math.floor(Date.now() / 1000),
        model: 'gpt-4',
        choices: [
          {
            index: 0,
            message: {
              role: 'assistant',
              content: 'Test response',
              refusal: null,
            },
            finish_reason: 'stop',
            logprobs: null,
          },
        ],
        usage: {
          prompt_tokens: 10,
          completion_tokens: 5,
          total_tokens: 15,
        },
      };

      vi.mocked(mockClient.chat.completions.create).mockResolvedValue(mockCompletion);

      const client = new OpenAIChatClient({
        client: mockClient,
        modelId: 'gpt-4',
      });

      await client.complete([createUserMessage('Test')], {
        temperature: 0.7,
        maxTokens: 500,
        topP: 0.9,
        frequencyPenalty: 0.5,
        presencePenalty: 0.5,
        stopSequences: ['END'],
        seed: 42,
      });

      expect(mockClient.chat.completions.create).toHaveBeenCalledWith(
        expect.objectContaining({
          temperature: 0.7,
          max_tokens: 500,
          top_p: 0.9,
          frequency_penalty: 0.5,
          presence_penalty: 0.5,
          stop: ['END'],
          seed: 42,
        })
      );
    });

    it('should override default model with options.modelId', async () => {
      const mockCompletion: ChatCompletion = {
        id: 'chatcmpl-model',
        object: 'chat.completion',
        created: Math.floor(Date.now() / 1000),
        model: 'gpt-3.5-turbo',
        choices: [
          {
            index: 0,
            message: {
              role: 'assistant',
              content: 'Test',
              refusal: null,
            },
            finish_reason: 'stop',
            logprobs: null,
          },
        ],
      };

      vi.mocked(mockClient.chat.completions.create).mockResolvedValue(mockCompletion);

      const client = new OpenAIChatClient({
        client: mockClient,
        modelId: 'gpt-4',
      });

      await client.complete([createUserMessage('Test')], {
        modelId: 'gpt-3.5-turbo',
      });

      expect(mockClient.chat.completions.create).toHaveBeenCalledWith(
        expect.objectContaining({
          model: 'gpt-3.5-turbo',
        })
      );
    });

    it('should throw error when no model is specified', async () => {
      const client = new OpenAIChatClient({
        client: mockClient,
      });

      await expect(client.complete([createUserMessage('Test')])).rejects.toThrow('Model ID is required');
    });

    it('should handle API errors gracefully', async () => {
      const apiError = new OpenAI.APIError(
        401,
        {
          error: {
            message: 'Invalid API key',
            type: 'invalid_request_error',
            code: 'invalid_api_key',
          },
        },
        'Invalid API key',
        new Headers()
      );

      vi.mocked(mockClient.chat.completions.create).mockRejectedValue(apiError);

      const client = new OpenAIChatClient({
        client: mockClient,
        modelId: 'gpt-4',
      });

      await expect(client.complete([createUserMessage('Test')])).rejects.toThrow(/OpenAI API error/);
    });

    it('should handle network errors', async () => {
      vi.mocked(mockClient.chat.completions.create).mockRejectedValue(new Error('Network error'));

      const client = new OpenAIChatClient({
        client: mockClient,
        modelId: 'gpt-4',
      });

      await expect(client.complete([createUserMessage('Test')])).rejects.toThrow(/OpenAI client error/);
    });
  });

  describe('completeStream', () => {
    it('should stream text deltas', async () => {
      const mockChunks: ChatCompletionChunk[] = [
        {
          id: 'chatcmpl-stream-1',
          object: 'chat.completion.chunk',
          created: Math.floor(Date.now() / 1000),
          model: 'gpt-4',
          choices: [
            {
              index: 0,
              delta: { role: 'assistant', content: 'Hello' },
              finish_reason: null,
              logprobs: null,
            },
          ],
        },
        {
          id: 'chatcmpl-stream-2',
          object: 'chat.completion.chunk',
          created: Math.floor(Date.now() / 1000),
          model: 'gpt-4',
          choices: [
            {
              index: 0,
              delta: { content: ' world' },
              finish_reason: null,
              logprobs: null,
            },
          ],
        },
        {
          id: 'chatcmpl-stream-3',
          object: 'chat.completion.chunk',
          created: Math.floor(Date.now() / 1000),
          model: 'gpt-4',
          choices: [
            {
              index: 0,
              delta: { content: '!' },
              finish_reason: 'stop',
              logprobs: null,
            },
          ],
        },
        {
          id: 'chatcmpl-stream-4',
          object: 'chat.completion.chunk',
          created: Math.floor(Date.now() / 1000),
          model: 'gpt-4',
          choices: [],
          usage: {
            prompt_tokens: 10,
            completion_tokens: 5,
            total_tokens: 15,
          },
        },
      ];

      // Create async generator
      async function* streamGenerator() {
        for (const chunk of mockChunks) {
          yield chunk;
        }
      }

      vi.mocked(mockClient.chat.completions.create).mockResolvedValue(streamGenerator() as any);

      const client = new OpenAIChatClient({
        client: mockClient,
        modelId: 'gpt-4',
      });

      const stream = client.completeStream([createUserMessage('Say hello')]);

      const events = [];
      for await (const event of stream) {
        events.push(event);
      }

      // Check message deltas
      const messageDeltas = events.filter((e) => e.type === 'message_delta');
      expect(messageDeltas).toHaveLength(3);
      expect(messageDeltas[0].type === 'message_delta' && messageDeltas[0].delta.role).toBe('assistant');
      if (messageDeltas[0].type === 'message_delta' && messageDeltas[0].delta.content) {
        const contents = Array.isArray(messageDeltas[0].delta.content)
          ? messageDeltas[0].delta.content
          : [messageDeltas[0].delta.content];
        expect(contents[0]).toEqual({
          type: 'text',
          text: 'Hello',
        });
      }

      // Check usage event
      const usageEvents = events.filter((e) => e.type === 'usage');
      expect(usageEvents).toHaveLength(1);
      expect(usageEvents[0].type === 'usage' && usageEvents[0].usage).toEqual({
        promptTokens: 10,
        completionTokens: 5,
        totalTokens: 15,
      });

      // Check metadata event
      const metadataEvents = events.filter((e) => e.type === 'metadata');
      expect(metadataEvents).toHaveLength(1);
      expect(metadataEvents[0].type === 'metadata' && metadataEvents[0].metadata).toEqual({
        provider: 'openai',
        modelId: 'gpt-4',
        finishReason: 'stop',
      });
    });

    it('should stream tool call deltas', async () => {
      const mockChunks: ChatCompletionChunk[] = [
        {
          id: 'chatcmpl-tool-1',
          object: 'chat.completion.chunk',
          created: Math.floor(Date.now() / 1000),
          model: 'gpt-4',
          choices: [
            {
              index: 0,
              delta: {
                role: 'assistant',
                tool_calls: [
                  {
                    index: 0,
                    id: 'call_123',
                    type: 'function',
                    function: {
                      name: 'get_weather',
                      arguments: '',
                    },
                  },
                ],
              },
              finish_reason: null,
              logprobs: null,
            },
          ],
        },
        {
          id: 'chatcmpl-tool-2',
          object: 'chat.completion.chunk',
          created: Math.floor(Date.now() / 1000),
          model: 'gpt-4',
          choices: [
            {
              index: 0,
              delta: {
                tool_calls: [
                  {
                    index: 0,
                    function: {
                      arguments: '{"location"',
                    },
                  },
                ],
              },
              finish_reason: null,
              logprobs: null,
            },
          ],
        },
        {
          id: 'chatcmpl-tool-3',
          object: 'chat.completion.chunk',
          created: Math.floor(Date.now() / 1000),
          model: 'gpt-4',
          choices: [
            {
              index: 0,
              delta: {
                tool_calls: [
                  {
                    index: 0,
                    function: {
                      arguments: ':"Seattle"}',
                    },
                  },
                ],
              },
              finish_reason: 'tool_calls',
              logprobs: null,
            },
          ],
        },
      ];

      async function* streamGenerator() {
        for (const chunk of mockChunks) {
          yield chunk;
        }
      }

      vi.mocked(mockClient.chat.completions.create).mockResolvedValue(streamGenerator() as any);

      const weatherTool = createTool(
        'get_weather',
        'Get weather',
        z.object({ location: z.string() }),
        async () => ({ temp: 72 })
      );

      const client = new OpenAIChatClient({
        client: mockClient,
        modelId: 'gpt-4',
      });

      const stream = client.completeStream(
        [createUserMessage('Weather in Seattle?')],
        { tools: [weatherTool] }
      );

      const events = [];
      for await (const event of stream) {
        events.push(event);
      }

      // Find tool call events
      const toolCallEvents = events.filter((e) => {
        if (e.type === 'message_delta' && e.delta.content) {
          const contents = Array.isArray(e.delta.content) ? e.delta.content : [e.delta.content];
          return contents.some((c) => c.type === 'function_call');
        }
        return false;
      });

      expect(toolCallEvents.length).toBeGreaterThan(0);

      // Check that we have complete tool call info
      const lastToolCallEvent = toolCallEvents[toolCallEvents.length - 1];
      if (lastToolCallEvent.type === 'message_delta' && lastToolCallEvent.delta.content) {
        const contents = Array.isArray(lastToolCallEvent.delta.content)
          ? lastToolCallEvent.delta.content
          : [lastToolCallEvent.delta.content];
        const toolCall = contents.find((c) => c.type === 'function_call');
        expect(toolCall).toBeDefined();
        if (toolCall && toolCall.type === 'function_call') {
          expect(toolCall.callId).toBe('call_123');
          expect(toolCall.name).toBe('get_weather');
        }
      }
    });

    it('should handle streaming errors', async () => {
      vi.mocked(mockClient.chat.completions.create).mockRejectedValue(new Error('Stream error'));

      const client = new OpenAIChatClient({
        client: mockClient,
        modelId: 'gpt-4',
      });

      const stream = client.completeStream([createUserMessage('Test')]);

      await expect(async () => {
        for await (const _event of stream) {
          // Should throw before yielding any events
        }
      }).rejects.toThrow(/OpenAI client error/);
    });

    it('should include stream_options in request', async () => {
      async function* emptyGenerator() {
        // Empty generator
      }

      vi.mocked(mockClient.chat.completions.create).mockResolvedValue(emptyGenerator() as any);

      const client = new OpenAIChatClient({
        client: mockClient,
        modelId: 'gpt-4',
      });

      const stream = client.completeStream([createUserMessage('Test')]);

      // Start consuming stream
      const iterator = stream[Symbol.asyncIterator]();
      await iterator.next();

      expect(mockClient.chat.completions.create).toHaveBeenCalledWith(
        expect.objectContaining({
          stream: true,
          stream_options: { include_usage: true },
        })
      );
    });
  });

  describe('message conversion', () => {
    it('should convert system messages', async () => {
      const mockCompletion: ChatCompletion = {
        id: 'test',
        object: 'chat.completion',
        created: Date.now(),
        model: 'gpt-4',
        choices: [
          {
            index: 0,
            message: { role: 'assistant', content: 'OK', refusal: null },
            finish_reason: 'stop',
            logprobs: null,
          },
        ],
      };

      vi.mocked(mockClient.chat.completions.create).mockResolvedValue(mockCompletion);

      const client = new OpenAIChatClient({
        client: mockClient,
        modelId: 'gpt-4',
      });

      await client.complete([createSystemMessage('You are a helpful assistant')]);

      expect(mockClient.chat.completions.create).toHaveBeenCalledWith(
        expect.objectContaining({
          messages: expect.arrayContaining([
            expect.objectContaining({
              role: 'system',
              content: 'You are a helpful assistant',
            }),
          ]),
        })
      );
    });

    it('should handle parallel tool calls option', async () => {
      const mockCompletion: ChatCompletion = {
        id: 'test',
        object: 'chat.completion',
        created: Date.now(),
        model: 'gpt-4',
        choices: [
          {
            index: 0,
            message: { role: 'assistant', content: 'OK', refusal: null },
            finish_reason: 'stop',
            logprobs: null,
          },
        ],
      };

      vi.mocked(mockClient.chat.completions.create).mockResolvedValue(mockCompletion);

      const tool = createTool('test', 'Test tool', z.object({}), async () => ({}));

      const client = new OpenAIChatClient({
        client: mockClient,
        modelId: 'gpt-4',
      });

      await client.complete([createUserMessage('Test')], {
        tools: [tool],
        parallelToolCalls: false,
      });

      expect(mockClient.chat.completions.create).toHaveBeenCalledWith(
        expect.objectContaining({
          parallel_tool_calls: false,
        })
      );
    });
  });
});
