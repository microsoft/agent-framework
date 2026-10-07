// Copyright (c) Microsoft. All rights reserved.

import assert from "node:assert/strict";
import { setImmediate } from "node:timers/promises";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

let server;
let ApiClient;
const originalStorage = globalThis.localStorage;

before(async () => {
  globalThis.localStorage = { getItem: () => null, removeItem: () => {} };
  server = await createServer({
    configFile: false,
    root: fileURLToPath(new URL("..", import.meta.url)),
    resolve: { alias: { "@": fileURLToPath(new URL("../src", import.meta.url)) } },
    server: { middlewareMode: true, hmr: false, ws: false, watch: null },
    optimizeDeps: { noDiscovery: true, include: [] },
  });
  ({ ApiClient } = await server.ssrLoadModule("/src/services/api.ts"));
});

after(async () => {
  await server?.close();
  globalThis.localStorage = originalStorage;
});

const span = (id, status = "OK") => ({
  type: "response.trace.completed",
  data: { span_id: id, status },
});

async function advanceTime(t, milliseconds) {
  while (milliseconds > 0) {
    await setImmediate();
    const step = Math.min(milliseconds, 500);
    t.mock.timers.tick(step);
    milliseconds -= step;
  }
  await setImmediate();
}

async function finishPollWindow(t) {
  await advanceTime(t, 6000);
}

test("merges spans exported five seconds after an unchanged early subset", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let polls = 0;
  t.mock.method(globalThis, "fetch", async () => ({
    ok: true,
    json: async () => ({ data: ++polls <= 10 ? [span("child")] : [span("parent"), span("child", "ERROR")] }),
  }));
  const client = new ApiClient("http://localhost");

  const pending = client.getTraceEvents("resp_delayed", true);
  await finishPollWindow(t);

  assert.deepEqual(await pending, [span("child", "ERROR"), span("parent")]);
  assert.equal(polls, 12);
});

test("keeps earlier spans when subsequent snapshots are partial or temporarily unavailable", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let polls = 0;
  t.mock.method(globalThis, "fetch", async () => {
    polls++;
    return {
      ok: polls !== 2,
      status: polls === 2 ? 503 : 200,
      json: async () => ({ data: polls === 1 ? [span("child")] : [span("parent")] }),
    };
  });
  const client = new ApiClient("http://localhost");

  const pending = client.getTraceEvents("resp_partial", true);
  await finishPollWindow(t);

  assert.deepEqual(await pending, [span("child"), span("parent")]);
  assert.equal(polls, 12);
});

test("retains spans and retries after fetch and JSON failures, including a failed last poll", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let polls = 0;
  t.mock.method(globalThis, "fetch", async () => {
    polls++;
    if (polls === 2 || polls === 12) throw new TypeError("Network connection lost");
    return {
      ok: true,
      json: async () => {
        if (polls === 3) throw new SyntaxError("Incomplete JSON");
        return { data: [span(polls === 1 ? "child" : "parent")] };
      },
    };
  });
  const pending = new ApiClient("http://localhost").getTraceEvents("resp_transient", true);
  await finishPollWindow(t);

  assert.deepEqual(await pending, [span("child"), span("parent")]);
  assert.equal(polls, 12);
});

test("slow timeout responses share a six-second deadline and cancel the active request", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const controller = new AbortController();
  t.after(() => controller.abort());
  let activeRequests = 0;
  let polls = 0;
  const fetch = t.mock.method(globalThis, "fetch", async (_url, { signal }) => {
    if (++polls === 1) return { ok: true, json: async () => ({ data: [span("child")] }) };
    activeRequests++;
    try {
      return await new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
          signal.removeEventListener("abort", onAbort);
          resolve({ ok: false, status: 503 });
        }, 2000);
        const onAbort = () => {
          clearTimeout(timer);
          reject(new DOMException("Request aborted", "AbortError"));
        };
        signal.addEventListener("abort", onAbort, { once: true });
      });
    } finally {
      activeRequests--;
    }
  });
  const outcomes = [];
  new ApiClient("http://localhost").getTraceEvents("resp_slow", true, controller.signal)
    .then((value) => outcomes.push({ value }), (error) => outcomes.push({ error }));

  await advanceTime(t, 5999);
  assert.deepEqual(outcomes, []);
  assert.equal(activeRequests, 1);
  await advanceTime(t, 1);
  assert.deepEqual(outcomes, [{ value: [span("child")] }]);
  assert.equal(activeRequests, 0);
  assert.equal(fetch.mock.callCount(), 4);
  await finishPollWindow(t);
  assert.equal(fetch.mock.callCount(), 4);
});

for (const stalledPhase of ["fetch", "body"]) {
  test(`deadline cancels a stalled ${stalledPhase} and returns previously collected spans`, async (t) => {
    t.mock.timers.enable({ apis: ["setTimeout"] });
    const controller = new AbortController();
    t.after(() => controller.abort());
    let aborted = false;
    let polls = 0;
    const fetch = t.mock.method(globalThis, "fetch", async (_url, { signal }) => {
      if (++polls === 1) return { ok: true, json: async () => ({ data: [span("child")] }) };
      const stall = () => new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => {
          aborted = true;
          reject(new DOMException("Request aborted", "AbortError"));
        }, { once: true });
      });
      return stalledPhase === "fetch" ? stall() : { ok: true, json: stall };
    });
    const outcomes = [];
    new ApiClient("http://localhost").getTraceEvents("resp_stalled", true, controller.signal)
      .then((value) => outcomes.push({ value }), (error) => outcomes.push({ error }));
    await finishPollWindow(t);

    assert.deepEqual(outcomes, [{ value: [span("child")] }]);
    assert.equal(aborted, true);
    assert.equal(fetch.mock.callCount(), 2);
  });

  test(`caller cancellation interrupts a stalled ${stalledPhase} and rejects instead of publishing spans`, async (t) => {
    t.mock.timers.enable({ apis: ["setTimeout"] });
    const controller = new AbortController();
    let aborted = false;
    const fetch = t.mock.method(globalThis, "fetch", async (_url, { signal }) => {
      const stall = () => new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => {
          aborted = true;
          reject(new DOMException("Request aborted", "AbortError"));
        }, { once: true });
      });
      return stalledPhase === "fetch" ? stall() : { ok: true, json: stall };
    });
    const pending = new ApiClient("http://localhost").getTraceEvents("resp_cancelled", true, controller.signal);
    const rejected = assert.rejects(pending, { name: "AbortError" });
    await advanceTime(t, 500);
    controller.abort();
    await rejected;
    await finishPollWindow(t);

    assert.equal(aborted, true);
    assert.equal(fetch.mock.callCount(), 1);
  });
}

test("an already cancelled request never starts trace polling", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch");
  const controller = new AbortController();
  controller.abort();

  await assert.rejects(new ApiClient("http://localhost").getTraceEvents("resp_cancelled", true, controller.signal), { name: "AbortError" });
  assert.equal(fetch.mock.callCount(), 0);
});

test("a non-retryable response stops polling without discarding collected spans", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let polls = 0;
  const fetch = t.mock.method(globalThis, "fetch", async () => ++polls === 1
    ? { ok: true, json: async () => ({ data: [span("child")] }) }
    : { ok: false, status: 400 });
  const pending = new ApiClient("http://localhost").getTraceEvents("resp_unavailable", true);
  await finishPollWindow(t);

  assert.deepEqual(await pending, [span("child")]);
  assert.equal(fetch.mock.callCount(), 2);
  assert.equal(fetch.mock.calls[0].arguments[1].signal.aborted, false);
});

test("cancellation during the poll interval stops requests and rejects the result", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const fetch = t.mock.method(globalThis, "fetch", async () => ({ ok: true, json: async () => ({ data: [span("child")] }) }));
  const controller = new AbortController();
  const client = new ApiClient("http://localhost");
  const pending = client.getTraceEvents("resp_cancelled", true, controller.signal);
  const rejected = assert.rejects(pending, { name: "AbortError" });
  await setImmediate();

  controller.abort();
  await rejected;
  await finishPollWindow(t);

  assert.equal(fetch.mock.callCount(), 1);
});

test("each call uses the supplied capability, including when it is disabled after a previous request", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const fetch = t.mock.method(globalThis, "fetch", async () => ({ ok: true, json: async () => ({ data: [span("child")] }) }));
  const client = new ApiClient("http://localhost");

  assert.deepEqual(await client.getTraceEvents("resp_disabled", false), []);
  assert.equal(fetch.mock.callCount(), 0);
  const pending = client.getTraceEvents("resp_enabled", true);
  await finishPollWindow(t);
  assert.deepEqual(await pending, [span("child")]);
  assert.equal(fetch.mock.callCount(), 12);
  assert.deepEqual(await client.getTraceEvents("resp_disabled_again", false), []);
  assert.equal(fetch.mock.callCount(), 12);
});

test("an unauthorized trace request clears the token and stops polling", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => ({ ok: false, status: 401 }));
  const client = new ApiClient("http://localhost");
  const clearAuthToken = t.mock.method(client, "clearAuthToken");

  assert.deepEqual(await client.getTraceEvents("resp_unauthorized", true), []);
  assert.equal(fetch.mock.callCount(), 1);
  assert.equal(clearAuthToken.mock.callCount(), 1);
});
