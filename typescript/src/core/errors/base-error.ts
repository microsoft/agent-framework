/**
 * Base error class for all Agent Framework errors.
 *
 * This class extends the native Error class and provides additional functionality:
 * - Cause chaining: Wrap underlying errors for better debugging
 * - Error codes: Optional codes for programmatic error handling
 * - Proper stack traces: Captures stack trace at the point of creation
 *
 * @example
 * ```typescript
 * // Basic usage
 * throw new AgentFrameworkError('Something went wrong');
 *
 * // With cause chaining
 * try {
 *   await someOperation();
 * } catch (error) {
 *   throw new AgentFrameworkError('Operation failed', error as Error);
 * }
 *
 * // With error code
 * throw new AgentFrameworkError('Invalid configuration', undefined, 'ERR_CONFIG_001');
 *
 * // With both cause and code
 * try {
 *   await riskyOperation();
 * } catch (error) {
 *   throw new AgentFrameworkError('Operation failed', error as Error, 'ERR_OP_001');
 * }
 * ```
 */
export class AgentFrameworkError extends Error {
  /**
   * The underlying error that caused this error, if any.
   */
  public readonly cause?: Error;

  /**
   * Optional error code for programmatic handling.
   */
  public readonly code?: string;

  /**
   * Creates a new AgentFrameworkError.
   *
   * @param message - The error message describing what went wrong
   * @param cause - Optional underlying error that caused this error
   * @param code - Optional error code for programmatic handling
   */
  constructor(message: string, cause?: Error, code?: string) {
    super(message);
    this.name = this.constructor.name;
    this.cause = cause;
    this.code = code;

    // Capture stack trace, excluding the constructor call from the stack
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, this.constructor);
    }
  }

  /**
   * Returns a string representation of the error including cause chain.
   *
   * @returns String representation of the error
   */
  public toString(): string {
    let result = `${this.name}: ${this.message}`;
    if (this.code) {
      result += ` [${this.code}]`;
    }
    if (this.cause) {
      result += `\nCaused by: ${this.cause.toString()}`;
    }
    return result;
  }

  /**
   * Returns a JSON representation of the error.
   *
   * @returns JSON-serializable object
   */
  public toJSON(): Record<string, unknown> {
    return {
      name: this.name,
      message: this.message,
      code: this.code,
      cause: this.cause
        ? {
            name: this.cause.name,
            message: this.cause.message,
          }
        : undefined,
    };
  }
}
