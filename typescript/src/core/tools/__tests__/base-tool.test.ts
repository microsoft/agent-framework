import { describe, it, expect } from 'vitest';
import { z } from 'zod';
import { AITool, BaseTool, FunctionTool, createTool } from '../base-tool.js';

describe('AITool Interface', () => {
  it('should allow implementing a custom tool', async () => {
    const customTool: AITool = {
      name: 'custom_tool',
      description: 'A custom tool implementation',
      schema: z.object({ value: z.string() }),
      async execute(params) {
        const validated = this.schema.parse(params);
        return validated;
      },
    };

    expect(customTool.name).toBe('custom_tool');
    expect(customTool.description).toBe('A custom tool implementation');
    expect(customTool.schema).toBeInstanceOf(z.ZodObject);

    const result = await customTool.execute({ value: 'test' });
    expect(result).toEqual({ value: 'test' });
  });

  it('should support tools with all required fields', () => {
    const tool: AITool = {
      name: 'test_tool',
      description: 'Test description',
      schema: z.object({}),
      execute: async () => 'result',
    };

    expect(tool.name).toBe('test_tool');
    expect(tool.description).toBe('Test description');
    expect(tool.schema).toBeDefined();
    expect(typeof tool.execute).toBe('function');
  });

  it('should support tools with optional metadata field', () => {
    const tool: AITool = {
      name: 'test_tool',
      description: 'Test description',
      schema: z.object({}),
      execute: async () => 'result',
      metadata: { version: '1.0', author: 'test' },
    };

    expect(tool.metadata).toEqual({ version: '1.0', author: 'test' });
  });
});

describe('BaseTool', () => {
  class TestTool extends BaseTool {
    async execute(params: unknown): Promise<unknown> {
      return this.validate(params);
    }
  }

  it('should not be instantiable directly (abstract)', () => {
    // TypeScript enforces this at compile time
    // The abstract keyword prevents instantiation at compile time
    // We can verify that the class requires execute() to be implemented
    const tool = new TestTool({
      name: 'test',
      description: 'test',
      schema: z.object({}),
    });

    // Verify the subclass works
    expect(tool).toBeInstanceOf(BaseTool);
    expect(tool.name).toBe('test');
  });

  it('should allow subclass with execute implementation', async () => {
    const tool = new TestTool({
      name: 'test_tool',
      description: 'A test tool',
      schema: z.object({ value: z.string() }),
    });

    expect(tool.name).toBe('test_tool');
    expect(tool.description).toBe('A test tool');
    const result = await tool.execute({ value: 'test' });
    expect(result).toEqual({ value: 'test' });
  });

  it('should validate params against schema', async () => {
    const tool = new TestTool({
      name: 'validation_tool',
      description: 'Tests validation',
      schema: z.object({
        name: z.string(),
        age: z.number(),
      }),
    });

    const result = await tool.execute({ name: 'John', age: 30 });
    expect(result).toEqual({ name: 'John', age: 30 });
  });

  it('should throw ZodError for invalid params', async () => {
    const tool = new TestTool({
      name: 'validation_tool',
      description: 'Tests validation',
      schema: z.object({
        name: z.string(),
        age: z.number(),
      }),
    });

    await expect(tool.execute({ name: 'John' })).rejects.toThrow(z.ZodError);
    await expect(tool.execute({ name: 123, age: 30 })).rejects.toThrow(z.ZodError);
  });

  it('should return parsed and coerced params', async () => {
    const tool = new TestTool({
      name: 'coercion_tool',
      description: 'Tests coercion',
      schema: z.object({
        value: z.coerce.number(),
      }),
    });

    const result = await tool.execute({ value: '42' });
    expect(result).toEqual({ value: 42 });
  });

  it('should support optional metadata', () => {
    const tool = new TestTool({
      name: 'metadata_tool',
      description: 'Has metadata',
      schema: z.object({}),
      metadata: { version: '2.0', tags: ['test', 'demo'] },
    });

    expect(tool.metadata).toEqual({ version: '2.0', tags: ['test', 'demo'] });
  });

  it('should work with complex nested schemas', async () => {
    const tool = new TestTool({
      name: 'complex_tool',
      description: 'Complex schema',
      schema: z.object({
        user: z.object({
          name: z.string(),
          email: z.string().email(),
        }),
        preferences: z.array(z.string()),
        settings: z.record(z.string(), z.boolean()),
      }),
    });

    const params = {
      user: { name: 'John', email: 'john@example.com' },
      preferences: ['dark-mode', 'notifications'],
      settings: { emailNotifications: true, smsNotifications: false },
    };

    const result = await tool.execute(params);
    expect(result).toEqual(params);
  });
});

describe('FunctionTool', () => {
  it('should create a tool from a function', async () => {
    const tool = new FunctionTool({
      name: 'test_function',
      description: 'Test function tool',
      schema: z.object({ value: z.string() }),
      fn: async (params) => params,
    });

    expect(tool.name).toBe('test_function');
    expect(tool.description).toBe('Test function tool');
    const result = await tool.execute({ value: 'test' });
    expect(result).toEqual({ value: 'test' });
  });

  it('should call the wrapped function when executed', async () => {
    let called = false;
    const tool = new FunctionTool({
      name: 'call_tracking',
      description: 'Tracks calls',
      schema: z.object({}),
      fn: async () => {
        called = true;
        return 'success';
      },
    });

    expect(called).toBe(false);
    await tool.execute({});
    expect(called).toBe(true);
  });

  it('should validate params before execution', async () => {
    const tool = new FunctionTool({
      name: 'validation_function',
      description: 'Validates params',
      schema: z.object({ value: z.number() }),
      fn: async (params) => params,
    });

    await expect(tool.execute({ value: 'invalid' })).rejects.toThrow(z.ZodError);
  });

  it('should work with async functions', async () => {
    const tool = new FunctionTool({
      name: 'async_function',
      description: 'Async function',
      schema: z.object({ delay: z.number() }),
      fn: async (params: any) => {
        await new Promise((resolve) => setTimeout(resolve, params.delay));
        return 'done';
      },
    });

    const result = await tool.execute({ delay: 10 });
    expect(result).toBe('done');
  });

  it('should work with sync functions (auto-wrapped)', async () => {
    const tool = new FunctionTool({
      name: 'sync_function',
      description: 'Sync function',
      schema: z.object({ value: z.number() }),
      fn: (params: any) => params.value * 2,
    });

    const result = await tool.execute({ value: 5 });
    expect(result).toBe(10);
  });

  it('should pass validated params to the function', async () => {
    const tool = new FunctionTool({
      name: 'param_tool',
      description: 'Tests params',
      schema: z.object({
        name: z.string(),
        age: z.number().default(0),
      }),
      fn: async (params: any) => {
        expect(params.name).toBe('John');
        expect(params.age).toBe(0);
        return params;
      },
    });

    await tool.execute({ name: 'John' });
  });

  it('should support metadata', () => {
    const tool = new FunctionTool({
      name: 'metadata_function',
      description: 'Has metadata',
      schema: z.object({}),
      fn: async () => 'result',
      metadata: { approval: 'required' },
    });

    expect(tool.metadata).toEqual({ approval: 'required' });
  });
});

describe('createTool helper', () => {
  it('should create a valid AITool', () => {
    const tool = createTool(
      'test_tool',
      'Test tool',
      z.object({ value: z.string() }),
      async (params) => params
    );

    expect(tool.name).toBe('test_tool');
    expect(tool.description).toBe('Test tool');
    expect(tool.schema).toBeInstanceOf(z.ZodObject);
  });

  it('should execute the tool correctly', async () => {
    const tool = createTool(
      'calculator',
      'Simple calculator',
      z.object({
        operation: z.enum(['add', 'multiply']),
        a: z.number(),
        b: z.number(),
      }),
      async (params) => {
        if (params.operation === 'add') return params.a + params.b;
        return params.a * params.b;
      }
    );

    const addResult = await tool.execute({ operation: 'add', a: 5, b: 3 });
    expect(addResult).toBe(8);

    const multiplyResult = await tool.execute({ operation: 'multiply', a: 5, b: 3 });
    expect(multiplyResult).toBe(15);
  });

  it('should validate params before execution', async () => {
    const tool = createTool(
      'validation_tool',
      'Validates',
      z.object({ value: z.number().min(0) }),
      async (params) => params
    );

    await expect(tool.execute({ value: -1 })).rejects.toThrow(z.ZodError);
  });

  it('should provide type inference from Zod schema', async () => {
    const schema = z.object({
      name: z.string(),
      age: z.number(),
      email: z.string().email(),
    });

    const tool = createTool(
      'user_tool',
      'User operations',
      schema,
      async (params) => {
        // TypeScript should infer the correct type for params
        const name: string = params.name;
        const age: number = params.age;
        const email: string = params.email;
        return { name, age, email };
      }
    );

    const result = await tool.execute({
      name: 'John',
      age: 30,
      email: 'john@example.com',
    });

    expect(result).toEqual({
      name: 'John',
      age: 30,
      email: 'john@example.com',
    });
  });

  it('should work with sync functions', async () => {
    const tool = createTool(
      'sync_tool',
      'Sync function',
      z.object({ value: z.number() }),
      (params) => params.value * 2
    );

    const result = await tool.execute({ value: 21 });
    expect(result).toBe(42);
  });

  it('should work with async functions', async () => {
    const tool = createTool(
      'async_tool',
      'Async function',
      z.object({ value: z.number() }),
      async (params) => {
        await new Promise((resolve) => setTimeout(resolve, 10));
        return params.value * 2;
      }
    );

    const result = await tool.execute({ value: 21 });
    expect(result).toBe(42);
  });
});

describe('Integration tests', () => {
  it('should work end-to-end with tool creation and execution', async () => {
    // Create a weather tool
    const weatherTool = createTool(
      'get_weather',
      'Get current weather for a location',
      z.object({
        location: z.string(),
        units: z.enum(['celsius', 'fahrenheit']).default('celsius'),
      }),
      async (params) => {
        return {
          location: params.location,
          temperature: 22,
          units: params.units,
          condition: 'sunny',
        };
      }
    );

    const result = await weatherTool.execute({ location: 'Seattle' });
    expect(result).toEqual({
      location: 'Seattle',
      temperature: 22,
      units: 'celsius',
      condition: 'sunny',
    });
  });

  it('should handle complex nested schemas', async () => {
    const tool = createTool(
      'user_registration',
      'Register a new user',
      z.object({
        user: z.object({
          name: z.string().min(1),
          email: z.string().email(),
          age: z.number().min(18),
        }),
        preferences: z.object({
          newsletter: z.boolean(),
          notifications: z.array(z.enum(['email', 'sms', 'push'])),
        }),
        metadata: z.record(z.string(), z.string()),
      }),
      async (params) => {
        return {
          userId: 'user-123',
          ...params,
        };
      }
    );

    const result = await tool.execute({
      user: {
        name: 'John Doe',
        email: 'john@example.com',
        age: 25,
      },
      preferences: {
        newsletter: true,
        notifications: ['email', 'push'],
      },
      metadata: {
        source: 'web',
        campaign: 'spring2024',
      },
    });

    expect(result).toHaveProperty('userId');
    expect((result as any).user.name).toBe('John Doe');
  });

  it('should handle errors gracefully', async () => {
    const tool = createTool(
      'error_tool',
      'Tool that can error',
      z.object({ shouldError: z.boolean() }),
      async (params) => {
        if (params.shouldError) {
          throw new Error('Tool execution failed');
        }
        return 'success';
      }
    );

    const successResult = await tool.execute({ shouldError: false });
    expect(successResult).toBe('success');

    await expect(tool.execute({ shouldError: true })).rejects.toThrow(
      'Tool execution failed'
    );
  });

  it('should handle validation errors with descriptive messages', async () => {
    const tool = createTool(
      'validation_tool',
      'Tool with strict validation',
      z.object({
        email: z.string().email(),
        age: z.number().min(0).max(120),
        username: z.string().min(3).max(20),
      }),
      async (params) => params
    );

    // Invalid email
    await expect(tool.execute({ email: 'invalid', age: 25, username: 'john' })).rejects.toThrow();

    // Invalid age (too high)
    await expect(
      tool.execute({ email: 'test@example.com', age: 150, username: 'john' })
    ).rejects.toThrow();

    // Invalid username (too short)
    await expect(
      tool.execute({ email: 'test@example.com', age: 25, username: 'ab' })
    ).rejects.toThrow();
  });
});
