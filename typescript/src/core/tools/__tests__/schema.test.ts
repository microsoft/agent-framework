import { describe, it, expect } from 'vitest';
import { z } from 'zod';
import { zodToJsonSchema, createToolSchema } from '../schema.js';
import { createTool } from '../base-tool.js';

describe('zodToJsonSchema', () => {
  describe('simple types', () => {
    it('should convert string type', () => {
      const schema = z.string();
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({ type: 'string' });
    });

    it('should convert number type', () => {
      const schema = z.number();
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({ type: 'number' });
    });

    it('should convert boolean type', () => {
      const schema = z.boolean();
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({ type: 'boolean' });
    });

    it('should convert integer type', () => {
      const schema = z.number().int();
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({ type: 'integer' });
    });
  });

  describe('string validations', () => {
    it('should handle minLength', () => {
      const schema = z.string().min(5);
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'string',
        minLength: 5,
      });
    });

    it('should handle maxLength', () => {
      const schema = z.string().max(10);
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'string',
        maxLength: 10,
      });
    });

    it('should handle email format', () => {
      const schema = z.string().email();
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'string',
        format: 'email',
      });
    });

    it('should handle url format', () => {
      const schema = z.string().url();
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'string',
        format: 'uri',
      });
    });

    it('should handle uuid format', () => {
      const schema = z.string().uuid();
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'string',
        format: 'uuid',
      });
    });

    it('should handle regex pattern', () => {
      const schema = z.string().regex(/^[a-z]+$/);
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'string',
        pattern: '^[a-z]+$',
      });
    });
  });

  describe('number validations', () => {
    it('should handle minimum', () => {
      const schema = z.number().min(0);
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'number',
        minimum: 0,
      });
    });

    it('should handle maximum', () => {
      const schema = z.number().max(100);
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'number',
        maximum: 100,
      });
    });

    it('should handle both min and max', () => {
      const schema = z.number().min(0).max(100);
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'number',
        minimum: 0,
        maximum: 100,
      });
    });
  });

  describe('enum types', () => {
    it('should convert enum', () => {
      const schema = z.enum(['option1', 'option2', 'option3']);
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'string',
        enum: ['option1', 'option2', 'option3'],
      });
    });

    it('should convert native enum', () => {
      enum Status {
        Active = 'active',
        Inactive = 'inactive',
      }

      const schema = z.nativeEnum(Status);
      const jsonSchema = zodToJsonSchema(schema);

      // zod-to-json-schema adds a type field for native enums
      expect(jsonSchema.enum).toEqual(['active', 'inactive']);
      expect(jsonSchema.type).toBe('string');
    });
  });

  describe('literal types', () => {
    it('should convert string literal', () => {
      const schema = z.literal('constant');
      const jsonSchema = zodToJsonSchema(schema);

      // zod-to-json-schema converts literals to enums with a single value
      expect(jsonSchema.enum).toEqual(['constant']);
    });

    it('should convert number literal', () => {
      const schema = z.literal(42);
      const jsonSchema = zodToJsonSchema(schema);

      // zod-to-json-schema converts literals to enums with a single value
      expect(jsonSchema.enum).toEqual([42]);
      expect(jsonSchema.type).toBe('number');
    });
  });

  describe('array types', () => {
    it('should convert simple array', () => {
      const schema = z.array(z.string());
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'array',
        items: { type: 'string' },
      });
    });

    it('should convert array with complex items', () => {
      const schema = z.array(
        z.object({
          name: z.string(),
          age: z.number(),
        })
      );
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'array',
        items: {
          type: 'object',
          properties: {
            name: { type: 'string' },
            age: { type: 'number' },
          },
          required: ['name', 'age'],
          additionalProperties: false,
        },
      });
    });
  });

  describe('object types', () => {
    it('should convert simple object', () => {
      const schema = z.object({
        name: z.string(),
        age: z.number(),
      });
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'object',
        properties: {
          name: { type: 'string' },
          age: { type: 'number' },
        },
        required: ['name', 'age'],
        additionalProperties: false,
      });
    });

    it('should handle optional fields', () => {
      const schema = z.object({
        name: z.string(),
        age: z.number().optional(),
      });
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'object',
        properties: {
          name: { type: 'string' },
          age: { type: 'number' },
        },
        required: ['name'],
        additionalProperties: false,
      });
    });

    it('should handle default values', () => {
      const schema = z.object({
        name: z.string(),
        role: z.string().default('user'),
      });
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'object',
        properties: {
          name: { type: 'string' },
          role: { type: 'string', default: 'user' },
        },
        required: ['name'],
        additionalProperties: false,
      });
    });

    it('should handle nested objects', () => {
      const schema = z.object({
        user: z.object({
          name: z.string(),
          email: z.string().email(),
        }),
        active: z.boolean(),
      });
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'object',
        properties: {
          user: {
            type: 'object',
            properties: {
              name: { type: 'string' },
              email: { type: 'string', format: 'email' },
            },
            required: ['name', 'email'],
            additionalProperties: false,
          },
          active: { type: 'boolean' },
        },
        required: ['user', 'active'],
        additionalProperties: false,
      });
    });

    it('should handle descriptions', () => {
      const schema = z.object({
        name: z.string().describe('The user name'),
        age: z.number().describe('The user age'),
      });
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema.properties).toEqual({
        name: { type: 'string', description: 'The user name' },
        age: { type: 'number', description: 'The user age' },
      });
    });
  });

  describe('nullable and optional', () => {
    it('should handle nullable', () => {
      const schema = z.string().nullable();
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'string',
        nullable: true,
      });
    });

    it('should handle optional', () => {
      const schema = z.string().optional();
      const jsonSchema = zodToJsonSchema(schema);

      // Optional values are represented as anyOf with undefined and the type
      expect(jsonSchema.anyOf).toBeDefined();
      expect(jsonSchema.anyOf).toHaveLength(2);
      // Find the string type in the anyOf array
      const stringType = jsonSchema.anyOf?.find((t: any) => t.type === 'string');
      expect(stringType).toBeDefined();
      expect(stringType?.type).toBe('string');
    });

    it('should handle default with nullable', () => {
      const schema = z.string().nullable().default('default');
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'string',
        nullable: true,
        default: 'default',
      });
    });
  });

  describe('union types', () => {
    it('should convert union', () => {
      const schema = z.union([z.string(), z.number()]);
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        anyOf: [{ type: 'string' }, { type: 'number' }],
      });
    });

    it('should convert union with objects', () => {
      const schema = z.union([
        z.object({ type: z.literal('a'), value: z.string() }),
        z.object({ type: z.literal('b'), value: z.number() }),
      ]);
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema.anyOf).toHaveLength(2);
    });
  });

  describe('intersection types', () => {
    it('should convert intersection', () => {
      const schema = z.intersection(
        z.object({ name: z.string() }),
        z.object({ age: z.number() })
      );
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        allOf: [
          {
            type: 'object',
            properties: { name: { type: 'string' } },
            required: ['name'],
          },
          {
            type: 'object',
            properties: { age: { type: 'number' } },
            required: ['age'],
          },
        ],
      });
    });
  });

  describe('record types', () => {
    it('should convert record', () => {
      const schema = z.record(z.string(), z.string());
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'object',
        additionalProperties: { type: 'string' },
      });
    });

    it('should convert record with complex values', () => {
      const schema = z.record(z.string(), z.object({ value: z.number() }));
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({
        type: 'object',
        additionalProperties: {
          type: 'object',
          properties: { value: { type: 'number' } },
          required: ['value'],
          additionalProperties: false,
        },
      });
    });
  });

  describe('any and unknown types', () => {
    it('should handle any', () => {
      const schema = z.any();
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({});
    });

    it('should handle unknown', () => {
      const schema = z.unknown();
      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema).toEqual({});
    });
  });

  describe('complex schemas', () => {
    it('should handle real-world schema', () => {
      const schema = z.object({
        user: z.object({
          id: z.string().uuid(),
          name: z.string().min(1).max(100),
          email: z.string().email(),
          age: z.number().min(0).max(120).optional(),
        }),
        preferences: z.object({
          theme: z.enum(['light', 'dark']).default('light'),
          notifications: z.array(z.enum(['email', 'sms', 'push'])),
        }),
        metadata: z.record(z.string()),
      });

      const jsonSchema = zodToJsonSchema(schema);

      expect(jsonSchema.type).toBe('object');
      expect(jsonSchema.properties).toHaveProperty('user');
      expect(jsonSchema.properties).toHaveProperty('preferences');
      expect(jsonSchema.properties).toHaveProperty('metadata');
      expect(jsonSchema.required).toEqual(['user', 'preferences', 'metadata']);
    });
  });
});

describe('createToolSchema', () => {
  it('should create standard AI tool schema', () => {
    const tool = createTool(
      'get_weather',
      'Get current weather for a location',
      z.object({
        location: z.string(),
        units: z.enum(['celsius', 'fahrenheit']).default('celsius'),
      }),
      async (params) => params
    );

    const schema = createToolSchema(tool);

    expect(schema).toEqual({
      type: 'function',
      function: {
        name: 'get_weather',
        description: 'Get current weather for a location',
        parameters: {
          type: 'object',
          properties: {
            location: { type: 'string' },
            units: {
              type: 'string',
              enum: ['celsius', 'fahrenheit'],
              default: 'celsius',
            },
          },
          required: ['location'],
          additionalProperties: false,
        },
      },
    });
  });

  it('should include all parameter details', () => {
    const tool = createTool(
      'search',
      'Search for information',
      z.object({
        query: z.string().min(1).describe('The search query'),
        maxResults: z.number().min(1).max(100).default(10).describe('Maximum results'),
        filters: z.array(z.string()).optional().describe('Optional filters'),
      }),
      async (params) => params
    );

    const schema = createToolSchema(tool);

    expect(schema.function.name).toBe('search');
    expect(schema.function.description).toBe('Search for information');
    expect(schema.function.parameters.properties).toHaveProperty('query');
    expect(schema.function.parameters.properties).toHaveProperty('maxResults');
    expect(schema.function.parameters.properties).toHaveProperty('filters');
  });

  it('should work with empty schema', () => {
    const tool = createTool(
      'no_params',
      'Function with no parameters',
      z.object({}),
      async () => 'result'
    );

    const schema = createToolSchema(tool);

    expect(schema).toEqual({
      type: 'function',
      function: {
        name: 'no_params',
        description: 'Function with no parameters',
        parameters: {
          type: 'object',
          properties: {},
          additionalProperties: false,
        },
      },
    });
  });

  it('should handle complex nested schemas', () => {
    const tool = createTool(
      'create_user',
      'Create a new user',
      z.object({
        user: z.object({
          name: z.string(),
          email: z.string().email(),
        }),
        settings: z.object({
          theme: z.enum(['light', 'dark']),
        }),
      }),
      async (params) => params
    );

    const schema = createToolSchema(tool);

    expect(schema.function.parameters.type).toBe('object');
    expect(schema.function.parameters.properties?.user).toBeDefined();
    expect(schema.function.parameters.properties?.settings).toBeDefined();
  });
});

describe('Schema conversion integration', () => {
  it('should support full workflow from tool to JSON schema', () => {
    // Create a realistic tool
    const weatherTool = createTool(
      'get_weather',
      'Get current weather information for a location',
      z.object({
        location: z.string().describe('City name or coordinates'),
        units: z.enum(['celsius', 'fahrenheit']).default('celsius'),
        includeHourly: z.boolean().default(false),
      }),
      async (params) => ({
        location: params.location,
        temperature: 22,
        units: params.units,
        hourly: params.includeHourly ? [] : undefined,
      })
    );

    // Convert to AI tool schema
    const schema = createToolSchema(weatherTool);

    // Verify the schema is in the correct format for LLMs
    expect(schema.type).toBe('function');
    expect(schema.function.name).toBe('get_weather');
    expect(schema.function.description).toContain('weather');
    expect(schema.function.parameters.type).toBe('object');
    expect(schema.function.parameters.properties).toBeDefined();
    expect(schema.function.parameters.required).toContain('location');
  });

  it('should handle all Zod features together', () => {
    const complexSchema = z.object({
      // Strings with constraints
      username: z.string().min(3).max(20),
      email: z.string().email(),
      website: z.string().url().optional(),

      // Numbers with constraints
      age: z.number().int().min(0).max(120),
      score: z.number().min(0).max(100).default(0),

      // Enums
      role: z.enum(['admin', 'user', 'guest']),

      // Arrays
      tags: z.array(z.string()),
      settings: z.array(
        z.object({
          key: z.string(),
          value: z.string(),
        })
      ),

      // Nested objects
      profile: z.object({
        bio: z.string().optional(),
        avatar: z.string().url().optional(),
      }),

      // Records
      metadata: z.record(z.string(), z.string()),

      // Nullable and optional
      deletedAt: z.string().nullable().optional(),
    });

    const jsonSchema = zodToJsonSchema(complexSchema);

    expect(jsonSchema.type).toBe('object');
    expect(jsonSchema.properties).toHaveProperty('username');
    expect(jsonSchema.properties).toHaveProperty('email');
    expect(jsonSchema.properties).toHaveProperty('role');
    expect(jsonSchema.properties).toHaveProperty('tags');
    expect(jsonSchema.properties).toHaveProperty('profile');
    expect(jsonSchema.properties).toHaveProperty('metadata');
    expect(jsonSchema.required).toContain('username');
    expect(jsonSchema.required).toContain('email');
    expect(jsonSchema.required).not.toContain('website');
  });
});
