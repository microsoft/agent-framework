import { randomUUID } from "node:crypto";

import type { ChatOptions } from "./chat-client.js";
import type { AgentLike } from "./middleware.js";
import { Message, type ChatResponse } from "./types.js";

export type ServiceSessionId = string | Record<string, string>;

export interface AgentSessionOptions {
  sessionId?: string;
  serviceSessionId?: ServiceSessionId;
  state?: Record<string, unknown>;
}

export class AgentSession {
  public readonly sessionId: string;
  public serviceSessionId?: ServiceSessionId;
  public readonly state: Record<string, unknown>;

  public constructor(options: AgentSessionOptions = {}) {
    this.sessionId = options.sessionId ?? randomUUID();
    this.state = { ...options.state };
    if (options.serviceSessionId !== undefined) this.serviceSessionId = options.serviceSessionId;
  }
}

export interface SessionContext {
  agent: AgentLike;
  session?: AgentSession;
  inputMessages: Message[];
  messages: Message[];
  options: ChatOptions;
  signal?: AbortSignal;
  response?: ChatResponse;
}

export interface ContextProvider {
  readonly sourceId: string;
  beforeRun?(context: SessionContext): void | Promise<void>;
  afterRun?(context: SessionContext): void | Promise<void>;
}

interface StoredMessage {
  role: Message["role"];
  contents: Message["contents"];
  authorName?: string;
  messageId?: string;
  additionalProperties: Record<string, unknown>;
}

function storeMessage(message: Message): StoredMessage {
  return {
    role: message.role,
    contents: message.contents.map((content) => ({ ...content })),
    ...(message.authorName === undefined ? {} : { authorName: message.authorName }),
    ...(message.messageId === undefined ? {} : { messageId: message.messageId }),
    additionalProperties: { ...message.additionalProperties },
  };
}

function restoreMessage(message: StoredMessage): Message {
  return new Message({
    role: message.role,
    contents: message.contents,
    ...(message.authorName === undefined ? {} : { authorName: message.authorName }),
    ...(message.messageId === undefined ? {} : { messageId: message.messageId }),
    additionalProperties: message.additionalProperties,
  });
}

export abstract class HistoryProvider implements ContextProvider {
  public abstract readonly sourceId: string;

  public abstract getMessages(session: AgentSession): Promise<Message[]>;
  public abstract saveMessages(session: AgentSession, messages: readonly Message[]): Promise<void>;

  public async beforeRun(context: SessionContext): Promise<void> {
    if (context.session === undefined) return;
    const history = await this.getMessages(context.session);
    context.messages.unshift(...history.map((message) => message.clone()));
  }

  public async afterRun(context: SessionContext): Promise<void> {
    if (context.session === undefined || context.response === undefined) return;
    await this.saveMessages(context.session, [...context.inputMessages, ...context.response.messages]);
  }
}

export class InMemoryHistoryProvider extends HistoryProvider {
  public readonly sourceId: string;
  readonly #stateKey: string;

  public constructor(sourceId = "in-memory-history") {
    super();
    this.sourceId = sourceId;
    this.#stateKey = `agent-framework:${sourceId}:messages`;
  }

  public async getMessages(session: AgentSession): Promise<Message[]> {
    const stored = session.state[this.#stateKey];
    if (!Array.isArray(stored)) return [];
    return (stored as StoredMessage[]).map(restoreMessage);
  }

  public async saveMessages(session: AgentSession, messages: readonly Message[]): Promise<void> {
    const stored = session.state[this.#stateKey];
    const history = Array.isArray(stored) ? (stored as StoredMessage[]) : [];
    session.state[this.#stateKey] = [...history, ...messages.map(storeMessage)];
  }

  public async clear(session: AgentSession): Promise<void> {
    delete session.state[this.#stateKey];
  }
}
