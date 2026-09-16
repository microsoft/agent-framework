import type {
  AgentResponse,
  AgentResponseUpdate,
  ChatResponse,
  ChatResponseUpdate,
  FunctionCallContent,
  Message,
  ResponseStream,
} from "./types.js";

export type MiddlewareNext = () => Promise<void>;

export interface AgentLike {
  id: string;
  name?: string;
}

export interface AgentSessionLike {
  sessionId: string;
  state: Record<string, unknown>;
}

export interface FunctionToolLike {
  name: string;
  description: string;
}

export interface AgentContext {
  agent: AgentLike;
  messages: Message[];
  options: Record<string, unknown>;
  stream: boolean;
  signal?: AbortSignal;
  session?: AgentSessionLike;
  result?: AgentResponse | ResponseStream<AgentResponseUpdate, AgentResponse>;
}

export interface ChatContext {
  messages: Message[];
  options: Record<string, unknown>;
  stream: boolean;
  signal?: AbortSignal;
  result?: ChatResponse | AsyncIterable<ChatResponseUpdate>;
}

export interface FunctionInvocationContext {
  tool: FunctionToolLike;
  call: FunctionCallContent;
  arguments: Record<string, unknown>;
  runtimeArguments: Readonly<Record<string, unknown>>;
  signal: AbortSignal;
  result?: unknown;
}

export type AgentMiddleware = (context: AgentContext, next: MiddlewareNext) => Promise<void>;
export type ChatMiddleware = (context: ChatContext, next: MiddlewareNext) => Promise<void>;
export type FunctionMiddleware = (context: FunctionInvocationContext, next: MiddlewareNext) => Promise<void>;

export async function runMiddleware<TContext>(
  context: TContext,
  middleware: readonly ((context: TContext, next: MiddlewareNext) => Promise<void>)[],
  terminal: () => Promise<void>,
): Promise<void> {
  let currentIndex = -1;

  async function dispatch(index: number): Promise<void> {
    if (index <= currentIndex) throw new Error("Middleware next() can only be called once.");
    currentIndex = index;
    const current = middleware[index];
    if (current === undefined) {
      await terminal();
      return;
    }
    await current(context, () => dispatch(index + 1));
  }

  await dispatch(0);
}
