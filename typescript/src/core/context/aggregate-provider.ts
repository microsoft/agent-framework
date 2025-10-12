/**
 * Aggregate Context Provider - Combines multiple context providers.
 *
 * This module provides the AggregateContextProvider class that delegates events
 * to multiple context providers and aggregates their responses.
 *
 * @module aggregate-provider
 */

import { ContextProvider, AIContext } from './context-provider.js';
import { ChatMessage } from '../types/chat-message.js';
import { AITool } from '../tools/base-tool.js';

/**
 * A ContextProvider that contains multiple context providers.
 *
 * It delegates events to multiple context providers and aggregates responses from those
 * events before returning. This allows you to combine multiple context providers into a
 * single provider.
 *
 * The AggregateContextProvider merges context from all providers by:
 * - Concatenating instructions (with newlines between)
 * - Combining message arrays
 * - Combining tool arrays
 *
 * @note An AggregateContextProvider can be created to combine multiple providers
 * when building agents or complex systems.
 *
 * @example
 * ```typescript
 * import { AggregateContextProvider } from '@microsoft/agent-framework-ts';
 *
 * // Create multiple context providers
 * const provider1 = new CustomContextProvider1();
 * const provider2 = new CustomContextProvider2();
 * const provider3 = new CustomContextProvider3();
 *
 * // Combine them into an aggregate provider
 * const aggregate = new AggregateContextProvider([provider1, provider2, provider3]);
 *
 * // Setup and use
 * await aggregate.setup();
 * const context = await aggregate.invoking(messages);
 * // context contains merged results from all three providers
 * ```
 *
 * @example
 * ```typescript
 * // Add providers dynamically
 * const aggregate = new AggregateContextProvider();
 * aggregate.add(new MemoryProvider());
 * aggregate.add(new PreferencesProvider());
 * aggregate.add(new ToolProvider());
 *
 * // All providers will be called during lifecycle hooks
 * await aggregate.threadCreated('thread-123');
 * ```
 */
export class AggregateContextProvider extends ContextProvider {
  /**
   * The list of context providers managed by this aggregate.
   */
  public readonly providers: ContextProvider[];

  /**
   * Initialize the AggregateContextProvider with context providers.
   *
   * @param contextProviders - The context provider(s) to add (single provider, array, or undefined)
   *
   * @example
   * ```typescript
   * // With array of providers
   * const aggregate = new AggregateContextProvider([provider1, provider2]);
   *
   * // With single provider
   * const aggregate = new AggregateContextProvider(provider1);
   *
   * // Empty (add providers later)
   * const aggregate = new AggregateContextProvider();
   * aggregate.add(provider1);
   * ```
   */
  constructor(contextProviders?: ContextProvider | ContextProvider[]) {
    super();

    if (contextProviders === undefined || contextProviders === null) {
      this.providers = [];
    } else if (Array.isArray(contextProviders)) {
      this.providers = [...contextProviders];
    } else {
      this.providers = [contextProviders];
    }
  }

  /**
   * Add a new context provider to the aggregate.
   *
   * @param contextProvider - The context provider to add
   *
   * @example
   * ```typescript
   * const aggregate = new AggregateContextProvider();
   * aggregate.add(new MemoryProvider());
   * aggregate.add(new ToolProvider());
   * ```
   */
  add(contextProvider: ContextProvider): void {
    this.providers.push(contextProvider);
  }

  /**
   * Called just after a new thread is created.
   *
   * Delegates the threadCreated call to all contained providers in parallel.
   *
   * @param threadId - The ID of the new thread
   */
  async threadCreated(threadId: string): Promise<void> {
    await Promise.all(this.providers.map((provider) => provider.threadCreated(threadId)));
  }

  /**
   * Called just before the model/agent is invoked.
   *
   * Delegates the invoking call to all contained providers in parallel and merges their results.
   * Instructions are concatenated with newlines, messages and tools are combined into arrays.
   *
   * @param messages - The most recent messages that the agent is being invoked with
   * @param tools - Optional tools available for this invocation
   * @returns A Promise resolving to merged AIContext from all providers
   *
   * @example
   * ```typescript
   * const aggregate = new AggregateContextProvider([provider1, provider2]);
   * const context = await aggregate.invoking(messages);
   * // context.instructions contains concatenated instructions from both providers
   * // context.messages contains combined messages from both providers
   * // context.tools contains combined tools from both providers
   * ```
   */
  async invoking(messages: ChatMessage[], tools?: AITool[]): Promise<AIContext> {
    // Call all providers in parallel
    const contexts = await Promise.all(
      this.providers.map((provider) => provider.invoking(messages, tools))
    );

    // Merge all contexts
    const instructions: string[] = [];
    const mergedMessages: ChatMessage[] = [];
    const mergedTools: AITool[] = [];

    for (const ctx of contexts) {
      if (ctx.instructions) {
        instructions.push(ctx.instructions);
      }
      if (ctx.messages && ctx.messages.length > 0) {
        mergedMessages.push(...ctx.messages);
      }
      if (ctx.tools && ctx.tools.length > 0) {
        mergedTools.push(...ctx.tools);
      }
    }

    return {
      instructions: instructions.length > 0 ? instructions.join('\n') : undefined,
      messages: mergedMessages.length > 0 ? mergedMessages : undefined,
      tools: mergedTools.length > 0 ? mergedTools : undefined,
    };
  }

  /**
   * Called after the agent has received a response from the underlying inference service.
   *
   * Delegates the invoked call to all contained providers in parallel.
   *
   * @param response - The message that was returned by the model/agent
   * @param context - The context that was provided for this invocation
   */
  async invoked(response: ChatMessage, context: AIContext): Promise<void> {
    await Promise.all(this.providers.map((provider) => provider.invoked(response, context)));
  }

  /**
   * Setup all contained context providers.
   *
   * Calls setup on all providers in parallel.
   */
  async setup(): Promise<void> {
    await Promise.all(this.providers.map((provider) => provider.setup()));
  }

  /**
   * Cleanup all contained context providers.
   *
   * Calls cleanup on all providers in parallel.
   */
  async cleanup(): Promise<void> {
    await Promise.all(this.providers.map((provider) => provider.cleanup()));
  }
}
