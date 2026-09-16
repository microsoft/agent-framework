import { defineTool } from "@microsoft/agent-framework-core";
import OpenAI from "openai";
import type {
  ChatCompletion,
  ChatCompletionChunk,
  ChatCompletionCreateParams,
} from "openai/resources/chat/completions/completions.js";
import { describe, expect, it, vi } from "vitest";

import { OpenAIChatCompletionClient } from "../src/index.js";

function completion(
  id: string,
  content: string | null,
  toolCalls: ChatCompletion["choices"][number]["message"]["tool_calls"] = [],
): ChatCompletion {
  return {
    id,
    object: "chat.completion",
    created: 1,
    model: "gpt-test",
    choices: [
      {
        index: 0,
        finish_reason: toolCalls.length === 0 ? "stop" : "tool_calls",
        logprobs: null,
        message: { role: "assistant", content, refusal: null, tool_calls: toolCalls },
      },
    ],
    usage: { prompt_tokens: 2, completion_tokens: 3, total_tokens: 5 },
  };
}

function chunk(
  id: string,
  delta: ChatCompletionChunk.Choice.Delta,
  finishReason: ChatCompletionChunk.Choice["finish_reason"] = null,
): ChatCompletionChunk {
  return {
    id,
    object: "chat.completion.chunk",
    created: 1,
    model: "gpt-test",
    choices: [{ index: 0, delta, finish_reason: finishReason, logprobs: null }],
  };
}

function mockOpenAI(responses: Array<ChatCompletion | ChatCompletionChunk[]>): {
  client: OpenAI;
  create: ReturnType<typeof vi.fn>;
} {
  const create = vi.fn(async (request: ChatCompletionCreateParams) => {
    const response = responses.shift();
    if (response === undefined) throw new Error("No response configured.");
    if (request.stream) {
      if (!Array.isArray(response)) throw new Error("Expected streaming response.");
      return (async function* () {
        for (const item of response) yield item;
      })();
    }
    if (Array.isArray(response)) throw new Error("Expected non-streaming response.");
    return response;
  });
  return {
    client: { chat: { completions: { create } } } as unknown as OpenAI,
    create,
  };
}

describe("OpenAIChatCompletionClient", () => {
  it("maps tool calls and sends correlated results on the next turn", async () => {
    const { client, create } = mockOpenAI([
      completion("response-1", null, [
        {
          id: "call-1",
          type: "function",
          function: { name: "get_weather", arguments: '{"city":"Seattle"}' },
        },
      ]),
      completion("response-2", "Rainy"),
    ]);
    const chatClient = new OpenAIChatCompletionClient({ client, model: "gpt-test" });
    const weather = defineTool({
      name: "get_weather",
      description: "Get weather for a city.",
      parameters: {
        type: "object",
        properties: { city: { type: "string" } },
        required: ["city"],
        additionalProperties: false,
      },
      execute: ({ city }) => ({ city, condition: "rain" }),
    });

    const response = await chatClient.getResponse("What is the weather?", {
      options: { instructions: "Be concise.", tools: [weather] },
    });

    expect(response.text).toBe("Rainy");
    expect(response.usageDetails).toEqual({ inputTokenCount: 4, outputTokenCount: 6, totalTokenCount: 10 });
    const secondRequest = create.mock.calls[1]?.[0] as ChatCompletionCreateParams;
    expect(secondRequest.messages).toContainEqual({
      role: "tool",
      tool_call_id: "call-1",
      content: '{"city":"Seattle","condition":"rain"}',
    });
    expect(secondRequest.messages).toContainEqual({
      role: "assistant",
      content: null,
      tool_calls: [
        {
          id: "call-1",
          type: "function",
          function: { name: "get_weather", arguments: '{"city":"Seattle"}' },
        },
      ],
    });
  });

  it("reassembles streamed OpenAI tool-call deltas", async () => {
    const { client } = mockOpenAI([
      [
        chunk("response-1", {
          role: "assistant",
          tool_calls: [{ index: 0, id: "call-1", type: "function", function: { name: "get_", arguments: '{"city":' } }],
        }),
        chunk(
          "response-1",
          { tool_calls: [{ index: 0, function: { name: "weather", arguments: '"Seattle"}' } }] },
          "tool_calls",
        ),
      ],
      [chunk("response-2", { role: "assistant", content: "Rainy" }, "stop")],
    ]);
    const chatClient = new OpenAIChatCompletionClient({ client, model: "gpt-test" });
    const weather = defineTool({
      name: "get_weather",
      parameters: {
        type: "object",
        properties: { city: { type: "string" } },
        required: ["city"],
      },
      execute: ({ city }) => `${String(city)}: rain`,
    });
    const stream = chatClient.getResponse("Weather?", { stream: true, options: { tools: [weather] } });

    const updates = [];
    for await (const update of stream) updates.push(update);
    const response = await stream.getFinalResponse();

    expect(updates.some((update) => update.contents.some((content) => content.type === "function_result"))).toBe(true);
    expect(updates[0]?.contents[0]?.id).toBe("openai:response-1:choice:0:tool:0");
    expect(response.messages.map((message) => message.role)).toEqual(["assistant", "tool", "assistant"]);
    expect(response.text).toBe("Rainy");
  });

  it("preserves non-streaming and streaming refusals", async () => {
    const nonStreamingRefusal = completion("response-1", null);
    nonStreamingRefusal.choices[0]!.message.refusal = "I cannot help with that.";
    const { client } = mockOpenAI([
      nonStreamingRefusal,
      [chunk("response-2", { role: "assistant", refusal: "I cannot help with that." }, "stop")],
    ]);
    const chatClient = new OpenAIChatCompletionClient({ client, model: "gpt-test" });

    const response = await chatClient.getResponse("request");
    const stream = chatClient.getResponse("request", { stream: true });
    for await (const _update of stream) {
      // Consume the refusal stream.
    }
    const streamingResponse = await stream.getFinalResponse();

    expect(response.text).toBe("I cannot help with that.");
    expect(response.messages[0]?.contents[0]?.additionalProperties).toEqual({ modelOutputKind: "refusal" });
    expect(streamingResponse.text).toBe("I cannot help with that.");
    expect(streamingResponse.messages[0]?.contents[0]?.additionalProperties).toEqual({
      modelOutputKind: "refusal",
    });
  });

  it("rejects tool results that cannot be represented as OpenAI content", async () => {
    const { client, create } = mockOpenAI([
      completion("response-1", null, [
        {
          id: "call-1",
          type: "function",
          function: { name: "invalid_result", arguments: "{}" },
        },
      ]),
    ]);
    const chatClient = new OpenAIChatCompletionClient({ client, model: "gpt-test" });
    const invalidResult = defineTool({
      name: "invalid_result",
      parameters: { type: "object", additionalProperties: false },
      execute: () => Symbol("not-json"),
    });

    await expect(chatClient.getResponse("request", { options: { tools: [invalidResult] } })).rejects.toThrow(
      "could not be serialized",
    );
    expect(create).toHaveBeenCalledTimes(1);
  });

  it("does not execute a replayed OpenAI tool-call occurrence twice", async () => {
    const replayed = completion("response-replayed", null, [
      {
        id: "call-reused",
        type: "function",
        function: { name: "side_effect", arguments: "{}" },
      },
    ]);
    const { client, create } = mockOpenAI([replayed, replayed, completion("response-final", "done")]);
    const chatClient = new OpenAIChatCompletionClient({ client, model: "gpt-test" });
    let executions = 0;
    const sideEffect = defineTool({
      name: "side_effect",
      parameters: { type: "object", additionalProperties: false },
      execute: () => {
        executions += 1;
        return "complete";
      },
    });

    const response = await chatClient.getResponse("request", { options: { tools: [sideEffect] } });
    const calls = response.messages.flatMap((message) =>
      message.contents.filter((content) => content.type === "function_call"),
    );

    expect(executions).toBe(1);
    expect(create).toHaveBeenCalledTimes(3);
    expect(calls).toHaveLength(1);
    expect(calls[0]?.id).toBe("openai:response-replayed:choice:0:tool:0");
    expect(response.text).toBe("done");
  });
});
