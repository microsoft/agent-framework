import 'reflect-metadata';
import { z } from 'zod';

/**
 * Metadata key used to store AI function information on decorated methods.
 * @internal
 */
const AI_FUNCTION_METADATA_KEY = 'ai:function';

/**
 * Configuration for the @aiFunction decorator.
 */
export interface AIFunctionConfig {
  /**
   * The name of the function.
   * If not provided, the method name will be used.
   */
  name?: string;

  /**
   * Human-readable description of the function's purpose.
   * This is sent to the LLM to help it decide when to use the function.
   */
  description: string;

  /**
   * Zod schema defining the function's input parameters.
   * Used for runtime validation and type inference.
   */
  schema: z.ZodSchema;
}

/**
 * Metadata stored on decorated methods.
 * @internal
 */
export interface AIFunctionMetadata {
  name: string;
  description: string;
  schema: z.ZodSchema;
}

/**
 * Method decorator that marks a method as an AI function.
 *
 * This decorator attaches metadata to a method that can be used by agents
 * to expose the method as a callable tool for LLMs. The decorated method
 * can still be called normally.
 *
 * @param config - Configuration for the AI function
 * @returns Method decorator
 *
 * @example
 * ```typescript
 * import { z } from 'zod';
 * import { aiFunction } from '@microsoft/agent-framework-ts';
 *
 * class SearchAgent {
 *   @aiFunction({
 *     description: 'Search the web for information',
 *     schema: z.object({
 *       query: z.string().describe('The search query'),
 *       maxResults: z.number().min(1).max(10).default(5),
 *     }),
 *   })
 *   async search(params: { query: string; maxResults?: number }) {
 *     // Perform search
 *     return { results: [] };
 *   }
 *
 *   @aiFunction({
 *     name: 'get_weather',
 *     description: 'Get current weather for a location',
 *     schema: z.object({
 *       location: z.string(),
 *     }),
 *   })
 *   async weatherLookup(params: { location: string }) {
 *     return { location: params.location, temp: 72 };
 *   }
 * }
 * ```
 */
export function aiFunction(config: AIFunctionConfig): MethodDecorator {
  return (
    target: object,
    propertyKey: string | symbol,
    descriptor: PropertyDescriptor
  ): PropertyDescriptor => {
    // Infer name from method name if not provided
    const functionName = config.name || String(propertyKey);

    // Create metadata object
    const metadata: AIFunctionMetadata = {
      name: functionName,
      description: config.description,
      schema: config.schema,
    };

    // Attach metadata to the method using reflect-metadata
    Reflect.defineMetadata(AI_FUNCTION_METADATA_KEY, metadata, target, propertyKey);

    // Return the original descriptor (method remains callable)
    return descriptor;
  };
}

/**
 * Retrieve AI function metadata from a decorated method.
 *
 * This function retrieves the metadata attached by the @aiFunction decorator.
 * Returns undefined if the method is not decorated.
 *
 * @param target - The target object containing the method
 * @param propertyKey - The name of the method
 * @returns The AI function metadata, or undefined if not decorated
 *
 * @example
 * ```typescript
 * class MyAgent {
 *   @aiFunction({
 *     description: 'Test function',
 *     schema: z.object({ value: z.string() }),
 *   })
 *   async test(params: { value: string }) {
 *     return params.value;
 *   }
 * }
 *
 * const agent = new MyAgent();
 * const metadata = getAIFunctionMetadata(agent, 'test');
 * console.log(metadata?.name); // 'test'
 * console.log(metadata?.description); // 'Test function'
 * ```
 */
export function getAIFunctionMetadata(
  target: object,
  propertyKey: string | symbol
): AIFunctionMetadata | undefined {
  return Reflect.getMetadata(AI_FUNCTION_METADATA_KEY, target, propertyKey);
}

/**
 * Check if a method is decorated with @aiFunction.
 *
 * @param target - The target object containing the method
 * @param propertyKey - The name of the method
 * @returns True if the method is decorated with @aiFunction, false otherwise
 *
 * @example
 * ```typescript
 * class MyAgent {
 *   @aiFunction({
 *     description: 'Test function',
 *     schema: z.object({}),
 *   })
 *   async decorated() {}
 *
 *   async notDecorated() {}
 * }
 *
 * const agent = new MyAgent();
 * console.log(isAIFunction(agent, 'decorated')); // true
 * console.log(isAIFunction(agent, 'notDecorated')); // false
 * ```
 */
export function isAIFunction(target: object, propertyKey: string | symbol): boolean {
  return Reflect.hasMetadata(AI_FUNCTION_METADATA_KEY, target, propertyKey);
}

/**
 * Get all AI function metadata from an object.
 *
 * This function scans an object and its prototype chain for methods decorated
 * with @aiFunction and returns their metadata.
 *
 * @param target - The target object to scan
 * @returns Array of AI function metadata with property keys
 *
 * @example
 * ```typescript
 * class MyAgent {
 *   @aiFunction({
 *     description: 'Function 1',
 *     schema: z.object({}),
 *   })
 *   async func1() {}
 *
 *   @aiFunction({
 *     description: 'Function 2',
 *     schema: z.object({}),
 *   })
 *   async func2() {}
 * }
 *
 * const agent = new MyAgent();
 * const functions = getAllAIFunctions(agent);
 * console.log(functions.length); // 2
 * console.log(functions[0].metadata.name); // 'func1'
 * ```
 */
export function getAllAIFunctions(
  target: object
): Array<{ propertyKey: string; metadata: AIFunctionMetadata }> {
  const functions: Array<{ propertyKey: string; metadata: AIFunctionMetadata }> = [];

  // Get all property names from the object and its prototype chain
  const propertyNames = new Set<string>();

  // Traverse prototype chain
  let currentObj = target;
  while (currentObj && currentObj !== Object.prototype) {
    Object.getOwnPropertyNames(currentObj).forEach((name) => propertyNames.add(name));
    currentObj = Object.getPrototypeOf(currentObj);
  }

  // Check each property for AI function metadata
  for (const propertyKey of propertyNames) {
    const metadata = getAIFunctionMetadata(target, propertyKey);
    if (metadata) {
      functions.push({ propertyKey, metadata });
    }
  }

  return functions;
}
