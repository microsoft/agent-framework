/**
 * Tests for ContextProvider and AggregateContextProvider
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  ContextProvider,
  AIContext,
  DEFAULT_CONTEXT_PROMPT,
} from '../context-provider.js';
import { AggregateContextProvider } from '../aggregate-provider.js';
import { ChatMessage, MessageRole, createUserMessage } from '../../types/chat-message.js';
import { AITool, createTool } from '../../tools/base-tool.js';
import { z } from 'zod';

// Test implementation of ContextProvider
class TestContextProvider extends ContextProvider {
  public threadCreatedCalls: string[] = [];
  public invokingCalls: { messages: ChatMessage[]; tools?: AITool[] }[] = [];
  public invokedCalls: { response: ChatMessage; context: AIContext }[] = [];
  public setupCalled = false;
  public cleanupCalled = false;

  async setup(): Promise<void> {
    this.setupCalled = true;
  }

  async cleanup(): Promise<void> {
    this.cleanupCalled = true;
  }

  async threadCreated(threadId: string): Promise<void> {
    this.threadCreatedCalls.push(threadId);
  }

  async invoking(messages: ChatMessage[], tools?: AITool[]): Promise<AIContext> {
    this.invokingCalls.push({ messages, tools });
    return {
      instructions: 'Test instructions',
      messages: [createUserMessage('Context message')],
      tools: [],
    };
  }

  async invoked(response: ChatMessage, context: AIContext): Promise<void> {
    this.invokedCalls.push({ response, context });
  }
}

// Another test provider with different context
class SecondTestProvider extends ContextProvider {
  async invoking(_messages: ChatMessage[]): Promise<AIContext> {
    return {
      instructions: 'Second provider instructions',
      messages: [createUserMessage('Second context message')],
      tools: [],
    };
  }
}

// Provider that returns minimal context
class MinimalProvider extends ContextProvider {
  async invoking(_messages: ChatMessage[]): Promise<AIContext> {
    return {};
  }
}

// Provider with only instructions
class InstructionsOnlyProvider extends ContextProvider {
  async invoking(_messages: ChatMessage[]): Promise<AIContext> {
    return {
      instructions: 'Only instructions here',
    };
  }
}

describe('ContextProvider', () => {
  describe('abstract class behavior', () => {
    it('can be extended to create concrete providers', () => {
      const provider = new TestContextProvider();
      expect(provider).toBeInstanceOf(ContextProvider);
    });

    it('requires implementation of invoking method', async () => {
      const provider = new TestContextProvider();
      const messages = [createUserMessage('Hello')];
      const context = await provider.invoking(messages);
      expect(context).toBeDefined();
    });
  });

  describe('lifecycle hooks', () => {
    let provider: TestContextProvider;

    beforeEach(() => {
      provider = new TestContextProvider();
    });

    it('calls threadCreated with thread ID', async () => {
      await provider.threadCreated('thread-123');
      expect(provider.threadCreatedCalls).toEqual(['thread-123']);
    });

    it('calls threadCreated multiple times for different threads', async () => {
      await provider.threadCreated('thread-1');
      await provider.threadCreated('thread-2');
      await provider.threadCreated('thread-3');
      expect(provider.threadCreatedCalls).toEqual(['thread-1', 'thread-2', 'thread-3']);
    });

    it('calls invoking with messages', async () => {
      const messages = [
        createUserMessage('First message'),
        createUserMessage('Second message'),
      ];
      await provider.invoking(messages);
      expect(provider.invokingCalls).toHaveLength(1);
      expect(provider.invokingCalls[0].messages).toEqual(messages);
    });

    it('calls invoking with messages and tools', async () => {
      const messages = [createUserMessage('Hello')];
      const tool = createTool(
        'test_tool',
        'Test tool',
        z.object({ param: z.string() }),
        async () => 'result'
      );
      const tools = [tool];

      await provider.invoking(messages, tools);
      expect(provider.invokingCalls).toHaveLength(1);
      expect(provider.invokingCalls[0].messages).toEqual(messages);
      expect(provider.invokingCalls[0].tools).toEqual(tools);
    });

    it('returns AIContext from invoking', async () => {
      const messages = [createUserMessage('Hello')];
      const context = await provider.invoking(messages);

      expect(context).toBeDefined();
      expect(context.instructions).toBe('Test instructions');
      expect(context.messages).toHaveLength(1);
      expect(context.tools).toEqual([]);
    });

    it('calls invoked with response and context', async () => {
      const response: ChatMessage = {
        role: MessageRole.Assistant,
        content: { type: 'text', text: 'Response' },
      };
      const context: AIContext = {
        instructions: 'Test instructions',
      };

      await provider.invoked(response, context);
      expect(provider.invokedCalls).toHaveLength(1);
      expect(provider.invokedCalls[0].response).toEqual(response);
      expect(provider.invokedCalls[0].context).toEqual(context);
    });

    it('calls setup when initializing', async () => {
      await provider.setup();
      expect(provider.setupCalled).toBe(true);
    });

    it('calls cleanup when disposing', async () => {
      await provider.cleanup();
      expect(provider.cleanupCalled).toBe(true);
    });
  });

  describe('AIContext structure', () => {
    it('supports instructions only', async () => {
      const provider = new InstructionsOnlyProvider();
      const context = await provider.invoking([createUserMessage('Test')]);

      expect(context.instructions).toBe('Only instructions here');
      expect(context.messages).toBeUndefined();
      expect(context.tools).toBeUndefined();
    });

    it('supports empty context', async () => {
      const provider = new MinimalProvider();
      const context = await provider.invoking([createUserMessage('Test')]);

      expect(context.instructions).toBeUndefined();
      expect(context.messages).toBeUndefined();
      expect(context.tools).toBeUndefined();
    });

    it('supports full context with all fields', async () => {
      const provider = new TestContextProvider();
      const context = await provider.invoking([createUserMessage('Test')]);

      expect(context.instructions).toBeDefined();
      expect(context.messages).toBeDefined();
      expect(context.tools).toBeDefined();
    });
  });

  describe('DEFAULT_CONTEXT_PROMPT', () => {
    it('is defined as a constant', () => {
      expect(DEFAULT_CONTEXT_PROMPT).toBeDefined();
      expect(typeof DEFAULT_CONTEXT_PROMPT).toBe('string');
    });

    it('contains expected memory prompt text', () => {
      expect(DEFAULT_CONTEXT_PROMPT).toContain('Memories');
      expect(DEFAULT_CONTEXT_PROMPT).toContain('Consider the following memories');
    });
  });
});

describe('AggregateContextProvider', () => {
  describe('constructor', () => {
    it('can be created with no providers', () => {
      const aggregate = new AggregateContextProvider();
      expect(aggregate.providers).toEqual([]);
    });

    it('can be created with a single provider', () => {
      const provider = new TestContextProvider();
      const aggregate = new AggregateContextProvider(provider);
      expect(aggregate.providers).toHaveLength(1);
      expect(aggregate.providers[0]).toBe(provider);
    });

    it('can be created with an array of providers', () => {
      const provider1 = new TestContextProvider();
      const provider2 = new SecondTestProvider();
      const aggregate = new AggregateContextProvider([provider1, provider2]);
      expect(aggregate.providers).toHaveLength(2);
      expect(aggregate.providers[0]).toBe(provider1);
      expect(aggregate.providers[1]).toBe(provider2);
    });

    it('can be created with undefined', () => {
      const aggregate = new AggregateContextProvider(undefined);
      expect(aggregate.providers).toEqual([]);
    });

    it('is an instance of ContextProvider', () => {
      const aggregate = new AggregateContextProvider();
      expect(aggregate).toBeInstanceOf(ContextProvider);
      expect(aggregate).toBeInstanceOf(AggregateContextProvider);
    });
  });

  describe('add method', () => {
    it('adds a provider to the aggregate', () => {
      const aggregate = new AggregateContextProvider();
      const provider = new TestContextProvider();

      aggregate.add(provider);
      expect(aggregate.providers).toHaveLength(1);
      expect(aggregate.providers[0]).toBe(provider);
    });

    it('adds multiple providers sequentially', () => {
      const aggregate = new AggregateContextProvider();
      const provider1 = new TestContextProvider();
      const provider2 = new SecondTestProvider();
      const provider3 = new MinimalProvider();

      aggregate.add(provider1);
      aggregate.add(provider2);
      aggregate.add(provider3);

      expect(aggregate.providers).toHaveLength(3);
      expect(aggregate.providers[0]).toBe(provider1);
      expect(aggregate.providers[1]).toBe(provider2);
      expect(aggregate.providers[2]).toBe(provider3);
    });
  });

  describe('threadCreated lifecycle', () => {
    it('calls threadCreated on all providers', async () => {
      const provider1 = new TestContextProvider();
      const provider2 = new TestContextProvider();
      const aggregate = new AggregateContextProvider([provider1, provider2]);

      await aggregate.threadCreated('thread-123');

      expect(provider1.threadCreatedCalls).toEqual(['thread-123']);
      expect(provider2.threadCreatedCalls).toEqual(['thread-123']);
    });

    it('calls threadCreated on providers added dynamically', async () => {
      const aggregate = new AggregateContextProvider();
      const provider = new TestContextProvider();
      aggregate.add(provider);

      await aggregate.threadCreated('thread-456');
      expect(provider.threadCreatedCalls).toEqual(['thread-456']);
    });

    it('handles empty provider list', async () => {
      const aggregate = new AggregateContextProvider();
      // Should not throw
      await expect(aggregate.threadCreated('thread-789')).resolves.toBeUndefined();
    });
  });

  describe('invoking lifecycle', () => {
    it('calls invoking on all providers', async () => {
      const provider1 = new TestContextProvider();
      const provider2 = new TestContextProvider();
      const aggregate = new AggregateContextProvider([provider1, provider2]);

      const messages = [createUserMessage('Test')];
      await aggregate.invoking(messages);

      expect(provider1.invokingCalls).toHaveLength(1);
      expect(provider2.invokingCalls).toHaveLength(1);
    });

    it('merges instructions from multiple providers', async () => {
      const provider1 = new TestContextProvider();
      const provider2 = new SecondTestProvider();
      const aggregate = new AggregateContextProvider([provider1, provider2]);

      const messages = [createUserMessage('Test')];
      const context = await aggregate.invoking(messages);

      expect(context.instructions).toContain('Test instructions');
      expect(context.instructions).toContain('Second provider instructions');
      expect(context.instructions).toMatch(/Test instructions\nSecond provider instructions/);
    });

    it('merges messages from multiple providers', async () => {
      const provider1 = new TestContextProvider();
      const provider2 = new SecondTestProvider();
      const aggregate = new AggregateContextProvider([provider1, provider2]);

      const messages = [createUserMessage('Test')];
      const context = await aggregate.invoking(messages);

      expect(context.messages).toHaveLength(2);
      expect(context.messages).toBeDefined();
      if (context.messages) {
        expect(context.messages[0].content).toEqual({ type: 'text', text: 'Context message' });
        expect(context.messages[1].content).toEqual({
          type: 'text',
          text: 'Second context message',
        });
      }
    });

    it('merges tools from multiple providers', async () => {
      class ToolProvider1 extends ContextProvider {
        async invoking(): Promise<AIContext> {
          return {
            tools: [
              createTool('tool1', 'Tool 1', z.object({}), async () => 'result1'),
            ],
          };
        }
      }

      class ToolProvider2 extends ContextProvider {
        async invoking(): Promise<AIContext> {
          return {
            tools: [
              createTool('tool2', 'Tool 2', z.object({}), async () => 'result2'),
            ],
          };
        }
      }

      const aggregate = new AggregateContextProvider([new ToolProvider1(), new ToolProvider2()]);
      const context = await aggregate.invoking([createUserMessage('Test')]);

      expect(context.tools).toHaveLength(2);
      expect(context.tools).toBeDefined();
      if (context.tools) {
        expect(context.tools[0].name).toBe('tool1');
        expect(context.tools[1].name).toBe('tool2');
      }
    });

    it('handles providers with partial context', async () => {
      const provider1 = new InstructionsOnlyProvider();
      const provider2 = new MinimalProvider();
      const aggregate = new AggregateContextProvider([provider1, provider2]);

      const context = await aggregate.invoking([createUserMessage('Test')]);

      expect(context.instructions).toBe('Only instructions here');
      expect(context.messages).toBeUndefined();
      expect(context.tools).toBeUndefined();
    });

    it('returns empty context when all providers return empty', async () => {
      const provider1 = new MinimalProvider();
      const provider2 = new MinimalProvider();
      const aggregate = new AggregateContextProvider([provider1, provider2]);

      const context = await aggregate.invoking([createUserMessage('Test')]);

      expect(context.instructions).toBeUndefined();
      expect(context.messages).toBeUndefined();
      expect(context.tools).toBeUndefined();
    });

    it('handles empty provider list', async () => {
      const aggregate = new AggregateContextProvider();
      const context = await aggregate.invoking([createUserMessage('Test')]);

      expect(context.instructions).toBeUndefined();
      expect(context.messages).toBeUndefined();
      expect(context.tools).toBeUndefined();
    });

    it('passes tools parameter to child providers', async () => {
      const provider = new TestContextProvider();
      const aggregate = new AggregateContextProvider([provider]);

      const messages = [createUserMessage('Test')];
      const tools = [createTool('test', 'Test', z.object({}), async () => 'result')];

      await aggregate.invoking(messages, tools);
      expect(provider.invokingCalls[0].tools).toEqual(tools);
    });
  });

  describe('invoked lifecycle', () => {
    it('calls invoked on all providers', async () => {
      const provider1 = new TestContextProvider();
      const provider2 = new TestContextProvider();
      const aggregate = new AggregateContextProvider([provider1, provider2]);

      const response: ChatMessage = {
        role: MessageRole.Assistant,
        content: { type: 'text', text: 'Response' },
      };
      const context: AIContext = { instructions: 'Test' };

      await aggregate.invoked(response, context);

      expect(provider1.invokedCalls).toHaveLength(1);
      expect(provider2.invokedCalls).toHaveLength(1);
      expect(provider1.invokedCalls[0].response).toEqual(response);
      expect(provider1.invokedCalls[0].context).toEqual(context);
    });

    it('handles empty provider list', async () => {
      const aggregate = new AggregateContextProvider();
      const response: ChatMessage = {
        role: MessageRole.Assistant,
        content: { type: 'text', text: 'Response' },
      };
      const context: AIContext = {};

      // Should not throw
      await expect(aggregate.invoked(response, context)).resolves.toBeUndefined();
    });
  });

  describe('setup and cleanup', () => {
    it('calls setup on all providers', async () => {
      const provider1 = new TestContextProvider();
      const provider2 = new TestContextProvider();
      const aggregate = new AggregateContextProvider([provider1, provider2]);

      await aggregate.setup();

      expect(provider1.setupCalled).toBe(true);
      expect(provider2.setupCalled).toBe(true);
    });

    it('calls cleanup on all providers', async () => {
      const provider1 = new TestContextProvider();
      const provider2 = new TestContextProvider();
      const aggregate = new AggregateContextProvider([provider1, provider2]);

      await aggregate.cleanup();

      expect(provider1.cleanupCalled).toBe(true);
      expect(provider2.cleanupCalled).toBe(true);
    });

    it('handles empty provider list for setup', async () => {
      const aggregate = new AggregateContextProvider();
      await expect(aggregate.setup()).resolves.toBeUndefined();
    });

    it('handles empty provider list for cleanup', async () => {
      const aggregate = new AggregateContextProvider();
      await expect(aggregate.cleanup()).resolves.toBeUndefined();
    });
  });

  describe('parallel execution', () => {
    it('executes all provider calls in parallel', async () => {
      const delays: number[] = [];

      class SlowProvider extends ContextProvider {
        constructor(private delay: number) {
          super();
        }

        async invoking(): Promise<AIContext> {
          const start = Date.now();
          await new Promise((resolve) => setTimeout(resolve, this.delay));
          delays.push(Date.now() - start);
          return { instructions: `Provider ${this.delay}` };
        }
      }

      const provider1 = new SlowProvider(50);
      const provider2 = new SlowProvider(50);
      const provider3 = new SlowProvider(50);
      const aggregate = new AggregateContextProvider([provider1, provider2, provider3]);

      const start = Date.now();
      await aggregate.invoking([createUserMessage('Test')]);
      const totalTime = Date.now() - start;

      // Should take ~50ms (parallel) not ~150ms (sequential)
      expect(totalTime).toBeLessThan(100);
    });
  });

  describe('edge cases', () => {
    it('handles provider that throws error during threadCreated', async () => {
      class ErrorProvider extends ContextProvider {
        async threadCreated(): Promise<void> {
          throw new Error('Thread creation failed');
        }

        async invoking(): Promise<AIContext> {
          return {};
        }
      }

      const aggregate = new AggregateContextProvider([new ErrorProvider()]);

      await expect(aggregate.threadCreated('thread-123')).rejects.toThrow(
        'Thread creation failed'
      );
    });

    it('handles provider that throws error during invoking', async () => {
      class ErrorProvider extends ContextProvider {
        async invoking(): Promise<AIContext> {
          throw new Error('Invoking failed');
        }
      }

      const aggregate = new AggregateContextProvider([new ErrorProvider()]);

      await expect(aggregate.invoking([createUserMessage('Test')])).rejects.toThrow(
        'Invoking failed'
      );
    });

    it('handles provider that throws error during invoked', async () => {
      class ErrorProvider extends ContextProvider {
        async invoking(): Promise<AIContext> {
          return {};
        }

        async invoked(): Promise<void> {
          throw new Error('Invoked failed');
        }
      }

      const aggregate = new AggregateContextProvider([new ErrorProvider()]);
      const response: ChatMessage = {
        role: MessageRole.Assistant,
        content: { type: 'text', text: 'Response' },
      };

      await expect(aggregate.invoked(response, {})).rejects.toThrow('Invoked failed');
    });

    it('preserves order of messages from providers', async () => {
      class OrderedProvider extends ContextProvider {
        constructor(private id: number) {
          super();
        }

        async invoking(): Promise<AIContext> {
          return {
            messages: [createUserMessage(`Message from provider ${this.id}`)],
          };
        }
      }

      const aggregate = new AggregateContextProvider([
        new OrderedProvider(1),
        new OrderedProvider(2),
        new OrderedProvider(3),
      ]);

      const context = await aggregate.invoking([createUserMessage('Test')]);

      expect(context.messages).toHaveLength(3);
      if (context.messages) {
        expect(context.messages[0].content).toEqual({
          type: 'text',
          text: 'Message from provider 1',
        });
        expect(context.messages[1].content).toEqual({
          type: 'text',
          text: 'Message from provider 2',
        });
        expect(context.messages[2].content).toEqual({
          type: 'text',
          text: 'Message from provider 3',
        });
      }
    });

    it('handles many providers efficiently', async () => {
      const providers = Array.from(
        { length: 100 },
        (_, i) =>
          new (class extends ContextProvider {
            async invoking(): Promise<AIContext> {
              return { instructions: `Provider ${i}` };
            }
          })()
      );

      const aggregate = new AggregateContextProvider(providers);
      const context = await aggregate.invoking([createUserMessage('Test')]);

      expect(context.instructions?.split('\n')).toHaveLength(100);
    });
  });
});
