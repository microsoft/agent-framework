/**
 * Message store interfaces for persisting and retrieving chat messages.
 *
 * This module defines the ChatMessageStore interface for managing chat messages
 * in conversations, along with filtering and querying options.
 *
 * @module message-store
 */

import { ChatMessage, MessageRole } from '../types/chat-message';

/**
 * Options for filtering and querying messages from the store.
 */
export interface ListOptions {
  /** Filter messages by role */
  role?: MessageRole;
  /** Filter messages created after this timestamp */
  afterTimestamp?: Date;
  /** Filter messages created before this timestamp */
  beforeTimestamp?: Date;
  /** Maximum number of messages to return */
  limit?: number;
  /** Number of messages to skip (for pagination) */
  offset?: number;
  /** Sort order: 'asc' for oldest first, 'desc' for newest first */
  sortOrder?: 'asc' | 'desc';
}

/**
 * Interface for storing and retrieving chat messages associated with threads.
 *
 * Implementations of this interface are responsible for managing the storage
 * of chat messages, supporting multiple threads with isolation between them.
 *
 * @example
 * ```typescript
 * // Create a message store
 * const store = new InMemoryMessageStore();
 *
 * // Add messages to a thread
 * await store.add('thread-1', createUserMessage('Hello'));
 *
 * // Retrieve messages
 * const messages = await store.list('thread-1');
 *
 * // Get a specific message
 * const message = await store.get('thread-1', 'message-id');
 *
 * // Clear a thread
 * await store.clear('thread-1');
 * ```
 */
export interface ChatMessageStore {
  /**
   * Add a message to the specified thread.
   *
   * @param threadId - The ID of the thread
   * @param message - The message to add
   * @returns Promise that resolves when the message is added
   *
   * @example
   * ```typescript
   * const message = createUserMessage('Hello, world!');
   * await store.add('thread-1', message);
   * ```
   */
  add(threadId: string, message: ChatMessage): Promise<void>;

  /**
   * Retrieve a specific message from the store.
   *
   * @param threadId - The ID of the thread
   * @param messageId - The ID of the message to retrieve
   * @returns Promise that resolves to the message if found, undefined otherwise
   *
   * @example
   * ```typescript
   * const message = await store.get('thread-1', 'msg-123');
   * if (message) {
   *   console.log(message.content);
   * }
   * ```
   */
  get(threadId: string, messageId: string): Promise<ChatMessage | undefined>;

  /**
   * List messages from the specified thread with optional filtering.
   *
   * @param threadId - The ID of the thread
   * @param options - Optional filtering and pagination options
   * @returns Promise that resolves to an array of messages
   *
   * @example
   * ```typescript
   * // Get all messages
   * const all = await store.list('thread-1');
   *
   * // Get only user messages
   * const userMessages = await store.list('thread-1', { role: MessageRole.User });
   *
   * // Get recent messages
   * const recent = await store.list('thread-1', {
   *   afterTimestamp: new Date('2024-01-01'),
   *   limit: 10
   * });
   * ```
   */
  list(threadId: string, options?: ListOptions): Promise<ChatMessage[]>;

  /**
   * Clear all messages from the specified thread.
   *
   * @param threadId - The ID of the thread to clear
   * @returns Promise that resolves when the thread is cleared
   *
   * @example
   * ```typescript
   * await store.clear('thread-1');
   * const messages = await store.list('thread-1'); // []
   * ```
   */
  clear(threadId: string): Promise<void>;
}
