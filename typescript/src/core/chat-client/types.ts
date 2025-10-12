/**
 * Chat Client Types
 *
 * Type definitions for chat completion requests, responses, and streaming events.
 * Part of the ChatClientProtocol interface for LLM provider abstraction.
 *
 * @module chat-client/types
 */

import type { AISettings } from '../types/agent-info';

/**
 * Forward reference to AITool type (will be defined in TASK-005).
 *
 * This represents a tool that can be called by the AI during chat completion.
 * The actual definition will be provided when the Tool interface is implemented.
 */
export interface AITool {
  // Forward reference - will be fully defined in TASK-005
  name: string;
  description?: string;
  [key: string]: unknown;
}

/**
 * Options for chat completion requests.
 *
 * Extends AISettings with chat-specific options including tools, parallel tool calls,
 * service-managed threads, and additional instructions.
 *
 * @example
 * ```typescript
 * const options: ChatCompletionOptions = {
 *   modelId: 'gpt-4',
 *   temperature: 0.7,
 *   maxTokens: 2000,
 *   tools: [calculatorTool, weatherTool],
 *   parallelToolCalls: true,
 * };
 * ```
 */
export interface ChatCompletionOptions extends AISettings {
  /** Available tools that the model can call during completion */
  tools?: AITool[];

  /** Whether to allow the model to call multiple tools in parallel */
  parallelToolCalls?: boolean;

  /**
   * Service-managed thread identifier for multi-turn conversations.
   * Used by providers that maintain conversation state server-side.
   */
  serviceThreadId?: string;

  /**
   * Additional instructions to append to the system message.
   * These are added on top of any existing agent instructions.
   */
  additionalInstructions?: string;

  /**
   * Custom metadata to include with the request.
   * Can be used for tracking, logging, or provider-specific parameters.
   */
  metadata?: Record<string, unknown>;
}

/**
 * Token usage information for a completion request.
 *
 * Tracks the number of tokens consumed by the prompt, completion,
 * and the total tokens used in the request.
 *
 * @example
 * ```typescript
 * const usage: UsageInfo = {
 *   promptTokens: 10,
 *   completionTokens: 25,
 *   totalTokens: 35,
 * };
 * ```
 */
export interface UsageInfo {
  /** Number of tokens in the prompt/input messages */
  promptTokens: number;

  /** Number of tokens generated in the completion/response */
  completionTokens: number;

  /** Total tokens used (promptTokens + completionTokens) */
  totalTokens: number;
}

/**
 * Provider-specific metadata about the completion.
 *
 * Contains information about the provider, model used, finish reason,
 * and any additional provider-specific fields.
 *
 * @example
 * ```typescript
 * const metadata: ProviderMetadata = {
 *   provider: 'openai',
 *   modelId: 'gpt-4-0613',
 *   finishReason: 'stop',
 *   requestId: 'req_abc123',
 * };
 * ```
 */
export interface ProviderMetadata {
  /** Provider identifier (e.g., 'openai', 'azure-openai', 'anthropic') */
  provider: string;

  /** Actual model used for the completion (may differ from requested model) */
  modelId: string;

  /**
   * Reason why the model stopped generating.
   * Common values: 'stop', 'length', 'tool_calls', 'content_filter'
   */
  finishReason?: string;

  /** Additional provider-specific fields */
  [key: string]: unknown;
}

/**
 * Message delta event in a streaming response.
 *
 * Contains a partial ChatMessage with incremental content updates.
 */
export type MessageDeltaEvent = {
  type: 'message_delta';
  /** Partial message with incremental updates */
  delta: Partial<import('../types/chat-message').ChatMessage>;
};

/**
 * Usage information event in a streaming response.
 *
 * Typically sent at the end of the stream with final token counts.
 */
export type UsageEvent = {
  type: 'usage';
  /** Token usage information */
  usage: UsageInfo;
};

/**
 * Metadata event in a streaming response.
 *
 * Contains provider-specific metadata about the completion.
 */
export type MetadataEvent = {
  type: 'metadata';
  /** Provider metadata */
  metadata: ProviderMetadata;
};

/**
 * Stream event types for chat completion streaming.
 *
 * A discriminated union representing the different types of events
 * that can be emitted during a streaming chat completion.
 *
 * @example
 * ```typescript
 * for await (const event of stream) {
 *   if (event.type === 'message_delta') {
 *     console.log('Delta:', event.delta);
 *   } else if (event.type === 'usage') {
 *     console.log('Usage:', event.usage);
 *   } else if (event.type === 'metadata') {
 *     console.log('Metadata:', event.metadata);
 *   }
 * }
 * ```
 */
export type StreamEvent = MessageDeltaEvent | UsageEvent | MetadataEvent;

// Type Guards

/**
 * Type guard for message delta events.
 *
 * @param event - Stream event to check
 * @returns True if event is a MessageDeltaEvent
 *
 * @example
 * ```typescript
 * if (isMessageDelta(event)) {
 *   console.log(event.delta.content); // TypeScript knows event is MessageDeltaEvent
 * }
 * ```
 */
export function isMessageDelta(event: StreamEvent): event is MessageDeltaEvent {
  return event.type === 'message_delta';
}

/**
 * Type guard for usage events.
 *
 * @param event - Stream event to check
 * @returns True if event is a UsageEvent
 *
 * @example
 * ```typescript
 * if (isUsageEvent(event)) {
 *   console.log(`Tokens: ${event.usage.totalTokens}`); // TypeScript knows event is UsageEvent
 * }
 * ```
 */
export function isUsageEvent(event: StreamEvent): event is UsageEvent {
  return event.type === 'usage';
}

/**
 * Type guard for metadata events.
 *
 * @param event - Stream event to check
 * @returns True if event is a MetadataEvent
 *
 * @example
 * ```typescript
 * if (isMetadataEvent(event)) {
 *   console.log(`Provider: ${event.metadata.provider}`); // TypeScript knows event is MetadataEvent
 * }
 * ```
 */
export function isMetadataEvent(event: StreamEvent): event is MetadataEvent {
  return event.type === 'metadata';
}
