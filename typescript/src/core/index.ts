/**
 * Core functionality for the Agent Framework.
 *
 * @module core
 */

// Error exports
export * from './errors';

// Logging exports
export { Logger, LogLevel, LoggingConfig, getLogger, configureLogging } from './logging/index.js';

// Type exports
export * from './types';

// Storage exports
export * from './storage';

// Chat client exports
export type {
  ChatClientProtocol,
  ChatCompletionOptions,
  UsageInfo,
  ProviderMetadata,
  MessageDeltaEvent,
  UsageEvent,
  MetadataEvent,
  StreamEvent,
} from './chat-client';
export { isMessageDelta, isUsageEvent, isMetadataEvent, MockChatClient } from './chat-client';

// Agent exports
export * from './agents';

// Tool exports (includes AITool which should be the canonical export)
export * from './tools';

// Context exports
export * from './context';

// Serialization exports
export {
  SerializationProtocol,
  SerializationMixin,
  SerializationOptions,
  DeserializationOptions,
  isSerializable,
  isSerializationProtocol,
} from './serialization.js';
