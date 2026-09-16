import { describe, expect, it } from "vitest";

import { ChatResponse, ChatResponseUpdate, Message, ResponseStream, functionCall } from "../src/index.js";

async function* streamUpdates(): AsyncGenerator<ChatResponseUpdate> {
  yield new ChatResponseUpdate({
    responseId: "response-1",
    contents: [
      { type: "function_call", callId: "first", name: "get_", arguments: '{"city":' },
      { type: "function_call", callId: "second", name: "get_", arguments: '{"city":' },
    ],
  });
  yield new ChatResponseUpdate({
    contents: [
      { type: "function_call", callId: "second", name: "time", arguments: '"Paris"}' },
      { type: "function_call", callId: "first", name: "weather", arguments: '"Seattle"}' },
    ],
    usageDetails: { outputTokenCount: 2 },
  });
}

describe("core response types", () => {
  it("normalizes strings into text content", () => {
    const message = new Message({ role: "user", contents: ["Hello", " world"] });

    expect(message.text).toBe("Hello world");
    expect(message.contents).toEqual([
      { type: "text", text: "Hello" },
      { type: "text", text: " world" },
    ]);
  });

  it("merges interleaved streaming function calls by call id", async () => {
    const responseStream = new ResponseStream(streamUpdates(), ChatResponse.fromUpdates);

    const updates = [];
    for await (const update of responseStream) updates.push(update);
    const response = await responseStream.getFinalResponse();

    expect(updates).toHaveLength(2);
    expect(response.responseId).toBe("response-1");
    expect(response.usageDetails).toEqual({ outputTokenCount: 2 });
    expect(response.messages[0]?.contents).toEqual([
      functionCall("first", "get_weather", '{"city":"Seattle"}'),
      functionCall("second", "get_time", '{"city":"Paris"}'),
    ]);
    await expect(responseStream.getFinalResponse()).resolves.toBe(response);
  });

  it("keeps stream failures sticky during finalization", async () => {
    const failure = new Error("stream failed");
    const responseStream = new ResponseStream(
      (async function* () {
        yield new ChatResponseUpdate({ contents: "partial" });
        throw failure;
      })(),
      ChatResponse.fromUpdates,
    );

    const consume = async () => {
      for await (const _update of responseStream) {
        // Consume until the source fails.
      }
    };

    await expect(consume()).rejects.toBe(failure);
    await expect(responseStream.getFinalResponse()).rejects.toBe(failure);
    await expect(responseStream.getFinalResponse()).rejects.toBe(failure);
  });

  it("prevents iteration from racing finalization", async () => {
    const responseStream = new ResponseStream(
      (async function* () {
        yield new ChatResponseUpdate({ contents: "first" });
        yield new ChatResponseUpdate({ contents: "second" });
      })(),
      ChatResponse.fromUpdates,
    );

    const finalResponse = responseStream.getFinalResponse();
    const iterator = responseStream[Symbol.asyncIterator]();

    await expect(iterator.next()).rejects.toThrow("consumed concurrently");
    await expect(finalResponse).resolves.toMatchObject({ text: "firstsecond" });
  });

  it("allows finalization to retry after active iteration completes", async () => {
    const responseStream = new ResponseStream(
      (async function* () {
        yield new ChatResponseUpdate({ contents: "complete" });
      })(),
      ChatResponse.fromUpdates,
    );
    const iterator = responseStream[Symbol.asyncIterator]();

    await expect(iterator.next()).resolves.toMatchObject({ done: false });
    await expect(responseStream.getFinalResponse()).rejects.toThrow("Finish iterating");
    await expect(iterator.next()).resolves.toMatchObject({ done: true });
    await expect(responseStream.getFinalResponse()).resolves.toMatchObject({ text: "complete" });
  });
});
