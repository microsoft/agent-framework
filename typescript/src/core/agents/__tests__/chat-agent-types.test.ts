/**
 * Unit tests for ChatAgent types and interfaces.
 *
 * Tests type definitions, class behavior, and computed properties.
 *
 * @module agents/__tests__/chat-agent-types
 */

import { describe, it, expect } from 'vitest';
import {
  AgentRunResponse,
  AgentRunResponseUpdate,
  type ToolChoice,
  type ChatAgentOptions,
  type ChatRunOptions,
  type MCPServerConfig,
  type UsageDetails,
} from '../chat-agent-types.js';
import { MessageRole, type ChatMessage } from '../../types/chat-message.js';

describe('ToolChoice Type', () => {
  it('should accept auto string literal', () => {
    const choice: ToolChoice = 'auto';
    expect(choice).toBe('auto');
  });

  it('should accept required string literal', () => {
    const choice: ToolChoice = 'required';
    expect(choice).toBe('required');
  });

  it('should accept none string literal', () => {
    const choice: ToolChoice = 'none';
    expect(choice).toBe('none');
  });

  it('should accept tool object with name', () => {
    const choice: ToolChoice = { type: 'tool', name: 'get_weather' };
    expect(choice).toEqual({ type: 'tool', name: 'get_weather' });
  });
});

describe('MCPServerConfig Interface', () => {
  it('should create valid MCP server config', () => {
    const config: MCPServerConfig = {
      serverUrl: 'http://localhost:8080',
      apiKey: 'secret-key',
      timeout: 30000,
    };

    expect(config.serverUrl).toBe('http://localhost:8080');
    expect(config.apiKey).toBe('secret-key');
    expect(config.timeout).toBe(30000);
  });

  it('should allow additional properties', () => {
    const config: MCPServerConfig = {
      serverUrl: 'http://localhost:8080',
      customProp: 'custom-value',
    };

    expect(config.customProp).toBe('custom-value');
  });

  it('should work with minimal config', () => {
    const config: MCPServerConfig = {
      serverUrl: 'http://localhost:8080',
    };

    expect(config.serverUrl).toBe('http://localhost:8080');
    expect(config.apiKey).toBeUndefined();
  });
});

describe('UsageDetails Interface', () => {
  it('should track token usage', () => {
    const usage: UsageDetails = {
      promptTokens: 50,
      completionTokens: 100,
      totalTokens: 150,
    };

    expect(usage.promptTokens).toBe(50);
    expect(usage.completionTokens).toBe(100);
    expect(usage.totalTokens).toBe(150);
  });

  it('should allow provider-specific metrics', () => {
    const usage: UsageDetails = {
      totalTokens: 100,
      cacheHits: 5,
      latencyMs: 250,
    };

    expect(usage.cacheHits).toBe(5);
    expect(usage.latencyMs).toBe(250);
  });
});

describe('ChatAgentOptions Interface', () => {
  it('should create valid agent options with required fields', () => {
    const mockClient = {} as any;

    const options: ChatAgentOptions = {
      chatClient: mockClient,
    };

    expect(options.chatClient).toBe(mockClient);
  });

  it('should create options with all standard fields', () => {
    const mockClient = {} as any;
    const mockTool = {} as any;
    const mockProvider = {} as any;

    const options: ChatAgentOptions = {
      chatClient: mockClient,
      id: 'agent-123',
      name: 'TestAgent',
      description: 'A test agent',
      instructions: 'You are helpful',
      tools: [mockTool],
      contextProviders: [mockProvider],
      temperature: 0.7,
      maxTokens: 500,
      topP: 0.9,
      frequencyPenalty: 0.5,
      presencePenalty: 0.5,
      stop: ['END'],
      seed: 42,
      store: true,
      toolChoice: 'auto',
      modelId: 'gpt-4',
      user: 'user-123',
    };

    expect(options.name).toBe('TestAgent');
    expect(options.temperature).toBe(0.7);
    expect(options.maxTokens).toBe(500);
    expect(options.toolChoice).toBe('auto');
  });

  it('should support service-managed threads', () => {
    const mockClient = {} as any;

    const options: ChatAgentOptions = {
      chatClient: mockClient,
      conversationId: 'thread_abc123',
    };

    expect(options.conversationId).toBe('thread_abc123');
    expect(options.messageStoreFactory).toBeUndefined();
  });

  it('should support local message storage', () => {
    const mockClient = {} as any;
    const mockFactory = () => ({} as any);

    const options: ChatAgentOptions = {
      chatClient: mockClient,
      messageStoreFactory: mockFactory,
    };

    expect(options.messageStoreFactory).toBe(mockFactory);
    expect(options.conversationId).toBeUndefined();
  });

  it('should support MCP servers', () => {
    const mockClient = {} as any;
    const mcpConfig: MCPServerConfig = {
      serverUrl: 'http://localhost:8080',
    };

    const options: ChatAgentOptions = {
      chatClient: mockClient,
      mcpServers: [mcpConfig],
    };

    expect(options.mcpServers).toHaveLength(1);
    expect(options.mcpServers?.[0].serverUrl).toBe('http://localhost:8080');
  });

  it('should support additional chat options', () => {
    const mockClient = {} as any;

    const options: ChatAgentOptions = {
      chatClient: mockClient,
      additionalChatOptions: {
        reasoning: { effort: 'high' },
      },
    };

    expect(options.additionalChatOptions).toEqual({
      reasoning: { effort: 'high' },
    });
  });
});

describe('ChatRunOptions Interface', () => {
  it('should create valid run options', () => {
    const mockThread = {} as any;

    const options: ChatRunOptions = {
      thread: mockThread,
      temperature: 0.8,
      maxTokens: 200,
    };

    expect(options.thread).toBe(mockThread);
    expect(options.temperature).toBe(0.8);
    expect(options.maxTokens).toBe(200);
  });

  it('should support tool choice override', () => {
    const options: ChatRunOptions = {
      toolChoice: { type: 'tool', name: 'calculator' },
    };

    expect(options.toolChoice).toEqual({ type: 'tool', name: 'calculator' });
  });

  it('should support runtime tool override', () => {
    const mockTool = {} as any;

    const options: ChatRunOptions = {
      tools: [mockTool],
    };

    expect(options.tools).toHaveLength(1);
  });

  it('should allow arbitrary properties', () => {
    const options: ChatRunOptions = {
      customProp: 'custom-value',
      anotherProp: 123,
    };

    expect(options.customProp).toBe('custom-value');
    expect(options.anotherProp).toBe(123);
  });
});

describe('AgentRunResponse', () => {
  describe('constructor', () => {
    it('should create response with messages', () => {
      const message: ChatMessage = {
        role: MessageRole.Assistant,
        content: { type: 'text', text: 'Hello' },
      };

      const response = new AgentRunResponse({
        messages: [message],
      });

      expect(response.messages).toHaveLength(1);
      expect(response.messages[0]).toBe(message);
    });

    it('should create response with all properties', () => {
      const message: ChatMessage = {
        role: MessageRole.Assistant,
        content: { type: 'text', text: 'Hello' },
      };

      const usage: UsageDetails = {
        promptTokens: 10,
        completionTokens: 20,
        totalTokens: 30,
      };

      const createdAt = new Date();

      const response = new AgentRunResponse({
        messages: [message],
        responseId: 'resp_123',
        createdAt,
        usageDetails: usage,
        value: { result: 42 },
        additionalProperties: { custom: 'value' },
      });

      expect(response.responseId).toBe('resp_123');
      expect(response.createdAt).toBe(createdAt);
      expect(response.usageDetails).toBe(usage);
      expect(response.value).toEqual({ result: 42 });
      expect(response.additionalProperties).toEqual({ custom: 'value' });
    });

    it('should create response with empty messages', () => {
      const response = new AgentRunResponse({
        messages: [],
      });

      expect(response.messages).toHaveLength(0);
      expect(response.text).toBe('');
    });
  });

  describe('text getter', () => {
    it('should extract text from single message', () => {
      const message: ChatMessage = {
        role: MessageRole.Assistant,
        content: { type: 'text', text: 'Hello world' },
      };

      const response = new AgentRunResponse({
        messages: [message],
      });

      expect(response.text).toBe('Hello world');
    });

    it('should concatenate text from multiple messages', () => {
      const messages: ChatMessage[] = [
        {
          role: MessageRole.Assistant,
          content: { type: 'text', text: 'Hello' },
        },
        {
          role: MessageRole.Assistant,
          content: { type: 'text', text: ' world' },
        },
      ];

      const response = new AgentRunResponse({
        messages,
      });

      expect(response.text).toBe('Hello world');
    });

    it('should handle messages with array content', () => {
      const message: ChatMessage = {
        role: MessageRole.Assistant,
        content: [
          { type: 'text', text: 'Part 1' },
          { type: 'text', text: ' Part 2' },
        ],
      };

      const response = new AgentRunResponse({
        messages: [message],
      });

      expect(response.text).toBe('Part 1 Part 2');
    });

    it('should return empty string for empty messages', () => {
      const response = new AgentRunResponse({
        messages: [],
      });

      expect(response.text).toBe('');
    });

    it('should ignore non-text content', () => {
      const message: ChatMessage = {
        role: MessageRole.Assistant,
        content: [
          { type: 'text', text: 'Hello' },
          { type: 'image', url: 'https://example.com/image.jpg' },
          { type: 'text', text: ' world' },
        ],
      };

      const response = new AgentRunResponse({
        messages: [message],
      });

      expect(response.text).toBe('Hello world');
    });

    it('should handle messages with no text content', () => {
      const message: ChatMessage = {
        role: MessageRole.Assistant,
        content: { type: 'function_call', callId: '123', name: 'func', arguments: '{}' },
      };

      const response = new AgentRunResponse({
        messages: [message],
      });

      expect(response.text).toBe('');
    });
  });

  describe('fromUpdates', () => {
    it('should combine updates into response', () => {
      const updates: AgentRunResponseUpdate[] = [
        new AgentRunResponseUpdate({
          content: { type: 'text', text: 'Hello' },
          role: MessageRole.Assistant,
          messageId: 'msg_1',
        }),
        new AgentRunResponseUpdate({
          content: { type: 'text', text: ' world' },
          role: MessageRole.Assistant,
          messageId: 'msg_1',
        }),
      ];

      const response = AgentRunResponse.fromUpdates(updates);

      expect(response.messages).toHaveLength(1);
      expect(response.text).toContain('Hello');
      expect(response.text).toContain('world');
    });

    it('should handle multiple messages', () => {
      const updates: AgentRunResponseUpdate[] = [
        new AgentRunResponseUpdate({
          content: { type: 'text', text: 'First' },
          role: MessageRole.Assistant,
          messageId: 'msg_1',
        }),
        new AgentRunResponseUpdate({
          content: { type: 'text', text: 'Second' },
          role: MessageRole.Assistant,
          messageId: 'msg_2',
        }),
      ];

      const response = AgentRunResponse.fromUpdates(updates);

      expect(response.messages).toHaveLength(2);
    });

    it('should preserve response metadata', () => {
      const usage: UsageDetails = { totalTokens: 100 };
      const createdAt = new Date();

      const updates: AgentRunResponseUpdate[] = [
        new AgentRunResponseUpdate({
          content: { type: 'text', text: 'Hello' },
          role: MessageRole.Assistant,
          responseId: 'resp_123',
          createdAt,
          usageDetails: usage,
        }),
      ];

      const response = AgentRunResponse.fromUpdates(updates);

      expect(response.responseId).toBe('resp_123');
      expect(response.createdAt).toBe(createdAt);
      expect(response.usageDetails).toBe(usage);
    });

    it('should handle empty updates array', () => {
      const response = AgentRunResponse.fromUpdates([]);

      expect(response.messages).toHaveLength(0);
      expect(response.text).toBe('');
    });
  });

  describe('toString', () => {
    it('should return text content', () => {
      const message: ChatMessage = {
        role: MessageRole.Assistant,
        content: { type: 'text', text: 'Hello world' },
      };

      const response = new AgentRunResponse({
        messages: [message],
      });

      expect(response.toString()).toBe('Hello world');
    });
  });
});

describe('AgentRunResponseUpdate', () => {
  describe('constructor', () => {
    it('should create update with content', () => {
      const update = new AgentRunResponseUpdate({
        content: { type: 'text', text: 'Hello' },
        role: MessageRole.Assistant,
      });

      expect(update.content).toEqual({ type: 'text', text: 'Hello' });
      expect(update.role).toBe(MessageRole.Assistant);
      expect(update.isFinal).toBe(false);
    });

    it('should create update with all properties', () => {
      const createdAt = new Date();
      const usage: UsageDetails = { totalTokens: 50 };

      const update = new AgentRunResponseUpdate({
        content: { type: 'text', text: 'Hello' },
        role: MessageRole.Assistant,
        authorName: 'Assistant',
        responseId: 'resp_123',
        messageId: 'msg_456',
        createdAt,
        isFinal: true,
        usageDetails: usage,
        additionalProperties: { custom: 'prop' },
      });

      expect(update.authorName).toBe('Assistant');
      expect(update.responseId).toBe('resp_123');
      expect(update.messageId).toBe('msg_456');
      expect(update.createdAt).toBe(createdAt);
      expect(update.isFinal).toBe(true);
      expect(update.usageDetails).toBe(usage);
      expect(update.additionalProperties).toEqual({ custom: 'prop' });
    });

    it('should default isFinal to false', () => {
      const update = new AgentRunResponseUpdate({
        content: { type: 'text', text: 'Hello' },
        role: MessageRole.Assistant,
      });

      expect(update.isFinal).toBe(false);
    });

    it('should create update without content', () => {
      const update = new AgentRunResponseUpdate({
        role: MessageRole.Assistant,
        isFinal: true,
      });

      expect(update.content).toBeUndefined();
      expect(update.text).toBe('');
    });
  });

  describe('text getter', () => {
    it('should extract text from content', () => {
      const update = new AgentRunResponseUpdate({
        content: { type: 'text', text: 'Hello world' },
        role: MessageRole.Assistant,
      });

      expect(update.text).toBe('Hello world');
    });

    it('should extract text from array content', () => {
      const update = new AgentRunResponseUpdate({
        content: [
          { type: 'text', text: 'Part 1' },
          { type: 'text', text: ' Part 2' },
        ],
        role: MessageRole.Assistant,
      });

      expect(update.text).toBe('Part 1 Part 2');
    });

    it('should return empty string for no content', () => {
      const update = new AgentRunResponseUpdate({
        role: MessageRole.Assistant,
      });

      expect(update.text).toBe('');
    });

    it('should ignore non-text content', () => {
      const update = new AgentRunResponseUpdate({
        content: [
          { type: 'text', text: 'Hello' },
          { type: 'image', url: 'https://example.com/img.jpg' },
        ],
        role: MessageRole.Assistant,
      });

      expect(update.text).toBe('Hello');
    });

    it('should handle function call content', () => {
      const update = new AgentRunResponseUpdate({
        content: {
          type: 'function_call',
          callId: '123',
          name: 'func',
          arguments: '{}',
        },
        role: MessageRole.Assistant,
      });

      expect(update.text).toBe('');
    });
  });

  describe('toString', () => {
    it('should return text content', () => {
      const update = new AgentRunResponseUpdate({
        content: { type: 'text', text: 'Hello' },
        role: MessageRole.Assistant,
      });

      expect(update.toString()).toBe('Hello');
    });
  });

  describe('streaming scenarios', () => {
    it('should represent initial chunk', () => {
      const update = new AgentRunResponseUpdate({
        content: { type: 'text', text: 'Hello' },
        role: MessageRole.Assistant,
        responseId: 'resp_123',
        messageId: 'msg_1',
        isFinal: false,
      });

      expect(update.isFinal).toBe(false);
      expect(update.text).toBe('Hello');
    });

    it('should represent middle chunk', () => {
      const update = new AgentRunResponseUpdate({
        content: { type: 'text', text: ' world' },
        role: MessageRole.Assistant,
        responseId: 'resp_123',
        messageId: 'msg_1',
        isFinal: false,
      });

      expect(update.isFinal).toBe(false);
      expect(update.text).toBe(' world');
    });

    it('should represent final chunk with usage', () => {
      const usage: UsageDetails = {
        promptTokens: 10,
        completionTokens: 20,
        totalTokens: 30,
      };

      const update = new AgentRunResponseUpdate({
        content: { type: 'text', text: '!' },
        role: MessageRole.Assistant,
        responseId: 'resp_123',
        messageId: 'msg_1',
        isFinal: true,
        usageDetails: usage,
      });

      expect(update.isFinal).toBe(true);
      expect(update.usageDetails).toBe(usage);
    });
  });
});

describe('Type Compatibility', () => {
  it('should allow ChatAgentOptions to be created from partial', () => {
    const mockClient = {} as any;

    const partial: Partial<ChatAgentOptions> = {
      chatClient: mockClient,
      temperature: 0.7,
    };

    // Should compile without error
    const options: ChatAgentOptions = partial as ChatAgentOptions;
    expect(options.chatClient).toBe(mockClient);
  });

  it('should allow ChatRunOptions with no properties', () => {
    const options: ChatRunOptions = {};
    expect(options).toEqual({});
  });

  it('should enforce ToolChoice type constraints', () => {
    // Valid values
    const validChoices: ToolChoice[] = [
      'auto',
      'required',
      'none',
      { type: 'tool', name: 'func' },
    ];

    expect(validChoices).toHaveLength(4);
  });
});
