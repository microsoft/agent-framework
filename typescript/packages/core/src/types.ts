export type Role = "system" | "developer" | "user" | "assistant" | "tool";

export type UsageDetails = Record<string, number | undefined> & {
  inputTokenCount?: number;
  outputTokenCount?: number;
  totalTokenCount?: number;
  cacheCreationInputTokenCount?: number;
  cacheReadInputTokenCount?: number;
  reasoningOutputTokenCount?: number;
};

export interface ContentBase {
  id?: string;
  additionalProperties?: Record<string, unknown>;
}

export interface TextContent extends ContentBase {
  type: "text";
  text: string;
}

export interface TextReasoningContent extends ContentBase {
  type: "text_reasoning";
  text: string;
}

export interface FunctionCallContent extends ContentBase {
  type: "function_call";
  callId: string;
  name?: string;
  arguments?: string | Record<string, unknown>;
}

export interface FunctionResultContent extends ContentBase {
  type: "function_result";
  callId: string;
  result: unknown;
  isError?: boolean;
}

export type Content = TextContent | TextReasoningContent | FunctionCallContent | FunctionResultContent;
export type ContentInput = string | Content;
export type MessageInput = string | Content | Message;

export function text(textValue: string): TextContent {
  return { type: "text", text: textValue };
}

export function functionCall(
  callId: string,
  name: string,
  argumentsValue: string | Record<string, unknown> = {},
): FunctionCallContent {
  return { type: "function_call", callId, name, arguments: argumentsValue };
}

export function functionResult(callId: string, result: unknown, isError = false): FunctionResultContent {
  return isError
    ? { type: "function_result", callId, result, isError: true }
    : { type: "function_result", callId, result };
}

function normalizeContents(contents: ContentInput | readonly ContentInput[] | undefined): Content[] {
  if (contents === undefined) {
    return [];
  }

  const values = Array.isArray(contents) ? contents : [contents];
  return values.map((item) => (typeof item === "string" ? text(item) : { ...item }));
}

export interface MessageOptions {
  role: Role;
  contents?: ContentInput | readonly ContentInput[];
  authorName?: string;
  messageId?: string;
  additionalProperties?: Record<string, unknown>;
}

export class Message {
  public role: Role;
  public contents: Content[];
  public authorName?: string;
  public messageId?: string;
  public additionalProperties: Record<string, unknown>;

  public constructor(options: MessageOptions) {
    this.role = options.role;
    this.contents = normalizeContents(options.contents);
    this.additionalProperties = { ...options.additionalProperties };
    if (options.authorName !== undefined) this.authorName = options.authorName;
    if (options.messageId !== undefined) this.messageId = options.messageId;
  }

  public get text(): string {
    return this.contents
      .filter((content): content is TextContent => content.type === "text")
      .map((content) => content.text)
      .join("");
  }

  public clone(): Message {
    return new Message({
      role: this.role,
      contents: this.contents.map((content) => ({ ...content })),
      ...(this.authorName === undefined ? {} : { authorName: this.authorName }),
      ...(this.messageId === undefined ? {} : { messageId: this.messageId }),
      additionalProperties: { ...this.additionalProperties },
    });
  }
}

export function normalizeMessages(
  messages: MessageInput | readonly MessageInput[] | undefined,
  defaultRole: Role = "user",
): Message[] {
  if (messages === undefined) return [];
  const values = Array.isArray(messages) ? messages : [messages];
  return values.map((value) => {
    if (value instanceof Message) return value.clone();
    return new Message({ role: defaultRole, contents: value as ContentInput });
  });
}

export interface ChatResponseUpdateOptions {
  role?: Role;
  contents?: ContentInput | readonly ContentInput[];
  authorName?: string;
  messageId?: string;
  responseId?: string;
  finishReason?: string;
  usageDetails?: UsageDetails;
  additionalProperties?: Record<string, unknown>;
}

export class ChatResponseUpdate {
  public role?: Role;
  public contents: Content[];
  public authorName?: string;
  public messageId?: string;
  public responseId?: string;
  public finishReason?: string;
  public usageDetails?: UsageDetails;
  public additionalProperties: Record<string, unknown>;

  public constructor(options: ChatResponseUpdateOptions = {}) {
    this.contents = normalizeContents(options.contents);
    this.additionalProperties = { ...options.additionalProperties };
    if (options.role !== undefined) this.role = options.role;
    if (options.authorName !== undefined) this.authorName = options.authorName;
    if (options.messageId !== undefined) this.messageId = options.messageId;
    if (options.responseId !== undefined) this.responseId = options.responseId;
    if (options.finishReason !== undefined) this.finishReason = options.finishReason;
    if (options.usageDetails !== undefined) this.usageDetails = { ...options.usageDetails };
  }

  public get text(): string {
    return this.contents
      .filter((content): content is TextContent => content.type === "text")
      .map((content) => content.text)
      .join("");
  }
}

export interface ChatResponseOptions {
  messages?: readonly Message[];
  responseId?: string;
  finishReason?: string;
  usageDetails?: UsageDetails;
  additionalProperties?: Record<string, unknown>;
}

function addUsage(total: UsageDetails | undefined, update: UsageDetails | undefined): UsageDetails | undefined {
  if (update === undefined) return total;
  const result: UsageDetails = { ...total };
  for (const [key, value] of Object.entries(update)) {
    if (typeof value === "number") result[key] = (result[key] ?? 0) + value;
  }
  return result;
}

function appendContent(target: Content[], incoming: Content): void {
  if (incoming.type === "function_call") {
    const existing = target.find(
      (content): content is FunctionCallContent =>
        content.type === "function_call" &&
        (incoming.id === undefined
          ? content.id === undefined && content.callId === incoming.callId
          : content.id === incoming.id),
    );
    if (existing !== undefined) {
      if (incoming.id !== undefined) existing.id ??= incoming.id;
      if (incoming.name !== undefined) existing.name = `${existing.name ?? ""}${incoming.name}`;
      if (incoming.arguments !== undefined) {
        existing.arguments =
          typeof existing.arguments === "string" && typeof incoming.arguments === "string"
            ? existing.arguments + incoming.arguments
            : incoming.arguments;
      }
      return;
    }
  }

  const previous = target.at(-1);
  if (
    (incoming.type === "text" || incoming.type === "text_reasoning") &&
    previous?.type === incoming.type &&
    previous.id === incoming.id
  ) {
    previous.text += incoming.text;
    return;
  }

  target.push({ ...incoming });
}

export class ChatResponse {
  public messages: Message[];
  public responseId?: string;
  public finishReason?: string;
  public usageDetails?: UsageDetails;
  public additionalProperties: Record<string, unknown>;

  public constructor(options: ChatResponseOptions = {}) {
    this.messages = (options.messages ?? []).map((message) => message.clone());
    this.additionalProperties = { ...options.additionalProperties };
    if (options.responseId !== undefined) this.responseId = options.responseId;
    if (options.finishReason !== undefined) this.finishReason = options.finishReason;
    if (options.usageDetails !== undefined) this.usageDetails = { ...options.usageDetails };
  }

  public get text(): string {
    return this.messages.map((message) => message.text).join("");
  }

  public static fromUpdates(updates: readonly ChatResponseUpdate[]): ChatResponse {
    const messages = new Map<string, Message>();
    let responseId: string | undefined;
    let finishReason: string | undefined;
    let usageDetails: UsageDetails | undefined;
    const additionalProperties: Record<string, unknown> = {};

    for (const update of updates) {
      const messageKey = update.messageId ?? "__default__";
      let message = messages.get(messageKey);
      if (message === undefined) {
        message = new Message({
          role: update.role ?? "assistant",
          ...(update.authorName === undefined ? {} : { authorName: update.authorName }),
          ...(update.messageId === undefined ? {} : { messageId: update.messageId }),
        });
        messages.set(messageKey, message);
      }
      if (update.role !== undefined) message.role = update.role;
      if (update.authorName !== undefined) message.authorName = update.authorName;
      for (const content of update.contents) appendContent(message.contents, content);
      if (update.responseId !== undefined) responseId = update.responseId;
      if (update.finishReason !== undefined) finishReason = update.finishReason;
      usageDetails = addUsage(usageDetails, update.usageDetails);
      Object.assign(additionalProperties, update.additionalProperties);
    }

    return new ChatResponse({
      messages: [...messages.values()],
      ...(responseId === undefined ? {} : { responseId }),
      ...(finishReason === undefined ? {} : { finishReason }),
      ...(usageDetails === undefined ? {} : { usageDetails }),
      additionalProperties,
    });
  }
}

export class AgentResponse extends ChatResponse {
  public static fromChatResponse(response: ChatResponse): AgentResponse {
    return new AgentResponse({
      messages: response.messages,
      ...(response.responseId === undefined ? {} : { responseId: response.responseId }),
      ...(response.finishReason === undefined ? {} : { finishReason: response.finishReason }),
      ...(response.usageDetails === undefined ? {} : { usageDetails: response.usageDetails }),
      additionalProperties: response.additionalProperties,
    });
  }
}

export class AgentResponseUpdate extends ChatResponseUpdate {}

export function addUsageDetails(
  first: UsageDetails | undefined,
  second: UsageDetails | undefined,
): UsageDetails | undefined {
  return addUsage(first, second);
}

export type ResponseFinalizer<TUpdate, TResponse> = (updates: readonly TUpdate[]) => TResponse | Promise<TResponse>;

export class ResponseStream<TUpdate, TResponse> implements AsyncIterable<TUpdate> {
  readonly #source: AsyncIterable<TUpdate> | Promise<AsyncIterable<TUpdate>>;
  readonly #finalizer: ResponseFinalizer<TUpdate, TResponse>;
  readonly #updates: TUpdate[] = [];
  #iterator?: AsyncIterator<TUpdate>;
  #complete = false;
  #active = false;
  #failed = false;
  #failure: unknown;
  #finalResponse?: Promise<TResponse>;

  public constructor(
    source: AsyncIterable<TUpdate> | Promise<AsyncIterable<TUpdate>>,
    finalizer: ResponseFinalizer<TUpdate, TResponse>,
  ) {
    this.#source = source;
    this.#finalizer = finalizer;
  }

  public [Symbol.asyncIterator](): AsyncIterator<TUpdate> {
    return this.#iterate();
  }

  public getFinalResponse(): Promise<TResponse> {
    if (this.#finalResponse !== undefined) return this.#finalResponse;
    if (this.#active) {
      return Promise.reject(new Error("Finish iterating the ResponseStream before finalizing it."));
    }
    this.#finalResponse = this.#finalize();
    return this.#finalResponse;
  }

  async #getIterator(): Promise<AsyncIterator<TUpdate>> {
    this.#iterator ??= (await this.#source)[Symbol.asyncIterator]();
    return this.#iterator;
  }

  async #readNext(): Promise<IteratorResult<TUpdate>> {
    if (this.#failed) throw this.#failure;
    if (this.#complete) return { done: true, value: undefined };
    try {
      const result = await (await this.#getIterator()).next();
      if (result.done) {
        this.#complete = true;
      } else {
        this.#updates.push(result.value);
      }
      return result;
    } catch (error) {
      this.#failed = true;
      this.#failure = error;
      throw error;
    }
  }

  async *#iterate(): AsyncGenerator<TUpdate> {
    if (this.#active) throw new Error("ResponseStream cannot be consumed concurrently.");
    this.#active = true;
    let index = 0;
    try {
      while (true) {
        if (index < this.#updates.length) {
          yield this.#updates[index++]!;
          continue;
        }
        const result = await this.#readNext();
        if (result.done) return;
        index += 1;
        yield result.value;
      }
    } finally {
      this.#active = false;
    }
  }

  async #finalize(): Promise<TResponse> {
    if (this.#active) throw new Error("Finish iterating the ResponseStream before finalizing it.");
    this.#active = true;
    try {
      while (!(await this.#readNext()).done) {
        // Updates are retained for finalization.
      }
      return await this.#finalizer(this.#updates);
    } finally {
      this.#active = false;
    }
  }
}
