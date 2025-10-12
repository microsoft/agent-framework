import { AgentFrameworkError } from './base-error';

/**
 * Error thrown during agent execution.
 *
 * This error indicates that an agent encountered a problem while executing
 * its main logic or processing a request. This could be due to:
 * - Invalid input or state
 * - Internal processing errors
 * - Unexpected conditions during execution
 *
 * @example
 * ```typescript
 * // Basic usage
 * throw new AgentExecutionError('Failed to process user request');
 *
 * // With cause chaining
 * try {
 *   await agent.process(message);
 * } catch (error) {
 *   throw new AgentExecutionError('Agent execution failed', error as Error, 'AGENT_EXEC_001');
 * }
 *
 * // Catching and handling
 * try {
 *   await agent.run();
 * } catch (error) {
 *   if (error instanceof AgentExecutionError) {
 *     console.error('Agent execution error:', error.message);
 *     // Handle gracefully
 *   }
 * }
 * ```
 */
export class AgentExecutionError extends AgentFrameworkError {
  /**
   * Creates a new AgentExecutionError.
   *
   * @param message - Description of the execution error
   * @param cause - Optional underlying error that caused this error
   * @param code - Optional error code for programmatic handling
   */
  constructor(message: string, cause?: Error, code?: string) {
    super(message, cause, code);
  }
}

/**
 * Error thrown during agent initialization.
 *
 * This error indicates that an agent could not be properly initialized or
 * configured. This could be due to:
 * - Missing required configuration
 * - Invalid configuration parameters
 * - Failed dependency injection
 * - Resource allocation failures
 *
 * @example
 * ```typescript
 * // Basic usage
 * throw new AgentInitializationError('Missing required configuration: apiKey');
 *
 * // With validation error
 * if (!config.model) {
 *   throw new AgentInitializationError(
 *     'Model configuration is required',
 *     undefined,
 *     'AGENT_INIT_CONFIG_001'
 *   );
 * }
 *
 * // With cause from dependency
 * try {
 *   const chatClient = await createChatClient(config);
 * } catch (error) {
 *   throw new AgentInitializationError(
 *     'Failed to initialize chat client',
 *     error as Error,
 *     'AGENT_INIT_CLIENT_001'
 *   );
 * }
 *
 * // Catching during agent creation
 * try {
 *   const agent = new ChatAgent(config);
 * } catch (error) {
 *   if (error instanceof AgentInitializationError) {
 *     console.error('Failed to create agent:', error.message);
 *     // Provide helpful error to user
 *   }
 * }
 * ```
 */
export class AgentInitializationError extends AgentFrameworkError {
  /**
   * Creates a new AgentInitializationError.
   *
   * @param message - Description of the initialization error
   * @param cause - Optional underlying error that caused this error
   * @param code - Optional error code for programmatic handling
   */
  constructor(message: string, cause?: Error, code?: string) {
    super(message, cause, code);
  }
}
