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

async function finishPollWindow(t) {
  for (let attempt = 0; attempt < 12; attempt++) {
    await setImmediate();
    t.mock.timers.tick(500);
  }
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
