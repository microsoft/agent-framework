import { z } from 'zod';

/**
 * Core interface for AI tools that can be invoked by LLMs.
 *
 * Tools are functions that the AI model can call to perform actions or retrieve information.
 * Each tool has a name, description, parameter schema, and execution logic.
 *
 * @example
 * ```typescript
 * import { z } from 'zod';
 * import { AITool } from '@microsoft/agent-framework-ts';
 *
 * const weatherTool: AITool = {
 *   name: 'get_weather',
 *   description: 'Get the current weather for a location',
 *   schema: z.object({
 *     location: z.string().describe('The city name'),
 *     units: z.enum(['celsius', 'fahrenheit']).default('celsius'),
 *   }),
 *   async execute(params) {
 *     const validated = this.schema.parse(params);
 *     // Fetch weather data
 *     return { location: validated.location, temp: 72, units: validated.units };
 *   },
 * };
 * ```
 */
export interface AITool {
  /**
   * The unique name of the tool.
   * Used by the LLM to identify and call the tool.
   */
  name: string;

  /**
   * Human-readable description of the tool's purpose and functionality.
   * This is sent to the LLM to help it decide when to use the tool.
   */
  description: string;

  /**
   * Zod schema defining the tool's input parameters.
   * Used for runtime validation and type inference.
   */
  schema: z.ZodSchema;

  /**
   * Execute the tool with the provided parameters.
   *
   * @param params - The parameters to pass to the tool (will be validated against schema)
   * @returns The result of the tool execution
   * @throws {z.ZodError} If the parameters don't match the schema
   */
  execute(params: unknown): Promise<unknown>;

  /**
   * Optional metadata associated with the tool.
   * Can be used for custom properties like approval modes, rate limits, etc.
   */
  metadata?: Record<string, unknown>;
}

/**
 * Abstract base class for implementing AI tools with built-in validation.
 *
 * Provides a foundation for creating custom tools with automatic parameter validation
 * using Zod schemas. Subclasses must implement the `execute` method.
 *
 * @example
 * ```typescript
 * import { z } from 'zod';
 * import { BaseTool } from '@microsoft/agent-framework-ts';
 *
 * class CalculatorTool extends BaseTool {
 *   constructor() {
 *     super({
 *       name: 'calculator',
 *       description: 'Perform basic math operations',
 *       schema: z.object({
 *         operation: z.enum(['add', 'subtract', 'multiply', 'divide']),
 *         a: z.number(),
 *         b: z.number(),
 *       }),
 *     });
 *   }
 *
 *   async execute(params: unknown): Promise<number> {
 *     const { operation, a, b } = this.validate(params);
 *     switch (operation) {
 *       case 'add': return a + b;
 *       case 'subtract': return a - b;
 *       case 'multiply': return a * b;
 *       case 'divide': return a / b;
 *     }
 *   }
 * }
 *
 * const calc = new CalculatorTool();
 * const result = await calc.execute({ operation: 'add', a: 5, b: 3 }); // 8
 * ```
 */
export abstract class BaseTool implements AITool {
  public readonly name: string;
  public readonly description: string;
  public readonly schema: z.ZodSchema;
  public readonly metadata?: Record<string, unknown>;

  /**
   * Create a new base tool.
   *
   * @param config - Configuration for the tool
   * @param config.name - The unique name of the tool
   * @param config.description - Human-readable description of the tool
   * @param config.schema - Zod schema for parameter validation
   * @param config.metadata - Optional metadata for the tool
   */
  constructor(config: {
    name: string;
    description: string;
    schema: z.ZodSchema;
    metadata?: Record<string, unknown>;
  }) {
    this.name = config.name;
    this.description = config.description;
    this.schema = config.schema;
    this.metadata = config.metadata;
  }

  /**
   * Execute the tool with the provided parameters.
   * Must be implemented by subclasses.
   *
   * @param params - The parameters to pass to the tool
   * @returns The result of the tool execution
   */
  abstract execute(params: unknown): Promise<unknown>;

  /**
   * Validate and parse parameters against the tool's schema.
   *
   * This method uses Zod to validate the input parameters and returns
   * the parsed/coerced result. Throws a ZodError if validation fails.
   *
   * @param params - The parameters to validate
   * @returns The validated and parsed parameters
   * @throws {z.ZodError} If validation fails
   *
   * @example
   * ```typescript
   * class MyTool extends BaseTool {
   *   async execute(params: unknown) {
   *     const validated = this.validate(params);
   *     // validated is now properly typed and validated
   *     return validated;
   *   }
   * }
   * ```
   */
  protected validate<T = unknown>(params: unknown): T {
    return this.schema.parse(params) as T;
  }
}

/**
 * A tool that wraps a function for use with AI models.
 *
 * FunctionTool allows you to wrap any function as an AITool, providing
 * automatic parameter validation and a consistent interface for the LLM.
 *
 * @example
 * ```typescript
 * import { z } from 'zod';
 * import { FunctionTool } from '@microsoft/agent-framework-ts';
 *
 * const weatherTool = new FunctionTool({
 *   name: 'get_weather',
 *   description: 'Get current weather for a location',
 *   schema: z.object({
 *     location: z.string(),
 *     units: z.enum(['celsius', 'fahrenheit']).default('celsius'),
 *   }),
 *   fn: async ({ location, units }) => {
 *     // Fetch weather data
 *     return { location, temp: 72, units };
 *   },
 * });
 *
 * const result = await weatherTool.execute({ location: 'Seattle' });
 * ```
 */
export class FunctionTool extends BaseTool {
  private fn: (params: unknown) => Promise<unknown>;

  /**
   * Create a new function tool.
   *
   * @param config - Configuration for the function tool
   * @param config.name - The unique name of the tool
   * @param config.description - Human-readable description of the tool
   * @param config.schema - Zod schema for parameter validation
   * @param config.fn - The function to wrap (sync or async)
   * @param config.metadata - Optional metadata for the tool
   */
  constructor(config: {
    name: string;
    description: string;
    schema: z.ZodSchema;
    fn: (params: unknown) => Promise<unknown> | unknown;
    metadata?: Record<string, unknown>;
  }) {
    super({
      name: config.name,
      description: config.description,
      schema: config.schema,
      metadata: config.metadata,
    });

    // Normalize sync/async functions to always be async
    this.fn = async (params: unknown): Promise<unknown> => {
      const result = config.fn(params);
      return result instanceof Promise ? result : Promise.resolve(result);
    };
  }

  /**
   * Execute the wrapped function with validated parameters.
   *
   * @param params - The parameters to pass to the function
   * @returns The result of the function execution
   * @throws {z.ZodError} If parameter validation fails
   */
  async execute(params: unknown): Promise<unknown> {
    const validated = this.validate(params);
    return this.fn(validated);
  }
}

/**
 * Helper function to create a tool from a function.
 *
 * This is a convenience function that creates a FunctionTool instance
 * with type inference from the Zod schema.
 *
 * @param name - The unique name of the tool
 * @param description - Human-readable description of the tool
 * @param schema - Zod schema for parameter validation
 * @param fn - The function to wrap (receives validated parameters)
 * @returns A new AITool instance
 *
 * @example
 * ```typescript
 * import { z } from 'zod';
 * import { createTool } from '@microsoft/agent-framework-ts';
 *
 * const weatherTool = createTool(
 *   'get_weather',
 *   'Get current weather for a location',
 *   z.object({
 *     location: z.string(),
 *     units: z.enum(['celsius', 'fahrenheit']).default('celsius'),
 *   }),
 *   async ({ location, units }) => {
 *     // params are automatically typed based on the schema
 *     return { location, temp: 72, units };
 *   }
 * );
 * ```
 */
export function createTool<T>(
  name: string,
  description: string,
  schema: z.ZodSchema<T>,
  fn: (params: T) => Promise<unknown> | unknown
): AITool {
  return new FunctionTool({
    name,
    description,
    schema,
    fn: async (params: unknown): Promise<unknown> => {
      const validated = schema.parse(params) as T;
      const result = fn(validated);
      return result instanceof Promise ? result : Promise.resolve(result);
    },
  });
}
