/**
 * Context Provider - Base class for managing AI context with lifecycle hooks.
 *
 * This module provides the core ContextProvider abstract class and AIContext interface
 * for managing context data that can be provided to the AI model during invocation.
 *
 * @module context-provider
 */

import { ChatMessage } from '../types/chat-message.js';
import { AITool } from '../tools/base-tool.js';

/**
 * Constant for the default context prompt used when assembling memories/instructions.
 */
export const DEFAULT_CONTEXT_PROMPT =
  '## Memories\nConsider the following memories when answering user questions:';

/**
 * Context data provided to the AI model during invocation.
 *
 * Each ContextProvider can provide its own context for each invocation.
 * This context will be combined with context supplied by other providers before being passed to the AI model.
 * This context is per invocation and will not be stored as part of the chat history.
 *
 * @example
 * ```typescript
 * import { AIContext } from '@microsoft/agent-framework-ts';
 *
 * // Create context with instructions
 * const context: AIContext = {
 *   instructions: "Use a professional tone when responding.",
 *   messages: [{ role: 'user', content: { type: 'text', text: 'Previous context' } }],
 *   tools: [myTool],
 * };
 *
 * // Access context properties
 * console.log(context.instructions);
 * console.log(context.messages.length);
 * ```
 */
export interface AIContext {
  /**
   * Additional instructions to provide to the AI model.
   * These instructions are merged with instructions from other providers.
   */
  instructions?: string;

  /**
   * Additional messages to include in the context.
   * These messages are merged with messages from other providers.
   */
  messages?: ChatMessage[];

  /**
   * Additional tools to provide for this invocation.
   * These tools are merged with tools from other providers.
   */
  tools?: AITool[];
}

/**
 * Abstract base class for all context providers.
 *
 * A context provider is a component that can be used to enhance the AI's context management.
 * It can listen to changes in the conversation and provide additional context to the AI model
 * just before invocation through lifecycle hooks.
 *
 * Lifecycle hooks:
 * - `threadCreated()`: Called when a new thread is created
 * - `invoking()`: Called just before the model is invoked (returns AIContext)
 * - `invoked()`: Called after the model returns a response
 *
 * @note ContextProvider is an abstract base class. You must subclass it and implement
 * the `invoking()` method to create a custom context provider. Ideally, you should
 * also implement the `invoked()` and `threadCreated()` methods to track conversation
 * state, but these are optional.
 *
 * @example
 * ```typescript
 * import { ContextProvider, AIContext, ChatMessage } from '@microsoft/agent-framework-ts';
 *
 * class CustomContextProvider extends ContextProvider {
 *   async invoking(messages: ChatMessage[]): Promise<AIContext> {
 *     // Add custom instructions before each invocation
 *     return {
 *       instructions: "Always be concise and helpful.",
 *       messages: [],
 *       tools: [],
 *     };
 *   }
 * }
 *
 * // Use with a chat agent
 * const provider = new CustomContextProvider();
 * await provider.setup();
 * try {
 *   // Use provider with agent
 * } finally {
 *   await provider.cleanup();
 * }
 * ```
 *
 * @example
 * ```typescript
 * // Example with conversation tracking
 * class ConversationTracker extends ContextProvider {
 *   private threadHistory: Map<string, ChatMessage[]> = new Map();
 *
 *   async threadCreated(threadId: string): Promise<void> {
 *     console.log(`New thread created: ${threadId}`);
 *     this.threadHistory.set(threadId, []);
 *   }
 *
 *   async invoking(messages: ChatMessage[]): Promise<AIContext> {
 *     // Provide context based on conversation history
 *     return {
 *       instructions: "Reference previous conversation context when relevant.",
 *     };
 *   }
 *
 *   async invoked(response: ChatMessage): Promise<void> {
 *     // Track the response for future context
 *     console.log(`Received response: ${response.role}`);
 *   }
 * }
 * ```
 */
export abstract class ContextProvider {
  /**
   * Called just after a new thread is created.
   *
   * Implementers can use this method to perform any operations required at the creation
   * of a new thread. For example, checking long-term storage for any data that is relevant
   * to the current session.
   *
   * @param threadId - The ID of the new thread
   *
   * @example
   * ```typescript
   * async threadCreated(threadId: string): Promise<void> {
   *   console.log(`Thread ${threadId} created`);
   *   // Initialize thread-specific data
   *   await this.loadThreadData(threadId);
   * }
   * ```
   */
  async threadCreated(_threadId: string): Promise<void> {
    // Default implementation does nothing
  }

  /**
   * Called just before the model/agent is invoked.
   *
   * Implementers can load any additional context required at this time,
   * and they should return any context that should be passed to the agent.
   *
   * @param messages - The most recent messages that the agent is being invoked with
   * @param tools - Optional tools available for this invocation
   * @returns A Promise resolving to an AIContext object containing instructions, messages, and tools to include
   *
   * @example
   * ```typescript
   * async invoking(messages: ChatMessage[], tools?: AITool[]): Promise<AIContext> {
   *   // Analyze recent messages to determine context
   *   const lastMessage = messages[messages.length - 1];
   *
   *   return {
   *     instructions: "Be helpful and concise.",
   *     messages: [], // Additional context messages
   *     tools: [], // Additional tools for this invocation
   *   };
   * }
   * ```
   */
  abstract invoking(messages: ChatMessage[], tools?: AITool[]): Promise<AIContext>;

  /**
   * Called after the agent has received a response from the underlying inference service.
   *
   * You can inspect the response message and update the state of the context provider.
   *
   * @param response - The message that was returned by the model/agent
   * @param context - The context that was provided for this invocation
   *
   * @example
   * ```typescript
   * async invoked(response: ChatMessage, context: AIContext): Promise<void> {
   *   // Track response for future context
   *   console.log(`Response received: ${response.role}`);
   *
   *   // Update internal state based on response
   *   if (this.shouldStoreResponse(response)) {
   *     await this.storeResponse(response);
   *   }
   * }
   * ```
   */
  async invoked(_response: ChatMessage, _context: AIContext): Promise<void> {
    // Default implementation does nothing
  }

  /**
   * Setup the context provider.
   *
   * Override this method to perform any setup operations when the context provider is initialized.
   * This is called when the provider is being prepared for use.
   *
   * @example
   * ```typescript
   * async setup(): Promise<void> {
   *   await super.setup();
   *   // Initialize database connections, load configuration, etc.
   *   await this.connectToDatabase();
   * }
   * ```
   */
  async setup(): Promise<void> {
    // Default implementation does nothing
  }

  /**
   * Cleanup the context provider.
   *
   * Override this method to perform any cleanup operations when the context provider is being disposed.
   * This is called when the provider is no longer needed.
   *
   * @example
   * ```typescript
   * async cleanup(): Promise<void> {
   *   // Close database connections, save state, etc.
   *   await this.disconnectFromDatabase();
   *   await super.cleanup();
   * }
   * ```
   */
  async cleanup(): Promise<void> {
    // Default implementation does nothing
  }
}
