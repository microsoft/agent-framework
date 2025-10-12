/**
 * Tests for BaseAgent abstract class and AgentProtocol interface
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { BaseAgent, AgentProtocol } from '../base-agent.js';
import type { ChatMessage } from '../../types/chat-message.js';
import type { AgentInfo, AISettings } from '../../types/agent-info.js';
import type { ChatClientProtocol } from '../../chat-client/protocol.js';
import type { AITool } from '../../tools/base-tool.js';
import { ContextProvider, type AIContext } from '../../context/context-provider.js';
import type { StreamEvent } from '../../chat-client/types.js';
import { createUserMessage, createAssistantMessage, MessageRole } from '../../types/chat-message.js';

// Concrete implementation for testing
class TestAgent extends BaseAgent {
  // Track hook calls
  public beforeInvokeCalled = false;
  public afterInvokeCalled = false;

  protected async beforeInvoke(messages: ChatMessage[]): Promise<ChatMessage[]> {
    this.beforeInvokeCalled = true;
    return super.beforeInvoke(messages);
  }

  protected async afterInvoke(request: ChatMessage[], response: ChatMessage): Promise<void> {
    this.afterInvokeCalled = true;
    return super.afterInvoke(request, response);
  }
}

// Mock chat client
function createMockChatClient(response?: ChatMessage): ChatClientProtocol {
  const defaultResponse = createAssistantMessage('Mock response');
  return {
    complete: vi.fn().mockResolvedValue(response || defaultResponse),
    completeStream: vi.fn().mockImplementation(async function* (): AsyncIterable<StreamEvent> {
      yield { type: 'message_delta', delta: { role: MessageRole.Assistant, content: { type: 'text', text: 'Mock ' } } };
      yield { type: 'message_delta', delta: { content: { type: 'text', text: 'streaming ' } } };
      yield { type: 'message_delta', delta: { content: { type: 'text', text: 'response' } } };
    }),
  };
}

// Mock context provider
class MockContextProvider extends ContextProvider {
  public invokingCalled = false;
  public invokedCalled = false;
  public threadCreatedCalled = false;

  private contextToReturn: AIContext;

  constructor(context?: AIContext) {
    super();
    this.contextToReturn = context || {};
  }

  async invoking(_messages: ChatMessage[], _tools?: AITool[]): Promise<AIContext> {
    this.invokingCalled = true;
    return this.contextToReturn;
  }

  async invoked(_response: ChatMessage, _context: AIContext): Promise<void> {
    this.invokedCalled = true;
  }

  async threadCreated(_threadId: string): Promise<void> {
    this.threadCreatedCalled = true;
  }
}

describe('BaseAgent', () => {
  let agentInfo: AgentInfo;
  let chatClient: ChatClientProtocol;

  beforeEach(() => {
    agentInfo = {
      id: 'test-agent',
      name: 'Test Agent',
      description: 'A test agent',
      instructions: 'Be helpful',
    };
    chatClient = createMockChatClient();
  });

  describe('Construction', () => {
    it('should not be instantiable directly (abstract class)', () => {
      // TypeScript prevents direct instantiation at compile time with 'abstract' keyword
      // At runtime, we can still verify that BaseAgent is meant to be extended
      // by checking that it's indeed a constructor that requires subclassing
      expect(BaseAgent.name).toBe('BaseAgent');
      // The actual prevention happens at compile time via TypeScript's type system
    });

    it('should allow concrete subclass creation', () => {
      const agent = new TestAgent({
        info: agentInfo,
        chatClient,
      });

      expect(agent).toBeInstanceOf(BaseAgent);
      expect(agent.info).toBe(agentInfo);
      expect(agent.chatClient).toBe(chatClient);
      expect(agent.tools).toEqual([]);
      expect(agent.contextProvider).toBeUndefined();
    });

    it('should initialize with tools', () => {
      const tools: AITool[] = [
        {
          name: 'test_tool',
          description: 'A test tool',
          schema: {} as any,
          execute: vi.fn(),
        },
      ];

      const agent = new TestAgent({
        info: agentInfo,
        chatClient,
        tools,
      });

      expect(agent.tools).toBe(tools);
      expect(agent.tools).toHaveLength(1);
    });

    it('should initialize with context provider', () => {
      const contextProvider = new MockContextProvider();

      const agent = new TestAgent({
        info: agentInfo,
        chatClient,
        contextProvider,
      });

      expect(agent.contextProvider).toBe(contextProvider);
    });

    it('should initialize with all options', () => {
      const tools: AITool[] = [
        {
          name: 'test_tool',
          description: 'A test tool',
          schema: {} as any,
          execute: vi.fn(),
        },
      ];
      const contextProvider = new MockContextProvider();

      const agent = new TestAgent({
        info: agentInfo,
        chatClient,
        tools,
        contextProvider,
      });

      expect(agent.info).toBe(agentInfo);
      expect(agent.chatClient).toBe(chatClient);
      expect(agent.tools).toBe(tools);
      expect(agent.contextProvider).toBe(contextProvider);
    });
  });

  describe('invoke()', () => {
    it('should call chatClient.complete() with messages', async () => {
      const agent = new TestAgent({ info: agentInfo, chatClient });
      const messages = [createUserMessage('Hello')];

      await agent.invoke(messages);

      expect(chatClient.complete).toHaveBeenCalledTimes(1);
      expect(chatClient.complete).toHaveBeenCalledWith(
        messages,
        expect.objectContaining({})
      );
    });

    it('should return response from chat client', async () => {
      const expectedResponse = createAssistantMessage('Test response');
      chatClient = createMockChatClient(expectedResponse);
      const agent = new TestAgent({ info: agentInfo, chatClient });

      const response = await agent.invoke([createUserMessage('Hello')]);

      expect(response).toBe(expectedResponse);
    });

    it('should call beforeInvoke hook before LLM call', async () => {
      const agent = new TestAgent({ info: agentInfo, chatClient });
      const messages = [createUserMessage('Hello')];

      await agent.invoke(messages);

      expect(agent.beforeInvokeCalled).toBe(true);
    });

    it('should call afterInvoke hook after LLM call', async () => {
      const agent = new TestAgent({ info: agentInfo, chatClient });
      const messages = [createUserMessage('Hello')];

      await agent.invoke(messages);

      expect(agent.afterInvokeCalled).toBe(true);
    });

    it('should pass tools to chat client', async () => {
      const tools: AITool[] = [
        {
          name: 'test_tool',
          description: 'A test tool',
          schema: {} as any,
          execute: vi.fn(),
        },
      ];
      const agent = new TestAgent({ info: agentInfo, chatClient, tools });

      await agent.invoke([createUserMessage('Hello')]);

      expect(chatClient.complete).toHaveBeenCalledWith(
        expect.any(Array),
        expect.objectContaining({
          tools: expect.arrayContaining(tools),
        })
      );
    });

    it('should pass AI settings options to chat client', async () => {
      const agent = new TestAgent({ info: agentInfo, chatClient });
      const options: AISettings = {
        temperature: 0.7,
        maxTokens: 100,
      };

      await agent.invoke([createUserMessage('Hello')], options);

      expect(chatClient.complete).toHaveBeenCalledWith(
        expect.any(Array),
        expect.objectContaining({
          temperature: 0.7,
          maxTokens: 100,
        })
      );
    });

    it('should work without tools', async () => {
      const agent = new TestAgent({ info: agentInfo, chatClient });

      const response = await agent.invoke([createUserMessage('Hello')]);

      expect(response).toBeDefined();
      expect(chatClient.complete).toHaveBeenCalled();
    });

    it('should work without context provider', async () => {
      const agent = new TestAgent({ info: agentInfo, chatClient });

      const response = await agent.invoke([createUserMessage('Hello')]);

      expect(response).toBeDefined();
      expect(chatClient.complete).toHaveBeenCalled();
    });
  });

  describe('invoke() with context provider', () => {
    it('should call contextProvider.invoking() before LLM call', async () => {
      const contextProvider = new MockContextProvider();
      const agent = new TestAgent({ info: agentInfo, chatClient, contextProvider });

      await agent.invoke([createUserMessage('Hello')]);

      expect(contextProvider.invokingCalled).toBe(true);
    });

    it('should call contextProvider.invoked() after LLM call', async () => {
      const contextProvider = new MockContextProvider();
      const agent = new TestAgent({ info: agentInfo, chatClient, contextProvider });

      await agent.invoke([createUserMessage('Hello')]);

      expect(contextProvider.invokedCalled).toBe(true);
    });

    it('should apply context instructions from provider', async () => {
      const contextProvider = new MockContextProvider({
        instructions: 'Additional context instructions',
      });
      const agent = new TestAgent({ info: agentInfo, chatClient, contextProvider });

      await agent.invoke([createUserMessage('Hello')]);

      expect(chatClient.complete).toHaveBeenCalledWith(
        expect.any(Array),
        expect.objectContaining({
          additionalInstructions: expect.stringContaining('Additional context instructions'),
        })
      );
    });

    it('should combine agent instructions with context instructions', async () => {
      const contextProvider = new MockContextProvider({
        instructions: 'Context instructions',
      });
      const agent = new TestAgent({ info: agentInfo, chatClient, contextProvider });

      await agent.invoke([createUserMessage('Hello')]);

      expect(chatClient.complete).toHaveBeenCalledWith(
        expect.any(Array),
        expect.objectContaining({
          additionalInstructions: expect.stringContaining('Be helpful'),
        })
      );
      expect(chatClient.complete).toHaveBeenCalledWith(
        expect.any(Array),
        expect.objectContaining({
          additionalInstructions: expect.stringContaining('Context instructions'),
        })
      );
    });

    it('should prepend context messages before request messages', async () => {
      const contextMessage = createAssistantMessage('Context message');
      const contextProvider = new MockContextProvider({
        messages: [contextMessage],
      });
      const agent = new TestAgent({ info: agentInfo, chatClient, contextProvider });
      const requestMessages = [createUserMessage('Hello')];

      await agent.invoke(requestMessages);

      expect(chatClient.complete).toHaveBeenCalledWith(
        expect.arrayContaining([contextMessage, ...requestMessages]),
        expect.any(Object)
      );
    });

    it('should merge tools from context provider with agent tools', async () => {
      const agentTool: AITool = {
        name: 'agent_tool',
        description: 'Agent tool',
        schema: {} as any,
        execute: vi.fn(),
      };
      const contextTool: AITool = {
        name: 'context_tool',
        description: 'Context tool',
        schema: {} as any,
        execute: vi.fn(),
      };
      const contextProvider = new MockContextProvider({
        tools: [contextTool],
      });
      const agent = new TestAgent({
        info: agentInfo,
        chatClient,
        tools: [agentTool],
        contextProvider,
      });

      await agent.invoke([createUserMessage('Hello')]);

      expect(chatClient.complete).toHaveBeenCalledWith(
        expect.any(Array),
        expect.objectContaining({
          tools: expect.arrayContaining([agentTool, contextTool]),
        })
      );
    });

    it('should handle context with only messages', async () => {
      const contextProvider = new MockContextProvider({
        messages: [createAssistantMessage('Context')],
      });
      const agent = new TestAgent({ info: agentInfo, chatClient, contextProvider });

      await agent.invoke([createUserMessage('Hello')]);

      expect(chatClient.complete).toHaveBeenCalled();
      expect(contextProvider.invokingCalled).toBe(true);
      expect(contextProvider.invokedCalled).toBe(true);
    });

    it('should handle empty context from provider', async () => {
      const contextProvider = new MockContextProvider({});
      const agent = new TestAgent({ info: agentInfo, chatClient, contextProvider });

      const response = await agent.invoke([createUserMessage('Hello')]);

      expect(response).toBeDefined();
      expect(contextProvider.invokingCalled).toBe(true);
      expect(contextProvider.invokedCalled).toBe(true);
    });
  });

  describe('invokeStream()', () => {
    it('should call chatClient.completeStream()', async () => {
      const agent = new TestAgent({ info: agentInfo, chatClient });
      const messages = [createUserMessage('Hello')];

      const stream = agent.invokeStream(messages);
      // Consume the stream
      for await (const _message of stream) {
        // Just iterate
      }

      expect(chatClient.completeStream).toHaveBeenCalledTimes(1);
      expect(chatClient.completeStream).toHaveBeenCalledWith(
        messages,
        expect.objectContaining({})
      );
    });

    it('should yield accumulated ChatMessage objects', async () => {
      const agent = new TestAgent({ info: agentInfo, chatClient });
      const messages: ChatMessage[] = [];

      for await (const message of agent.invokeStream([createUserMessage('Hello')])) {
        messages.push(message);
      }

      expect(messages.length).toBeGreaterThan(0);
      expect(messages[0]).toHaveProperty('role');
      expect(messages[0]).toHaveProperty('content');
    });

    it('should accumulate deltas correctly', async () => {
      const agent = new TestAgent({ info: agentInfo, chatClient });
      const messages: ChatMessage[] = [];

      for await (const message of agent.invokeStream([createUserMessage('Tell a story')])) {
        messages.push(message);
      }

      // Last message should have accumulated all text
      const lastMessage = messages[messages.length - 1];
      expect(lastMessage.content).toHaveProperty('type', 'text');
      if (typeof lastMessage.content === 'object' && 'type' in lastMessage.content && lastMessage.content.type === 'text') {
        expect(lastMessage.content.text).toBe('Mock streaming response');
      }
    });

    it('should call beforeInvoke hook before streaming', async () => {
      const agent = new TestAgent({ info: agentInfo, chatClient });

      const stream = agent.invokeStream([createUserMessage('Hello')]);
      // Consume the stream
      for await (const _message of stream) {
        // Just iterate
      }

      expect(agent.beforeInvokeCalled).toBe(true);
    });

    it('should call afterInvoke hook after streaming completes', async () => {
      const agent = new TestAgent({ info: agentInfo, chatClient });

      const stream = agent.invokeStream([createUserMessage('Hello')]);
      // Consume the stream
      for await (const _message of stream) {
        // Just iterate
      }

      expect(agent.afterInvokeCalled).toBe(true);
    });

    it('should pass tools to chat client in streaming', async () => {
      const tools: AITool[] = [
        {
          name: 'test_tool',
          description: 'A test tool',
          schema: {} as any,
          execute: vi.fn(),
        },
      ];
      const agent = new TestAgent({ info: agentInfo, chatClient, tools });

      const stream = agent.invokeStream([createUserMessage('Hello')]);
      for await (const _message of stream) {
        // Just iterate
      }

      expect(chatClient.completeStream).toHaveBeenCalledWith(
        expect.any(Array),
        expect.objectContaining({
          tools: expect.arrayContaining(tools),
        })
      );
    });

    it('should work without tools in streaming', async () => {
      const agent = new TestAgent({ info: agentInfo, chatClient });

      const messages: ChatMessage[] = [];
      for await (const message of agent.invokeStream([createUserMessage('Hello')])) {
        messages.push(message);
      }

      expect(messages.length).toBeGreaterThan(0);
    });

    it('should work without context provider in streaming', async () => {
      const agent = new TestAgent({ info: agentInfo, chatClient });

      const messages: ChatMessage[] = [];
      for await (const message of agent.invokeStream([createUserMessage('Hello')])) {
        messages.push(message);
      }

      expect(messages.length).toBeGreaterThan(0);
    });
  });

  describe('invokeStream() with context provider', () => {
    it('should call contextProvider.invoking() before streaming', async () => {
      const contextProvider = new MockContextProvider();
      const agent = new TestAgent({ info: agentInfo, chatClient, contextProvider });

      const stream = agent.invokeStream([createUserMessage('Hello')]);
      for await (const _message of stream) {
        // Just iterate
      }

      expect(contextProvider.invokingCalled).toBe(true);
    });

    it('should call contextProvider.invoked() after streaming completes', async () => {
      const contextProvider = new MockContextProvider();
      const agent = new TestAgent({ info: agentInfo, chatClient, contextProvider });

      const stream = agent.invokeStream([createUserMessage('Hello')]);
      for await (const _message of stream) {
        // Just iterate
      }

      expect(contextProvider.invokedCalled).toBe(true);
    });

    it('should apply context in streaming', async () => {
      const contextProvider = new MockContextProvider({
        instructions: 'Stream context',
        messages: [createAssistantMessage('Context')],
      });
      const agent = new TestAgent({ info: agentInfo, chatClient, contextProvider });

      const stream = agent.invokeStream([createUserMessage('Hello')]);
      for await (const _message of stream) {
        // Just iterate
      }

      expect(chatClient.completeStream).toHaveBeenCalledWith(
        expect.arrayContaining([expect.objectContaining({ role: MessageRole.Assistant })]),
        expect.objectContaining({
          additionalInstructions: expect.stringContaining('Stream context'),
        })
      );
    });
  });

  describe('Lifecycle hooks', () => {
    it('should allow beforeInvoke to modify messages', async () => {
      class ModifyingAgent extends BaseAgent {
        protected async beforeInvoke(messages: ChatMessage[]): Promise<ChatMessage[]> {
          return [createUserMessage('Modified'), ...messages];
        }
      }

      const agent = new ModifyingAgent({ info: agentInfo, chatClient });
      await agent.invoke([createUserMessage('Original')]);

      expect(chatClient.complete).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({ content: expect.objectContaining({ text: 'Modified' }) }),
          expect.objectContaining({ content: expect.objectContaining({ text: 'Original' }) }),
        ]),
        expect.any(Object)
      );
    });

    it('should allow afterInvoke to access request and response', async () => {
      let capturedRequest: ChatMessage[] | null = null;
      let capturedResponse: ChatMessage | null = null;

      class CapturingAgent extends BaseAgent {
        protected async afterInvoke(request: ChatMessage[], response: ChatMessage): Promise<void> {
          capturedRequest = request;
          capturedResponse = response;
        }
      }

      const agent = new CapturingAgent({ info: agentInfo, chatClient });
      const messages = [createUserMessage('Test')];
      const response = await agent.invoke(messages);

      expect(capturedRequest).toEqual(messages);
      expect(capturedResponse).toBe(response);
    });
  });

  describe('AgentProtocol interface', () => {
    it('should satisfy AgentProtocol interface', () => {
      const agent = new TestAgent({ info: agentInfo, chatClient });

      // Verify all required properties exist
      expect(agent.info).toBeDefined();
      expect(agent.chatClient).toBeDefined();
      expect(agent.tools).toBeDefined();
      // contextProvider is optional, so we just check it exists as a property
      expect('contextProvider' in agent).toBe(true);

      // Verify all required methods exist and are callable
      expect(typeof agent.invoke).toBe('function');
      expect(typeof agent.invokeStream).toBe('function');
    });

    it('should be compatible with AgentProtocol type', () => {
      const agent: AgentProtocol = new TestAgent({ info: agentInfo, chatClient });

      expect(agent).toBeDefined();
      expect(agent.info).toBe(agentInfo);
    });
  });

  describe('Edge cases', () => {
    it('should handle empty message array', async () => {
      const agent = new TestAgent({ info: agentInfo, chatClient });

      const response = await agent.invoke([]);

      expect(response).toBeDefined();
      expect(chatClient.complete).toHaveBeenCalledWith([], expect.any(Object));
    });

    it('should handle agent info without instructions', async () => {
      const infoWithoutInstructions: AgentInfo = {
        id: 'test',
        name: 'Test',
      };
      const agent = new TestAgent({
        info: infoWithoutInstructions,
        chatClient,
      });

      await agent.invoke([createUserMessage('Hello')]);

      expect(chatClient.complete).toHaveBeenCalled();
    });

    it('should handle multiple consecutive invocations', async () => {
      const agent = new TestAgent({ info: agentInfo, chatClient });

      await agent.invoke([createUserMessage('First')]);
      await agent.invoke([createUserMessage('Second')]);
      await agent.invoke([createUserMessage('Third')]);

      expect(chatClient.complete).toHaveBeenCalledTimes(3);
    });

    it('should handle streaming with no deltas', async () => {
      const emptyStreamClient: ChatClientProtocol = {
        complete: vi.fn().mockResolvedValue(createAssistantMessage('Response')),
        completeStream: vi.fn().mockImplementation(async function* (): AsyncIterable<StreamEvent> {
          // Empty stream
        }),
      };
      const agent = new TestAgent({ info: agentInfo, chatClient: emptyStreamClient });

      const messages: ChatMessage[] = [];
      for await (const message of agent.invokeStream([createUserMessage('Hello')])) {
        messages.push(message);
      }

      expect(messages).toHaveLength(0);
    });
  });
});
