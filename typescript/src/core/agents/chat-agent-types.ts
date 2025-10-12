/**
 * ChatAgent Types & Interfaces
 *
 * Type definitions for ChatAgent configuration, execution, and responses.
 * These types define the contracts for chat-based agent interactions.
 *
 * @module agents/chat-agent-types
 */

import type { ChatClientProtocol } from '../chat-client/protocol.js';
import type { AITool } from '../tools/base-tool.js';
import type { ContextProvider } from '../context/context-provider.js';
import type { ChatMessage } from '../types/chat-message.js';
import type { AgentThread } from './agent-thread.js';
import type { ChatMessageStore } from '../storage/message-store.js';

/**
 * Tool choice mode for controlling tool usage in chat completions.
 *
 * - `'auto'`: The model decides whether to use tools based on context
 * - `'required'`: The model must use at least one tool
 * - `'none'`: The model cannot use any tools
 * - `{ type: 'tool', name: string }`: The model must use the specified tool
 *
 * @example
 * ```typescript
 * // Let the model decide
 * const choice1: ToolChoice = 'auto';
 *
 * // Force tool usage
 * const choice2: ToolChoice = 'required';
 *
 * // Disable tools
 * const choice3: ToolChoice = 'none';
 *
 * // Require specific tool
 * const choice4: ToolChoice = { type: 'tool', name: 'get_weather' };
 * ```
 */
export type ToolChoice =
  | 'auto'
  | 'required'
  | 'none'
  | { type: 'tool'; name: string };

/**
 * MCP (Model Context Protocol) server configuration.
 *
 * Defines connection settings for external tool servers that provide
 * additional capabilities to agents.
 *
 * @example
 * ```typescript
 * const mcpConfig: MCPServerConfig = {
 *   serverUrl: 'http://localhost:8080',
 *   apiKey: 'secret-key',
 *   timeout: 30000
 * };
 * ```
 */
export interface MCPServerConfig {
  /** URL of the MCP server */
  readonly serverUrl: string;

  /** Optional API key for authentication */
  readonly apiKey?: string;

  /** Optional request timeout in milliseconds */
  readonly timeout?: number;

  /** Additional server-specific configuration */
  readonly [key: string]: unknown;
}

/**
 * Usage statistics for chat completion requests.
 *
 * Tracks token consumption and other metrics for LLM interactions.
 *
 * @example
 * ```typescript
 * const usage: UsageDetails = {
 *   promptTokens: 50,
 *   completionTokens: 100,
 *   totalTokens: 150
 * };
 * ```
 */
export interface UsageDetails {
  /** Number of tokens in the prompt */
  readonly promptTokens?: number;

  /** Number of tokens in the completion */
  readonly completionTokens?: number;

  /** Total tokens used (prompt + completion) */
  readonly totalTokens?: number;

  /** Additional provider-specific usage metrics */
  readonly [key: string]: unknown;
}

/**
 * Options for creating a ChatAgent.
 *
 * Configures the agent's behavior, tools, context providers, and chat settings.
 * All properties except `chatClient` are optional.
 *
 * @example
 * ```typescript
 * import { ChatAgentOptions } from '@microsoft/agent-framework';
 *
 * const options: ChatAgentOptions = {
 *   chatClient: myOpenAIClient,
 *   name: 'assistant',
 *   instructions: 'You are a helpful assistant.',
 *   tools: [weatherTool, calculatorTool],
 *   temperature: 0.7,
 *   maxTokens: 500
 * };
 * ```
 *
 * @example
 * ```typescript
 * // With service-managed threads
 * const options: ChatAgentOptions = {
 *   chatClient: myClient,
 *   conversationId: 'thread_abc123',
 *   instructions: 'Be concise'
 * };
 * ```
 *
 * @example
 * ```typescript
 * // With local message storage
 * const options: ChatAgentOptions = {
 *   chatClient: myClient,
 *   messageStoreFactory: () => new InMemoryMessageStore(),
 *   tools: [myTool]
 * };
 * ```
 */
export interface ChatAgentOptions {
  // Required Properties

  /** Chat client for LLM communication (required) */
  readonly chatClient: ChatClientProtocol;

  // Agent Identity

  /** Unique identifier for the agent. Auto-generated if not provided. */
  readonly id?: string;

  /** Human-readable name for the agent */
  readonly name?: string;

  /** Brief description of the agent's purpose */
  readonly description?: string;

  // Agent Instructions & Context

  /** System instructions that define the agent's behavior and personality */
  readonly instructions?: string;

  /** Context providers for dynamic context injection */
  readonly contextProviders?: ContextProvider | ContextProvider[];

  // Tools & Capabilities

  /** Tools available to the agent for function calling */
  readonly tools?: AITool | AITool[];

  /** MCP server configurations for external tool integration */
  readonly mcpServers?: MCPServerConfig[];

  // Thread Management

  /**
   * Conversation ID for service-managed threads.
   * Cannot be used together with messageStoreFactory.
   */
  readonly conversationId?: string;

  /**
   * Factory function to create message store for local thread management.
   * Cannot be used together with conversationId.
   */
  readonly messageStoreFactory?: () => ChatMessageStore;

  // Chat Completion Parameters

  /** Model identifier to use for completions */
  readonly modelId?: string;

  /** Sampling temperature (0.0 to 2.0). Higher values make output more random. */
  readonly temperature?: number;

  /** Maximum number of tokens to generate */
  readonly maxTokens?: number;

  /** Nucleus sampling parameter (0.0 to 1.0) */
  readonly topP?: number;

  /** Frequency penalty (-2.0 to 2.0). Penalizes repeated tokens based on frequency. */
  readonly frequencyPenalty?: number;

  /** Presence penalty (-2.0 to 2.0). Penalizes repeated tokens based on presence. */
  readonly presencePenalty?: number;

  /** Stop sequences to end generation */
  readonly stop?: string | string[];

  /** Random seed for deterministic sampling */
  readonly seed?: number;

  /** Whether to store the conversation on the service */
  readonly store?: boolean;

  /** Logit bias for token probabilities */
  readonly logitBias?: Record<string, number>;

  /** User identifier for tracking and rate limiting */
  readonly user?: string;

  /** Metadata to attach to requests */
  readonly metadata?: Record<string, unknown>;

  /** Tool choice mode controlling when tools are used */
  readonly toolChoice?: ToolChoice;

  /** Response format specification (e.g., for structured outputs) */
  readonly responseFormat?: unknown;

  // Provider-Specific Options

  /**
   * Additional provider-specific chat options.
   * Use this for parameters specific to your LLM provider.
   *
   * @example
   * ```typescript
   * additionalChatOptions: {
   *   reasoning: { effort: 'high', summary: 'concise' } // OpenAI-specific
   * }
   * ```
   */
  readonly additionalChatOptions?: Record<string, unknown>;

  // Middleware & Additional Properties

  /** Middleware for intercepting agent and function calls */
  readonly middleware?: unknown | unknown[];

  /** Additional properties for custom extensions */
  readonly additionalProperties?: Record<string, unknown>;
}

/**
 * Options for executing a ChatAgent's run() or runStream() methods.
 *
 * These options can override the agent's constructor options for a specific execution.
 * Runtime options take precedence over constructor options.
 *
 * @example
 * ```typescript
 * import { ChatRunOptions } from '@microsoft/agent-framework';
 *
 * const runOptions: ChatRunOptions = {
 *   thread: myThread,
 *   temperature: 0.9,
 *   maxTokens: 200,
 *   toolChoice: 'required'
 * };
 *
 * const response = await agent.run('Hello!', runOptions);
 * ```
 *
 * @example
 * ```typescript
 * // Override tool choice for a specific run
 * const response = await agent.run('Calculate 2+2', {
 *   toolChoice: { type: 'tool', name: 'calculator' }
 * });
 * ```
 */
export interface ChatRunOptions {
  /** Thread to use for this execution. Creates new if not provided. */
  readonly thread?: AgentThread;

  /** Override model identifier */
  readonly modelId?: string;

  /** Override temperature */
  readonly temperature?: number;

  /** Override max tokens */
  readonly maxTokens?: number;

  /** Override top-p */
  readonly topP?: number;

  /** Override frequency penalty */
  readonly frequencyPenalty?: number;

  /** Override presence penalty */
  readonly presencePenalty?: number;

  /** Override stop sequences */
  readonly stop?: string | string[];

  /** Override random seed */
  readonly seed?: number;

  /** Override store flag */
  readonly store?: boolean;

  /** Override logit bias */
  readonly logitBias?: Record<string, number>;

  /** Override user identifier */
  readonly user?: string;

  /** Override metadata */
  readonly metadata?: Record<string, unknown>;

  /** Override tool choice */
  readonly toolChoice?: ToolChoice;

  /** Override response format */
  readonly responseFormat?: unknown;

  /** Override tools for this execution */
  readonly tools?: AITool | AITool[];

  /** Override additional chat options */
  readonly additionalChatOptions?: Record<string, unknown>;

  /** Additional execution-specific properties */
  readonly [key: string]: unknown;
}

/**
 * Response from a ChatAgent execution.
 *
 * Contains the agent's response messages, metadata, and usage statistics.
 * Provides a convenient `.text` getter to extract all text content.
 *
 * @example
 * ```typescript
 * const response = await agent.run('What is TypeScript?');
 *
 * console.log(response.text);
 * // "TypeScript is a typed superset of JavaScript..."
 *
 * console.log(response.messages.length); // 1
 * console.log(response.responseId); // "resp_abc123"
 * console.log(response.usageDetails?.totalTokens); // 150
 * ```
 *
 * @example
 * ```typescript
 * // Access individual messages
 * for (const message of response.messages) {
 *   console.log(message.role, message.content);
 * }
 * ```
 */
export class AgentRunResponse {
  /** Response messages from the agent */
  public readonly messages: ChatMessage[];

  /** Unique identifier for this response */
  public readonly responseId?: string;

  /** Timestamp when the response was created */
  public readonly createdAt?: Date;

  /** Token usage statistics */
  public readonly usageDetails?: UsageDetails;

  /** Structured output value (for structured response formats) */
  public readonly value?: unknown;

  /** Raw response from the underlying chat client */
  public readonly rawRepresentation?: unknown;

  /** Additional properties from the provider */
  public readonly additionalProperties?: Record<string, unknown>;

  /**
   * Create a new AgentRunResponse.
   *
   * @param options - Response configuration
   *
   * @example
   * ```typescript
   * const response = new AgentRunResponse({
   *   messages: [assistantMessage],
   *   responseId: 'resp_123',
   *   usageDetails: { totalTokens: 100 }
   * });
   * ```
   */
  constructor(options: {
    messages: ChatMessage[];
    responseId?: string;
    createdAt?: Date;
    usageDetails?: UsageDetails;
    value?: unknown;
    rawRepresentation?: unknown;
    additionalProperties?: Record<string, unknown>;
  }) {
    this.messages = options.messages;
    this.responseId = options.responseId;
    this.createdAt = options.createdAt;
    this.usageDetails = options.usageDetails;
    this.value = options.value;
    this.rawRepresentation = options.rawRepresentation;
    this.additionalProperties = options.additionalProperties;
  }

  /**
   * Extract all text content from response messages.
   *
   * Concatenates text from all messages in the response.
   * Returns empty string if there are no messages or no text content.
   *
   * @returns Concatenated text from all messages
   *
   * @example
   * ```typescript
   * const response = await agent.run('Hello!');
   * console.log(response.text); // "Hello! How can I help you today?"
   * ```
   */
  get text(): string {
    if (!this.messages || this.messages.length === 0) {
      return '';
    }

    return this.messages
      .map((msg) => {
        // Extract text from message content
        const contents = Array.isArray(msg.content) ? msg.content : [msg.content];
        return contents
          .filter((c) => c.type === 'text')
          .map((c) => (c.type === 'text' ? c.text : ''))
          .join('');
      })
      .join('');
  }

  /**
   * Create AgentRunResponse from streaming updates.
   *
   * Combines multiple AgentRunResponseUpdate objects into a single response.
   * Used internally to aggregate streaming responses.
   *
   * @param updates - Array of streaming updates
   * @returns Complete response assembled from updates
   *
   * @example
   * ```typescript
   * const updates: AgentRunResponseUpdate[] = [];
   * for await (const update of agent.runStream('Hello')) {
   *   updates.push(update);
   * }
   * const response = AgentRunResponse.fromUpdates(updates);
   * ```
   */
  static fromUpdates(updates: AgentRunResponseUpdate[]): AgentRunResponse {
    // Accumulate all updates into messages
    const messageMap = new Map<string, ChatMessage>();
    let lastResponseId: string | undefined;
    let lastCreatedAt: Date | undefined;
    let lastUsage: UsageDetails | undefined;

    for (const update of updates) {
      if (update.responseId) {
        lastResponseId = update.responseId;
      }
      if (update.createdAt) {
        lastCreatedAt = update.createdAt;
      }
      if (update.usageDetails) {
        lastUsage = update.usageDetails;
      }

      const messageId = update.messageId || 'default';

      if (!messageMap.has(messageId)) {
        // Create new message
        messageMap.set(messageId, {
          role: update.role,
          content: update.content || { type: 'text', text: '' },
          name: update.authorName,
          timestamp: update.createdAt,
        });
      } else {
        // Append to existing message
        const existing = messageMap.get(messageId)!;
        const existingContent = Array.isArray(existing.content)
          ? existing.content
          : [existing.content];

        if (update.content) {
          const newContent = Array.isArray(update.content)
            ? update.content
            : [update.content];
          messageMap.set(messageId, {
            ...existing,
            content: [...existingContent, ...newContent],
          });
        }
      }
    }

    return new AgentRunResponse({
      messages: Array.from(messageMap.values()),
      responseId: lastResponseId,
      createdAt: lastCreatedAt,
      usageDetails: lastUsage,
    });
  }

  /**
   * Convert response to a string (returns text content).
   *
   * @returns Text content of the response
   */
  toString(): string {
    return this.text;
  }
}

/**
 * Streaming update from a ChatAgent execution.
 *
 * Represents a single chunk in a streaming response. Updates are yielded
 * as the agent processes the request and generates the response.
 *
 * @example
 * ```typescript
 * for await (const update of agent.runStream('Tell me a story')) {
 *   console.log(update.text); // Print each chunk as it arrives
 *   if (update.isFinal) {
 *     console.log('Stream complete!');
 *   }
 * }
 * ```
 *
 * @example
 * ```typescript
 * // Accumulate updates
 * let fullText = '';
 * for await (const update of agent.runStream('What is 2+2?')) {
 *   fullText += update.text;
 * }
 * console.log(fullText); // "4"
 * ```
 */
export class AgentRunResponseUpdate {
  /** Content in this update chunk */
  public readonly content?: import('../types/chat-message.js').Content | import('../types/chat-message.js').Content[];

  /** Role of the message author */
  public readonly role: import('../types/chat-message.js').MessageRole;

  /** Name of the message author */
  public readonly authorName?: string;

  /** Response ID this update belongs to */
  public readonly responseId?: string;

  /** Message ID this update belongs to */
  public readonly messageId?: string;

  /** Timestamp of this update */
  public readonly createdAt?: Date;

  /** Whether this is the final update in the stream */
  public readonly isFinal: boolean;

  /** Token usage (typically only in final update) */
  public readonly usageDetails?: UsageDetails;

  /** Additional properties from the provider */
  public readonly additionalProperties?: Record<string, unknown>;

  /** Raw update from the underlying chat client */
  public readonly rawRepresentation?: unknown;

  /**
   * Create a new AgentRunResponseUpdate.
   *
   * @param options - Update configuration
   *
   * @example
   * ```typescript
   * const update = new AgentRunResponseUpdate({
   *   content: { type: 'text', text: 'Hello' },
   *   role: MessageRole.Assistant,
   *   isFinal: false
   * });
   * ```
   */
  constructor(options: {
    content?: import('../types/chat-message.js').Content | import('../types/chat-message.js').Content[];
    role: import('../types/chat-message.js').MessageRole;
    authorName?: string;
    responseId?: string;
    messageId?: string;
    createdAt?: Date;
    isFinal?: boolean;
    usageDetails?: UsageDetails;
    additionalProperties?: Record<string, unknown>;
    rawRepresentation?: unknown;
  }) {
    this.content = options.content;
    this.role = options.role;
    this.authorName = options.authorName;
    this.responseId = options.responseId;
    this.messageId = options.messageId;
    this.createdAt = options.createdAt;
    this.isFinal = options.isFinal ?? false;
    this.usageDetails = options.usageDetails;
    this.additionalProperties = options.additionalProperties;
    this.rawRepresentation = options.rawRepresentation;
  }

  /**
   * Extract text content from this update.
   *
   * Returns empty string if there is no text content in this update.
   *
   * @returns Text content of this update
   *
   * @example
   * ```typescript
   * for await (const update of agent.runStream('Count to 3')) {
   *   process.stdout.write(update.text); // "1", "2", "3"
   * }
   * ```
   */
  get text(): string {
    if (!this.content) {
      return '';
    }

    const contents = Array.isArray(this.content) ? this.content : [this.content];
    return contents
      .filter((c) => c.type === 'text')
      .map((c) => (c.type === 'text' ? c.text : ''))
      .join('');
  }

  /**
   * Convert update to a string (returns text content).
   *
   * @returns Text content of this update
   */
  toString(): string {
    return this.text;
  }
}
