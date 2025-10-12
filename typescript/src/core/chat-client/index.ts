/**
 * Chat Client Module
 *
 * Core chat client protocol and types for LLM provider abstraction.
 * Includes interfaces, types, and a mock implementation for testing.
 *
 * @module chat-client
 */

// Export protocol
export type { ChatClientProtocol } from './protocol';

// Export types
export type {
  AITool,
  ChatCompletionOptions,
  UsageInfo,
  ProviderMetadata,
  MessageDeltaEvent,
  UsageEvent,
  MetadataEvent,
  StreamEvent,
} from './types';

// Export type guards
export { isMessageDelta, isUsageEvent, isMetadataEvent } from './types';

// Export mock implementation
export { MockChatClient } from './mock-client';
