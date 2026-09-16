import { describe, expect, it } from "vitest";

import {
  BaseChatClient,
  ChatResponse,
  ChatResponseUpdate,
  Message,
  MiddlewareFailure,
  defineTool,
  functionCall,
  functionResult,
  type BaseChatClientOptions,
  type ChatClientRequest,
} from "../src/index.js";

class TestChatClient extends BaseChatClient {
  public readonly requests: ChatClientRequest[] = [];
  public readonly responses: ChatResponse[] = [];
  public readonly streamingResponses: ChatResponseUpdate[][] = [];

  public constructor(options: BaseChatClientOptions = {}) {
    super(options);
  }

  protected override async getResponseCore(
    request: ChatClientRequest,
  ): Promise<ChatResponse | AsyncIterable<ChatResponseUpdate>> {
    this.requests.push(request);
    if (request.stream) {
      const updates = this.streamingResponses.shift() ?? [];
      return (async function* () {
        for (const update of updates) yield update;
      })();
    }
    const response = this.responses.shift();
    if (response === undefined) throw new Error("No response configured.");
    return response;
  }
}

const parameters = {
  type: "object",
  properties: { value: { type: "string" } },
  required: ["value"],
  additionalProperties: false,
};

describe("BaseChatClient function invocation", () => {
  it("executes a function call and returns the complete ordered transcript", async () => {
    const client = new TestChatClient();
    let executions = 0;
    const tool = defineTool({
      name: "process",
      parameters,
      execute: ({ value }) => {
        executions += 1;
        return `Processed ${String(value)}`;
      },
    });
    client.responses.push(
      new ChatResponse({
        messages: [new Message({ role: "assistant", contents: functionCall("call-1", "process", '{"value":"one"}') })],
      }),
      new ChatResponse({ messages: [new Message({ role: "assistant", contents: "done" })] }),
    );

    const response = await client.getResponse("hello", { options: { tools: [tool], toolChoice: "auto" } });

    expect(executions).toBe(1);
    expect(response.messages.map((message) => message.role)).toEqual(["assistant", "tool", "assistant"]);
    expect(response.messages[1]?.contents[0]).toMatchObject({
      type: "function_result",
      callId: "call-1",
      result: "Processed one",
    });
    expect(response.messages[2]?.text).toBe("done");
    expect(client.requests[1]?.messages.at(-1)?.role).toBe("tool");
  });

  it("streams call chunks, the tool result, and final text", async () => {
    const client = new TestChatClient();
    const tool = defineTool({
      name: "process",
      parameters,
      execute: ({ value }) => `Processed ${String(value)}`,
    });
    client.streamingResponses.push(
      [
        new ChatResponseUpdate({
          role: "assistant",
          contents: { type: "function_call", callId: "call-1", name: "pro", arguments: '{"value":' },
        }),
        new ChatResponseUpdate({
          role: "assistant",
          contents: { type: "function_call", callId: "call-1", name: "cess", arguments: '"one"}' },
        }),
      ],
      [new ChatResponseUpdate({ role: "assistant", contents: "done" })],
    );

    const stream = client.getResponse("hello", {
      stream: true,
      options: { tools: [tool], toolChoice: "auto" },
    });
    const updates = [];
    for await (const update of stream) updates.push(update);
    const response = await stream.getFinalResponse();

    expect(updates).toHaveLength(4);
    expect(updates[0]?.contents[0]?.id).toBe(updates[1]?.contents[0]?.id);
    expect(updates[2]?.contents[0]).toMatchObject({ type: "function_result", result: "Processed one" });
    expect(updates[3]?.text).toBe("done");
    expect(response.messages.map((message) => message.role)).toEqual(["assistant", "tool", "assistant"]);
  });

  it("omits suppressed replay turns from streaming responses and follow-up history", async () => {
    const client = new TestChatClient();
    let executions = 0;
    const tool = defineTool({
      name: "process",
      parameters,
      execute: ({ value }) => {
        executions += 1;
        return value;
      },
    });
    const call = { ...functionCall("call-1", "process", { value: "one" }), id: "stable-occurrence" };
    client.streamingResponses.push(
      [new ChatResponseUpdate({ role: "assistant", messageId: "original-turn", contents: call })],
      [
        new ChatResponseUpdate({ role: "assistant", messageId: "replayed-turn", contents: call }),
        new ChatResponseUpdate({
          responseId: "replayed-response",
          messageId: "replayed-metadata",
          finishReason: "tool_calls",
          usageDetails: { outputTokenCount: 3 },
        }),
      ],
      [
        new ChatResponseUpdate({
          role: "assistant",
          messageId: "final-turn",
          responseId: "final-response",
          contents: "done",
          finishReason: "stop",
          usageDetails: { outputTokenCount: 2 },
        }),
      ],
    );

    const stream = client.getResponse("hello", { stream: true, options: { tools: [tool] } });
    const updates = [];
    for await (const update of stream) updates.push(update);
    const response = await stream.getFinalResponse();

    expect(executions).toBe(1);
    expect(client.requests).toHaveLength(3);
    expect(client.requests[2]?.options.toolChoice).toBe("none");
    expect(client.requests[2]?.messages).toEqual(client.requests[1]?.messages);
    expect(client.requests[2]?.messages.map((message) => message.role)).toEqual(["user", "assistant", "tool"]);
    expect(response.messages.map((message) => message.role)).toEqual(["assistant", "tool", "assistant"]);
    expect(response.messages.every((message) => message.contents.length > 0)).toBe(true);
    expect(response.text).toBe("done");
    expect(response.responseId).toBe("final-response");
    expect(response.finishReason).toBe("stop");
    expect(response.usageDetails).toEqual({ outputTokenCount: 5 });
    expect(updates.some((update) => update.contents.length === 0 && update.usageDetails?.outputTokenCount === 3)).toBe(
      true,
    );
  });

  it("executes parallel calls while preserving model result order", async () => {
    const client = new TestChatClient();
    const completed: string[] = [];
    const tool = defineTool({
      name: "process",
      parameters,
      execute: async ({ value }) => {
        const delay = value === "first" ? 20 : 0;
        await new Promise((resolve) => setTimeout(resolve, delay));
        completed.push(String(value));
        return value;
      },
    });
    client.responses.push(
      new ChatResponse({
        messages: [
          new Message({
            role: "assistant",
            contents: [
              functionCall("call-1", "process", { value: "first" }),
              functionCall("call-2", "process", { value: "second" }),
            ],
          }),
        ],
      }),
      new ChatResponse({ messages: [new Message({ role: "assistant", contents: "done" })] }),
    );

    const response = await client.getResponse("hello", { options: { tools: [tool] } });

    expect(completed).toEqual(["second", "first"]);
    expect(response.messages[1]?.contents.map((content) => "callId" in content && content.callId)).toEqual([
      "call-1",
      "call-2",
    ]);
  });

  it("turns ordinary failures into results but propagates MiddlewareFailure", async () => {
    const recoverableClient = new TestChatClient();
    const failingTool = defineTool({
      name: "fail",
      parameters: { type: "object", additionalProperties: false },
      execute: () => {
        throw new Error("private detail");
      },
    });
    recoverableClient.responses.push(
      new ChatResponse({
        messages: [new Message({ role: "assistant", contents: functionCall("call-1", "fail") })],
      }),
      new ChatResponse({ messages: [new Message({ role: "assistant", contents: "recovered" })] }),
    );

    const recovered = await recoverableClient.getResponse("hello", { options: { tools: [failingTool] } });
    expect(recovered.messages[1]?.contents[0]).toMatchObject({
      isError: true,
      result: "Tool 'fail' failed.",
    });

    const fatalClient = new TestChatClient({
      functionMiddleware: [async () => Promise.reject(new MiddlewareFailure("abort"))],
    });
    fatalClient.responses.push(
      new ChatResponse({
        messages: [new Message({ role: "assistant", contents: functionCall("call-2", "fail") })],
      }),
    );
    await expect(fatalClient.getResponse("hello", { options: { tools: [failingTool] } })).rejects.toThrow(
      MiddlewareFailure,
    );
  });

  it("propagates caller cancellation to an executing tool", async () => {
    const client = new TestChatClient();
    const controller = new AbortController();
    let started: (() => void) | undefined;
    const toolStarted = new Promise<void>((resolve) => {
      started = resolve;
    });
    let toolSignal: AbortSignal | undefined;
    const tool = defineTool({
      name: "wait",
      parameters: { type: "object", additionalProperties: false },
      execute: async (_arguments, context) => {
        toolSignal = context.signal;
        started?.();
        await new Promise((_resolve, reject) => {
          context.signal.addEventListener("abort", () => reject(context.signal.reason), { once: true });
        });
      },
    });
    client.responses.push(
      new ChatResponse({
        messages: [new Message({ role: "assistant", contents: functionCall("call-1", "wait") })],
      }),
    );

    const response = client.getResponse("hello", { options: { tools: [tool] }, signal: controller.signal });
    await toolStarted;
    controller.abort(new Error("cancelled"));

    await expect(response).rejects.toThrow("cancelled");
    expect(toolSignal?.aborted).toBe(true);
  });

  it("filters function calls returned after the invocation limit", async () => {
    const client = new TestChatClient();
    const tool = defineTool({
      name: "process",
      parameters,
      execute: ({ value }) => value,
    });
    client.responses.push(
      new ChatResponse({
        messages: [new Message({ role: "assistant", contents: functionCall("call-1", "process", { value: "one" }) })],
      }),
      new ChatResponse({
        messages: [new Message({ role: "assistant", contents: functionCall("orphan", "process", { value: "two" }) })],
      }),
    );

    const response = await client.getResponse("hello", {
      options: { tools: [tool] },
      functionInvocation: { maxIterations: 1 },
    });
    const calls = response.messages.flatMap((message) =>
      message.contents.filter((content) => content.type === "function_call"),
    );
    const results = response.messages.flatMap((message) =>
      message.contents.filter((content) => content.type === "function_result"),
    );

    expect(calls.map((call) => call.callId)).toEqual(["call-1"]);
    expect(results.map((result) => result.callId)).toEqual(["call-1"]);
    expect(response.text).toContain("Function invocation limit reached");
  });

  it("filters streamed function calls returned after the invocation limit", async () => {
    const client = new TestChatClient();
    const tool = defineTool({
      name: "process",
      parameters,
      execute: ({ value }) => value,
    });
    client.streamingResponses.push(
      [
        new ChatResponseUpdate({
          role: "assistant",
          contents: functionCall("call-1", "process", { value: "one" }),
        }),
      ],
      [
        new ChatResponseUpdate({
          role: "assistant",
          contents: functionCall("orphan", "process", { value: "two" }),
        }),
      ],
    );

    const stream = client.getResponse("hello", {
      stream: true,
      options: { tools: [tool] },
      functionInvocation: { maxIterations: 1 },
    });
    for await (const _update of stream) {
      // Consume the complete function-calling stream.
    }
    const response = await stream.getFinalResponse();
    const calls = response.messages.flatMap((message) =>
      message.contents.filter((content) => content.type === "function_call"),
    );
    const results = response.messages.flatMap((message) =>
      message.contents.filter((content) => content.type === "function_result"),
    );

    expect(calls.map((call) => call.callId)).toEqual(["call-1"]);
    expect(results.map((result) => result.callId)).toEqual(["call-1"]);
    expect(response.text).toContain("Function invocation limit reached");
  });

  it("does not execute provider-completed function calls again", async () => {
    const client = new TestChatClient();
    let executions = 0;
    const tool = defineTool({
      name: "process",
      parameters,
      execute: () => {
        executions += 1;
      },
    });
    client.responses.push(
      new ChatResponse({
        messages: [
          new Message({
            role: "assistant",
            contents: { ...functionCall("call-1", "process", { value: "one" }), id: "provider-occurrence" },
          }),
          new Message({
            role: "tool",
            contents: { ...functionResult("call-1", "provider result"), id: "provider-occurrence" },
          }),
          new Message({ role: "assistant", contents: "done" }),
        ],
      }),
    );

    const response = await client.getResponse("hello", { options: { tools: [tool] } });

    expect(executions).toBe(0);
    expect(client.requests).toHaveLength(1);
    expect(response.text).toBe("done");
  });

  it("executes a stable function-call occurrence at most once", async () => {
    const client = new TestChatClient();
    let executions = 0;
    const tool = defineTool({
      name: "process",
      parameters,
      execute: () => {
        executions += 1;
        return "processed";
      },
    });
    const repeatedCall = {
      ...functionCall("call-1", "process", { value: "one" }),
      id: "af-call-stable",
    };
    client.responses.push(
      new ChatResponse({
        messages: [new Message({ role: "assistant", contents: [repeatedCall, repeatedCall] })],
      }),
      new ChatResponse({ messages: [new Message({ role: "assistant", contents: "done" })] }),
    );

    const response = await client.getResponse("hello", { options: { tools: [tool] } });
    const calls = response.messages.flatMap((message) =>
      message.contents.filter((content) => content.type === "function_call"),
    );
    const results = response.messages.flatMap((message) =>
      message.contents.filter((content) => content.type === "function_result"),
    );

    expect(executions).toBe(1);
    expect(calls).toHaveLength(1);
    expect(results).toHaveLength(1);
  });

  it("preserves final provider metadata after function invocation", async () => {
    const client = new TestChatClient();
    const tool = defineTool({
      name: "process",
      parameters,
      execute: ({ value }) => value,
    });
    client.responses.push(
      new ChatResponse({
        messages: [new Message({ role: "assistant", contents: functionCall("call-1", "process", { value: "one" }) })],
        additionalProperties: { model: "tool-model" },
      }),
      new ChatResponse({
        messages: [new Message({ role: "assistant", contents: "done" })],
        responseId: "response-final",
        finishReason: "stop",
        additionalProperties: { model: "final-model" },
      }),
    );

    const response = await client.getResponse("hello", { options: { tools: [tool] } });

    expect(response.responseId).toBe("response-final");
    expect(response.finishReason).toBe("stop");
    expect(response.additionalProperties).toEqual({ model: "final-model" });
  });

  it("counts consecutive error-bearing model turns instead of individual calls", async () => {
    const client = new TestChatClient();
    let executions = 0;
    const tool = defineTool({
      name: "fail",
      parameters,
      execute: () => {
        executions += 1;
        throw new Error("failed");
      },
    });
    const failedTurn = (turn: number, count: number) =>
      new ChatResponse({
        messages: [
          new Message({
            role: "assistant",
            contents: Array.from({ length: count }, (_, index) =>
              functionCall(`call-${turn}-${index}`, "fail", { value: "one" }),
            ),
          }),
        ],
      });
    client.responses.push(
      failedTurn(1, 2),
      failedTurn(2, 2),
      failedTurn(3, 1),
      new ChatResponse({ messages: [new Message({ role: "assistant", contents: "done" })] }),
    );

    const response = await client.getResponse("hello", {
      options: { tools: [tool] },
      functionInvocation: { maxConsecutiveErrors: 3 },
    });

    expect(executions).toBe(5);
    expect(client.requests).toHaveLength(4);
    expect(response.text).toBe("done");
  });

  it("rejects cancellation between streamed provider updates", async () => {
    class SignalIgnoringClient extends BaseChatClient {
      public releaseSecondUpdate: (() => void) | undefined;

      protected override async getResponseCore(
        request: ChatClientRequest,
      ): Promise<ChatResponse | AsyncIterable<ChatResponseUpdate>> {
        if (!request.stream) {
          return new ChatResponse({ messages: [new Message({ role: "assistant", contents: "done" })] });
        }
        const secondUpdate = new Promise<void>((resolve) => {
          this.releaseSecondUpdate = resolve;
        });
        return (async function* () {
          yield new ChatResponseUpdate({ role: "assistant", contents: "first" });
          await secondUpdate;
          yield new ChatResponseUpdate({ role: "assistant", contents: "second" });
        })();
      }
    }

    const client = new SignalIgnoringClient();
    const controller = new AbortController();
    const stream = client.getResponse("hello", { stream: true, signal: controller.signal });
    const iterator = stream[Symbol.asyncIterator]();

    await expect(iterator.next()).resolves.toMatchObject({ value: { text: "first" } });
    controller.abort(new Error("cancelled"));
    client.releaseSecondUpdate?.();

    await expect(iterator.next()).rejects.toThrow("cancelled");
    await expect(stream.getFinalResponse()).rejects.toThrow("cancelled");
  });

  it("does not bind an explicit stale result occurrence to a new call", async () => {
    const client = new TestChatClient();
    let executions = 0;
    const tool = defineTool({
      name: "process",
      parameters,
      execute: () => {
        executions += 1;
        return "fresh result";
      },
    });
    client.responses.push(
      new ChatResponse({
        messages: [
          new Message({
            role: "assistant",
            contents: { ...functionCall("reused", "process", { value: "one" }), id: "af-call-current" },
          }),
          new Message({
            role: "tool",
            contents: { ...functionResult("reused", "stale result"), id: "af-call-stale" },
          }),
        ],
      }),
      new ChatResponse({ messages: [new Message({ role: "assistant", contents: "done" })] }),
    );

    const response = await client.getResponse("hello", { options: { tools: [tool] } });
    const results = response.messages.flatMap((message) =>
      message.contents.filter((content) => content.type === "function_result"),
    );

    expect(executions).toBe(1);
    expect(results).toEqual([
      expect.objectContaining({ id: "af-call-current", callId: "reused", result: "fresh result" }),
    ]);
  });

  it("requires both occurrence and call id to match and drops orphan results", async () => {
    const client = new TestChatClient();
    let executions = 0;
    const tool = defineTool({
      name: "process",
      parameters,
      execute: () => {
        executions += 1;
        return "fresh result";
      },
    });
    client.responses.push(
      new ChatResponse({
        messages: [
          new Message({
            role: "assistant",
            contents: { ...functionCall("current-call", "process", { value: "one" }), id: "af-call-current" },
          }),
          new Message({
            role: "tool",
            contents: { ...functionResult("wrong-call", "mismatched"), id: "af-call-current" },
          }),
          new Message({ role: "tool", contents: functionResult("current-call", "missing occurrence") }),
          new Message({ role: "tool", contents: functionResult("orphan", "stale") }),
        ],
      }),
      new ChatResponse({ messages: [new Message({ role: "assistant", contents: "done" })] }),
    );

    const response = await client.getResponse("hello", { options: { tools: [tool] } });
    const results = response.messages.flatMap((message) =>
      message.contents.filter((content) => content.type === "function_result"),
    );

    expect(executions).toBe(1);
    expect(results).toEqual([
      expect.objectContaining({ id: "af-call-current", callId: "current-call", result: "fresh result" }),
    ]);
    expect(client.requests[1]?.messages.flatMap((message) => message.contents)).not.toEqual(
      expect.arrayContaining([
        expect.objectContaining({ type: "function_result", callId: "wrong-call" }),
        expect.objectContaining({ type: "function_result", callId: "orphan" }),
      ]),
    );
  });

  it("suppresses duplicate streamed occurrence IDs before exposing them", async () => {
    const client = new TestChatClient();
    let executions = 0;
    const tool = defineTool({
      name: "process",
      parameters,
      execute: () => {
        executions += 1;
        return "processed";
      },
    });
    client.streamingResponses.push(
      [
        new ChatResponseUpdate({
          role: "assistant",
          contents: [
            { ...functionCall("call-1", "process", { value: "one" }), id: "af-call-duplicate" },
            { ...functionCall("call-2", "process", { value: "two" }), id: "af-call-duplicate" },
            functionResult("call-1", "missing occurrence"),
          ],
        }),
      ],
      [new ChatResponseUpdate({ role: "assistant", contents: "done" })],
    );

    const stream = client.getResponse("hello", { stream: true, options: { tools: [tool] } });
    for await (const _update of stream) {
      // Consume the complete function-calling stream.
    }
    const response = await stream.getFinalResponse();
    const calls = response.messages.flatMap((message) =>
      message.contents.filter((content) => content.type === "function_call"),
    );
    const results = response.messages.flatMap((message) =>
      message.contents.filter((content) => content.type === "function_result"),
    );

    expect(executions).toBe(1);
    expect(calls.map((call) => call.callId)).toEqual(["call-1"]);
    expect(results.map((result) => result.callId)).toEqual(["call-1"]);
    expect(client.requests[1]?.messages.flatMap((message) => message.contents)).not.toEqual(
      expect.arrayContaining([expect.objectContaining({ type: "function_result", result: "missing occurrence" })]),
    );
  });

  it("drops unmatched results when function invocation is disabled", async () => {
    const client = new TestChatClient();
    client.responses.push(
      new ChatResponse({
        messages: [
          new Message({ role: "tool", contents: functionResult("orphan", "stale") }),
          new Message({ role: "assistant", contents: "done" }),
        ],
      }),
    );

    const response = await client.getResponse("hello");

    expect(response.messages.flatMap((message) => message.contents)).toEqual([{ type: "text", text: "done" }]);
  });
});
