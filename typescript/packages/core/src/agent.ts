import { randomUUID } from "node:crypto";

import { abortableAsyncIterable } from "./cancellation.js";
import type { ChatOptions, ChatRequestOptions, SupportsChatGetResponse } from "./chat-client.js";
import { AgentInvalidResponseError } from "./errors.js";
import { runMiddleware, type AgentContext, type AgentMiddleware } from "./middleware.js";
import {
  AgentSession,
  HistoryProvider,
  InMemoryHistoryProvider,
  type ContextProvider,
  type ServiceSessionId,
  type SessionContext,
} from "./sessions.js";
import { normalizeTools, type FunctionTool } from "./tools.js";
import { AgentResponse, AgentResponseUpdate, ResponseStream, normalizeMessages, type MessageInput } from "./types.js";

export interface AgentOptions<TOptions extends ChatOptions = ChatOptions> {
  client: SupportsChatGetResponse<TOptions>;
  id?: string;
  name?: string;
  description?: string;
  instructions?: string;
  tools?: readonly FunctionTool[];
  options?: TOptions;
  middleware?: readonly AgentMiddleware[];
  contextProviders?: readonly ContextProvider[];
  additionalProperties?: Record<string, unknown>;
}

export type AgentRunOptions<TOptions extends ChatOptions = ChatOptions> = Omit<
  ChatRequestOptions<TOptions>,
  "stream" | "options"
> & {
  stream?: boolean;
  session?: AgentSession;
  options?: TOptions;
};

export interface SupportsAgentRun<TOptions extends ChatOptions = ChatOptions> {
  readonly id: string;
  readonly name?: string;
  readonly description?: string;
  run(
    messages?: MessageInput | readonly MessageInput[],
    options?: AgentRunOptions<TOptions> & { stream?: false },
  ): Promise<AgentResponse>;
  run(
    messages: MessageInput | readonly MessageInput[] | undefined,
    options: AgentRunOptions<TOptions> & { stream: true },
  ): ResponseStream<AgentResponseUpdate, AgentResponse>;
  createSession(sessionId?: string): AgentSession;
}

function mergeOptions<TOptions extends ChatOptions>(base: TOptions, override: TOptions | undefined): TOptions {
  const result = { ...base, ...override } as ChatOptions;
  if (base.instructions !== undefined && override?.instructions !== undefined) {
    result.instructions = `${base.instructions}\n${override.instructions}`;
  }
  if (base.tools !== undefined || override?.tools !== undefined) {
    result.tools = normalizeTools([...(base.tools ?? []), ...(override?.tools ?? [])]);
  }
  const baseMetadata = base.metadata;
  const overrideMetadata = override?.metadata;
  if (
    baseMetadata !== null &&
    typeof baseMetadata === "object" &&
    overrideMetadata !== null &&
    typeof overrideMetadata === "object"
  ) {
    result.metadata = { ...baseMetadata, ...overrideMetadata };
  }
  return result as TOptions;
}

function responseUpdate(update: AgentResponseUpdate): AgentResponseUpdate {
  return new AgentResponseUpdate({
    ...(update.role === undefined ? {} : { role: update.role }),
    contents: update.contents,
    ...(update.authorName === undefined ? {} : { authorName: update.authorName }),
    ...(update.messageId === undefined ? {} : { messageId: update.messageId }),
    ...(update.responseId === undefined ? {} : { responseId: update.responseId }),
    ...(update.finishReason === undefined ? {} : { finishReason: update.finishReason }),
    ...(update.usageDetails === undefined ? {} : { usageDetails: update.usageDetails }),
    additionalProperties: update.additionalProperties,
  });
}

export class Agent<TOptions extends ChatOptions = ChatOptions> implements SupportsAgentRun<TOptions> {
  public readonly id: string;
  public readonly name?: string;
  public readonly description?: string;
  public readonly client: SupportsChatGetResponse<TOptions>;
  public readonly contextProviders: readonly ContextProvider[];
  public readonly additionalProperties: Record<string, unknown>;

  readonly #baseOptions: TOptions;
  readonly #middleware: readonly AgentMiddleware[];
  readonly #defaultHistory = new InMemoryHistoryProvider();

  public constructor(options: AgentOptions<TOptions>) {
    this.id = options.id ?? randomUUID();
    this.client = options.client;
    this.contextProviders = [...(options.contextProviders ?? [])];
    this.additionalProperties = { ...options.additionalProperties };
    this.#middleware = [...(options.middleware ?? [])];
    this.#baseOptions = {
      ...(options.options ?? ({} as TOptions)),
      ...(options.instructions === undefined ? {} : { instructions: options.instructions }),
      ...(options.tools === undefined ? {} : { tools: normalizeTools(options.tools) }),
    } as TOptions;
    if (options.name !== undefined) this.name = options.name;
    if (options.description !== undefined) this.description = options.description;
  }

  public createSession(sessionId?: string): AgentSession {
    return new AgentSession(sessionId === undefined ? {} : { sessionId });
  }

  public getSession(serviceSessionId: ServiceSessionId, sessionId?: string): AgentSession {
    return new AgentSession({
      serviceSessionId,
      ...(sessionId === undefined ? {} : { sessionId }),
    });
  }

  public run(
    messages?: MessageInput | readonly MessageInput[],
    options?: AgentRunOptions<TOptions> & { stream?: false },
  ): Promise<AgentResponse>;
  public run(
    messages: MessageInput | readonly MessageInput[] | undefined,
    options: AgentRunOptions<TOptions> & { stream: true },
  ): ResponseStream<AgentResponseUpdate, AgentResponse>;
  public run(
    messages?: MessageInput | readonly MessageInput[],
    options: AgentRunOptions<TOptions> = {},
  ): Promise<AgentResponse> | ResponseStream<AgentResponseUpdate, AgentResponse> {
    const inputMessages = normalizeMessages(messages);
    const chatOptions = mergeOptions(this.#baseOptions, options.options);
    if (options.stream === true) return this.#stream(inputMessages, chatOptions, options);
    return this.#run(inputMessages, chatOptions, options);
  }

  #providers(session: AgentSession | undefined): readonly ContextProvider[] {
    if (session === undefined || this.contextProviders.some((provider) => provider instanceof HistoryProvider)) {
      return this.contextProviders;
    }
    return [this.#defaultHistory, ...this.contextProviders];
  }

  #sessionContext(
    context: AgentContext,
    inputMessages: readonly ReturnType<typeof normalizeMessages>[number][],
  ): SessionContext {
    return {
      agent: this,
      ...(context.session === undefined ? {} : { session: context.session as AgentSession }),
      inputMessages: inputMessages.map((message) => message.clone()),
      messages: context.messages,
      options: context.options as TOptions,
      ...(context.signal === undefined ? {} : { signal: context.signal }),
    };
  }

  async #run(
    inputMessages: ReturnType<typeof normalizeMessages>,
    options: TOptions,
    request: AgentRunOptions<TOptions>,
  ): Promise<AgentResponse> {
    request.signal?.throwIfAborted();
    const context: AgentContext = {
      agent: this,
      messages: inputMessages.map((message) => message.clone()),
      options,
      stream: false,
      ...(request.signal === undefined ? {} : { signal: request.signal }),
      ...(request.session === undefined ? {} : { session: request.session }),
    };
    await runMiddleware(context, this.#middleware, async () => {
      context.signal?.throwIfAborted();
      const sessionContext = this.#sessionContext(context, inputMessages);
      const providers = this.#providers(sessionContext.session);
      for (const provider of providers) {
        sessionContext.signal?.throwIfAborted();
        await provider.beforeRun?.(sessionContext);
        sessionContext.signal?.throwIfAborted();
      }
      const response = await this.client.getResponse(sessionContext.messages, {
        options: sessionContext.options as TOptions,
        ...(request.functionInvocation === undefined ? {} : { functionInvocation: request.functionInvocation }),
        ...(request.functionInvocationArguments === undefined
          ? {}
          : { functionInvocationArguments: request.functionInvocationArguments }),
        ...(sessionContext.signal === undefined ? {} : { signal: sessionContext.signal }),
      });
      sessionContext.signal?.throwIfAborted();
      const agentResponse = AgentResponse.fromChatResponse(response);
      sessionContext.response = agentResponse;
      for (const provider of [...providers].reverse()) {
        sessionContext.signal?.throwIfAborted();
        await provider.afterRun?.(sessionContext);
        sessionContext.signal?.throwIfAborted();
      }
      context.result = agentResponse;
    });
    if (!(context.result instanceof AgentResponse)) {
      throw new AgentInvalidResponseError("Agent middleware completed without a non-streaming response.");
    }
    return context.result;
  }

  #stream(
    inputMessages: ReturnType<typeof normalizeMessages>,
    options: TOptions,
    request: AgentRunOptions<TOptions>,
  ): ResponseStream<AgentResponseUpdate, AgentResponse> {
    let finalResponse: AgentResponse | undefined;
    const source = async function* (agent: Agent<TOptions>): AsyncGenerator<AgentResponseUpdate> {
      request.signal?.throwIfAborted();
      const context: AgentContext = {
        agent,
        messages: inputMessages.map((message) => message.clone()),
        options,
        stream: true,
        ...(request.signal === undefined ? {} : { signal: request.signal }),
        ...(request.session === undefined ? {} : { session: request.session }),
      };
      await runMiddleware(context, agent.#middleware, async () => {
        context.signal?.throwIfAborted();
        const sessionContext = agent.#sessionContext(context, inputMessages);
        const providers = agent.#providers(sessionContext.session);
        for (const provider of providers) {
          sessionContext.signal?.throwIfAborted();
          await provider.beforeRun?.(sessionContext);
          sessionContext.signal?.throwIfAborted();
        }
        const chatStream = agent.client.getResponse(sessionContext.messages, {
          stream: true,
          options: sessionContext.options as TOptions,
          ...(request.functionInvocation === undefined ? {} : { functionInvocation: request.functionInvocation }),
          ...(request.functionInvocationArguments === undefined
            ? {}
            : { functionInvocationArguments: request.functionInvocationArguments }),
          ...(sessionContext.signal === undefined ? {} : { signal: sessionContext.signal }),
        });
        let mappedFinal: AgentResponse | undefined;
        const mappedSource = async function* (): AsyncGenerator<AgentResponseUpdate> {
          for await (const update of abortableAsyncIterable(chatStream, sessionContext.signal)) {
            yield responseUpdate(update);
          }
          sessionContext.signal?.throwIfAborted();
          mappedFinal = AgentResponse.fromChatResponse(await chatStream.getFinalResponse());
          sessionContext.response = mappedFinal;
          for (const provider of [...providers].reverse()) {
            sessionContext.signal?.throwIfAborted();
            await provider.afterRun?.(sessionContext);
            sessionContext.signal?.throwIfAborted();
          }
        };
        context.result = new ResponseStream(mappedSource(), () => {
          if (mappedFinal === undefined) throw new AgentInvalidResponseError("Agent stream did not complete.");
          return mappedFinal;
        });
      });
      if (!(context.result instanceof ResponseStream)) {
        throw new AgentInvalidResponseError("Agent middleware completed without a streaming response.");
      }
      for await (const update of abortableAsyncIterable(context.result, context.signal)) yield update;
      context.signal?.throwIfAborted();
      finalResponse = await context.result.getFinalResponse();
    };

    return new ResponseStream(source(this), () => {
      if (finalResponse === undefined) throw new AgentInvalidResponseError("Agent stream did not complete.");
      return finalResponse;
    });
  }
}
