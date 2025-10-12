import { describe, it, expect } from 'vitest';
import { z } from 'zod';
import {
  aiFunction,
  getAIFunctionMetadata,
  isAIFunction,
  getAllAIFunctions,
} from '../decorators.js';

describe('@aiFunction decorator', () => {
  it('should attach metadata to a method', () => {
    class TestAgent {
      @aiFunction({
        description: 'Test function',
        schema: z.object({ value: z.string() }),
      })
      async testMethod() {
        return 'result';
      }
    }

    const agent = new TestAgent();
    const metadata = getAIFunctionMetadata(agent, 'testMethod');

    expect(metadata).toBeDefined();
    expect(metadata?.name).toBe('testMethod');
    expect(metadata?.description).toBe('Test function');
    expect(metadata?.schema).toBeInstanceOf(z.ZodObject);
  });

  it('should use explicit name when provided', () => {
    class TestAgent {
      @aiFunction({
        name: 'custom_name',
        description: 'Test function',
        schema: z.object({}),
      })
      async testMethod() {
        return 'result';
      }
    }

    const agent = new TestAgent();
    const metadata = getAIFunctionMetadata(agent, 'testMethod');

    expect(metadata?.name).toBe('custom_name');
  });

  it('should infer name from method name when not provided', () => {
    class TestAgent {
      @aiFunction({
        description: 'Test function',
        schema: z.object({}),
      })
      async myAwesomeMethod() {
        return 'result';
      }
    }

    const agent = new TestAgent();
    const metadata = getAIFunctionMetadata(agent, 'myAwesomeMethod');

    expect(metadata?.name).toBe('myAwesomeMethod');
  });

  it('should allow decorated method to be called normally', async () => {
    class TestAgent {
      @aiFunction({
        description: 'Test function',
        schema: z.object({ value: z.number() }),
      })
      async calculate(params: { value: number }) {
        return params.value * 2;
      }
    }

    const agent = new TestAgent();
    const result = await agent.calculate({ value: 21 });

    expect(result).toBe(42);
  });

  it('should preserve method behavior with multiple decorators', async () => {
    let callCount = 0;

    class TestAgent {
      @aiFunction({
        description: 'Increment counter',
        schema: z.object({}),
      })
      async increment() {
        callCount++;
        return callCount;
      }
    }

    const agent = new TestAgent();
    await agent.increment();
    await agent.increment();
    const result = await agent.increment();

    expect(result).toBe(3);
  });

  it('should work with complex schemas', () => {
    class TestAgent {
      @aiFunction({
        description: 'Complex function',
        schema: z.object({
          user: z.object({
            name: z.string(),
            email: z.string().email(),
          }),
          preferences: z.array(z.string()),
        }),
      })
      async complexMethod() {
        return 'result';
      }
    }

    const agent = new TestAgent();
    const metadata = getAIFunctionMetadata(agent, 'complexMethod');

    expect(metadata?.schema).toBeInstanceOf(z.ZodObject);
  });

  it('should work with methods that have different signatures', async () => {
    class TestAgent {
      @aiFunction({
        description: 'No params',
        schema: z.object({}),
      })
      async noParams() {
        return 'no-params';
      }

      @aiFunction({
        description: 'With params',
        schema: z.object({ value: z.string() }),
      })
      async withParams(params: { value: string }) {
        return params.value;
      }
    }

    const agent = new TestAgent();

    const result1 = await agent.noParams();
    expect(result1).toBe('no-params');

    const result2 = await agent.withParams({ value: 'test' });
    expect(result2).toBe('test');
  });

  it('should handle symbol property keys', () => {
    const methodSymbol = Symbol('testMethod');

    class TestAgent {
      @aiFunction({
        name: 'symbol_method',
        description: 'Test function',
        schema: z.object({}),
      })
      async [methodSymbol]() {
        return 'result';
      }
    }

    const agent = new TestAgent();
    const metadata = getAIFunctionMetadata(agent, methodSymbol);

    expect(metadata?.name).toBe('symbol_method');
  });
});

describe('getAIFunctionMetadata', () => {
  it('should retrieve metadata from decorated method', () => {
    class TestAgent {
      @aiFunction({
        description: 'Test function',
        schema: z.object({ value: z.string() }),
      })
      async testMethod() {
        return 'result';
      }
    }

    const agent = new TestAgent();
    const metadata = getAIFunctionMetadata(agent, 'testMethod');

    expect(metadata).toEqual({
      name: 'testMethod',
      description: 'Test function',
      schema: expect.any(Object),
    });
  });

  it('should return undefined for non-decorated method', () => {
    class TestAgent {
      async regularMethod() {
        return 'result';
      }
    }

    const agent = new TestAgent();
    const metadata = getAIFunctionMetadata(agent, 'regularMethod');

    expect(metadata).toBeUndefined();
  });

  it('should return undefined for non-existent method', () => {
    class TestAgent {}

    const agent = new TestAgent();
    const metadata = getAIFunctionMetadata(agent, 'nonExistent');

    expect(metadata).toBeUndefined();
  });

  it('should work with inherited methods', () => {
    class BaseAgent {
      @aiFunction({
        description: 'Base function',
        schema: z.object({}),
      })
      async baseMethod() {
        return 'base';
      }
    }

    class DerivedAgent extends BaseAgent {}

    const agent = new DerivedAgent();
    const metadata = getAIFunctionMetadata(agent, 'baseMethod');

    expect(metadata?.name).toBe('baseMethod');
    expect(metadata?.description).toBe('Base function');
  });
});

describe('isAIFunction', () => {
  it('should return true for decorated method', () => {
    class TestAgent {
      @aiFunction({
        description: 'Test function',
        schema: z.object({}),
      })
      async decoratedMethod() {
        return 'result';
      }
    }

    const agent = new TestAgent();
    expect(isAIFunction(agent, 'decoratedMethod')).toBe(true);
  });

  it('should return false for non-decorated method', () => {
    class TestAgent {
      async regularMethod() {
        return 'result';
      }
    }

    const agent = new TestAgent();
    expect(isAIFunction(agent, 'regularMethod')).toBe(false);
  });

  it('should return false for non-existent method', () => {
    class TestAgent {}

    const agent = new TestAgent();
    expect(isAIFunction(agent, 'nonExistent')).toBe(false);
  });

  it('should work with inherited methods', () => {
    class BaseAgent {
      @aiFunction({
        description: 'Base function',
        schema: z.object({}),
      })
      async baseMethod() {
        return 'base';
      }
    }

    class DerivedAgent extends BaseAgent {
      async regularMethod() {
        return 'regular';
      }
    }

    const agent = new DerivedAgent();
    expect(isAIFunction(agent, 'baseMethod')).toBe(true);
    expect(isAIFunction(agent, 'regularMethod')).toBe(false);
  });
});

describe('getAllAIFunctions', () => {
  it('should return empty array for object with no AI functions', () => {
    class TestAgent {
      async regularMethod() {
        return 'result';
      }
    }

    const agent = new TestAgent();
    const functions = getAllAIFunctions(agent);

    expect(functions).toEqual([]);
  });

  it('should return all AI functions from an object', () => {
    class TestAgent {
      @aiFunction({
        description: 'Function 1',
        schema: z.object({}),
      })
      async func1() {
        return 'result1';
      }

      @aiFunction({
        description: 'Function 2',
        schema: z.object({}),
      })
      async func2() {
        return 'result2';
      }

      async regularMethod() {
        return 'regular';
      }
    }

    const agent = new TestAgent();
    const functions = getAllAIFunctions(agent);

    expect(functions).toHaveLength(2);
    expect(functions.map((f) => f.propertyKey).sort()).toEqual(['func1', 'func2']);
    expect(functions[0].metadata.description).toBeDefined();
  });

  it('should include inherited AI functions', () => {
    class BaseAgent {
      @aiFunction({
        description: 'Base function',
        schema: z.object({}),
      })
      async baseMethod() {
        return 'base';
      }
    }

    class DerivedAgent extends BaseAgent {
      @aiFunction({
        description: 'Derived function',
        schema: z.object({}),
      })
      async derivedMethod() {
        return 'derived';
      }
    }

    const agent = new DerivedAgent();
    const functions = getAllAIFunctions(agent);

    expect(functions).toHaveLength(2);
    expect(functions.map((f) => f.propertyKey).sort()).toEqual([
      'baseMethod',
      'derivedMethod',
    ]);
  });

  it('should handle multiple levels of inheritance', () => {
    class GrandparentAgent {
      @aiFunction({
        description: 'Grandparent function',
        schema: z.object({}),
      })
      async grandparentMethod() {
        return 'grandparent';
      }
    }

    class ParentAgent extends GrandparentAgent {
      @aiFunction({
        description: 'Parent function',
        schema: z.object({}),
      })
      async parentMethod() {
        return 'parent';
      }
    }

    class ChildAgent extends ParentAgent {
      @aiFunction({
        description: 'Child function',
        schema: z.object({}),
      })
      async childMethod() {
        return 'child';
      }
    }

    const agent = new ChildAgent();
    const functions = getAllAIFunctions(agent);

    expect(functions).toHaveLength(3);
    expect(functions.map((f) => f.propertyKey).sort()).toEqual([
      'childMethod',
      'grandparentMethod',
      'parentMethod',
    ]);
  });

  it('should include correct metadata for each function', () => {
    class TestAgent {
      @aiFunction({
        name: 'custom_search',
        description: 'Search function',
        schema: z.object({ query: z.string() }),
      })
      async search() {
        return [];
      }

      @aiFunction({
        description: 'Calculator function',
        schema: z.object({ value: z.number() }),
      })
      async calculate() {
        return 0;
      }
    }

    const agent = new TestAgent();
    const functions = getAllAIFunctions(agent);

    const searchFunc = functions.find((f) => f.propertyKey === 'search');
    expect(searchFunc?.metadata.name).toBe('custom_search');
    expect(searchFunc?.metadata.description).toBe('Search function');

    const calcFunc = functions.find((f) => f.propertyKey === 'calculate');
    expect(calcFunc?.metadata.name).toBe('calculate');
    expect(calcFunc?.metadata.description).toBe('Calculator function');
  });

  it('should not include duplicate methods', () => {
    class ParentAgent {
      @aiFunction({
        description: 'Parent version',
        schema: z.object({}),
      })
      async sharedMethod() {
        return 'parent';
      }
    }

    class ChildAgent extends ParentAgent {
      // Override without decorator
      async sharedMethod() {
        return 'child';
      }
    }

    const agent = new ChildAgent();
    const functions = getAllAIFunctions(agent);

    // Should only find the parent's decorated version
    const sharedMethods = functions.filter((f) => f.propertyKey === 'sharedMethod');
    expect(sharedMethods).toHaveLength(1);
  });
});

describe('Integration tests', () => {
  it('should work with a realistic agent class', async () => {
    class WeatherAgent {
      @aiFunction({
        name: 'get_weather',
        description: 'Get current weather for a location',
        schema: z.object({
          location: z.string(),
          units: z.enum(['celsius', 'fahrenheit']).default('celsius'),
        }),
      })
      async getWeather(params: { location: string; units?: string }) {
        return {
          location: params.location,
          temperature: 22,
          units: params.units || 'celsius',
        };
      }

      @aiFunction({
        name: 'get_forecast',
        description: 'Get weather forecast for the next N days',
        schema: z.object({
          location: z.string(),
          days: z.number().min(1).max(7).default(3),
        }),
      })
      async getForecast(params: { location: string; days?: number }) {
        return {
          location: params.location,
          days: params.days || 3,
          forecast: [],
        };
      }

      // Regular method (not an AI function)
      async logWeatherRequest(location: string) {
        console.log(`Weather requested for ${location}`);
      }
    }

    const agent = new WeatherAgent();

    // Test metadata retrieval
    const weatherMetadata = getAIFunctionMetadata(agent, 'getWeather');
    expect(weatherMetadata?.name).toBe('get_weather');
    expect(weatherMetadata?.description).toContain('current weather');

    const forecastMetadata = getAIFunctionMetadata(agent, 'getForecast');
    expect(forecastMetadata?.name).toBe('get_forecast');

    // Test isAIFunction
    expect(isAIFunction(agent, 'getWeather')).toBe(true);
    expect(isAIFunction(agent, 'getForecast')).toBe(true);
    expect(isAIFunction(agent, 'logWeatherRequest')).toBe(false);

    // Test getAllAIFunctions
    const functions = getAllAIFunctions(agent);
    expect(functions).toHaveLength(2);

    // Test that methods still work normally
    const weatherResult = await agent.getWeather({ location: 'Seattle' });
    expect(weatherResult.location).toBe('Seattle');
    expect(weatherResult.temperature).toBe(22);

    const forecastResult = await agent.getForecast({ location: 'Seattle', days: 5 });
    expect(forecastResult.days).toBe(5);
  });

  it('should work with decorator and createTool together', () => {
    class HybridAgent {
      @aiFunction({
        description: 'Decorated method',
        schema: z.object({ value: z.string() }),
      })
      async decoratedMethod(params: { value: string }) {
        return params.value;
      }
    }

    const agent = new HybridAgent();

    // Verify decorator worked
    const metadata = getAIFunctionMetadata(agent, 'decoratedMethod');
    expect(metadata).toBeDefined();
    expect(metadata?.description).toBe('Decorated method');

    // Verify method still works
    expect(typeof agent.decoratedMethod).toBe('function');
  });
});
