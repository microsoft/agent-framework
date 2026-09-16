import { describe, expect, it } from "vitest";

import {
  Agent,
  BaseChatClient,
  ChatResponse,
  ChatResponseUpdate,
  Message,
  ResponseStream,
  type ChatClientRequest,
  type SupportsChatGetResponse,
} from "../src/index.js";

class EchoClient extends BaseChatClient {
  public readonly requests: ChatClientRequest[] = [];
  public responseNumber = 0;

  protected override async getResponseCore(
    request: ChatClientRequest,
  ): Promise<ChatResponse | AsyncIterable<ChatResponseUpdate>> {
    this.requests.push(request);
    this.responseNumber += 1;
    if (request.stream) {
      const value = this.responseNumber;
      return (async function* () {
        yield new ChatResponseUpdate({ role: "assistant", contents: `response ${value}` });
      })();
    }
    return new ChatResponse({
      messages: [new Message({ role: "assistant", contents: `response ${this.responseNumber}` })],
    });
  }
}

describe("Agent", () => {
  it("applies instructions and preserves in-memory history for a session", async () => {
    const client = new EchoClient();
    const agent = new Agent({ client, name: "assistant", instructions: "Be concise." });
    const session = agent.createSession("session-1");

    await agent.run("first", { session });
    const response = await agent.run("second", { session });

    expect(response.text).toBe("response 2");
    expect(client.requests[0]?.options.instructions).toBe("Be concise.");
    expect(client.requests[1]?.messages.map((message) => `${message.role}:${message.text}`)).toEqual([
      "user:first",
      "assistant:response 1",
      "user:second",
    ]);
  });

  it("keeps separate session histories isolated", async () => {
    const client = new EchoClient();
    const agent = new Agent({ client });
    const first = agent.createSession("first");
    const second = agent.createSession("second");

    await agent.run("one", { session: first });
    await agent.run("two", { session: second });

    expect(client.requests[1]?.messages.map((message) => message.text)).toEqual(["two"]);
  });

  it("persists a streamed response after the stream completes", async () => {
    const client = new EchoClient();
    const agent = new Agent({ client });
    const session = agent.createSession("stream");
    const stream = agent.run("first", { stream: true, session });

    const updates = [];
    for await (const update of stream) updates.push(update);
    const response = await stream.getFinalResponse();
    await agent.run("second", { session });

    expect(updates[0]?.text).toBe("response 1");
    expect(response.text).toBe("response 1");
    expect(client.requests[1]?.messages.map((message) => `${message.role}:${message.text}`)).toEqual([
      "user:first",
      "assistant:response 1",
      "user:second",
    ]);
  });

  it("runs agent middleware in onion order", async () => {
    const events: string[] = [];
    const client = new EchoClient();
    const agent = new Agent({
      client,
      middleware: [
        async (_context, next) => {
          events.push("first:before");
          await next();
          events.push("first:after");
        },
        async (_context, next) => {
          events.push("second:before");
          await next();
          events.push("second:after");
        },
      ],
    });

    await agent.run("hello");

    expect(events).toEqual(["first:before", "second:before", "second:after", "first:after"]);
  });

  it("propagates cancellation through context providers", async () => {
    const client = new EchoClient();
    const controller = new AbortController();
    let started: (() => void) | undefined;
    const providerStarted = new Promise<void>((resolve) => {
      started = resolve;
    });
    let providerSignal: AbortSignal | undefined;
    const agent = new Agent({
      client,
      contextProviders: [
        {
          sourceId: "blocking",
          beforeRun: async (context) => {
            providerSignal = (context as typeof context & { signal?: AbortSignal }).signal;
            started?.();
            if (providerSignal === undefined) throw new Error("Context provider did not receive a signal.");
            await new Promise((_resolve, reject) => {
              providerSignal?.addEventListener("abort", () => reject(providerSignal?.reason), { once: true });
            });
          },
        },
      ],
    });

    const run = agent.run("hello", { signal: controller.signal });
    await providerStarted;
    controller.abort(new Error("cancelled"));

    await expect(run).rejects.toThrow("cancelled");
    expect(providerSignal?.aborted).toBe(true);
  });

  it("uses a session supplied by agent middleware for default history", async () => {
    const client = new EchoClient();
    const session = new Agent({ client }).createSession("middleware-session");
    const agent = new Agent({
      client,
      middleware: [
        async (context, next) => {
          context.session = session;
          await next();
        },
      ],
    });

    await agent.run("first");
    await agent.run("second");

    expect(client.requests[1]?.messages.map((message) => `${message.role}:${message.text}`)).toEqual([
      "user:first",
      "assistant:response 1",
      "user:second",
    ]);
  });

  it("enforces streaming cancellation for a custom client that ignores the signal", async () => {
    let releaseSecondUpdate: (() => void) | undefined;
    const client = {
      additionalProperties: {},
      getResponse: (_messages: unknown, request: { stream?: boolean } = {}) => {
        if (request.stream !== true) {
          return Promise.resolve(
            new ChatResponse({ messages: [new Message({ role: "assistant", contents: "done" })] }),
          );
        }
        const secondUpdate = new Promise<void>((resolve) => {
          releaseSecondUpdate = resolve;
        });
        return new ResponseStream(
          (async function* () {
            yield new ChatResponseUpdate({ role: "assistant", contents: "first" });
            await secondUpdate;
            yield new ChatResponseUpdate({ role: "assistant", contents: "second" });
          })(),
          ChatResponse.fromUpdates,
        );
      },
    } as unknown as SupportsChatGetResponse;
    const agent = new Agent({ client });
    const controller = new AbortController();
    const stream = agent.run("hello", { stream: true, signal: controller.signal });
    const iterator = stream[Symbol.asyncIterator]();

    await expect(iterator.next()).resolves.toMatchObject({ value: { text: "first" } });
    controller.abort(new Error("cancelled"));

    await expect(iterator.next()).rejects.toThrow("cancelled");
    await expect(stream.getFinalResponse()).rejects.toThrow("cancelled");
    releaseSecondUpdate?.();
  });

  it("enforces non-streaming cancellation after a custom client completes", async () => {
    let complete: ((response: ChatResponse) => void) | undefined;
    const clientResponse = new Promise<ChatResponse>((resolve) => {
      complete = resolve;
    });
    const client = {
      additionalProperties: {},
      getResponse: () => clientResponse,
    } as unknown as SupportsChatGetResponse;
    const agent = new Agent({ client });
    const controller = new AbortController();

    const run = agent.run("hello", { signal: controller.signal });
    controller.abort(new Error("cancelled"));
    complete?.(new ChatResponse({ messages: [new Message({ role: "assistant", contents: "too late" })] }));

    await expect(run).rejects.toThrow("cancelled");
  });
});
