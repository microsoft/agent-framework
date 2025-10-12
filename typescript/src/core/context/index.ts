/**
 * Context module - AI context management with lifecycle hooks.
 *
 * This module provides functionality for managing AI context through providers
 * that can enhance the AI's context with additional instructions, messages, and tools.
 *
 * Key components:
 * - ContextProvider: Abstract base class for custom context providers
 * - AIContext: Interface for context data (instructions, messages, tools)
 * - AggregateContextProvider: Combines multiple context providers
 * - DEFAULT_CONTEXT_PROMPT: Standard prompt for memory/context assembly
 *
 * @module context
 */

export {
  ContextProvider,
  AIContext,
  DEFAULT_CONTEXT_PROMPT,
} from './context-provider.js';

export { AggregateContextProvider } from './aggregate-provider.js';
