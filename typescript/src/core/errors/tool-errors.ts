import { AgentFrameworkError } from './base-error';

/**
 * Error thrown during tool execution.
 *
 * This error indicates that a tool failed to execute successfully. This could be due to:
 * - Invalid tool parameters
 * - Tool implementation errors
 * - External service failures
 * - Permission or authorization issues
 * - Resource unavailability
 *
 * @example
 * ```typescript
 * // Basic usage
 * throw new ToolExecutionError('Failed to execute search tool');
 *
 * // With cause chaining from external service
 * try {
 *   const result = await externalAPI.call(params);
 * } catch (error) {
 *   throw new ToolExecutionError(
 *     'External API call failed',
 *     error as Error,
 *     'TOOL_EXEC_API_001'
 *   );
 * }
 *
 * // With parameter validation
 * if (!params.query) {
 *   throw new ToolExecutionError(
 *     'Missing required parameter: query',
 *     undefined,
 *     'TOOL_EXEC_PARAM_001'
 *   );
 * }
 *
 * // In tool implementation
 * async function executeTool(params: ToolParams): Promise<ToolResult> {
 *   try {
 *     return await performOperation(params);
 *   } catch (error) {
 *     throw new ToolExecutionError(
 *       `Tool ${params.name} execution failed: ${error.message}`,
 *       error as Error
 *     );
 *   }
 * }
 *
 * // Catching and handling
 * try {
 *   await tool.execute(params);
 * } catch (error) {
 *   if (error instanceof ToolExecutionError) {
 *     console.error('Tool execution failed:', error.message);
 *     // Fallback to alternative tool or graceful degradation
 *   }
 * }
 * ```
 */
export class ToolExecutionError extends AgentFrameworkError {
  /**
   * Creates a new ToolExecutionError.
   *
   * @param message - Description of the tool execution error
   * @param cause - Optional underlying error that caused this error
   * @param code - Optional error code for programmatic handling
   */
  constructor(message: string, cause?: Error, code?: string) {
    super(message, cause, code);
  }
}
