/**
 * Microsoft Agent Framework for TypeScript
 *
 * Core type definitions for agent metadata and AI model settings.
 */

/**
 * Agent metadata and configuration.
 *
 * Represents the core information about an agent including its identity,
 * purpose, and behavior instructions.
 */
export interface AgentInfo {
  /** Unique identifier for the agent */
  id: string;
  /** Display name for the agent */
  name: string;
  /** Description of the agent's purpose and capabilities */
  description?: string;
  /** System instructions that guide the agent's behavior */
  instructions?: string;
  /** Custom properties for agent-specific metadata */
  metadata?: Record<string, unknown>;
}

/**
 * Response format configuration for AI model output.
 */
export interface ResponseFormat {
  /** The type of response format */
  type: 'text' | 'json_object';
}

/**
 * Streaming options for AI model responses.
 */
export interface StreamOptions {
  /** Whether to include usage information in the stream */
  includeUsage?: boolean;
}

/**
 * AI model settings for chat completion.
 *
 * Configures parameters that control the behavior and output of AI models,
 * including sampling strategies, token limits, and penalties.
 */
export interface AISettings {
  /** Model identifier (e.g., 'gpt-4', 'gpt-3.5-turbo') */
  modelId?: string;
  /**
   * Temperature for sampling (0.0 to 2.0).
   * Higher values make output more random, lower values more deterministic.
   */
  temperature?: number;
  /**
   * Top-p for nucleus sampling (0.0 to 1.0).
   * Controls diversity by considering tokens with cumulative probability mass of top_p.
   */
  topP?: number;
  /**
   * Maximum number of tokens to generate (positive integer).
   * Limits the length of the model's response.
   */
  maxTokens?: number;
  /** Custom stop sequences that will halt generation */
  stopSequences?: string[];
  /**
   * Presence penalty (-2.0 to 2.0).
   * Positive values encourage the model to talk about new topics.
   */
  presencePenalty?: number;
  /**
   * Frequency penalty (-2.0 to 2.0).
   * Positive values decrease likelihood of repeating the same line.
   */
  frequencyPenalty?: number;
  /** Seed for reproducible sampling */
  seed?: number;
  /** Output format configuration */
  responseFormat?: ResponseFormat;
  /** Streaming configuration */
  streamOptions?: StreamOptions;
}

/**
 * Default AI settings with sensible defaults for common use cases.
 */
export const DEFAULT_AI_SETTINGS: Readonly<AISettings> = Object.freeze({
  temperature: 1.0,
  topP: 1.0,
  maxTokens: 4096,
});

/**
 * Validate temperature value.
 *
 * @param value - Temperature to validate
 * @throws {TypeError} If value is not in range [0, 2]
 */
export function validateTemperature(value: number): void {
  if (typeof value !== 'number' || isNaN(value)) {
    throw new TypeError(`Temperature must be a number, got ${typeof value}`);
  }
  if (value < 0 || value > 2) {
    throw new TypeError(`Temperature must be between 0 and 2, got ${value}`);
  }
}

/**
 * Validate top-p value.
 *
 * @param value - Top-p to validate
 * @throws {TypeError} If value is not in range [0, 1]
 */
export function validateTopP(value: number): void {
  if (typeof value !== 'number' || isNaN(value)) {
    throw new TypeError(`TopP must be a number, got ${typeof value}`);
  }
  if (value < 0 || value > 1) {
    throw new TypeError(`TopP must be between 0 and 1, got ${value}`);
  }
}

/**
 * Validate max tokens value.
 *
 * @param value - Max tokens to validate
 * @throws {TypeError} If value is not a positive integer
 */
export function validateMaxTokens(value: number): void {
  if (typeof value !== 'number' || isNaN(value)) {
    throw new TypeError(`MaxTokens must be a number, got ${typeof value}`);
  }
  if (!Number.isInteger(value)) {
    throw new TypeError(`MaxTokens must be an integer, got ${value}`);
  }
  if (value <= 0) {
    throw new TypeError(`MaxTokens must be positive, got ${value}`);
  }
}

/**
 * Validate penalty value (presence or frequency).
 *
 * @param value - Penalty to validate
 * @param parameterName - Name of the parameter for error messages
 * @throws {TypeError} If value is not in range [-2, 2]
 */
export function validatePenalty(value: number, parameterName: string = 'Penalty'): void {
  if (typeof value !== 'number' || isNaN(value)) {
    throw new TypeError(`${parameterName} must be a number, got ${typeof value}`);
  }
  if (value < -2 || value > 2) {
    throw new TypeError(`${parameterName} must be between -2 and 2, got ${value}`);
  }
}

/**
 * Validate all fields in AISettings object.
 *
 * @param settings - AISettings to validate
 * @throws {TypeError} If any field has an invalid value
 */
export function validateAISettings(settings: AISettings): void {
  if (settings.temperature !== undefined) {
    validateTemperature(settings.temperature);
  }
  if (settings.topP !== undefined) {
    validateTopP(settings.topP);
  }
  if (settings.maxTokens !== undefined) {
    validateMaxTokens(settings.maxTokens);
  }
  if (settings.presencePenalty !== undefined) {
    validatePenalty(settings.presencePenalty, 'PresencePenalty');
  }
  if (settings.frequencyPenalty !== undefined) {
    validatePenalty(settings.frequencyPenalty, 'FrequencyPenalty');
  }
}

/**
 * Builder for AISettings with validation and fluent interface.
 *
 * Provides a convenient way to construct AISettings objects with inline
 * validation of all parameter values.
 *
 * @example
 * ```typescript
 * const settings = new AISettingsBuilder()
 *   .modelId('gpt-4')
 *   .temperature(0.7)
 *   .maxTokens(2000)
 *   .build();
 * ```
 */
export class AISettingsBuilder {
  private settings: AISettings = {};

  /**
   * Set the model ID.
   *
   * @param id - Model identifier
   * @returns Builder instance for chaining
   */
  modelId(id: string): this {
    this.settings.modelId = id;
    return this;
  }

  /**
   * Set the temperature.
   *
   * @param value - Temperature value (0.0 to 2.0)
   * @returns Builder instance for chaining
   * @throws {TypeError} If value is not in range [0, 2]
   */
  temperature(value: number): this {
    validateTemperature(value);
    this.settings.temperature = value;
    return this;
  }

  /**
   * Set the top-p value.
   *
   * @param value - Top-p value (0.0 to 1.0)
   * @returns Builder instance for chaining
   * @throws {TypeError} If value is not in range [0, 1]
   */
  topP(value: number): this {
    validateTopP(value);
    this.settings.topP = value;
    return this;
  }

  /**
   * Set the maximum tokens.
   *
   * @param value - Maximum number of tokens (positive integer)
   * @returns Builder instance for chaining
   * @throws {TypeError} If value is not a positive integer
   */
  maxTokens(value: number): this {
    validateMaxTokens(value);
    this.settings.maxTokens = value;
    return this;
  }

  /**
   * Set the stop sequences.
   *
   * @param sequences - Array of stop sequences
   * @returns Builder instance for chaining
   */
  stopSequences(sequences: string[]): this {
    this.settings.stopSequences = sequences;
    return this;
  }

  /**
   * Set the presence penalty.
   *
   * @param value - Presence penalty value (-2.0 to 2.0)
   * @returns Builder instance for chaining
   * @throws {TypeError} If value is not in range [-2, 2]
   */
  presencePenalty(value: number): this {
    validatePenalty(value, 'PresencePenalty');
    this.settings.presencePenalty = value;
    return this;
  }

  /**
   * Set the frequency penalty.
   *
   * @param value - Frequency penalty value (-2.0 to 2.0)
   * @returns Builder instance for chaining
   * @throws {TypeError} If value is not in range [-2, 2]
   */
  frequencyPenalty(value: number): this {
    validatePenalty(value, 'FrequencyPenalty');
    this.settings.frequencyPenalty = value;
    return this;
  }

  /**
   * Set the seed for reproducible sampling.
   *
   * @param value - Seed value
   * @returns Builder instance for chaining
   */
  seed(value: number): this {
    this.settings.seed = value;
    return this;
  }

  /**
   * Set the response format.
   *
   * @param format - Response format configuration
   * @returns Builder instance for chaining
   */
  responseFormat(format: ResponseFormat): this {
    this.settings.responseFormat = format;
    return this;
  }

  /**
   * Set the streaming options.
   *
   * @param options - Streaming configuration
   * @returns Builder instance for chaining
   */
  streamOptions(options: StreamOptions): this {
    this.settings.streamOptions = options;
    return this;
  }

  /**
   * Build the AISettings object.
   *
   * Returns a new object with all configured settings. The returned object
   * is independent of the builder's internal state.
   *
   * @returns New AISettings instance
   */
  build(): AISettings {
    return { ...this.settings };
  }
}
