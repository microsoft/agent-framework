// Copyright (c) Microsoft. All rights reserved.

import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

let server;
let ApiClient;
let AgentDetailsModal;
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
  ({ AgentDetailsModal } = await server.ssrLoadModule(
    "/src/components/features/agent/agent-details-modal.tsx"
  ));
});

after(async () => {
  await server?.close();
  globalThis.localStorage = originalStorage;
});

async function renderDiscoveredAgent(t, contextProvider) {
  t.mock.method(globalThis, "fetch", async () => ({
    ok: true,
    json: async () => ({
      entities: [{
        id: "test-agent",
        type: "agent",
        source: "in_memory",
        context_provider: contextProvider,
      }],
    }),
  }));
  const { agents } = await new ApiClient("http://localhost").getEntities();
  return renderToStaticMarkup(createElement(AgentDetailsModal, {
    agent: agents[0],
    open: true,
    onOpenChange: () => {},
  }));
}

test("separates multiple context provider names in discovery order", async (t) => {
  const html = await renderDiscoveredAgent(t, [
    "InMemoryHistoryProvider",
    "ContextProvider",
  ]);

  assert.match(html, />InMemoryHistoryProvider, ContextProvider<\/div>/);
  assert.doesNotMatch(html, /InMemoryHistoryProviderContextProvider/);
});

test("renders a single context provider without an added separator", async (t) => {
  const html = await renderDiscoveredAgent(t, ["InMemoryHistoryProvider"]);

  assert.match(html, />InMemoryHistoryProvider<\/div>/);
});

test("omits the context provider card when discovery has no providers", async (t) => {
  const html = await renderDiscoveredAgent(t, undefined);

  assert.doesNotMatch(html, /Context Provider/);
});
