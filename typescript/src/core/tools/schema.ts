import { z } from 'zod';
import { zodToJsonSchema as convertZodToJsonSchema } from 'zod-to-json-schema';
import type { AITool } from './base-tool.js';

/**
 * JSON Schema representation for tool parameters.
 * Used by LLMs to understand the expected structure of tool inputs.
 */
export interface JsonSchema {
  type?: string;
  properties?: Record<string, JsonSchema>;
  items?: JsonSchema;
  enum?: unknown[];
  const?: unknown;
  description?: string;
  default?: unknown;
  required?: string[];
  additionalProperties?: boolean | JsonSchema;
  minLength?: number;
  maxLength?: number;
  minimum?: number;
  maximum?: number;
  pattern?: string;
  format?: string;
  anyOf?: JsonSchema[];
  allOf?: JsonSchema[];
  oneOf?: JsonSchema[];
  not?: JsonSchema;
  nullable?: boolean;
  [key: string]: unknown;
}

/**
 * Standard AI tool schema format for LLM function calling.
 * Follows the OpenAI function calling specification.
 */
export interface AIToolSchema {
  type: 'function';
  function: {
    name: string;
    description: string;
    parameters: JsonSchema;
  };
}

/**
 * Convert a Zod schema to JSON Schema format for LLM consumption.
 *
 * This function converts Zod schemas to the JSON Schema format expected by
 * LLMs for function calling. It uses the zod-to-json-schema library for
 * robust conversion of all Zod types.
 *
 * @param schema - The Zod schema to convert
 * @returns JSON Schema representation of the Zod schema
 *
 * @example
 * ```typescript
 * import { z } from 'zod';
 * import { zodToJsonSchema } from '@microsoft/agent-framework-ts';
 *
 * const schema = z.object({
 *   name: z.string().describe('The user name'),
 *   age: z.number().min(0).max(120).optional(),
 *   email: z.string().email(),
 *   role: z.enum(['admin', 'user']).default('user'),
 * });
 *
 * const jsonSchema = zodToJsonSchema(schema);
 * // {
 * //   type: 'object',
 * //   properties: {
 * //     name: { type: 'string', description: 'The user name' },
 * //     age: { type: 'number', minimum: 0, maximum: 120 },
 * //     email: { type: 'string', format: 'email' },
 * //     role: { type: 'string', enum: ['admin', 'user'], default: 'user' }
 * //   },
 * //   required: ['name', 'email']
 * // }
 * ```
 */
export function zodToJsonSchema(schema: z.ZodSchema): JsonSchema {
  // Use the zod-to-json-schema library for robust conversion
  const result = convertZodToJsonSchema(schema, {
    target: 'openApi3',
    $refStrategy: 'none',
  });

  // Remove $schema property as it's not needed for LLM function calling
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { $schema, ...jsonSchema } = result as JsonSchema & { $schema?: string };

  return jsonSchema as JsonSchema;
}

/**
 * Create an AI tool schema from a tool instance.
 *
 * This converts a tool into the standard format expected by LLM function
 * calling APIs (e.g., OpenAI's function calling).
 *
 * @param tool - The AI tool to convert
 * @returns AI tool schema in the standard format
 *
 * @example
 * ```typescript
 * import { z } from 'zod';
 * import { createTool, createToolSchema } from '@microsoft/agent-framework-ts';
 *
 * const weatherTool = createTool(
 *   'get_weather',
 *   'Get current weather',
 *   z.object({ location: z.string() }),
 *   async ({ location }) => ({ temp: 72 })
 * );
 *
 * const schema = createToolSchema(weatherTool);
 * // {
 * //   type: 'function',
 * //   function: {
 * //     name: 'get_weather',
 * //     description: 'Get current weather',
 * //     parameters: {
 * //       type: 'object',
 * //       properties: { location: { type: 'string' } },
 * //       required: ['location']
 * //     }
 * //   }
 * // }
 * ```
 */
export function createToolSchema(tool: AITool): AIToolSchema {
  return {
    type: 'function',
    function: {
      name: tool.name,
      description: tool.description,
      parameters: zodToJsonSchema(tool.schema),
    },
  };
}
