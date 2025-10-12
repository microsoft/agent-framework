/**
 * Thread-local message store interfaces and implementations.
 *
 * This module provides interfaces for per-thread message storage used in local-managed threads.
 * Each thread gets its own ChatMessageStore instance for managing conversation history.
 *
 * @module thread-message-store
 */

import { ChatMessage } from '../types/chat-message';

/**
 * Interface for storing and retrieving chat messages in a single thread.
 *
 * Unlike the multi-thread ChatMessageStore, this interface manages messages for a single
 * thread. Each thread creates its own instance when using local-managed message storage.
 *
 * Implementations can be synchronous or asynchronous to support both in-memory and
 * persistent storage backends.
 *
 * @example
 * ```typescript
 * // Using in-memory store
 * const store = new InMemoryMessageStore();
 * await store.addMessage({ role: 'user', content: 'Hello' });
 * const messages = await store.getMessages();
 *
 * // Using with agent
 * const agent = new ChatAgent({
 *   chatClient,
 *   messageStoreFactory: () => new InMemoryMessageStore()
 * });
 * ```
 */
export interface ChatMessageStore {
  /**
   * Add a message to the store.
   *
   * @param message - The message to add
   * @returns Promise that resolves when the message is added, or void for synchronous implementations
   *
   * @example
   * ```typescript
   * const message = { role: 'user', content: 'Hello, world!' };
   * await store.addMessage(message);
   * ```
   */
  addMessage(message: ChatMessage): Promise<void> | void;

  /**
   * Get all messages from the store.
   *
   * Messages are returned in chronological order (oldest first).
   *
   * @returns Promise that resolves to array of messages, or array for synchronous implementations
   *
   * @example
   * ```typescript
   * const messages = await store.getMessages();
   * console.log(`Thread has ${messages.length} messages`);
   * ```
   */
  getMessages(): Promise<ChatMessage[]> | ChatMessage[];

  /**
   * Clear all messages from the store.
   *
   * @returns Promise that resolves when cleared, or void for synchronous implementations
   *
   * @example
   * ```typescript
   * await store.clear();
   * const messages = await store.getMessages(); // []
   * ```
   */
  clear(): Promise<void> | void;

  /**
   * Get the number of messages in the store.
   *
   * @returns Promise that resolves to message count, or number for synchronous implementations
   *
   * @example
   * ```typescript
   * const count = await store.size();
   * console.log(`Store has ${count} messages`);
   * ```
   */
  size(): Promise<number> | number;
}

/**
 * In-memory implementation of ChatMessageStore.
 *
 * Stores messages in a simple array. Not persistent across restarts.
 * This is a synchronous implementation suitable for local development and testing.
 *
 * @example
 * ```typescript
 * const store = new InMemoryMessageStore();
 *
 * // Add messages
 * store.addMessage({ role: 'user', content: 'Hello' });
 * store.addMessage({ role: 'assistant', content: 'Hi there!' });
 *
 * // Retrieve all messages
 * const messages = store.getMessages();
 * console.log(`Chat has ${messages.length} messages`);
 *
 * // Clear the store
 * store.clear();
 * ```
 */
export class InMemoryMessageStore implements ChatMessageStore {
  private messages: ChatMessage[] = [];

  /**
   * Add a message to the store.
   *
   * Messages are appended to the end of the array, maintaining chronological order.
   *
   * @param message - The message to add
   *
   * @example
   * ```typescript
   * const message = { role: 'user', content: 'Hello, world!' };
   * store.addMessage(message);
   * ```
   */
  addMessage(message: ChatMessage): void {
    this.messages.push(message);
  }

  /**
   * Get all messages from the store.
   *
   * Returns a copy of the messages array to prevent external mutations.
   * Messages are in chronological order (oldest first).
   *
   * @returns Array of all messages in the store
   *
   * @example
   * ```typescript
   * const messages = store.getMessages();
   * console.log(`Thread has ${messages.length} messages`);
   * ```
   */
  getMessages(): ChatMessage[] {
    return [...this.messages];
  }

  /**
   * Clear all messages from the store.
   *
   * After clearing, the store will be empty and size() will return 0.
   *
   * @example
   * ```typescript
   * store.clear();
   * console.log(store.size()); // 0
   * ```
   */
  clear(): void {
    this.messages = [];
  }

  /**
   * Get the number of messages in the store.
   *
   * @returns The number of messages currently stored
   *
   * @example
   * ```typescript
   * const count = store.size();
   * console.log(`Store has ${count} messages`);
   * ```
   */
  size(): number {
    return this.messages.length;
  }
}

/**
 * Configuration options for local thread management.
 */
export interface LocalThreadOptions {
  /**
   * Factory function to create message store instances.
   *
   * Each thread will call this factory to create its own message store instance.
   * This enables thread isolation while allowing custom storage implementations.
   *
   * @example
   * ```typescript
   * const agent = new ChatAgent({
   *   chatClient,
   *   messageStoreFactory: () => new InMemoryMessageStore()
   * });
   * ```
   */
  messageStoreFactory?: () => ChatMessageStore;
}

/**
 * Default message store factory.
 *
 * Creates a new InMemoryMessageStore instance. Use this as the default
 * factory for local-managed threads.
 *
 * @returns A new InMemoryMessageStore instance
 *
 * @example
 * ```typescript
 * const agent = new ChatAgent({
 *   chatClient,
 *   messageStoreFactory: createDefaultMessageStore
 * });
 * ```
 */
export function createDefaultMessageStore(): ChatMessageStore {
  return new InMemoryMessageStore();
}
