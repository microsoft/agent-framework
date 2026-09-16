import { Ajv, type ErrorObject, type ValidateFunction } from "ajv";

import { MiddlewareFailure, ToolExecutionError } from "./errors.js";
import { runMiddleware, type FunctionInvocationContext, type FunctionMiddleware } from "./middleware.js";
import type { FunctionCallContent } from "./types.js";

export type JsonSchema = Record<string, unknown>;
export type ToolArguments = Record<string, unknown>;
export type ToolExecutor<TArguments extends ToolArguments = ToolArguments, TResult = unknown> = (
  argumentsValue: TArguments,
  context: FunctionInvocationContext,
) => TResult | Promise<TResult>;

export interface FunctionToolOptions<TArguments extends ToolArguments = ToolArguments, TResult = unknown> {
  name: string;
  description?: string;
  parameters: JsonSchema;
  execute: ToolExecutor<TArguments, TResult>;
  middleware?: readonly FunctionMiddleware[];
  maxInvocations?: number;
  maxInvocationErrors?: number;
  additionalProperties?: Record<string, unknown>;
}

export interface FunctionToolDefinition {
  type: "function";
  function: {
    name: string;
    description: string;
    parameters: JsonSchema;
  };
}

const ajv = new Ajv({ allErrors: true, strict: false });

function validationMessage(errors: ErrorObject[] | null | undefined): string {
  if (errors === null || errors === undefined || errors.length === 0) {
    return "Tool arguments do not match the declared schema.";
  }
  return `Tool arguments do not match the declared schema: ${errors
    .map((error) => `${error.instancePath || "/"} ${error.message ?? "is invalid"}`)
    .join("; ")}`;
}

export function parseToolArguments(argumentsValue: FunctionCallContent["arguments"]): ToolArguments {
  if (argumentsValue === undefined || argumentsValue === "") return {};

  let parsed: unknown = argumentsValue;
  if (typeof argumentsValue === "string") {
    try {
      parsed = JSON.parse(argumentsValue) as unknown;
    } catch (error) {
      throw new ToolExecutionError("Tool arguments must be valid JSON.", { cause: error });
    }
  }

  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new ToolExecutionError("Tool arguments must be a JSON object.");
  }
  return { ...(parsed as ToolArguments) };
}

export class FunctionTool<TArguments extends ToolArguments = ToolArguments, TResult = unknown> {
  public readonly name: string;
  public readonly description: string;
  public readonly parameters: JsonSchema;
  public readonly additionalProperties: Record<string, unknown>;
  public readonly maxInvocations?: number;
  public readonly maxInvocationErrors?: number;

  readonly #execute: ToolExecutor<TArguments, TResult>;
  readonly #middleware: readonly FunctionMiddleware[];
  readonly #validate: ValidateFunction<TArguments>;
  #invocationCount = 0;
  #invocationErrorCount = 0;

  public constructor(options: FunctionToolOptions<TArguments, TResult>) {
    if (options.name.trim().length === 0) throw new TypeError("Tool name cannot be empty.");
    if (
      options.maxInvocations !== undefined &&
      (!Number.isSafeInteger(options.maxInvocations) || options.maxInvocations < 1)
    ) {
      throw new RangeError("maxInvocations must be a positive safe integer.");
    }
    if (
      options.maxInvocationErrors !== undefined &&
      (!Number.isSafeInteger(options.maxInvocationErrors) || options.maxInvocationErrors < 1)
    ) {
      throw new RangeError("maxInvocationErrors must be a positive safe integer.");
    }

    this.name = options.name;
    this.description = options.description ?? "";
    this.parameters = { ...options.parameters };
    this.additionalProperties = { ...options.additionalProperties };
    if (options.maxInvocations !== undefined) this.maxInvocations = options.maxInvocations;
    if (options.maxInvocationErrors !== undefined) this.maxInvocationErrors = options.maxInvocationErrors;
    this.#execute = options.execute;
    this.#middleware = [...(options.middleware ?? [])];
    this.#validate = ajv.compile<TArguments>(this.parameters);
  }

  public get definition(): FunctionToolDefinition {
    return {
      type: "function",
      function: {
        name: this.name,
        description: this.description,
        parameters: { ...this.parameters },
      },
    };
  }

  public async invoke(
    call: FunctionCallContent,
    options: {
      middleware?: readonly FunctionMiddleware[];
      runtimeArguments?: Readonly<ToolArguments>;
      signal?: AbortSignal;
    } = {},
  ): Promise<TResult> {
    if (this.maxInvocations !== undefined && this.#invocationCount >= this.maxInvocations) {
      throw new ToolExecutionError(`Tool '${this.name}' has reached its invocation limit.`);
    }
    if (this.maxInvocationErrors !== undefined && this.#invocationErrorCount >= this.maxInvocationErrors) {
      throw new ToolExecutionError(`Tool '${this.name}' has reached its invocation error limit.`);
    }

    const signal = options.signal ?? new AbortController().signal;

    try {
      signal.throwIfAborted();
      const argumentsValue = parseToolArguments(call.arguments);
      if (!this.#validate(argumentsValue)) {
        throw new ToolExecutionError(validationMessage(this.#validate.errors));
      }
      const context: FunctionInvocationContext = {
        tool: this,
        call,
        arguments: argumentsValue,
        runtimeArguments: { ...options.runtimeArguments },
        signal,
      };
      const middleware = [...this.#middleware, ...(options.middleware ?? [])];
      await runMiddleware(context, middleware, async () => {
        signal.throwIfAborted();
        if (!this.#validate(context.arguments)) {
          throw new ToolExecutionError(validationMessage(this.#validate.errors));
        }
        if (this.maxInvocations !== undefined && this.#invocationCount >= this.maxInvocations) {
          throw new ToolExecutionError(`Tool '${this.name}' has reached its invocation limit.`);
        }
        this.#invocationCount += 1;
        context.result = await this.#execute(context.arguments as TArguments, context);
        signal.throwIfAborted();
      });
      return context.result as TResult;
    } catch (error) {
      if (error instanceof MiddlewareFailure || signal.aborted) throw error;
      this.#invocationErrorCount += 1;
      throw error;
    }
  }
}

export function defineTool<TArguments extends ToolArguments = ToolArguments, TResult = unknown>(
  options: FunctionToolOptions<TArguments, TResult>,
): FunctionTool<TArguments, TResult> {
  return new FunctionTool(options);
}

export function normalizeTools(tools: readonly FunctionTool[] | undefined): FunctionTool[] {
  const result = [...(tools ?? [])];
  const names = new Set<string>();
  for (const tool of result) {
    if (names.has(tool.name)) throw new TypeError(`Tool names must be unique; found '${tool.name}' more than once.`);
    names.add(tool.name);
  }
  return result;
}
