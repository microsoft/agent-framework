/**
 * Agent Thread Management
 *
 * This module defines AgentThread class for managing conversation threads,
 * supporting both service-managed and local-managed thread modes with
 * complete serialization support.
 *
 * @module agent-thread
 */

import { ChatMessage } from '../types/chat-message';
import { ChatMessageStore } from '../storage/message-store';
import { InMemoryMessageStore } from '../storage/in-memory-store';
import { AgentThreadError } from '../errors/agent-errors';

/**
 * Serialized state for a ChatMessageStore.
 * Contains all messages in the store.
 */
export interface MessageStoreState {
  /** List of messages in the store */
  messages: ChatMessage[];
}

/**
 * Serialized state for an AgentThread.
 * Contains either a service thread ID OR message store state, never both.
 */
export interface ThreadState {
  /** ID of a service-managed thread (mutually exclusive with messageStoreState) */
  serviceThreadId?: string;
  /** State of a local message store (mutually exclusive with serviceThreadId) */
  messageStoreState?: MessageStoreState;
}

/**
 * Options for creating a new AgentThread.
 */
export interface AgentThreadOptions {
  /** ID of a service-managed thread (mutually exclusive with messageStore) */
  serviceThreadId?: string;
  /** Local message store instance (mutually exclusive with serviceThreadId) */
  messageStore?: ChatMessageStore;
}

/**
 * Represents a conversation thread for an agent.
 *
 * An AgentThread maintains conversation state and message history. It supports
 * two mutually exclusive modes:
 *
 * 1. **Service-managed threads**: Thread state is stored remotely by a service
 *    (e.g., OpenAI Assistants API). Identified by `serviceThreadId`.
 *
 * 2. **Local-managed threads**: Thread state is stored locally using a
 *    `ChatMessageStore` implementation.
 *
 * These modes are mutually exclusive - a thread cannot have both a
 * `serviceThreadId` and a `messageStore`.
 *
 * @example
 * ```typescript
 * // Service-managed thread
 * const serviceThread = new AgentThread({
 *   serviceThreadId: 'thread_abc123'
 * });
 *
 * // Local-managed thread with in-memory store
 * const localThread = new AgentThread({
 *   messageStore: new InMemoryMessageStore()
 * });
 *
 * // Serialize and restore thread state
 * const state = await localThread.serialize();
 * const restored = await AgentThread.deserialize(state);
 *
 * // Add messages to a thread
 * const message = createUserMessage('Hello');
 * await localThread.onNewMessages([message]);
 * ```
 */
export class AgentThread {
  private _serviceThreadId?: string;
  private _messageStore?: ChatMessageStore;
  private _threadId: string;

  /**
   * Create a new AgentThread.
   *
   * Either `serviceThreadId` OR `messageStore` may be provided, but not both.
   * If neither is provided, the thread is uninitialized and will be configured
   * on first use.
   *
   * @param options - Configuration options for the thread
   * @throws {AgentThreadError} If both serviceThreadId and messageStore are provided
   *
   * @example
   * ```typescript
   * // Service-managed thread
   * const thread1 = new AgentThread({ serviceThreadId: 'thread_123' });
   *
   * // Local-managed thread
   * const thread2 = new AgentThread({ messageStore: new InMemoryMessageStore() });
   *
   * // Uninitialized thread
   * const thread3 = new AgentThread({});
   * ```
   */
  constructor(options: AgentThreadOptions = {}) {
    const { serviceThreadId, messageStore } = options;

    // Validate mutually exclusive constraint
    if (serviceThreadId !== undefined && messageStore !== undefined) {
      throw new AgentThreadError(
        'Cannot specify both serviceThreadId and messageStore. ' +
          'Use serviceThreadId for service-managed threads or messageStore for local storage.',
      );
    }

    this._serviceThreadId = serviceThreadId;
    this._messageStore = messageStore;
    this._threadId = this._generateThreadId();
  }

  /**
   * Generate a unique thread ID for internal tracking.
   */
  private _generateThreadId(): string {
    return `thread_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
  }

  /**
   * Get the ID of the service-managed thread.
   * Returns undefined if this is a local-managed thread.
   */
  get serviceThreadId(): string | undefined {
    return this._serviceThreadId;
  }

  /**
   * Set the ID of the service-managed thread.
   *
   * @throws {AgentThreadError} If the thread already has a message store
   */
  set serviceThreadId(value: string | undefined) {
    if (value === undefined) {
      return;
    }

    if (this._messageStore !== undefined) {
      throw new AgentThreadError(
        'Cannot set serviceThreadId when messageStore is already set. ' +
          'Threads cannot switch between service-managed and local-managed modes.',
      );
    }

    this._serviceThreadId = value;
  }

  /**
   * Get the local message store.
   * Returns undefined if this is a service-managed thread.
   */
  get messageStore(): ChatMessageStore | undefined {
    return this._messageStore;
  }

  /**
   * Set the local message store.
   *
   * @throws {AgentThreadError} If the thread already has a service thread ID
   */
  set messageStore(value: ChatMessageStore | undefined) {
    if (value === undefined) {
      return;
    }

    if (this._serviceThreadId !== undefined) {
      throw new AgentThreadError(
        'Cannot set messageStore when serviceThreadId is already set. ' +
          'Threads cannot switch between service-managed and local-managed modes.',
      );
    }

    this._messageStore = value;
  }

  /**
   * Get the internal thread ID for tracking.
   */
  get threadId(): string {
    return this._threadId;
  }

  /**
   * Check if the thread is initialized.
   * A thread is initialized if it has either a serviceThreadId or a messageStore.
   */
  get isInitialized(): boolean {
    return this._serviceThreadId !== undefined || this._messageStore !== undefined;
  }

  /**
   * Check if this is a service-managed thread.
   */
  get isServiceManaged(): boolean {
    return this._serviceThreadId !== undefined;
  }

  /**
   * Check if this is a local-managed thread.
   */
  get isLocalManaged(): boolean {
    return this._messageStore !== undefined;
  }

  /**
   * Handle new messages added to the conversation.
   *
   * For service-managed threads, this is a no-op as the service handles storage.
   * For local-managed threads, messages are added to the message store.
   * For uninitialized threads, a default in-memory store is created.
   *
   * @param messages - Message or array of messages to add
   *
   * @example
   * ```typescript
   * const message = createUserMessage('Hello');
   * await thread.onNewMessages([message]);
   *
   * // Or a single message
   * await thread.onNewMessages(message);
   * ```
   */
  async onNewMessages(messages: ChatMessage | ChatMessage[]): Promise<void> {
    // Service-managed threads don't need to store messages locally
    if (this._serviceThreadId !== undefined) {
      return;
    }

    // Create default store if needed
    if (this._messageStore === undefined) {
      this._messageStore = new InMemoryMessageStore();
    }

    // Add messages to store
    const messageArray = Array.isArray(messages) ? messages : [messages];
    for (const message of messageArray) {
      await this._messageStore.add(this._threadId, message);
    }
  }

  /**
   * Get all messages from the thread.
   *
   * @returns Array of messages, or empty array for service-managed threads
   *
   * @example
   * ```typescript
   * const messages = await thread.getMessages();
   * console.log(`Thread has ${messages.length} messages`);
   * ```
   */
  async getMessages(): Promise<ChatMessage[]> {
    if (this._messageStore === undefined) {
      return [];
    }

    return await this._messageStore.list(this._threadId);
  }

  /**
   * Serialize the thread state for persistence.
   *
   * The serialized state includes either:
   * - `serviceThreadId` for service-managed threads
   * - `messageStoreState` with all messages for local-managed threads
   *
   * @returns Promise resolving to the serialized thread state
   *
   * @example
   * ```typescript
   * const state = await thread.serialize();
   * // Save state to database, file, etc.
   * await saveToDatabase(state);
   * ```
   */
  async serialize(): Promise<ThreadState> {
    const state: ThreadState = {};

    if (this._serviceThreadId !== undefined) {
      state.serviceThreadId = this._serviceThreadId;
    } else if (this._messageStore !== undefined) {
      const messages = await this._messageStore.list(this._threadId);
      state.messageStoreState = { messages };
    }

    return state;
  }

  /**
   * Deserialize a thread from saved state.
   *
   * Creates a new AgentThread instance from previously serialized state.
   * The thread will be configured as either service-managed or local-managed
   * based on the state content.
   *
   * @param state - Previously serialized thread state
   * @param messageStore - Optional custom message store to use for local-managed threads
   * @returns Promise resolving to a new AgentThread instance
   * @throws {AgentThreadError} If the state is invalid or contains both modes
   *
   * @example
   * ```typescript
   * // Deserialize with default in-memory store
   * const thread = await AgentThread.deserialize(savedState);
   *
   * // Deserialize with custom store
   * const customStore = new CustomMessageStore();
   * const thread = await AgentThread.deserialize(savedState, customStore);
   * ```
   */
  static async deserialize(state: ThreadState, messageStore?: ChatMessageStore): Promise<AgentThread> {
    // Validate state
    if (state.serviceThreadId !== undefined && state.messageStoreState !== undefined) {
      throw new AgentThreadError(
        'Invalid thread state: cannot have both serviceThreadId and messageStoreState. ' +
          'Thread state must represent either a service-managed or local-managed thread, not both.',
      );
    }

    // Service-managed thread
    if (state.serviceThreadId !== undefined) {
      return new AgentThread({ serviceThreadId: state.serviceThreadId });
    }

    // Local-managed thread
    if (state.messageStoreState !== undefined) {
      const store = messageStore ?? new InMemoryMessageStore();
      const thread = new AgentThread({ messageStore: store });

      // Add messages to the store
      if (state.messageStoreState.messages && state.messageStoreState.messages.length > 0) {
        await thread.onNewMessages(state.messageStoreState.messages);
      }

      return thread;
    }

    // Uninitialized thread
    return new AgentThread({});
  }

  /**
   * Update this thread from serialized state.
   *
   * This method modifies the current thread instance rather than creating a new one.
   * Useful for restoring thread state in place.
   *
   * @param state - Previously serialized thread state
   * @throws {AgentThreadError} If the state is invalid or would cause a mode conflict
   *
   * @example
   * ```typescript
   * const thread = new AgentThread({});
   * await thread.updateFromState(savedState);
   * ```
   */
  async updateFromState(state: ThreadState): Promise<void> {
    // Validate state
    if (state.serviceThreadId !== undefined && state.messageStoreState !== undefined) {
      throw new AgentThreadError(
        'Invalid thread state: cannot have both serviceThreadId and messageStoreState.',
      );
    }

    // Update service thread ID
    if (state.serviceThreadId !== undefined) {
      this.serviceThreadId = state.serviceThreadId;
      return;
    }

    // Update local-managed state
    if (state.messageStoreState !== undefined) {
      // If we don't have a message store yet, create one using the setter
      // This will throw if we already have a serviceThreadId
      if (this._messageStore === undefined) {
        this.messageStore = new InMemoryMessageStore();
      }

      // Add messages to the store
      if (state.messageStoreState.messages && state.messageStoreState.messages.length > 0) {
        await this.onNewMessages(state.messageStoreState.messages);
      }
    }
  }

  /**
   * Clear all messages from a local-managed thread.
   *
   * This is a no-op for service-managed threads.
   *
   * @example
   * ```typescript
   * await thread.clear();
   * const messages = await thread.getMessages(); // []
   * ```
   */
  async clear(): Promise<void> {
    if (this._messageStore !== undefined) {
      await this._messageStore.clear(this._threadId);
    }
  }
}
