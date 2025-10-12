import { AgentFrameworkError } from './base-error';

/**
 * Error thrown by chat client operations.
 *
 * This error indicates that a chat client encountered a problem while communicating
 * with the underlying LLM service. This could be due to:
 * - Network connectivity issues
 * - Authentication or authorization failures
 * - Rate limiting or quota exceeded
 * - Invalid request format or parameters
 * - Service unavailability or timeouts
 * - Content filtering or policy violations
 * - Invalid API responses
 *
 * @example
 * ```typescript
 * // Basic usage
 * throw new ChatClientError('Failed to communicate with LLM service');
 *
 * // With cause from network error
 * try {
 *   const response = await fetch(apiUrl, options);
 * } catch (error) {
 *   throw new ChatClientError(
 *     'Network request failed',
 *     error as Error,
 *     'CHAT_CLIENT_NETWORK_001'
 *   );
 * }
 *
 * // Authentication error
 * if (!apiKey) {
 *   throw new ChatClientError(
 *     'API key is required',
 *     undefined,
 *     'CHAT_CLIENT_AUTH_001'
 *   );
 * }
 *
 * // Rate limiting
 * if (response.status === 429) {
 *   throw new ChatClientError(
 *     'Rate limit exceeded. Please retry after some time.',
 *     undefined,
 *     'CHAT_CLIENT_RATE_LIMIT_001'
 *   );
 * }
 *
 * // In chat client implementation
 * async function sendMessage(message: string): Promise<string> {
 *   try {
 *     const response = await llmService.complete(message);
 *     if (!response.ok) {
 *       throw new ChatClientError(
 *         `LLM service returned error: ${response.statusText}`,
 *         undefined,
 *         `CHAT_CLIENT_HTTP_${response.status}`
 *       );
 *     }
 *     return response.data;
 *   } catch (error) {
 *     if (error instanceof ChatClientError) {
 *       throw error;
 *     }
 *     throw new ChatClientError('Unexpected error in chat client', error as Error);
 *   }
 * }
 *
 * // Catching and handling
 * try {
 *   await chatClient.sendMessage('Hello');
 * } catch (error) {
 *   if (error instanceof ChatClientError) {
 *     if (error.code === 'CHAT_CLIENT_RATE_LIMIT_001') {
 *       // Implement retry logic with backoff
 *       await delay(5000);
 *       await chatClient.sendMessage('Hello');
 *     } else {
 *       console.error('Chat client error:', error.message);
 *     }
 *   }
 * }
 * ```
 */
export class ChatClientError extends AgentFrameworkError {
  /**
   * Creates a new ChatClientError.
   *
   * @param message - Description of the chat client error
   * @param cause - Optional underlying error that caused this error
   * @param code - Optional error code for programmatic handling
   */
  constructor(message: string, cause?: Error, code?: string) {
    super(message, cause, code);
  }
}
