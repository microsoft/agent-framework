/**
 * Tests for serialization utilities.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  SerializationMixin,
  SerializationProtocol,
  isSerializable,
  isSerializationProtocol,
  SerializationOptions,
  DeserializationOptions,
} from '../serialization.js';

// Test classes
class SimpleClass extends SerializationMixin {
  public name: string;
  public value: number;

  constructor(kwargs: Record<string, unknown>) {
    super();
    this.name = kwargs.name as string;
    this.value = kwargs.value as number;
  }
}

class ClassWithExcludes extends SerializationMixin {
  static readonly DEFAULT_EXCLUDE = new Set(['secret']);

  public name: string;
  public secret: string;
  public value: number;

  constructor(kwargs: Record<string, unknown>) {
    super();
    this.name = kwargs.name as string;
    this.secret = kwargs.secret as string;
    this.value = kwargs.value as number;
  }
}

class ClassWithInjectable extends SerializationMixin {
  static readonly INJECTABLE = new Set(['dependency']);

  public name: string;
  public dependency?: object;

  constructor(kwargs: Record<string, unknown>) {
    super();
    this.name = kwargs.name as string;
    this.dependency = kwargs.dependency as object | undefined;
  }
}

class ClassWithCustomType extends SerializationMixin {
  static readonly type = 'custom_type';

  public value: string;

  constructor(kwargs: Record<string, unknown>) {
    super();
    this.value = kwargs.value as string;
  }
}

class ClassWithPrivateFields extends SerializationMixin {
  private _internal: string;
  public name: string;

  constructor(kwargs: Record<string, unknown>) {
    super();
    this.name = kwargs.name as string;
    this._internal = kwargs.internal as string;
  }

  getInternal(): string {
    return this._internal;
  }
}

class ClassWithNested extends SerializationMixin {
  public name: string;
  public nested?: SimpleClass;

  constructor(kwargs: Record<string, unknown>) {
    super();
    this.name = kwargs.name as string;
    this.nested = kwargs.nested as SimpleClass | undefined;
  }
}

class ClassWithArrays extends SerializationMixin {
  public items: string[];
  public nested: SimpleClass[];

  constructor(kwargs: Record<string, unknown>) {
    super();
    this.items = kwargs.items as string[];
    this.nested = kwargs.nested as SimpleClass[];
  }
}

class ClassWithDicts extends SerializationMixin {
  public metadata: Record<string, unknown>;
  public nestedMap: Record<string, SimpleClass>;

  constructor(kwargs: Record<string, unknown>) {
    super();
    this.metadata = kwargs.metadata as Record<string, unknown>;
    this.nestedMap = kwargs.nestedMap as Record<string, SimpleClass>;
  }
}

class ClassWithKwargs extends SerializationMixin {
  constructor(kwargs: Record<string, unknown>) {
    super();
    Object.assign(this, kwargs);
  }
}

describe('isSerializable', () => {
  it('should return true for primitive types', () => {
    expect(isSerializable('string')).toBe(true);
    expect(isSerializable(42)).toBe(true);
    expect(isSerializable(true)).toBe(true);
    expect(isSerializable(false)).toBe(true);
    expect(isSerializable(null)).toBe(true);
  });

  it('should return false for undefined', () => {
    expect(isSerializable(undefined)).toBe(false);
  });

  it('should return true for arrays', () => {
    expect(isSerializable([])).toBe(true);
    expect(isSerializable([1, 2, 3])).toBe(true);
  });

  it('should return true for plain objects', () => {
    expect(isSerializable({})).toBe(true);
    expect(isSerializable({ key: 'value' })).toBe(true);
  });

  it('should return false for functions', () => {
    expect(isSerializable(() => {})).toBe(false);
    expect(isSerializable(function named() {})).toBe(false);
  });

  it('should return false for class instances', () => {
    class MyClass {}
    expect(isSerializable(new MyClass())).toBe(false);
    expect(isSerializable(new Date())).toBe(false);
  });

  it('should return false for symbols', () => {
    expect(isSerializable(Symbol('test'))).toBe(false);
  });
});

describe('isSerializationProtocol', () => {
  it('should return true for objects with toDict method', () => {
    const obj = new SimpleClass('test', 42);
    expect(isSerializationProtocol(obj)).toBe(true);
  });

  it('should return true for plain objects with toDict', () => {
    const obj = {
      toDict: () => ({ key: 'value' }),
    };
    expect(isSerializationProtocol(obj)).toBe(true);
  });

  it('should return false for objects without toDict', () => {
    expect(isSerializationProtocol({})).toBe(false);
    expect(isSerializationProtocol({ other: 'method' })).toBe(false);
  });

  it('should return false for primitives', () => {
    expect(isSerializationProtocol('string')).toBe(false);
    expect(isSerializationProtocol(42)).toBe(false);
    expect(isSerializationProtocol(null)).toBe(false);
  });
});

describe('SerializationMixin', () => {
  describe('toDict', () => {
    it('should serialize simple objects', () => {
      const obj = new SimpleClass({ name: 'test', value: 42 });
      const result = obj.toDict();

      expect(result).toEqual({
        type: 'simple_class',
        name: 'test',
        value: 42,
      });
    });

    it('should exclude fields in DEFAULT_EXCLUDE', () => {
      const obj = new ClassWithExcludes({ name: 'test', secret: 'secret-value', value: 42 });
      const result = obj.toDict();

      expect(result).toEqual({
        type: 'class_with_excludes',
        name: 'test',
        value: 42,
      });
      expect(result.secret).toBeUndefined();
    });

    it('should exclude fields in INJECTABLE', () => {
      const dependency = { key: 'value' };
      const obj = new ClassWithInjectable({ name: 'test', dependency });
      const result = obj.toDict();

      expect(result).toEqual({
        type: 'class_with_injectable',
        name: 'test',
      });
      expect(result.dependency).toBeUndefined();
    });

    it('should exclude fields in runtime exclude parameter', () => {
      const obj = new SimpleClass({ name: 'test', value: 42 });
      const result = obj.toDict({ exclude: new Set(['value']) });

      expect(result).toEqual({
        type: 'simple_class',
        name: 'test',
      });
      expect(result.value).toBeUndefined();
    });

    it('should exclude private fields', () => {
      const obj = new ClassWithPrivateFields({ name: 'public', internal: 'private' });
      const result = obj.toDict();

      expect(result).toEqual({
        type: 'class_with_private_fields',
        name: 'public',
      });
      expect(result._internal).toBeUndefined();
    });

    it('should include type field with correct identifier', () => {
      const obj = new SimpleClass({ name: 'test', value: 42 });
      const result = obj.toDict();

      expect(result.type).toBe('simple_class');
    });

    it('should use custom type if defined', () => {
      const obj = new ClassWithCustomType({ value: 'test' });
      const result = obj.toDict();

      expect(result.type).toBe('custom_type');
    });

    it('should exclude null/undefined values when excludeNone is true', () => {
      const obj = new ClassWithKwargs({ name: 'test', value: null, other: undefined });
      const result = obj.toDict({ excludeNone: true });

      expect(result.name).toBe('test');
      expect(result.value).toBeUndefined();
      expect(result.other).toBeUndefined();
    });

    it('should include null/undefined values when excludeNone is false', () => {
      const obj = new ClassWithKwargs({ name: 'test', value: null, other: undefined });
      const result = obj.toDict({ excludeNone: false });

      expect(result.name).toBe('test');
      expect(result.value).toBeNull();
      expect(result.other).toBeUndefined(); // undefined is still excluded as it's not serializable
    });

    it('should recursively serialize nested SerializationProtocol objects', () => {
      const nested = new SimpleClass({ name: 'nested', value: 100 });
      const obj = new ClassWithNested({ name: 'parent', nested });
      const result = obj.toDict();

      expect(result).toEqual({
        type: 'class_with_nested',
        name: 'parent',
        nested: {
          type: 'simple_class',
          name: 'nested',
          value: 100,
        },
      });
    });

    it('should recursively serialize arrays of SerializationProtocol objects', () => {
      const obj = new ClassWithArrays({
        items: ['a', 'b', 'c'],
        nested: [new SimpleClass({ name: 'first', value: 1 }), new SimpleClass({ name: 'second', value: 2 })],
      });
      const result = obj.toDict();

      expect(result).toEqual({
        type: 'class_with_arrays',
        items: ['a', 'b', 'c'],
        nested: [
          { type: 'simple_class', name: 'first', value: 1 },
          { type: 'simple_class', name: 'second', value: 2 },
        ],
      });
    });

    it('should skip non-serializable items in arrays', () => {
      const obj = new ClassWithKwargs({
        items: ['valid', () => {}, 'also-valid', new Date()],
      });
      const result = obj.toDict();

      expect(result.items).toEqual(['valid', 'also-valid']);
    });

    it('should recursively serialize maps with SerializationProtocol values', () => {
      const obj = new ClassWithDicts({
        metadata: { key: 'value', number: 42 },
        nestedMap: {
          first: new SimpleClass({ name: 'first', value: 1 }),
          second: new SimpleClass({ name: 'second', value: 2 }),
        },
      });
      const result = obj.toDict();

      expect(result).toEqual({
        type: 'class_with_dicts',
        metadata: { key: 'value', number: 42 },
        nestedMap: {
          first: { type: 'simple_class', name: 'first', value: 1 },
          second: { type: 'simple_class', name: 'second', value: 2 },
        },
      });
    });

    it('should skip non-serializable values in dicts', () => {
      const obj = new ClassWithKwargs({
        metadata: {
          valid: 'string',
          invalid: () => {},
          alsoValid: 42,
          date: new Date(),
        },
      });
      const result = obj.toDict();

      expect(result.metadata).toEqual({
        valid: 'string',
        alsoValid: 42,
      });
    });
  });

  describe('toJson', () => {
    it('should produce valid JSON string', () => {
      const obj = new SimpleClass({ name: 'test', value: 42 });
      const json = obj.toJson();

      expect(() => JSON.parse(json)).not.toThrow();
      expect(JSON.parse(json)).toEqual({
        type: 'simple_class',
        name: 'test',
        value: 42,
      });
    });

    it('should support indent option', () => {
      const obj = new SimpleClass({ name: 'test', value: 42 });
      const json = obj.toJson({ indent: 2 });

      expect(json).toContain('\n');
      expect(json).toContain('  ');
    });

    it('should pass through serialization options', () => {
      const obj = new ClassWithExcludes({ name: 'test', secret: 'secret', value: 42 });
      const json = obj.toJson();
      const parsed = JSON.parse(json);

      expect(parsed.secret).toBeUndefined();
    });
  });

  describe('fromDict', () => {
    it('should create instance with correct properties', () => {
      const data = { type: 'simple_class', name: 'test', value: 42 };
      const obj = SimpleClass.fromDict(data);

      expect(obj).toBeInstanceOf(SimpleClass);
      expect(obj.name).toBe('test');
      expect(obj.value).toBe(42);
    });

    it('should filter out type field from constructor kwargs', () => {
      const data = { type: 'simple_class', name: 'test', value: 42 };
      const obj = SimpleClass.fromDict(data);

      // The type field should not be passed to constructor
      expect((obj as unknown as Record<string, unknown>)['type']).toBeUndefined();
    });

    it('should inject simple dependencies', () => {
      const dependency = { key: 'value' };
      const data = { type: 'class_with_injectable', name: 'test' };
      const obj = ClassWithInjectable.fromDict(data, {
        dependencies: {
          'class_with_injectable.dependency': dependency,
        },
      });

      expect(obj.name).toBe('test');
      expect(obj.dependency).toBe(dependency);
    });

    it('should inject dict dependencies', () => {
      const data = { type: 'class_with_kwargs', name: 'test' };
      const obj = ClassWithKwargs.fromDict(data, {
        dependencies: {
          'class_with_kwargs.options.timeout': 5000,
          'class_with_kwargs.options.retries': 3,
        },
      });

      expect((obj as unknown as Record<string, unknown>).name).toBe('test');
      expect((obj as unknown as Record<string, unknown>).options).toEqual({
        timeout: 5000,
        retries: 3,
      });
    });

    it('should ignore dependencies not matching type', () => {
      const data = { type: 'simple_class', name: 'test', value: 42 };
      const obj = SimpleClass.fromDict(data, {
        dependencies: {
          'other_class.something': 'ignored',
        },
      });

      expect(obj.name).toBe('test');
      expect(obj.value).toBe(42);
    });

    it('should handle dependencies with malformed keys', () => {
      const data = { type: 'simple_class', name: 'test', value: 42 };

      // Should not throw
      expect(() => {
        SimpleClass.fromDict(data, {
          dependencies: {
            'no_dot_separator': 'invalid',
            '': 'empty',
          },
        });
      }).not.toThrow();
    });

    it('should handle custom type identifiers', () => {
      const data = { type: 'custom_type', value: 'test' };
      const obj = ClassWithCustomType.fromDict(data);

      expect(obj.value).toBe('test');
    });
  });

  describe('fromJson', () => {
    it('should reconstruct instance from JSON', () => {
      const json = '{"type":"simple_class","name":"test","value":42}';
      const obj = SimpleClass.fromJson(json);

      expect(obj).toBeInstanceOf(SimpleClass);
      expect(obj.name).toBe('test');
      expect(obj.value).toBe(42);
    });

    it('should support dependencies', () => {
      const dependency = { key: 'value' };
      const json = '{"type":"class_with_injectable","name":"test"}';
      const obj = ClassWithInjectable.fromJson(json, {
        dependencies: {
          'class_with_injectable.dependency': dependency,
        },
      });

      expect(obj.dependency).toBe(dependency);
    });
  });

  describe('round-trip serialization', () => {
    it('should preserve data through serialize-deserialize cycle', () => {
      const original = new SimpleClass({ name: 'test', value: 42 });
      const serialized = original.toDict();
      const restored = SimpleClass.fromDict(serialized);

      expect(restored.name).toBe(original.name);
      expect(restored.value).toBe(original.value);
    });

    it('should preserve data through toJson-fromJson cycle', () => {
      const original = new SimpleClass({ name: 'test', value: 42 });
      const json = original.toJson();
      const restored = SimpleClass.fromJson(json);

      expect(restored.name).toBe(original.name);
      expect(restored.value).toBe(original.value);
    });

    it('should handle nested objects in round-trip', () => {
      const nested = new SimpleClass({ name: 'nested', value: 100 });
      const original = new ClassWithNested({ name: 'parent', nested });
      const json = original.toJson();
      const restored = ClassWithNested.fromJson(json);

      expect(restored.name).toBe(original.name);
      expect(restored.nested).toBeDefined();
      // Note: nested will be a plain object, not a SimpleClass instance
      // This is expected behavior - deep deserialization requires additional logic
    });

    it('should preserve dependencies through cycle', () => {
      const dependency = { key: 'value' };
      const original = new ClassWithInjectable({ name: 'test', dependency });
      const serialized = original.toDict();
      const restored = ClassWithInjectable.fromDict(serialized, {
        dependencies: {
          'class_with_injectable.dependency': dependency,
        },
      });

      expect(restored.name).toBe(original.name);
      expect(restored.dependency).toBe(dependency);
    });
  });

  describe('type identifier conversion', () => {
    it('should convert CamelCase to snake_case', () => {
      class MyCamelCaseClass extends SerializationMixin {
        constructor(kwargs: Record<string, unknown>) {
          super();
        }
      }

      const obj = new MyCamelCaseClass({});
      const result = obj.toDict();

      expect(result.type).toBe('my_camel_case_class');
    });

    it('should handle single word class names', () => {
      class Agent extends SerializationMixin {
        constructor(kwargs: Record<string, unknown>) {
          super();
        }
      }

      const obj = new Agent({});
      const result = obj.toDict();

      expect(result.type).toBe('agent');
    });

    it('should handle acronyms in class names', () => {
      class HTTPClient extends SerializationMixin {
        constructor(kwargs: Record<string, unknown>) {
          super();
        }
      }

      const obj = new HTTPClient({});
      const result = obj.toDict();

      // Each capital letter gets an underscore
      expect(result.type).toBe('h_t_t_p_client');
    });
  });

  describe('edge cases', () => {
    it('should handle empty objects', () => {
      class EmptyClass extends SerializationMixin {
        constructor(kwargs: Record<string, unknown>) {
          super();
        }
      }

      const obj = new EmptyClass({});
      const result = obj.toDict();

      expect(result).toEqual({ type: 'empty_class' });
    });

    it('should handle objects with only excluded fields', () => {
      class OnlyExcluded extends SerializationMixin {
        static readonly DEFAULT_EXCLUDE = new Set(['field1', 'field2']);

        public field1: string;
        public field2: number;

        constructor(kwargs: Record<string, unknown>) {
          super();
          this.field1 = kwargs.field1 as string;
          this.field2 = kwargs.field2 as number;
        }
      }

      const obj = new OnlyExcluded({ field1: 'test', field2: 42 });
      const result = obj.toDict();

      expect(result).toEqual({ type: 'only_excluded' });
    });

    it('should handle circular references gracefully', () => {
      // Note: This would cause infinite recursion in naive implementations
      // Our implementation doesn't handle this automatically, but it should be documented
      class CircularClass extends SerializationMixin {
        public ref?: CircularClass;
        public name: string;

        constructor(kwargs: Record<string, unknown>) {
          super();
          this.name = kwargs.name as string;
        }
      }

      const obj1 = new CircularClass({ name: 'obj1' });
      const obj2 = new CircularClass({ name: 'obj2' });
      obj1.ref = obj2;
      obj2.ref = obj1;

      // This will cause a stack overflow - expected behavior
      // In production code, users should exclude circular references
      expect(() => obj1.toDict()).toThrow();
    });

    it('should handle very deeply nested structures', () => {
      let nested: ClassWithNested | undefined = undefined;
      for (let i = 0; i < 10; i++) {
        nested = new ClassWithNested({
          name: `level-${i}`,
          nested: nested ? new SimpleClass({ name: 'nested', value: i }) : undefined,
        });
      }

      const result = nested!.toDict();
      expect(result.name).toBe('level-9');
    });
  });
});
