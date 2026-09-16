import {
  AgentInvalidRequestError,
  AgentInvalidResponseError,
  BaseChatClient,
  ChatResponse,
  ChatResponseUpdate,
  Message,
  type BaseChatClientOptions,
  type ChatClientRequest,
  type ChatOptions,
  type Content,
  type FunctionCallContent,
  type FunctionResultContent,
  type UsageDetails,
} from "@microsoft/agent-framework-core";
import OpenAI, { type ClientOptions } from "openai";
import type {
  ChatCompletion,
  ChatCompletionChunk,
  ChatCompletionCreateParamsBase,
  ChatCompletionCreateParamsNonStreaming,
  ChatCompletionCreateParamsStreaming,
  ChatCompletionFunctionTool,
  ChatCompletionMessageParam,
  ChatCompletionToolChoiceOption,
} from "openai/resources/chat/completions/completions.js";
import type { CompletionUsage } from "openai/resources/completions.js";

export interface OpenAIChatCompletionOptions extends ChatOptions {
  model?: string;
  temperature?: number;
  maxCompletionTokens?: number;
  maxTokens?: number;
  topP?: number;
  stop?: string | readonly string[];
  seed?: number;
  user?: string;
  frequencyPenalty?: number;
  presencePenalty?: number;
  parallelToolCalls?: boolean;
  store?: boolean;
  metadata?: Record<string, string>;
}

export interface OpenAIChatCompletionClientOptions extends BaseChatClientOptions {
  client?: OpenAI;
  clientOptions?: ClientOptions;
  model?: string;
}

interface PendingToolCall {
  id?: string;
  occurrenceId: string;
  name: string;
  argumentsValue: string;
}

function stringifyResult(result: unknown): string {
  if (typeof result === "string") return result;
  if (result === undefined) return "null";
  try {
    const serialized = JSON.stringify(result);
    if (serialized === undefined) {
      throw new TypeError("The value has no JSON representation.");
    }
    return serialized;
  } catch (error) {
    throw new AgentInvalidRequestError("A tool result could not be serialized as JSON.", { cause: error });
  }
}

function serializeCall(call: FunctionCallContent) {
  if (call.name === undefined || call.name.length === 0) {
    throw new AgentInvalidRequestError(`Function call '${call.callId}' does not have a name.`);
  }
  return {
    id: call.callId,
    type: "function" as const,
    function: {
      name: call.name,
      arguments: typeof call.arguments === "string" ? call.arguments : JSON.stringify(call.arguments ?? {}),
    },
  };
}

function serializeMessage(message: Message): ChatCompletionMessageParam[] {
  if (message.contents.some((content) => content.type === "text_reasoning")) {
    throw new AgentInvalidRequestError("This OpenAI Chat Completions adapter does not support text_reasoning input.");
  }

  const calls = message.contents.filter((content): content is FunctionCallContent => content.type === "function_call");
  const results = message.contents.filter(
    (content): content is FunctionResultContent => content.type === "function_result",
  );

  if (message.role === "tool") {
    if (results.length === 0) {
      throw new AgentInvalidRequestError("OpenAI tool messages must contain a function result.");
    }
    return results.map((result) => ({
      role: "tool",
      tool_call_id: result.callId,
      content: stringifyResult(result.result),
    }));
  }

  if (results.length > 0) {
    throw new AgentInvalidRequestError("Function results must use the tool role for OpenAI Chat Completions.");
  }

  if (message.role === "assistant") {
    return [
      {
        role: "assistant",
        content: message.text.length === 0 ? null : message.text,
        ...(message.authorName === undefined ? {} : { name: message.authorName }),
        ...(calls.length === 0 ? {} : { tool_calls: calls.map(serializeCall) }),
      },
    ];
  }

  if (calls.length > 0) {
    throw new AgentInvalidRequestError("Function calls must use the assistant role for OpenAI Chat Completions.");
  }
  return [
    {
      role: message.role,
      content: message.text,
      ...(message.authorName === undefined ? {} : { name: message.authorName }),
    } as ChatCompletionMessageParam,
  ];
}

function serializeMessages(
  messages: readonly Message[],
  instructions: string | undefined,
): ChatCompletionMessageParam[] {
  return [
    ...(instructions === undefined ? [] : [{ role: "developer" as const, content: instructions }]),
    ...messages.flatMap(serializeMessage),
  ];
}

function usageDetails(usage: CompletionUsage | null | undefined): UsageDetails | undefined {
  if (usage === null || usage === undefined) return undefined;
  const reasoningTokens = usage.completion_tokens_details?.reasoning_tokens;
  const cacheReadTokens = usage.prompt_tokens_details?.cached_tokens;
  return {
    inputTokenCount: usage.prompt_tokens,
    outputTokenCount: usage.completion_tokens,
    totalTokenCount: usage.total_tokens,
    ...(reasoningTokens === undefined ? {} : { reasoningOutputTokenCount: reasoningTokens }),
    ...(cacheReadTokens === undefined ? {} : { cacheReadInputTokenCount: cacheReadTokens }),
  };
}

function toolChoice(value: OpenAIChatCompletionOptions["toolChoice"]): ChatCompletionToolChoiceOption | undefined {
  if (value === undefined) return undefined;
  if (value === "auto" || value === "none" || value === "required") return value;
  return { type: "function", function: { name: value } };
}

function commonRequest(
  messages: readonly Message[],
  options: OpenAIChatCompletionOptions,
  defaultModel: string | undefined,
): Omit<ChatCompletionCreateParamsBase, "stream"> {
  const model = options.model ?? defaultModel;
  if (model === undefined || model.length === 0) {
    throw new AgentInvalidRequestError(
      "An OpenAI model is required. Set model or the OPENAI_CHAT_MODEL environment variable.",
    );
  }
  const choice = toolChoice(options.toolChoice);
  const tools = options.tools?.map((tool) => tool.definition as ChatCompletionFunctionTool);
  return {
    model,
    messages: serializeMessages(messages, options.instructions),
    ...(options.temperature === undefined ? {} : { temperature: options.temperature }),
    ...(options.maxCompletionTokens === undefined ? {} : { max_completion_tokens: options.maxCompletionTokens }),
    ...(options.maxTokens === undefined ? {} : { max_tokens: options.maxTokens }),
    ...(options.topP === undefined ? {} : { top_p: options.topP }),
    ...(options.stop === undefined
      ? {}
      : { stop: [...(typeof options.stop === "string" ? [options.stop] : options.stop)] }),
    ...(options.seed === undefined ? {} : { seed: options.seed }),
    ...(options.user === undefined ? {} : { user: options.user }),
    ...(options.frequencyPenalty === undefined ? {} : { frequency_penalty: options.frequencyPenalty }),
    ...(options.presencePenalty === undefined ? {} : { presence_penalty: options.presencePenalty }),
    ...(options.parallelToolCalls === undefined ? {} : { parallel_tool_calls: options.parallelToolCalls }),
    ...(options.store === undefined ? {} : { store: options.store }),
    ...(options.metadata === undefined ? {} : { metadata: options.metadata }),
    ...(choice === undefined ? {} : { tool_choice: choice }),
    ...(tools === undefined || tools.length === 0 ? {} : { tools }),
  };
}

function responseContents(completion: ChatCompletion): Content[] {
  const choice = completion.choices[0];
  if (choice === undefined) throw new AgentInvalidResponseError("OpenAI returned no completion choices.");
  const contents: Content[] = [];
  if (choice.message.content !== null && choice.message.content.length > 0) {
    contents.push({ type: "text", text: choice.message.content });
  }
  if (choice.message.refusal !== null && choice.message.refusal.length > 0) {
    contents.push({
      type: "text",
      text: choice.message.refusal,
      additionalProperties: { modelOutputKind: "refusal" },
    });
  }
  for (const [toolIndex, call] of (choice.message.tool_calls ?? []).entries()) {
    if (call.type !== "function") {
      throw new AgentInvalidResponseError(`Unsupported OpenAI tool call type '${call.type}'.`);
    }
    contents.push({
      type: "function_call",
      id: `openai:${completion.id}:choice:${choice.index}:tool:${toolIndex}`,
      callId: call.id,
      name: call.function.name,
      arguments: call.function.arguments,
    });
  }
  return contents;
}

function mapResponse(completion: ChatCompletion): ChatResponse {
  const choice = completion.choices[0];
  if (choice === undefined) throw new AgentInvalidResponseError("OpenAI returned no completion choices.");
  const mappedUsage = usageDetails(completion.usage);
  return new ChatResponse({
    messages: [new Message({ role: "assistant", contents: responseContents(completion) })],
    responseId: completion.id,
    ...(choice.finish_reason === null ? {} : { finishReason: choice.finish_reason }),
    ...(mappedUsage === undefined ? {} : { usageDetails: mappedUsage }),
    additionalProperties: { model: completion.model, createdAt: completion.created },
  });
}

export class OpenAIChatCompletionClient extends BaseChatClient<OpenAIChatCompletionOptions> {
  public readonly openAI: OpenAI;
  public readonly model: string | undefined;

  public constructor(options: OpenAIChatCompletionClientOptions = {}) {
    const { client, clientOptions, model, ...baseOptions } = options;
    super(baseOptions);
    if (client !== undefined && clientOptions !== undefined) {
      throw new TypeError("Pass either client or clientOptions, not both.");
    }
    this.openAI = client ?? new OpenAI(clientOptions);
    this.model = model ?? process.env.OPENAI_CHAT_MODEL ?? process.env.OPENAI_MODEL;
  }

  protected override async getResponseCore(
    request: ChatClientRequest<OpenAIChatCompletionOptions>,
  ): Promise<ChatResponse | AsyncIterable<ChatResponseUpdate>> {
    const common = commonRequest(request.messages, request.options, this.model);
    const requestOptions = request.signal === undefined ? undefined : { signal: request.signal };
    if (request.stream) {
      const body: ChatCompletionCreateParamsStreaming = {
        ...common,
        stream: true,
        stream_options: { include_usage: true },
      };
      const stream = await this.openAI.chat.completions.create(body, requestOptions);
      return this.#mapStream(stream);
    }

    const body: ChatCompletionCreateParamsNonStreaming = { ...common, stream: false };
    return mapResponse(await this.openAI.chat.completions.create(body, requestOptions));
  }

  async *#mapStream(chunks: AsyncIterable<ChatCompletionChunk>): AsyncGenerator<ChatResponseUpdate> {
    const pendingCalls = new Map<number, PendingToolCall>();
    let hasChoice = false;
    for await (const chunk of chunks) {
      const choice = chunk.choices[0];
      hasChoice ||= choice !== undefined;
      const contents: Content[] = [];
      if (choice?.delta.content !== undefined && choice.delta.content !== null) {
        contents.push({ type: "text", text: choice.delta.content });
      }
      if (choice?.delta.refusal !== undefined && choice.delta.refusal !== null) {
        contents.push({
          type: "text",
          text: choice.delta.refusal,
          additionalProperties: { modelOutputKind: "refusal" },
        });
      }
      for (const delta of choice?.delta.tool_calls ?? []) {
        if (delta.type !== undefined && delta.type !== "function") {
          throw new AgentInvalidResponseError(`Unsupported OpenAI streaming tool call type '${delta.type}'.`);
        }
        const pending = pendingCalls.get(delta.index) ?? {
          occurrenceId: `openai:${chunk.id}:choice:${choice?.index ?? 0}:tool:${delta.index}`,
          name: "",
          argumentsValue: "",
        };
        if (delta.id !== undefined) pending.id = delta.id;
        if (delta.function?.name !== undefined) pending.name += delta.function.name;
        if (delta.function?.arguments !== undefined) pending.argumentsValue += delta.function.arguments;
        pendingCalls.set(delta.index, pending);
        if (pending.id !== undefined) {
          contents.push({
            type: "function_call",
            id: pending.occurrenceId,
            callId: pending.id,
            ...(pending.name.length === 0 ? {} : { name: pending.name }),
            ...(pending.argumentsValue.length === 0 ? {} : { arguments: pending.argumentsValue }),
          });
          pending.name = "";
          pending.argumentsValue = "";
        }
      }

      const mappedUsage = usageDetails(chunk.usage);
      if (contents.length > 0 || mappedUsage !== undefined || choice?.finish_reason !== null) {
        yield new ChatResponseUpdate({
          role: "assistant",
          contents,
          messageId: chunk.id,
          responseId: chunk.id,
          ...(choice?.finish_reason === undefined || choice.finish_reason === null
            ? {}
            : { finishReason: choice.finish_reason }),
          ...(mappedUsage === undefined ? {} : { usageDetails: mappedUsage }),
          additionalProperties: { model: chunk.model, createdAt: chunk.created },
        });
      }
    }

    if (!hasChoice) {
      throw new AgentInvalidResponseError("OpenAI returned no completion choices.");
    }

    const unresolved = [...pendingCalls.values()].find((pending) => pending.id === undefined);
    if (unresolved !== undefined) {
      throw new AgentInvalidResponseError("OpenAI streamed a tool call without an id.");
    }
  }
}
