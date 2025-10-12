/**
 * In-memory implementation of ChatMessageStore.
 *
 * This module provides a thread-safe, in-memory message store implementation
 * that stores messages in a Map data structure with support for filtering
 * and querying.
 *
 * @module in-memory-store
 */

import { randomUUID } from 'crypto';
import { ChatMessage } from '../types/chat-message';
import { ChatMessageStore, ListOptions } from './message-store';

/**
 * Internal representation of a stored message with an ID.
 */
interface StoredMessage {
  id: string;
  message: ChatMessage;
}

/**
 * In-memory implementation of ChatMessageStore.
 *
 * This implementation stores messages in memory using a Map data structure,
 * with each thread maintaining its own isolated list of messages. Messages
 * are assigned unique IDs if not already present in metadata.
 *
 * Features:
 * - Thread-safe operations using Map
 * - Automatic message ID generation
 * - Support for filtering by role, timestamp, and other criteria
 * - Multiple thread isolation
 * - Efficient querying with sorting and pagination
 *
 * @example
 * ```typescript
 * import { InMemoryMessageStore, createUserMessage, MessageRole } from '@microsoft/agent-framework-ts';
 *
 * // Create a new store
 * const store = new InMemoryMessageStore();
 *
 * // Add messages
 * const message1 = createUserMessage('Hello');
 * await store.add('thread-1', message1);
 *
 * const message2 = createUserMessage('How are you?');
 * await store.add('thread-1', message2);
 *
 * // List all messages
 * const all = await store.list('thread-1');
 * console.log(`Thread has ${all.length} messages`);
 *
 * // Filter by role
 * const userMessages = await store.list('thread-1', {
 *   role: MessageRole.User
 * });
 *
 * // Get messages with pagination
 * const recent = await store.list('thread-1', {
 *   limit: 10,
 *   sortOrder: 'desc'
 * });
 * ```
 */
export class InMemoryMessageStore implements ChatMessageStore {
  private threads: Map<string, StoredMessage[]>;

  /**
   * Create a new InMemoryMessageStore.
   */
  constructor() {
    this.threads = new Map<string, StoredMessage[]>();
  }

  /**
   * Add a message to the specified thread.
   *
   * If the message doesn't have a message ID in its metadata, one will be
   * automatically generated using a UUID.
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
  async add(threadId: string, message: ChatMessage): Promise<void> {
    // Get or create the thread
    let threadMessages = this.threads.get(threadId);
    if (!threadMessages) {
      threadMessages = [];
      this.threads.set(threadId, threadMessages);
    }

    // Generate message ID if not present
    const messageId = (message.metadata?.messageId as string) ?? randomUUID();

    // Store the message with its ID
    const storedMessage: StoredMessage = {
      id: messageId,
      message: {
        ...message,
        metadata: {
          ...message.metadata,
          messageId,
        },
      },
    };

    threadMessages.push(storedMessage);
  }

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
  async get(threadId: string, messageId: string): Promise<ChatMessage | undefined> {
    const threadMessages = this.threads.get(threadId);
    if (!threadMessages) {
      return undefined;
    }

    const stored = threadMessages.find((m) => m.id === messageId);
    return stored?.message;
  }

  /**
   * List messages from the specified thread with optional filtering.
   *
   * Supports filtering by:
   * - Role (user, assistant, system, tool)
   * - Timestamp range (after/before)
   * - Pagination (limit/offset)
   * - Sort order (ascending/descending by timestamp)
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
   * const userMessages = await store.list('thread-1', {
   *   role: MessageRole.User
   * });
   *
   * // Get recent messages with pagination
   * const recent = await store.list('thread-1', {
   *   afterTimestamp: new Date('2024-01-01'),
   *   limit: 10,
   *   sortOrder: 'desc'
   * });
   * ```
   */
  async list(threadId: string, options?: ListOptions): Promise<ChatMessage[]> {
    const threadMessages = this.threads.get(threadId);
    if (!threadMessages) {
      return [];
    }

    // Start with all messages
    let messages = threadMessages.map((m) => m.message);

    // Apply role filter
    if (options?.role !== undefined) {
      messages = messages.filter((m) => m.role === options.role);
    }

    // Apply timestamp filters
    if (options?.afterTimestamp !== undefined) {
      messages = messages.filter((m) => {
        if (!m.timestamp) return false;
        return m.timestamp > options.afterTimestamp!;
      });
    }

    if (options?.beforeTimestamp !== undefined) {
      messages = messages.filter((m) => {
        if (!m.timestamp) return false;
        return m.timestamp < options.beforeTimestamp!;
      });
    }

    // Apply sorting
    const sortOrder = options?.sortOrder ?? 'asc';
    messages.sort((a, b) => {
      const timeA = a.timestamp?.getTime() ?? 0;
      const timeB = b.timestamp?.getTime() ?? 0;
      return sortOrder === 'asc' ? timeA - timeB : timeB - timeA;
    });

    // Apply pagination
    const offset = options?.offset ?? 0;
    const limit = options?.limit;

    if (offset > 0) {
      messages = messages.slice(offset);
    }

    if (limit !== undefined) {
      if (limit === 0) {
        return [];
      }
      if (limit > 0) {
        messages = messages.slice(0, limit);
      }
    }

    return messages;
  }

  /**
   * Clear all messages from the specified thread.
   *
   * After clearing, the thread will have no messages but will still exist
   * in the store. Subsequent add operations will work normally.
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
  async clear(threadId: string): Promise<void> {
    this.threads.delete(threadId);
  }

  /**
   * Get the number of threads in the store.
   *
   * This is a utility method for debugging and testing purposes.
   *
   * @returns The number of threads
   */
  getThreadCount(): number {
    return this.threads.size;
  }

  /**
   * Get the number of messages in a specific thread.
   *
   * This is a utility method for debugging and testing purposes.
   *
   * @param threadId - The ID of the thread
   * @returns The number of messages in the thread
   */
  getMessageCount(threadId: string): number {
    const threadMessages = this.threads.get(threadId);
    return threadMessages?.length ?? 0;
  }
}
