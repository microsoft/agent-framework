/**
 * BaseAgent - Abstract base class for AI agents with lifecycle hooks.
 *
 * This module provides the core AgentProtocol interface and BaseAgent abstract class
 * for implementing AI agents with chat client integration, tool support, context providers,
 * and lifecycle hooks.
 *
 * @module agents/base-agent
 */

import type { ChatMessage } from '../types/chat-message.js';
import type { AgentInfo, AISettings } from '../types/agent-info.js';
import type { ChatClientProtocol } from '../chat-client/protocol.js';
import type { ChatCompletionOptions } from '../chat-client/types.js';
import type { AITool } from '../tools/base-tool.js';
import type { ContextProvider, AIContext } from '../context/context-provider.js';
import { isMessageDelta } from '../chat-client/types.js';
import { MessageRole } from '../types/chat-message.js';

/**
 * Protocol interface for AI agents.
 *
 * Defines the standard interface that all agent implementations must follow.
 * This uses structural typing, so any class implementing these methods is compatible.
 *
 * @example
 * ```typescript
 * import { AgentProtocol, ChatMessage } from '@microsoft/agent-framework-ts';
 *
 * class CustomAgent implements AgentProtocol {
 *   readonly info = { id: 'custom', name: 'Custom Agent' };
 *   readonly chatClient = myChatClient;
 *   readonly tools = [];
 *
 *   async invoke(messages: ChatMessage[]): Promise<ChatMessage> {
 *     // Custom implementation
 *   }
 *
 *   async *invokeStream(messages: ChatMessage[]): AsyncIterable<ChatMessage> {
 *     // Custom streaming implementation
 *   }
 * }
 * ```
 */
export interface AgentProtocol {
  /** Agent metadata and configuration */
  readonly info: AgentInfo;

  /** Chat client for LLM communication */
  readonly chatClient: ChatClientProtocol;

  /** Tools available to this agent */
  readonly tools: AITool[];

  /** Optional context provider for dynamic context injection */
  readonly contextProvider?: ContextProvider;

  /**
   * Invoke the agent with messages and get a complete response.
   *
   * This is a blocking operation that returns the full response after the LLM completes.
   *
   * @param messages - Input messages for the agent
   * @param options - Optional AI settings to override defaults
   * @returns Promise resolving to the assistant's response message
   *
   * @example
   * ```typescript
   * const response = await agent.invoke([
   *   createUserMessage('What is TypeScript?')
   * ]);
   * console.log(getTextContent(response));
   * ```
   */
  invoke(messages: ChatMessage[], options?: AISettings): Promise<ChatMessage>;

  /**
   * Invoke the agent with streaming responses.
   *
   * Returns an async iterable that yields complete ChatMessage objects as they are
   * assembled from streaming deltas.
   *
   * @param messages - Input messages for the agent
   * @param options - Optional AI settings to override defaults
   * @returns AsyncIterable yielding ChatMessage objects
   *
   * @example
   * ```typescript
   * for await (const message of agent.invokeStream([createUserMessage('Tell a story')])) {
   *   console.log(getTextContent(message));
   * }
   * ```
   */
  invokeStream(messages: ChatMessage[], options?: AISettings): AsyncIterable<ChatMessage>;
}

/**
 * Abstract base class for AI agents.
 *
 * Provides core functionality for agent implementations including:
 * - Chat client integration
 * - Tool management
 * - Context provider integration with lifecycle hooks
 * - Lifecycle hooks (beforeInvoke, afterInvoke)
 * - Streaming support
 *
 * Subclasses can override lifecycle hooks to customize behavior before and after LLM calls.
 *
 * @note This is an abstract class and cannot be instantiated directly.
 * Create a concrete subclass to use it.
 *
 * @example
 * ```typescript
 * import { BaseAgent, ChatMessage } from '@microsoft/agent-framework-ts';
 *
 * class SimpleAgent extends BaseAgent {
 *   // Optionally override lifecycle hooks
 *   protected async beforeInvoke(messages: ChatMessage[]): Promise<ChatMessage[]> {
 *     console.log('About to invoke LLM');
 *     return messages;
 *   }
 *
 *   protected async afterInvoke(request: ChatMessage[], response: ChatMessage): Promise<void> {
 *     console.log('LLM invocation complete');
 *   }
 * }
 *
 * const agent = new SimpleAgent({
 *   info: { id: 'agent-1', name: 'My Agent', instructions: 'Be helpful' },
 *   chatClient: myChatClient,
 *   tools: [weatherTool, calculatorTool],
 * });
 *
 * const response = await agent.invoke([createUserMessage('Hello')]);
 * ```
 *
 * @example
 * ```typescript
 * // With context provider
 * const agent = new SimpleAgent({
 *   info: { id: 'agent-2', name: 'Context Agent' },
 *   chatClient: myChatClient,
 *   contextProvider: myContextProvider,
 * });
 *
 * // Context provider's invoking() will be called before LLM
 * // Context provider's invoked() will be called after LLM
 * const response = await agent.invoke([createUserMessage('What do you know?')]);
 * ```
 *
 * @example
 * ```typescript
 * // Streaming support
 * for await (const message of agent.invokeStream([createUserMessage('Tell a story')])) {
 *   process.stdout.write(getTextContent(message));
 * }
 * ```
 */
export abstract class BaseAgent implements AgentProtocol {
  /** Agent metadata and configuration */
  public readonly info: AgentInfo;

  /** Chat client for LLM communication */
  public readonly chatClient: ChatClientProtocol;

  /** Tools available to this agent */
  public readonly tools: AITool[];

  /** Optional context provider for dynamic context injection */
  public readonly contextProvider?: ContextProvider;

  /**
   * Create a new BaseAgent instance.
   *
   * @param config - Configuration object
   * @param config.info - Agent metadata and configuration
   * @param config.chatClient - Chat client for LLM communication
   * @param config.tools - Optional array of tools available to the agent
   * @param config.contextProvider - Optional context provider for dynamic context
   *
   * @example
   * ```typescript
   * const agent = new MyAgent({
   *   info: {
   *     id: 'agent-1',
   *     name: 'Assistant',
   *     description: 'A helpful assistant',
   *     instructions: 'Be concise and helpful',
   *   },
   *   chatClient: myChatClient,
   *   tools: [weatherTool],
   *   contextProvider: myContextProvider,
   * });
   * ```
   */
  constructor(config: {
    info: AgentInfo;
    chatClient: ChatClientProtocol;
    tools?: AITool[];
    contextProvider?: ContextProvider;
  }) {
    this.info = config.info;
    this.chatClient = config.chatClient;
    this.tools = config.tools || [];
    this.contextProvider = config.contextProvider;
  }

  /**
   * Invoke the agent with messages and get a complete response.
   *
   * Execution flow:
   * 1. Call beforeInvoke() hook
   * 2. Call contextProvider.invoking() if present
   * 3. Merge context (instructions, messages, tools)
   * 4. Call chatClient.complete() with merged data
   * 5. Call afterInvoke() hook
   * 6. Call contextProvider.invoked() if present
   * 7. Return response
   *
   * @param messages - Input messages for the agent
   * @param options - Optional AI settings to override defaults
   * @returns Promise resolving to the assistant's response message
   *
   * @example
   * ```typescript
   * const response = await agent.invoke(
   *   [createUserMessage('What is 2+2?')],
   *   { temperature: 0.7, maxTokens: 100 }
   * );
   * console.log(getTextContent(response)); // "4"
   * ```
   */
  async invoke(messages: ChatMessage[], options?: AISettings): Promise<ChatMessage> {
    // Apply before hook
    messages = await this.beforeInvoke(messages);

    // Get context from provider
    let context: AIContext | undefined;
    if (this.contextProvider) {
      context = await this.contextProvider.invoking(messages, this.tools);
    }

    // Merge context
    const mergedOptions = this.mergeContext(options, context);
    const allMessages = this.mergeMessages(messages, context);

    // Call LLM
    const response = await this.chatClient.complete(allMessages, mergedOptions);

    // Apply after hook
    await this.afterInvoke(messages, response);

    // Notify context provider
    if (this.contextProvider && context) {
      await this.contextProvider.invoked(response, context);
    }

    return response;
  }

  /**
   * Invoke the agent with streaming responses.
   *
   * Returns an async iterable that yields complete ChatMessage objects as they are
   * assembled from streaming deltas. The stream accumulates deltas and yields
   * ChatMessage objects with accumulated content.
   *
   * Execution flow:
   * 1. Call beforeInvoke() hook
   * 2. Call contextProvider.invoking() if present
   * 3. Merge context (instructions, messages, tools)
   * 4. Call chatClient.completeStream() with merged data
   * 5. Accumulate deltas and yield ChatMessage objects
   * 6. Call afterInvoke() hook with final response
   * 7. Call contextProvider.invoked() if present
   *
   * @param messages - Input messages for the agent
   * @param options - Optional AI settings to override defaults
   * @returns AsyncIterable yielding ChatMessage objects
   *
   * @example
   * ```typescript
   * for await (const message of agent.invokeStream([createUserMessage('Tell a story')])) {
   *   process.stdout.write(getTextContent(message));
   * }
   * ```
   */
  async *invokeStream(messages: ChatMessage[], options?: AISettings): AsyncIterable<ChatMessage> {
    // Apply before hook
    messages = await this.beforeInvoke(messages);

    // Get context from provider
    let context: AIContext | undefined;
    if (this.contextProvider) {
      context = await this.contextProvider.invoking(messages, this.tools);
    }

    // Merge context
    const mergedOptions = this.mergeContext(options, context);
    const allMessages = this.mergeMessages(messages, context);

    // Call LLM with streaming
    const stream = this.chatClient.completeStream(allMessages, mergedOptions);

    // Accumulate message deltas
    let accumulatedMessage: ChatMessage | null = null;

    for await (const event of stream) {
      if (isMessageDelta(event)) {
        // Accumulate deltas into a complete message
        if (accumulatedMessage === null) {
          // Initialize with first delta
          accumulatedMessage = {
            role: event.delta.role || MessageRole.Assistant,
            content: event.delta.content || { type: 'text', text: '' },
            name: event.delta.name,
            timestamp: event.delta.timestamp || new Date(),
            metadata: event.delta.metadata,
          };
        } else {
          // Merge subsequent deltas
          if (event.delta.content) {
            accumulatedMessage = this.mergeDelta(accumulatedMessage, event.delta);
          }
        }

        // Yield the accumulated message
        yield { ...accumulatedMessage };
      }
    }

    // Final accumulated message is the response
    if (accumulatedMessage) {
      // Apply after hook
      await this.afterInvoke(messages, accumulatedMessage);

      // Notify context provider
      if (this.contextProvider && context) {
        await this.contextProvider.invoked(accumulatedMessage, context);
      }
    }
  }

  /**
   * Lifecycle hook called before the LLM is invoked.
   *
   * Override this method to modify messages or perform actions before the LLM call.
   * The returned messages will be used for the invocation.
   *
   * @param messages - Input messages
   * @returns Promise resolving to the messages to send to the LLM
   *
   * @example
   * ```typescript
   * protected async beforeInvoke(messages: ChatMessage[]): Promise<ChatMessage[]> {
   *   console.log(`Invoking with ${messages.length} messages`);
   *   // Add a custom system message
   *   return [createSystemMessage('Extra context'), ...messages];
   * }
   * ```
   */
  protected async beforeInvoke(messages: ChatMessage[]): Promise<ChatMessage[]> {
    return messages;
  }

  /**
   * Lifecycle hook called after the LLM returns a response.
   *
   * Override this method to perform actions after the LLM call, such as logging,
   * metrics collection, or response modification.
   *
   * @param request - The original request messages
   * @param response - The response from the LLM
   * @returns Promise that resolves when the hook is complete
   *
   * @example
   * ```typescript
   * protected async afterInvoke(request: ChatMessage[], response: ChatMessage): Promise<void> {
   *   console.log(`Received response: ${getTextContent(response).substring(0, 50)}...`);
   *   await this.logToAnalytics(request, response);
   * }
   * ```
   */
  protected async afterInvoke(_request: ChatMessage[], _response: ChatMessage): Promise<void> {
    // Default implementation does nothing
  }

  /**
   * Merge context from ContextProvider with AI settings.
   *
   * Combines instructions, tools, and other options from the context provider
   * with the provided options.
   *
   * @param options - Base AI settings
   * @param context - Context from provider
   * @returns Merged ChatCompletionOptions
   */
  private mergeContext(options?: AISettings, context?: AIContext): ChatCompletionOptions {
    const merged: ChatCompletionOptions = { ...options };

    // Merge tools
    const allTools = [...this.tools];
    if (context?.tools) {
      allTools.push(...context.tools);
    }
    if (allTools.length > 0) {
      merged.tools = allTools;
    }

    // Merge instructions
    if (context?.instructions) {
      if (this.info.instructions) {
        // Combine agent instructions with context instructions
        merged.additionalInstructions = this.info.instructions + '\n' + context.instructions;
      } else {
        merged.additionalInstructions = context.instructions;
      }
    } else if (this.info.instructions) {
      merged.additionalInstructions = this.info.instructions;
    }

    return merged;
  }

  /**
   * Merge messages from context provider with request messages.
   *
   * Context messages are prepended before the request messages.
   *
   * @param messages - Request messages
   * @param context - Context from provider
   * @returns Combined message array
   */
  private mergeMessages(messages: ChatMessage[], context?: AIContext): ChatMessage[] {
    if (context?.messages && context.messages.length > 0) {
      return [...context.messages, ...messages];
    }
    return messages;
  }

  /**
   * Merge a delta into an accumulated message.
   *
   * Handles merging partial content from streaming deltas into the accumulated message.
   *
   * @param accumulated - Current accumulated message
   * @param delta - Partial message delta
   * @returns Updated accumulated message
   */
  private mergeDelta(
    accumulated: ChatMessage,
    delta: Partial<ChatMessage>
  ): ChatMessage {
    // For simplicity, we accumulate text content
    // In a full implementation, this would handle all content types
    if (delta.content) {
      const currentContent = accumulated.content;
      const deltaContent = delta.content;

      // Handle text content accumulation
      if (
        typeof currentContent === 'object' &&
        'type' in currentContent &&
        currentContent.type === 'text' &&
        typeof deltaContent === 'object' &&
        'type' in deltaContent &&
        deltaContent.type === 'text'
      ) {
        return {
          ...accumulated,
          content: {
            type: 'text',
            text: currentContent.text + deltaContent.text,
          },
        };
      } else if (Array.isArray(deltaContent)) {
        // If delta is an array, append to existing content
        const currentArray = Array.isArray(currentContent) ? currentContent : [currentContent];
        return {
          ...accumulated,
          content: [...currentArray, ...deltaContent],
        };
      } else {
        // Otherwise replace content
        return {
          ...accumulated,
          content: deltaContent,
        };
      }
    }

    return accumulated;
  }
}
