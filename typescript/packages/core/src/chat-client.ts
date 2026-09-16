import { randomUUID } from "node:crypto";

import { abortableAsyncIterable } from "./cancellation.js";
import { AgentInvalidResponseError, MiddlewareFailure } from "./errors.js";
import { runMiddleware, type ChatContext, type ChatMiddleware, type FunctionMiddleware } from "./middleware.js";
import { normalizeTools, type FunctionTool, type ToolArguments } from "./tools.js";
import {
  ChatResponse,
  ChatResponseUpdate,
  Message,
  ResponseStream,
  addUsageDetails,
  functionResult,
  normalizeMessages,
  type FunctionCallContent,
  type FunctionResultContent,
  type Content,
  type MessageInput,
  type UsageDetails,
} from "./types.js";

export const DEFAULT_MAX_FUNCTION_CALLING_ITERATIONS = 40;
export const DEFAULT_MAX_CONSECUTIVE_TOOL_ERRORS = 3;
export const FUNCTION_CALL_LIMIT_MESSAGE = "Function invocation limit reached before a final answer could be produced.";

export interface FunctionInvocationConfiguration {
  enabled: boolean;
  maxIterations: number;
  maxFunctionCalls?: number | undefined;
  maxConsecutiveErrors: number;
  parallel: boolean;
  includeDetailedErrors: boolean;
}

export interface ChatOptions extends Record<string, unknown> {
  instructions?: string;
  tools?: readonly FunctionTool[];
  toolChoice?: "auto" | "none" | "required" | string;
}

export interface ChatRequestOptions<TOptions extends ChatOptions = ChatOptions> {
  stream?: boolean;
  options?: TOptions;
  functionInvocation?: boolean | Partial<FunctionInvocationConfiguration>;
  functionInvocationArguments?: Readonly<ToolArguments>;
  signal?: AbortSignal;
}

export interface ChatClientRequest<TOptions extends ChatOptions = ChatOptions> {
  messages: readonly Message[];
  options: TOptions;
  stream: boolean;
  signal?: AbortSignal;
}

export interface BaseChatClientOptions {
  middleware?: readonly ChatMiddleware[];
  functionMiddleware?: readonly FunctionMiddleware[];
  functionInvocation?: Partial<FunctionInvocationConfiguration>;
  additionalProperties?: Record<string, unknown>;
}

export interface SupportsChatGetResponse<TOptions extends ChatOptions = ChatOptions> {
  readonly additionalProperties: Record<string, unknown>;
  getResponse(
    messages: MessageInput | readonly MessageInput[],
    request?: ChatRequestOptions<TOptions> & { stream?: false },
  ): Promise<ChatResponse>;
  getResponse(
    messages: MessageInput | readonly MessageInput[],
    request: ChatRequestOptions<TOptions> & { stream: true },
  ): ResponseStream<ChatResponseUpdate, ChatResponse>;
}

interface InvocationBatchResult {
  message: Message;
  errorCount: number;
  attemptedCount: number;
  limitReached: boolean;
}

function createOccurrenceId(): string {
  return `af-call-${randomUUID().replaceAll("-", "")}`;
}

function isAsyncIterable(value: unknown): value is AsyncIterable<ChatResponseUpdate> {
  return (
    value !== null &&
    typeof value === "object" &&
    Symbol.asyncIterator in value &&
    typeof (value as AsyncIterable<ChatResponseUpdate>)[Symbol.asyncIterator] === "function"
  );
}

function resolveConfiguration(
  base: FunctionInvocationConfiguration,
  override: boolean | Partial<FunctionInvocationConfiguration> | undefined,
): FunctionInvocationConfiguration {
  const result: FunctionInvocationConfiguration =
    typeof override === "boolean" ? { ...base, enabled: override } : { ...base, ...override };
  if (!Number.isInteger(result.maxIterations) || result.maxIterations < 1) {
    throw new RangeError("maxIterations must be a positive integer.");
  }
  if (
    result.maxFunctionCalls !== undefined &&
    (!Number.isInteger(result.maxFunctionCalls) || result.maxFunctionCalls < 1)
  ) {
    throw new RangeError("maxFunctionCalls must be a positive integer.");
  }
  if (!Number.isInteger(result.maxConsecutiveErrors) || result.maxConsecutiveErrors < 1) {
    throw new RangeError("maxConsecutiveErrors must be a positive integer.");
  }
  return result;
}

interface ExtractedFunctionCalls {
  calls: FunctionCallContent[];
  suppressedCalls: boolean;
}

function callsFromResponse(response: ChatResponse, seenOccurrenceIds: Set<string>): ExtractedFunctionCalls {
  const calls: FunctionCallContent[] = [];
  const openCalls = new Map<string, FunctionCallContent[]>();
  const openCallsByOccurrence = new Map<string, FunctionCallContent>();
  const completedCalls = new Set<FunctionCallContent>();
  const retainedMessages: Message[] = [];
  let suppressedCalls = false;
  for (const message of response.messages) {
    const retainedContents: Content[] = [];
    for (const content of message.contents) {
      if (content?.type === "function_call") {
        const occurrenceId = content.id ?? createOccurrenceId();
        const call = { ...content, id: occurrenceId };
        if (seenOccurrenceIds.has(occurrenceId)) {
          suppressedCalls = true;
          continue;
        }
        seenOccurrenceIds.add(occurrenceId);
        retainedContents.push(call);
        calls.push(call);
        const pending = openCalls.get(call.callId) ?? [];
        pending.push(call);
        openCalls.set(call.callId, pending);
        openCallsByOccurrence.set(occurrenceId, call);
      } else if (content?.type === "function_result") {
        const pending = openCalls.get(content.callId);
        const occurrenceMatch = content.id === undefined ? undefined : openCallsByOccurrence.get(content.id);
        const completed = occurrenceMatch?.callId === content.callId ? occurrenceMatch : undefined;
        if (completed !== undefined) {
          completedCalls.add(completed);
          openCallsByOccurrence.delete(completed.id!);
          const pendingIndex = pending?.indexOf(completed) ?? -1;
          if (pendingIndex >= 0) pending?.splice(pendingIndex, 1);
          retainedContents.push(content);
        }
      } else {
        retainedContents.push(content);
      }
    }
    message.contents = retainedContents;
    if (retainedContents.length > 0) retainedMessages.push(message);
  }
  response.messages = retainedMessages;
  return {
    calls: calls.filter((call) => !completedCalls.has(call)),
    suppressedCalls,
  };
}

function sanitizeFinalResponse(response: ChatResponse): ChatResponse {
  const messages = response.messages
    .map(
      (message) =>
        new Message({
          role: message.role,
          contents: message.contents.filter(
            (content) => content.type !== "function_call" && content.type !== "function_result",
          ),
          ...(message.authorName === undefined ? {} : { authorName: message.authorName }),
          ...(message.messageId === undefined ? {} : { messageId: message.messageId }),
          additionalProperties: message.additionalProperties,
        }),
    )
    .filter((message) => message.contents.length > 0);
  return new ChatResponse({
    messages,
    ...(response.responseId === undefined ? {} : { responseId: response.responseId }),
    ...(response.finishReason === undefined ? {} : { finishReason: response.finishReason }),
    ...(response.usageDetails === undefined ? {} : { usageDetails: response.usageDetails }),
    additionalProperties: response.additionalProperties,
  });
}

function errorResult(call: FunctionCallContent, message: string): FunctionResultContent {
  return {
    ...functionResult(call.callId, message, true),
    ...(call.id === undefined ? {} : { id: call.id }),
  };
}

function errorText(toolName: string, error: unknown, includeDetails: boolean): string {
  const prefix = `Tool '${toolName}' failed.`;
  if (!includeDetails || !(error instanceof Error) || error.message.length === 0) return prefix;
  return `${prefix} ${error.message}`;
}

function responseFromMessages(
  messages: readonly Message[],
  responseId: string | undefined,
  usageDetails: UsageDetails | undefined,
  finishReason: string | undefined,
  additionalProperties: Readonly<Record<string, unknown>>,
): ChatResponse {
  return new ChatResponse({
    messages,
    ...(responseId === undefined ? {} : { responseId }),
    ...(usageDetails === undefined ? {} : { usageDetails }),
    ...(finishReason === undefined ? {} : { finishReason }),
    additionalProperties: { ...additionalProperties },
  });
}

export abstract class BaseChatClient<
  TOptions extends ChatOptions = ChatOptions,
> implements SupportsChatGetResponse<TOptions> {
  public readonly additionalProperties: Record<string, unknown>;
  public readonly functionInvocationConfiguration: FunctionInvocationConfiguration;

  readonly #middleware: readonly ChatMiddleware[];
  readonly #functionMiddleware: readonly FunctionMiddleware[];

  public constructor(options: BaseChatClientOptions = {}) {
    this.additionalProperties = { ...options.additionalProperties };
    this.#middleware = [...(options.middleware ?? [])];
    this.#functionMiddleware = [...(options.functionMiddleware ?? [])];
    this.functionInvocationConfiguration = resolveConfiguration(
      {
        enabled: true,
        maxIterations: DEFAULT_MAX_FUNCTION_CALLING_ITERATIONS,
        maxConsecutiveErrors: DEFAULT_MAX_CONSECUTIVE_TOOL_ERRORS,
        parallel: true,
        includeDetailedErrors: false,
      },
      options.functionInvocation,
    );
  }

  public getResponse(
    messages: MessageInput | readonly MessageInput[],
    request?: ChatRequestOptions<TOptions> & { stream?: false },
  ): Promise<ChatResponse>;
  public getResponse(
    messages: MessageInput | readonly MessageInput[],
    request: ChatRequestOptions<TOptions> & { stream: true },
  ): ResponseStream<ChatResponseUpdate, ChatResponse>;
  public getResponse(
    messages: MessageInput | readonly MessageInput[],
    request: ChatRequestOptions<TOptions> = {},
  ): Promise<ChatResponse> | ResponseStream<ChatResponseUpdate, ChatResponse> {
    const normalizedMessages = normalizeMessages(messages);
    const options = { ...(request.options ?? ({} as TOptions)) };
    const configuration = resolveConfiguration(this.functionInvocationConfiguration, request.functionInvocation);

    if (request.stream === true) {
      return new ResponseStream(
        this.#streamResponse(
          normalizedMessages,
          options,
          configuration,
          request.functionInvocationArguments,
          request.signal,
        ),
        ChatResponse.fromUpdates,
      );
    }
    return this.#getNonStreamingResponse(
      normalizedMessages,
      options,
      configuration,
      request.functionInvocationArguments,
      request.signal,
    );
  }

  protected abstract getResponseCore(
    request: ChatClientRequest<TOptions>,
  ): Promise<ChatResponse | AsyncIterable<ChatResponseUpdate>>;

  async #requestOnce(
    messages: readonly Message[],
    options: TOptions,
    stream: boolean,
    signal: AbortSignal | undefined,
  ): Promise<ChatResponse | AsyncIterable<ChatResponseUpdate>> {
    signal?.throwIfAborted();
    const context: ChatContext = {
      messages: messages.map((message) => message.clone()),
      options: { ...options },
      stream,
      ...(signal === undefined ? {} : { signal }),
    };
    await runMiddleware(context, this.#middleware, async () => {
      context.signal?.throwIfAborted();
      context.result = await this.getResponseCore({
        messages: context.messages,
        options: context.options as TOptions,
        stream,
        ...(context.signal === undefined ? {} : { signal: context.signal }),
      });
    });
    context.signal?.throwIfAborted();
    if (context.result === undefined) {
      throw new AgentInvalidResponseError("Chat middleware completed without producing a response.");
    }
    return context.result;
  }

  async #requestResponse(
    messages: readonly Message[],
    options: TOptions,
    signal: AbortSignal | undefined,
  ): Promise<ChatResponse> {
    const response = await this.#requestOnce(messages, options, false, signal);
    if (isAsyncIterable(response)) {
      throw new AgentInvalidResponseError("A non-streaming chat request returned a stream.");
    }
    return response;
  }

  async #requestStream(
    messages: readonly Message[],
    options: TOptions,
    signal: AbortSignal | undefined,
  ): Promise<AsyncIterable<ChatResponseUpdate>> {
    const response = await this.#requestOnce(messages, options, true, signal);
    if (!isAsyncIterable(response)) {
      throw new AgentInvalidResponseError("A streaming chat request returned a non-streaming response.");
    }
    return response;
  }

  async #invokeCalls(
    calls: readonly FunctionCallContent[],
    tools: readonly FunctionTool[],
    configuration: FunctionInvocationConfiguration,
    runtimeArguments: Readonly<ToolArguments> | undefined,
    remainingCalls: number | undefined,
    signal: AbortSignal | undefined,
  ): Promise<InvocationBatchResult> {
    const toolsByName = new Map(tools.map((tool) => [tool.name, tool]));
    const controller = new AbortController();
    const invocationSignal = signal === undefined ? controller.signal : AbortSignal.any([signal, controller.signal]);
    const executeCall = async (call: FunctionCallContent, index: number): Promise<FunctionResultContent> => {
      invocationSignal.throwIfAborted();
      const name = call.name ?? "";
      if (remainingCalls !== undefined && index >= remainingCalls) {
        return errorResult(call, FUNCTION_CALL_LIMIT_MESSAGE);
      }
      const tool = toolsByName.get(name);
      if (tool === undefined) return errorResult(call, `Tool '${name}' is not available.`);
      try {
        const result = await tool.invoke(call, {
          middleware: this.#functionMiddleware,
          ...(runtimeArguments === undefined ? {} : { runtimeArguments }),
          signal: invocationSignal,
        });
        return {
          ...functionResult(call.callId, result),
          ...(call.id === undefined ? {} : { id: call.id }),
        };
      } catch (error) {
        if (signal?.aborted) throw signal.reason ?? new DOMException("The operation was aborted.", "AbortError");
        if (error instanceof MiddlewareFailure) {
          controller.abort(error);
          throw error;
        }
        return errorResult(call, errorText(name, error, configuration.includeDetailedErrors));
      }
    };

    let contents: FunctionResultContent[] = [];
    try {
      if (configuration.parallel) {
        contents = await Promise.all(calls.map(executeCall));
      } else {
        for (let index = 0; index < calls.length; index += 1) {
          contents.push(await executeCall(calls[index]!, index));
        }
      }
    } catch (error) {
      controller.abort(error);
      if (signal?.aborted) throw signal.reason ?? new DOMException("The operation was aborted.", "AbortError");
      throw error;
    }

    const attemptedCount = remainingCalls === undefined ? calls.length : Math.min(calls.length, remainingCalls);
    return {
      message: new Message({ role: "tool", contents }),
      errorCount: contents.filter((content) => content.isError === true).length,
      attemptedCount,
      limitReached: remainingCalls !== undefined && calls.length >= remainingCalls,
    };
  }

  async #getNonStreamingResponse(
    inputMessages: readonly Message[],
    options: TOptions,
    configuration: FunctionInvocationConfiguration,
    runtimeArguments: Readonly<ToolArguments> | undefined,
    signal: AbortSignal | undefined,
  ): Promise<ChatResponse> {
    const tools = normalizeTools(options.tools);
    if (!configuration.enabled || tools.length === 0 || options.toolChoice === "none") {
      const response = await this.#requestResponse(inputMessages, options, signal);
      callsFromResponse(response, new Set<string>());
      return response;
    }

    const history = inputMessages.map((message) => message.clone());
    const output: Message[] = [];
    let usageDetails: UsageDetails | undefined;
    let responseId: string | undefined;
    let finishReason: string | undefined;
    const additionalProperties: Record<string, unknown> = {};
    let invocationCount = 0;
    let consecutiveErrors = 0;
    const seenOccurrenceIds = new Set<string>();

    for (let iteration = 0; iteration < configuration.maxIterations; iteration += 1) {
      const response = await this.#requestResponse(history, options, signal);
      usageDetails = addUsageDetails(usageDetails, response.usageDetails);
      responseId = response.responseId ?? responseId;
      finishReason = response.finishReason ?? finishReason;
      Object.assign(additionalProperties, response.additionalProperties);
      const { calls, suppressedCalls } = callsFromResponse(response, seenOccurrenceIds);
      output.push(...response.messages);
      history.push(...response.messages.map((message) => message.clone()));
      if (calls.length === 0) {
        if (suppressedCalls && response.text.trim().length === 0) break;
        return responseFromMessages(output, responseId, usageDetails, finishReason, additionalProperties);
      }

      const remainingCalls =
        configuration.maxFunctionCalls === undefined
          ? undefined
          : Math.max(configuration.maxFunctionCalls - invocationCount, 0);
      const batch = await this.#invokeCalls(calls, tools, configuration, runtimeArguments, remainingCalls, signal);
      invocationCount += batch.attemptedCount;
      consecutiveErrors = batch.errorCount === 0 ? 0 : consecutiveErrors + 1;
      output.push(batch.message);
      history.push(batch.message.clone());
      if (
        batch.limitReached ||
        consecutiveErrors >= configuration.maxConsecutiveErrors ||
        iteration + 1 >= configuration.maxIterations
      ) {
        break;
      }
    }

    const finalOptions = { ...options, tools: [], toolChoice: "none" } as unknown as TOptions;
    const finalResponse = sanitizeFinalResponse(await this.#requestResponse(history, finalOptions, signal));
    usageDetails = addUsageDetails(usageDetails, finalResponse.usageDetails);
    responseId = finalResponse.responseId ?? responseId;
    finishReason = finalResponse.finishReason ?? finishReason;
    Object.assign(additionalProperties, finalResponse.additionalProperties);
    output.push(...finalResponse.messages);
    if (finalResponse.text.trim().length === 0) {
      output.push(new Message({ role: "assistant", contents: FUNCTION_CALL_LIMIT_MESSAGE }));
    }
    return responseFromMessages(output, responseId, usageDetails, finishReason, additionalProperties);
  }

  async *#streamResponse(
    inputMessages: readonly Message[],
    options: TOptions,
    configuration: FunctionInvocationConfiguration,
    runtimeArguments: Readonly<ToolArguments> | undefined,
    signal: AbortSignal | undefined,
  ): AsyncGenerator<ChatResponseUpdate> {
    const tools = normalizeTools(options.tools);
    const useFunctionInvocation = configuration.enabled && tools.length > 0 && options.toolChoice !== "none";
    const history = inputMessages.map((message) => message.clone());
    let invocationCount = 0;
    let consecutiveErrors = 0;
    let forceFinalTurn = false;
    const seenOccurrenceIds = new Set<string>();

    for (let iteration = 0; ; iteration += 1) {
      const finalTurn = useFunctionInvocation && (forceFinalTurn || iteration >= configuration.maxIterations);
      const requestOptions = finalTurn
        ? ({ ...options, tools: [], toolChoice: "none" } as unknown as TOptions)
        : options;
      const source = await this.#requestStream(history, requestOptions, signal);
      const turnId = `af-message-${randomUUID().replaceAll("-", "")}`;
      const occurrenceIds = new Map<string, string>();
      const occurrenceCallIds = new Map<string, string>();
      const completedOccurrenceIds = new Set<string>();
      const turnUpdates: ChatResponseUpdate[] = [];
      let suppressedCalls = false;

      for await (const rawUpdate of abortableAsyncIterable(source, signal)) {
        const contents: Content[] = [];
        for (const content of rawUpdate.contents) {
          if (finalTurn && (content.type === "function_call" || content.type === "function_result")) continue;
          if (content.type === "function_result") {
            const occurrenceId = content.id;
            if (
              occurrenceId === undefined ||
              completedOccurrenceIds.has(occurrenceId) ||
              occurrenceCallIds.get(occurrenceId) !== content.callId
            ) {
              continue;
            }
            completedOccurrenceIds.add(occurrenceId);
            contents.push({ ...content, id: occurrenceId });
            continue;
          }
          if (content.type !== "function_call") {
            contents.push({ ...content });
            continue;
          }
          const occurrenceId = content.id ?? occurrenceIds.get(content.callId) ?? createOccurrenceId();
          occurrenceIds.set(content.callId, occurrenceId);
          const occurrenceCallId = occurrenceCallIds.get(occurrenceId);
          if (
            seenOccurrenceIds.has(occurrenceId) ||
            (occurrenceCallId !== undefined && occurrenceCallId !== content.callId)
          ) {
            suppressedCalls = true;
            continue;
          }
          if (occurrenceCallId === undefined) {
            occurrenceCallIds.set(occurrenceId, content.callId);
          }
          contents.push({ ...content, id: occurrenceId });
        }
        const update = new ChatResponseUpdate({
          ...(rawUpdate.role === undefined ? {} : { role: rawUpdate.role }),
          contents,
          ...(rawUpdate.authorName === undefined ? {} : { authorName: rawUpdate.authorName }),
          messageId: rawUpdate.messageId ?? turnId,
          ...(rawUpdate.responseId === undefined ? {} : { responseId: rawUpdate.responseId }),
          ...(rawUpdate.finishReason === undefined ? {} : { finishReason: rawUpdate.finishReason }),
          ...(rawUpdate.usageDetails === undefined ? {} : { usageDetails: rawUpdate.usageDetails }),
          additionalProperties: rawUpdate.additionalProperties,
        });
        turnUpdates.push(update);
        yield update;
      }

      const response = ChatResponse.fromUpdates(turnUpdates);
      const extracted = callsFromResponse(response, seenOccurrenceIds);
      suppressedCalls ||= extracted.suppressedCalls;
      const { calls } = extracted;
      history.push(...response.messages.map((message) => message.clone()));
      if (!useFunctionInvocation || finalTurn || calls.length === 0) {
        if (finalTurn && response.text.trim().length === 0) {
          yield new ChatResponseUpdate({ role: "assistant", messageId: turnId, contents: FUNCTION_CALL_LIMIT_MESSAGE });
        }
        if (useFunctionInvocation && !finalTurn && suppressedCalls && response.text.trim().length === 0) {
          forceFinalTurn = true;
          continue;
        }
        return;
      }

      const remainingCalls =
        configuration.maxFunctionCalls === undefined
          ? undefined
          : Math.max(configuration.maxFunctionCalls - invocationCount, 0);
      const batch = await this.#invokeCalls(calls, tools, configuration, runtimeArguments, remainingCalls, signal);
      invocationCount += batch.attemptedCount;
      consecutiveErrors = batch.errorCount === 0 ? 0 : consecutiveErrors + 1;
      history.push(batch.message.clone());
      yield new ChatResponseUpdate({
        role: "tool",
        messageId: `af-message-${randomUUID().replaceAll("-", "")}`,
        contents: batch.message.contents,
      });

      forceFinalTurn = batch.limitReached || consecutiveErrors >= configuration.maxConsecutiveErrors;
    }
  }
}
