/**
 * Tests for ChatClientProtocol and related types.
 *
 * Comprehensive test coverage for the chat client protocol interface,
 * types, type guards, and mock implementation.
 */

import { describe, it, expect } from 'vitest';
import {
  ChatClientProtocol,
  MockChatClient,
  isMessageDelta,
  isUsageEvent,
  isMetadataEvent,
  type ChatCompletionOptions,
  type UsageInfo,
  type ProviderMetadata,
  type StreamEvent,
  type MessageDeltaEvent,
  type UsageEvent,
  type MetadataEvent,
} from '../index';
import { createUserMessage, createAssistantMessage, getTextContent, MessageRole } from '../../types/chat-message';

describe('ChatClientProtocol', () => {
  describe('interface compliance', () => {
    it('should allow MockChatClient to implement ChatClientProtocol', () => {
      const client: ChatClientProtocol = new MockChatClient();
      expect(client).toBeDefined();
      expect(typeof client.complete).toBe('function');
      expect(typeof client.completeStream).toBe('function');
    });

    it('should support structural typing (duck typing)', () => {
      // Create a custom implementation without explicit interface declaration
      const customClient = {
        async complete() {
          return createAssistantMessage('Custom response');
        },
        async *completeStream() {
          yield { type: 'message_delta' as const, delta: {} };
        },
      };

      // TypeScript should accept this due to structural typing
      const client: ChatClientProtocol = customClient as ChatClientProtocol;
      expect(client).toBeDefined();
    });
  });

  describe('ChatCompletionOptions', () => {
    it('should extend AISettings', () => {
      const options: ChatCompletionOptions = {
        modelId: 'gpt-4',
        temperature: 0.7,
        maxTokens: 2000,
      };
      expect(options.modelId).toBe('gpt-4');
      expect(options.temperature).toBe(0.7);
      expect(options.maxTokens).toBe(2000);
    });

    it('should support all AISettings fields', () => {
      const options: ChatCompletionOptions = {
        modelId: 'gpt-4',
        temperature: 0.8,
        topP: 0.9,
        maxTokens: 1500,
        stopSequences: ['END', 'STOP'],
        presencePenalty: 0.5,
        frequencyPenalty: 0.3,
        seed: 42,
        responseFormat: { type: 'json_object' },
        streamOptions: { includeUsage: true },
      };
      expect(options.modelId).toBe('gpt-4');
      expect(options.temperature).toBe(0.8);
      expect(options.topP).toBe(0.9);
      expect(options.maxTokens).toBe(1500);
      expect(options.stopSequences).toEqual(['END', 'STOP']);
      expect(options.presencePenalty).toBe(0.5);
      expect(options.frequencyPenalty).toBe(0.3);
      expect(options.seed).toBe(42);
      expect(options.responseFormat?.type).toBe('json_object');
      expect(options.streamOptions?.includeUsage).toBe(true);
    });

    it('should support chat-specific fields', () => {
      const options: ChatCompletionOptions = {
        tools: [{ name: 'calculator', description: 'Math operations' }],
        parallelToolCalls: true,
        serviceThreadId: 'thread_123',
        additionalInstructions: 'Be concise',
        metadata: { userId: 'user_456', sessionId: 'session_789' },
      };
      expect(options.tools).toHaveLength(1);
      expect(options.tools![0].name).toBe('calculator');
      expect(options.parallelToolCalls).toBe(true);
      expect(options.serviceThreadId).toBe('thread_123');
      expect(options.additionalInstructions).toBe('Be concise');
      expect(options.metadata?.userId).toBe('user_456');
    });

    it('should work with only AISettings fields', () => {
      const options: ChatCompletionOptions = {
        temperature: 0.5,
      };
      expect(options.temperature).toBe(0.5);
      expect(options.tools).toBeUndefined();
    });

    it('should work with only chat-specific fields', () => {
      const options: ChatCompletionOptions = {
        tools: [{ name: 'search' }],
        parallelToolCalls: false,
      };
      expect(options.tools).toHaveLength(1);
      expect(options.parallelToolCalls).toBe(false);
      expect(options.temperature).toBeUndefined();
    });

    it('should support all fields combined', () => {
      const options: ChatCompletionOptions = {
        modelId: 'gpt-4',
        temperature: 0.7,
        maxTokens: 2000,
        tools: [{ name: 'weather' }],
        parallelToolCalls: true,
        serviceThreadId: 'thread_abc',
        additionalInstructions: 'Use metric units',
        metadata: { locale: 'en-US' },
      };
      expect(options.modelId).toBe('gpt-4');
      expect(options.tools).toHaveLength(1);
      expect(options.metadata?.locale).toBe('en-US');
    });
  });

  describe('UsageInfo', () => {
    it('should contain all required token fields', () => {
      const usage: UsageInfo = {
        promptTokens: 10,
        completionTokens: 25,
        totalTokens: 35,
      };
      expect(usage.promptTokens).toBe(10);
      expect(usage.completionTokens).toBe(25);
      expect(usage.totalTokens).toBe(35);
    });

    it('should calculate totalTokens correctly', () => {
      const usage: UsageInfo = {
        promptTokens: 100,
        completionTokens: 200,
        totalTokens: 300,
      };
      expect(usage.totalTokens).toBe(usage.promptTokens + usage.completionTokens);
    });

    it('should work with zero tokens', () => {
      const usage: UsageInfo = {
        promptTokens: 0,
        completionTokens: 0,
        totalTokens: 0,
      };
      expect(usage.totalTokens).toBe(0);
    });
  });

  describe('ProviderMetadata', () => {
    it('should contain required fields', () => {
      const metadata: ProviderMetadata = {
        provider: 'openai',
        modelId: 'gpt-4-0613',
      };
      expect(metadata.provider).toBe('openai');
      expect(metadata.modelId).toBe('gpt-4-0613');
    });

    it('should support optional finishReason', () => {
      const metadata: ProviderMetadata = {
        provider: 'openai',
        modelId: 'gpt-4',
        finishReason: 'stop',
      };
      expect(metadata.finishReason).toBe('stop');
    });

    it('should support provider-specific fields', () => {
      const metadata: ProviderMetadata = {
        provider: 'azure-openai',
        modelId: 'gpt-4',
        finishReason: 'length',
        requestId: 'req_abc123',
        deployment: 'my-deployment',
        region: 'eastus',
      };
      expect(metadata.requestId).toBe('req_abc123');
      expect(metadata.deployment).toBe('my-deployment');
      expect(metadata.region).toBe('eastus');
    });

    it('should support different providers', () => {
      const providers = ['openai', 'azure-openai', 'anthropic', 'google'];
      providers.forEach((provider) => {
        const metadata: ProviderMetadata = {
          provider,
          modelId: 'some-model',
        };
        expect(metadata.provider).toBe(provider);
      });
    });

    it('should support different finish reasons', () => {
      const finishReasons = ['stop', 'length', 'tool_calls', 'content_filter'];
      finishReasons.forEach((reason) => {
        const metadata: ProviderMetadata = {
          provider: 'openai',
          modelId: 'gpt-4',
          finishReason: reason,
        };
        expect(metadata.finishReason).toBe(reason);
      });
    });
  });

  describe('StreamEvent type guards', () => {
    it('should identify message_delta events correctly', () => {
      const event: MessageDeltaEvent = {
        type: 'message_delta',
        delta: { content: { type: 'text', text: 'Hello' } },
      };
      expect(isMessageDelta(event)).toBe(true);
      expect(isUsageEvent(event)).toBe(false);
      expect(isMetadataEvent(event)).toBe(false);
    });

    it('should identify usage events correctly', () => {
      const event: UsageEvent = {
        type: 'usage',
        usage: { promptTokens: 10, completionTokens: 20, totalTokens: 30 },
      };
      expect(isUsageEvent(event)).toBe(true);
      expect(isMessageDelta(event)).toBe(false);
      expect(isMetadataEvent(event)).toBe(false);
    });

    it('should identify metadata events correctly', () => {
      const event: MetadataEvent = {
        type: 'metadata',
        metadata: { provider: 'openai', modelId: 'gpt-4' },
      };
      expect(isMetadataEvent(event)).toBe(true);
      expect(isMessageDelta(event)).toBe(false);
      expect(isUsageEvent(event)).toBe(false);
    });

    it('should work with StreamEvent union type', () => {
      const events: StreamEvent[] = [
        { type: 'message_delta', delta: {} },
        { type: 'usage', usage: { promptTokens: 1, completionTokens: 2, totalTokens: 3 } },
        { type: 'metadata', metadata: { provider: 'test', modelId: 'test-model' } },
      ];

      expect(isMessageDelta(events[0])).toBe(true);
      expect(isUsageEvent(events[1])).toBe(true);
      expect(isMetadataEvent(events[2])).toBe(true);
    });
  });

  describe('MockChatClient', () => {
    describe('complete()', () => {
      it('should return an assistant message', async () => {
        const client = new MockChatClient();
        const response = await client.complete([createUserMessage('Hello')]);

        expect(response.role).toBe(MessageRole.Assistant);
        expect(getTextContent(response)).toBe('Mock response');
      });

      it('should return custom response text', async () => {
        const client = new MockChatClient({ response: 'Custom test response' });
        const response = await client.complete([createUserMessage('Hello')]);

        expect(getTextContent(response)).toBe('Custom test response');
      });

      it('should handle empty message array', async () => {
        const client = new MockChatClient();
        const response = await client.complete([]);

        expect(response).toBeDefined();
        expect(response.role).toBe(MessageRole.Assistant);
      });

      it('should handle options parameter', async () => {
        const client = new MockChatClient();
        const options: ChatCompletionOptions = {
          temperature: 0.5,
          maxTokens: 100,
        };
        const response = await client.complete([createUserMessage('Hello')], options);

        expect(response).toBeDefined();
      });

      it('should include mock usage in metadata', async () => {
        const client = new MockChatClient();
        const response = await client.complete([createUserMessage('Hello world')]);

        expect(response.metadata).toBeDefined();
        expect(response.metadata?.mockUsage).toBeDefined();
        expect(typeof (response.metadata?.mockUsage as UsageInfo).promptTokens).toBe('number');
        expect(typeof (response.metadata?.mockUsage as UsageInfo).completionTokens).toBe('number');
        expect(typeof (response.metadata?.mockUsage as UsageInfo).totalTokens).toBe('number');
      });

      it('should include mock provider info in metadata', async () => {
        const client = new MockChatClient();
        const response = await client.complete([createUserMessage('Hello')]);

        expect(response.metadata?.mockProvider).toBe('mock');
        expect(response.metadata?.mockModel).toBe('mock-model-v1');
      });
    });

    describe('completeStream()', () => {
      it('should return an async iterable', async () => {
        const client = new MockChatClient();
        const stream = client.completeStream([createUserMessage('Hello')]);

        expect(stream).toBeDefined();
        expect(typeof stream[Symbol.asyncIterator]).toBe('function');
      });

      it('should yield message delta events', async () => {
        const client = new MockChatClient();
        const stream = client.completeStream([createUserMessage('Hello')]);

        const events: StreamEvent[] = [];
        for await (const event of stream) {
          events.push(event);
        }

        const deltaEvents = events.filter(isMessageDelta);
        expect(deltaEvents.length).toBeGreaterThan(0);
      });

      it('should yield usage event', async () => {
        const client = new MockChatClient();
        const stream = client.completeStream([createUserMessage('Hello')]);

        const events: StreamEvent[] = [];
        for await (const event of stream) {
          events.push(event);
        }

        const usageEvents = events.filter(isUsageEvent);
        expect(usageEvents).toHaveLength(1);
        expect(usageEvents[0].usage.totalTokens).toBeGreaterThan(0);
      });

      it('should yield metadata event', async () => {
        const client = new MockChatClient();
        const stream = client.completeStream([createUserMessage('Hello')]);

        const events: StreamEvent[] = [];
        for await (const event of stream) {
          events.push(event);
        }

        const metadataEvents = events.filter(isMetadataEvent);
        expect(metadataEvents).toHaveLength(1);
        expect(metadataEvents[0].metadata.provider).toBe('mock');
        expect(metadataEvents[0].metadata.modelId).toBe('mock-model-v1');
        expect(metadataEvents[0].metadata.finishReason).toBe('stop');
      });

      it('should be consumable with for-await-of', async () => {
        const client = new MockChatClient();
        const stream = client.completeStream([createUserMessage('Hello')]);

        let eventCount = 0;
        for await (const event of stream) {
          expect(event).toBeDefined();
          expect(event.type).toBeDefined();
          eventCount++;
        }

        expect(eventCount).toBeGreaterThan(0);
      });

      it('should reconstruct full message from deltas', async () => {
        const client = new MockChatClient();
        const stream = client.completeStream([createUserMessage('Hello')]);

        let fullText = '';
        for await (const event of stream) {
          if (isMessageDelta(event)) {
            const content = event.delta.content;
            if (content && typeof content === 'object' && 'type' in content && content.type === 'text') {
              fullText += content.text;
            }
          }
        }

        expect(fullText).toBe('Mock response');
      });

      it('should support custom response text in stream', async () => {
        const client = new MockChatClient({ response: 'Custom streaming response' });
        const stream = client.completeStream([createUserMessage('Hello')]);

        let fullText = '';
        for await (const event of stream) {
          if (isMessageDelta(event)) {
            const content = event.delta.content;
            if (content && typeof content === 'object' && 'type' in content && content.type === 'text') {
              fullText += content.text;
            }
          }
        }

        expect(fullText).toBe('Custom streaming response');
      });

      it('should handle empty message array', async () => {
        const client = new MockChatClient();
        const stream = client.completeStream([]);

        const events: StreamEvent[] = [];
        for await (const event of stream) {
          events.push(event);
        }

        expect(events.length).toBeGreaterThan(0);
      });

      it('should handle options parameter', async () => {
        const client = new MockChatClient();
        const options: ChatCompletionOptions = {
          temperature: 0.5,
          maxTokens: 100,
        };
        const stream = client.completeStream([createUserMessage('Hello')], options);

        const events: StreamEvent[] = [];
        for await (const event of stream) {
          events.push(event);
        }

        expect(events.length).toBeGreaterThan(0);
      });

      it('should respect includeUsage option', async () => {
        const client = new MockChatClient({ includeUsage: false });
        const stream = client.completeStream([createUserMessage('Hello')]);

        const events: StreamEvent[] = [];
        for await (const event of stream) {
          events.push(event);
        }

        const usageEvents = events.filter(isUsageEvent);
        expect(usageEvents).toHaveLength(0);
      });

      it('should respect includeMetadata option', async () => {
        const client = new MockChatClient({ includeMetadata: false });
        const stream = client.completeStream([createUserMessage('Hello')]);

        const events: StreamEvent[] = [];
        for await (const event of stream) {
          events.push(event);
        }

        const metadataEvents = events.filter(isMetadataEvent);
        expect(metadataEvents).toHaveLength(0);
      });

      it('should emit message deltas in correct order', async () => {
        const client = new MockChatClient({ response: 'First Second Third' });
        const stream = client.completeStream([createUserMessage('Hello')]);

        const deltaTexts: string[] = [];
        for await (const event of stream) {
          if (isMessageDelta(event)) {
            const content = event.delta.content;
            if (content && typeof content === 'object' && 'type' in content && content.type === 'text') {
              deltaTexts.push(content.text);
            }
          }
        }

        expect(deltaTexts).toEqual(['First', ' Second', ' Third']);
      });
    });

    describe('duck typing compatibility', () => {
      it('should be usable where ChatClientProtocol is expected', async () => {
        const client: ChatClientProtocol = new MockChatClient();
        const response = await client.complete([createUserMessage('Test')]);
        expect(response).toBeDefined();
      });

      it('should support polymorphism', async () => {
        const clients: ChatClientProtocol[] = [
          new MockChatClient({ response: 'Response 1' }),
          new MockChatClient({ response: 'Response 2' }),
        ];

        const responses = await Promise.all(clients.map((c) => c.complete([createUserMessage('Test')])));

        expect(getTextContent(responses[0])).toBe('Response 1');
        expect(getTextContent(responses[1])).toBe('Response 2');
      });
    });
  });
});
