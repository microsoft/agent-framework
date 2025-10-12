/**
 * Service Thread Types
 *
 * This module defines types and validation logic for service-managed thread configuration.
 * Service-managed threads store conversation history remotely (e.g., OpenAI Assistants API)
 * rather than locally in a message store.
 *
 * @module service-thread-types
 */

import { AgentInitializationError } from '../errors/agent-errors';
import { ChatMessageStore } from '../storage/message-store';

/**
 * Thread type enumeration.
 *
 * Indicates how conversation history is managed:
 * - **SERVICE_MANAGED**: Thread managed by external service (e.g., OpenAI Assistants)
 * - **LOCAL_MANAGED**: Thread managed locally with message store
 * - **UNDETERMINED**: Thread type not yet determined (will be set on first use)
 *
 * @example
 * ```typescript
 * // Check thread type
 * if (threadType === ThreadType.SERVICE_MANAGED) {
 *   console.log('Using service-managed thread');
 * }
 * ```
 */
export enum ThreadType {
  /** Thread managed by external service (e.g., OpenAI Assistants) */
  SERVICE_MANAGED = 'service_managed',

  /** Thread managed locally with message store */
  LOCAL_MANAGED = 'local_managed',

  /** Thread type not yet determined */
  UNDETERMINED = 'undetermined',
}

/**
 * Options for configuring a service-managed thread.
 *
 * Service-managed threads use a conversation ID provided by the external service
 * to maintain thread state remotely.
 *
 * @example
 * ```typescript
 * const options: ServiceThreadOptions = {
 *   conversationId: 'thread_abc123'
 * };
 * ```
 */
export interface ServiceThreadOptions {
  /** Existing conversation ID from service */
  conversationId?: string;
}

/**
 * Options that can conflict with service-managed threads.
 *
 * Used internally for validation to ensure mutually exclusive thread configurations.
 */
export interface ThreadConfigurationOptions {
  /** Service conversation ID */
  conversationId?: string;
  /** Factory function for creating message stores */
  messageStoreFactory?: () => ChatMessageStore;
}

/**
 * Options for determining thread type.
 *
 * Used by determineThreadType to assess thread configuration state.
 */
export interface ThreadTypeOptions {
  /** Service conversation ID */
  conversationId?: string;
  /** Factory function for creating message stores */
  messageStoreFactory?: () => ChatMessageStore;
  /** Whether a conversation ID was received from a service response */
  hasConversationIdFromResponse?: boolean;
}

/**
 * Validate thread configuration options.
 *
 * Ensures that conversationId and messageStoreFactory are not both provided,
 * as they represent mutually exclusive threading strategies:
 * - **conversationId**: Use service-managed thread (remote storage)
 * - **messageStoreFactory**: Use local-managed thread (local storage)
 *
 * @param options - Thread configuration options to validate
 * @throws {AgentInitializationError} If both conversationId and messageStoreFactory are provided
 *
 * @example
 * ```typescript
 * // Valid - service-managed
 * validateThreadOptions({ conversationId: 'thread-123' });
 *
 * // Valid - local-managed
 * validateThreadOptions({ messageStoreFactory: () => new InMemoryMessageStore() });
 *
 * // Valid - undetermined (neither provided)
 * validateThreadOptions({});
 *
 * // Invalid - throws error
 * try {
 *   validateThreadOptions({
 *     conversationId: 'thread-123',
 *     messageStoreFactory: () => new InMemoryMessageStore()
 *   });
 * } catch (error) {
 *   console.error('Configuration error:', error.message);
 * }
 * ```
 */
export function validateThreadOptions(options: ThreadConfigurationOptions): void {
  if (options.conversationId && options.messageStoreFactory) {
    throw new AgentInitializationError(
      'Cannot specify both conversationId and messageStoreFactory. ' +
        'Use conversationId for service-managed threads or messageStoreFactory for local threads.',
    );
  }
}

/**
 * Determine thread type based on configuration.
 *
 * Returns:
 * - **SERVICE_MANAGED**: If conversationId is provided or was received from service
 * - **LOCAL_MANAGED**: If messageStoreFactory is provided
 * - **UNDETERMINED**: If neither is provided and no service response received
 *
 * @param options - Thread configuration and state options
 * @returns The determined thread type
 *
 * @example
 * ```typescript
 * // Service-managed (explicit)
 * const type1 = determineThreadType({
 *   conversationId: 'thread-123'
 * });
 * console.log(type1); // ThreadType.SERVICE_MANAGED
 *
 * // Service-managed (from response)
 * const type2 = determineThreadType({
 *   hasConversationIdFromResponse: true
 * });
 * console.log(type2); // ThreadType.SERVICE_MANAGED
 *
 * // Local-managed
 * const type3 = determineThreadType({
 *   messageStoreFactory: () => new InMemoryMessageStore()
 * });
 * console.log(type3); // ThreadType.LOCAL_MANAGED
 *
 * // Undetermined
 * const type4 = determineThreadType({});
 * console.log(type4); // ThreadType.UNDETERMINED
 * ```
 */
export function determineThreadType(options: ThreadTypeOptions): ThreadType {
  // Service-managed: explicit conversation ID
  if (options.conversationId) {
    return ThreadType.SERVICE_MANAGED;
  }

  // Service-managed: conversation ID from service response
  if (options.hasConversationIdFromResponse) {
    return ThreadType.SERVICE_MANAGED;
  }

  // Local-managed: message store factory provided
  if (options.messageStoreFactory) {
    return ThreadType.LOCAL_MANAGED;
  }

  // Not yet determined
  return ThreadType.UNDETERMINED;
}

/**
 * Type guard to check if thread type is service-managed.
 *
 * @param threadType - The thread type to check
 * @returns True if thread type is SERVICE_MANAGED
 *
 * @example
 * ```typescript
 * const type = determineThreadType({ conversationId: 'thread-123' });
 * if (isServiceManaged(type)) {
 *   console.log('Using remote thread storage');
 * }
 * ```
 */
export function isServiceManaged(threadType: ThreadType): boolean {
  return threadType === ThreadType.SERVICE_MANAGED;
}

/**
 * Type guard to check if thread type is local-managed.
 *
 * @param threadType - The thread type to check
 * @returns True if thread type is LOCAL_MANAGED
 *
 * @example
 * ```typescript
 * const type = determineThreadType({
 *   messageStoreFactory: () => new InMemoryMessageStore()
 * });
 * if (isLocalManaged(type)) {
 *   console.log('Using local thread storage');
 * }
 * ```
 */
export function isLocalManaged(threadType: ThreadType): boolean {
  return threadType === ThreadType.LOCAL_MANAGED;
}

/**
 * Type guard to check if thread type is undetermined.
 *
 * @param threadType - The thread type to check
 * @returns True if thread type is UNDETERMINED
 *
 * @example
 * ```typescript
 * const type = determineThreadType({});
 * if (isUndetermined(type)) {
 *   console.log('Thread type will be determined on first use');
 * }
 * ```
 */
export function isUndetermined(threadType: ThreadType): boolean {
  return threadType === ThreadType.UNDETERMINED;
}
