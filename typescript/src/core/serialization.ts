/**
 * Serialization utilities for converting objects to/from JSON with dependency injection support.
 *
 * This module provides a generic serialization framework that supports:
 * - Automatic field inclusion/exclusion based on metadata
 * - Recursive serialization of nested objects
 * - Dependency injection for non-serializable components
 * - Type identification for deserialization
 *
 * @module serialization
 */

import { getLogger } from './logging/index.js';

const logger = getLogger();

/**
 * Regular expression pattern for converting CamelCase to snake_case.
 */
const CAMEL_TO_SNAKE_PATTERN = /(?<!^)(?=[A-Z])/;

/**
 * Protocol for objects that support serialization and deserialization.
 *
 * Classes implementing this protocol can be converted to/from plain JavaScript objects
 * for JSON serialization and persistence.
 *
 * @example
 * ```typescript
 * class MyClass implements SerializationProtocol {
 *   constructor(public value: string) {}
 *
 *   toDict(): Record<string, unknown> {
 *     return { type: 'my_class', value: this.value };
 *   }
 *
 *   static fromDict(data: Record<string, unknown>): MyClass {
 *     return new MyClass(data.value as string);
 *   }
 * }
 * ```
 */
export interface SerializationProtocol {
  /**
   * Convert the instance to a dictionary representation.
   *
   * @param options - Serialization options
   * @returns Dictionary representation of the instance
   */
  toDict(options?: SerializationOptions): Record<string, unknown>;
}

/**
 * Options for controlling serialization behavior.
 */
export interface SerializationOptions {
  /**
   * Fields to exclude from serialization.
   */
  exclude?: Set<string>;

  /**
   * Whether to exclude null and undefined values from the output.
   * @default true
   */
  excludeNone?: boolean;
}

/**
 * Options for controlling deserialization behavior.
 */
export interface DeserializationOptions {
  /**
   * Dependencies to inject during deserialization.
   *
   * Keys should be in format:
   * - `"<type>.<parameter>"` for simple dependencies
   * - `"<type>.<dict-parameter>.<key>"` for nested dict dependencies
   *
   * @example
   * ```typescript
   * {
   *   'chat_agent.chatClient': clientInstance,
   *   'chat_agent.options.timeout': 5000
   * }
   * ```
   */
  dependencies?: Record<string, unknown>;
}

/**
 * Check if a value is JSON serializable.
 *
 * Returns true for primitive types, null, arrays, and plain objects.
 * Returns false for functions, class instances, and other non-JSON types.
 *
 * @param value - The value to check
 * @returns True if the value is JSON serializable
 *
 * @example
 * ```typescript
 * isSerializable('hello') // true
 * isSerializable(42) // true
 * isSerializable([1, 2, 3]) // true
 * isSerializable({ key: 'value' }) // true
 * isSerializable(new Date()) // false
 * isSerializable(() => {}) // false
 * ```
 */
export function isSerializable(value: unknown): boolean {
  if (value === null) return true;
  if (value === undefined) return false;

  const type = typeof value;
  if (type === 'string' || type === 'number' || type === 'boolean') {
    return true;
  }

  if (Array.isArray(value)) {
    return true;
  }

  // Check for plain objects (not class instances)
  if (type === 'object' && value.constructor === Object) {
    return true;
  }

  return false;
}

/**
 * Type guard to check if a value implements SerializationProtocol.
 *
 * @param value - The value to check
 * @returns True if the value has a toDict method
 *
 * @example
 * ```typescript
 * if (isSerializationProtocol(obj)) {
 *   const dict = obj.toDict();
 * }
 * ```
 */
export function isSerializationProtocol(value: unknown): value is SerializationProtocol {
  return value !== null && typeof value === 'object' && typeof (value as SerializationProtocol).toDict === 'function';
}

/**
 * Mixin class providing default serialization and deserialization behavior.
 *
 * Classes extending this mixin automatically gain serialization capabilities with:
 * - Automatic field discovery and serialization
 * - Configurable field exclusion via DEFAULT_EXCLUDE
 * - Dependency injection support via INJECTABLE
 * - Recursive serialization of nested objects
 * - Type identification for deserialization
 *
 * @example
 * ```typescript
 * class ChatAgent extends SerializationMixin {
 *   static readonly DEFAULT_EXCLUDE = new Set(['additionalProperties']);
 *   static readonly INJECTABLE = new Set(['chatClient']);
 *
 *   constructor(
 *     public chatClient: ChatClientProtocol,
 *     public name: string,
 *     public additionalProperties: Record<string, unknown> = {}
 *   ) {
 *     super();
 *   }
 * }
 *
 * const agent = new ChatAgent(client, 'my-agent');
 * const serialized = agent.toDict(); // excludes chatClient, additionalProperties
 * const json = agent.toJson();
 *
 * const restored = ChatAgent.fromDict(serialized, {
 *   dependencies: { 'chat_agent.chatClient': client }
 * });
 * ```
 */
export class SerializationMixin implements SerializationProtocol {
  /**
   * Fields to always exclude from serialization.
   *
   * Override in subclasses to specify fields that should never be serialized.
   */
  static readonly DEFAULT_EXCLUDE: Set<string> = new Set();

  /**
   * Fields that are injectable dependencies.
   *
   * These fields are:
   * - Excluded from serialization
   * - Can be provided via the dependencies parameter in fromDict/fromJson
   *
   * Override in subclasses to specify which dependencies can be injected.
   */
  static readonly INJECTABLE: Set<string> = new Set();

  /**
   * Custom type identifier for this class.
   *
   * If not specified, the class name will be converted to snake_case.
   *
   * @example
   * ```typescript
   * class MyAgent extends SerializationMixin {
   *   static readonly type = 'custom_agent_type';
   * }
   * ```
   */
  static readonly type?: string;

  /**
   * Convert the instance to a dictionary representation.
   *
   * Automatically serializes all public instance properties, excluding:
   * - Fields in DEFAULT_EXCLUDE
   * - Fields in INJECTABLE
   * - Fields in the runtime exclude parameter
   * - Private fields (starting with underscore)
   * - Null/undefined values (when excludeNone is true)
   *
   * Recursively serializes nested SerializationProtocol objects, arrays, and plain objects.
   *
   * @param options - Serialization options
   * @returns Dictionary representation of the instance
   *
   * @example
   * ```typescript
   * const dict = agent.toDict();
   * const dictWithExtras = agent.toDict({
   *   exclude: new Set(['temporaryField']),
   *   excludeNone: false
   * });
   * ```
   */
  toDict(options: SerializationOptions = {}): Record<string, unknown> {
    const { exclude = new Set(), excludeNone = true } = options;
    const constructor = this.constructor as typeof SerializationMixin;

    // Combine exclude sets
    const combined = new Set([...constructor.DEFAULT_EXCLUDE, ...constructor.INJECTABLE, ...exclude]);

    // Start with type field (unless excluded)
    const result: Record<string, unknown> = combined.has('type') ? {} : { type: this.getTypeIdentifier() };

    // Serialize all public instance properties
    for (const [key, value] of Object.entries(this)) {
      // Skip if excluded or private
      if (combined.has(key) || key.startsWith('_')) {
        continue;
      }

      // Skip null/undefined if excludeNone
      if (excludeNone && (value === null || value === undefined)) {
        continue;
      }

      // Recursively serialize SerializationProtocol objects
      if (isSerializationProtocol(value)) {
        result[key] = value.toDict(options);
        continue;
      }

      // Handle arrays
      if (Array.isArray(value)) {
        const valueAsList: unknown[] = [];
        for (const item of value) {
          if (isSerializationProtocol(item)) {
            valueAsList.push(item.toDict(options));
            continue;
          }
          if (isSerializable(item)) {
            valueAsList.push(item);
            continue;
          }
          logger.debug(`Skipping non-serializable item in list attribute '${key}' of type ${typeof item}`);
        }
        result[key] = valueAsList;
        continue;
      }

      // Handle plain objects/maps
      if (typeof value === 'object' && value !== null && value.constructor === Object) {
        const serializedObj: Record<string, unknown> = {};
        for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
          if (isSerializationProtocol(v)) {
            serializedObj[k] = v.toDict(options);
            continue;
          }
          if (isSerializable(v)) {
            serializedObj[k] = v;
            continue;
          }
          logger.debug(
            `Skipping non-serializable value for key '${k}' in dict attribute '${key}' of type ${typeof v}`
          );
        }
        result[key] = serializedObj;
        continue;
      }

      // Include if JSON serializable
      if (isSerializable(value)) {
        result[key] = value;
        continue;
      }

      logger.debug(`Skipping non-serializable attribute '${key}' of type ${typeof value}`);
    }

    return result;
  }

  /**
   * Convert the instance to a JSON string.
   *
   * @param options - Serialization options plus JSON.stringify options (indent, replacer)
   * @returns JSON string representation of the instance
   *
   * @example
   * ```typescript
   * const json = agent.toJson();
   * const prettyJson = agent.toJson({ indent: 2 });
   * ```
   */
  toJson(
    options: SerializationOptions & { indent?: number; replacer?: (key: string, value: unknown) => unknown } = {}
  ): string {
    const { indent, replacer, ...serializationOptions } = options;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return JSON.stringify(this.toDict(serializationOptions), replacer as any, indent);
  }

  /**
   * Create an instance from a dictionary.
   *
   * Injects dependencies specified in the dependencies parameter and passes
   * remaining data to the constructor.
   *
   * @param data - Dictionary containing the instance data
   * @param options - Deserialization options including dependencies
   * @returns New instance of the class
   *
   * @example
   * ```typescript
   * const data = { name: 'my-agent', model: 'gpt-4' };
   * const agent = ChatAgent.fromDict(data, {
   *   dependencies: {
   *     'chat_agent.chatClient': clientInstance
   *   }
   * });
   * ```
   */
  static fromDict<T extends SerializationMixin>(
    this: (new (kwargs: Record<string, unknown>) => T) & typeof SerializationMixin,
    data: Record<string, unknown>,
    options: DeserializationOptions = {}
  ): T {
    const { dependencies = {} } = options;
    const typeId = this.getTypeIdentifier();

    // Filter out 'type' field
    const kwargs: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(data)) {
      if (key !== 'type') {
        kwargs[key] = value;
      }
    }

    // Process dependencies
    for (const [depKey, depValue] of Object.entries(dependencies)) {
      const parts = depKey.split('.');
      if (parts.length < 2) {
        continue;
      }

      const [depType, param, ...rest] = parts;

      // Skip if not for this type
      if (depType !== typeId) {
        continue;
      }

      // Log debug message if dependency is not in INJECTABLE
      if (!this.INJECTABLE.has(param)) {
        logger.debug(
          `Dependency '${param}' for type '${typeId}' is not in INJECTABLE set. ` +
            `Available injectable parameters: ${Array.from(this.INJECTABLE).join(', ')}`
        );
      }

      if (rest.length === 0) {
        // Simple dependency: <type>.<parameter>
        kwargs[param] = depValue;
      } else if (rest.length === 1) {
        // Dict dependency: <type>.<dict-parameter>.<key>
        const key = rest[0];
        if (!(param in kwargs)) {
          kwargs[param] = {};
        }
        (kwargs[param] as Record<string, unknown>)[key] = depValue;
      }
    }

    return new this(kwargs);
  }

  /**
   * Create an instance from a JSON string.
   *
   * @param json - JSON string containing the instance data
   * @param options - Deserialization options including dependencies
   * @returns New instance of the class
   *
   * @example
   * ```typescript
   * const json = '{"name":"my-agent","model":"gpt-4"}';
   * const agent = ChatAgent.fromJson(json, {
   *   dependencies: {
   *     'chat_agent.chatClient': clientInstance
   *   }
   * });
   * ```
   */
  static fromJson<T extends SerializationMixin>(
    this: (new (kwargs: Record<string, unknown>) => T) & typeof SerializationMixin,
    json: string,
    options: DeserializationOptions = {}
  ): T {
    const data = JSON.parse(json) as Record<string, unknown>;
    return this.fromDict(data, options) as T;
  }

  /**
   * Get the type identifier for this instance.
   *
   * Uses the static `type` property if defined, otherwise converts
   * the class name to snake_case.
   *
   * @returns Type identifier string
   * @protected
   */
  protected getTypeIdentifier(): string {
    const constructor = this.constructor as typeof SerializationMixin;
    return constructor.getTypeIdentifier();
  }

  /**
   * Get the type identifier for this class.
   *
   * Uses the static `type` property if defined, otherwise converts
   * the class name to snake_case.
   *
   * @returns Type identifier string
   * @private
   */
  private static getTypeIdentifier(): string {
    if (this.type) {
      return this.type;
    }

    // Convert class name to snake_case
    return this.name.split(CAMEL_TO_SNAKE_PATTERN).join('_').toLowerCase();
  }
}
