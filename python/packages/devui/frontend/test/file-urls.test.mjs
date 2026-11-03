// Copyright (c) Microsoft. All rights reserved.

import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { act, createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Window } from "happy-dom";
import { createServer } from "vite";

let server;
let getSafeFileUrl;
let createEmbeddedFileBlob;
let OpenAIContentRenderer;
let createRoot;
let window;
const originalWindow = globalThis.window;
const originalDocument = globalThis.document;
const originalActEnvironment = globalThis.IS_REACT_ACT_ENVIRONMENT;

before(async () => {
  window = new Window({ url: "http://localhost" });
  globalThis.window = window;
  globalThis.document = window.document;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  ({ createRoot } = await import("react-dom/client"));
  server = await createServer({
    configFile: false,
    root: fileURLToPath(new URL("..", import.meta.url)),
    resolve: { alias: { "@": fileURLToPath(new URL("../src", import.meta.url)) } },
    esbuild: { jsx: "automatic" },
    server: { middlewareMode: true, hmr: false, ws: false, watch: null },
    optimizeDeps: { noDiscovery: true, include: [] },
  });
  ({ getSafeFileUrl, createEmbeddedFileBlob } = await server.ssrLoadModule("/src/lib/file-urls.ts"));
  ({ OpenAIContentRenderer } = await server.ssrLoadModule(
    "/src/components/features/agent/message-renderers/OpenAIContentRenderer.tsx",
  ));
});

after(async () => {
  await server?.close();
  await window?.happyDOM.close();
  globalThis.window = originalWindow;
  globalThis.document = originalDocument;
  globalThis.IS_REACT_ACT_ENVIRONMENT = originalActEnvironment;
});

function renderFile(filename, fileUrl, type = "output_file") {
  return renderToStaticMarkup(createElement(OpenAIContentRenderer, {
    content: { type, filename, file_url: fileUrl },
  }));
}

test("allows HTTP and HTTPS file links", () => {
  for (const url of ["https://example.com/report.pdf", "http://localhost:8090/report.pdf"]) {
    assert.equal(getSafeFileUrl(url), url);
    const markup = renderFile("report.pdf", url);
    assert.ok(markup.includes(`href="${url}"`));
    assert.ok(!markup.includes("disabled"));
  }
});

test("blocks unsupported schemes, including disguised script schemes, in file controls", () => {
  for (const url of [
    "javascript:void(0)//report.pdf",
    " \tJaVaScRiPt:void(0)//report.pdf",
    "java\nscript:void(0)//report.pdf",
    "data:text/html;base64,SGVsbG8=",
    "blob:https://example.com/untrusted",
    "file:///report.pdf",
    "ftp://example.com/report.pdf",
    "//example.com/report.pdf",
    "/report.pdf",
    "not a URL",
  ]) {
    assert.equal(getSafeFileUrl(url), undefined);
    for (const type of ["input_file", "output_file"]) {
      const pdf = renderFile("report.pdf", url, type);
      assert.match(pdf, /disabled=""/);
      assert.ok(!pdf.includes("href="));
      assert.ok(pdf.includes("This file cannot be opened"));
      const generic = renderFile("report.txt", url, type);
      assert.ok(!generic.includes("href="));
      assert.ok(generic.includes("This file cannot be downloaded"));
    }
  }
});

test("keeps ordinary downloads and audio playback", () => {
  assert.ok(renderFile("report.txt", "https://example.com/report.txt")
    .includes('href="https://example.com/report.txt"'));
  assert.ok(renderFile("recording.mp3", "data:audio/mpeg;base64,SGVsbG8=")
    .includes('<source src="data:audio/mpeg;base64,SGVsbG8="'));
});

test("preserves embedded PDFs as PDF blobs without allowing direct data navigation", async () => {
  const pdf = "%PDF-1.7\nexample\n%%EOF";
  const base64 = btoa(pdf);
  for (const data of [base64, `data:application/pdf;base64,${base64}`]) {
    const blob = createEmbeddedFileBlob(data, "application/pdf");
    assert.equal(blob.type, "application/pdf");
    assert.equal(await blob.text(), pdf);
    assert.equal(getSafeFileUrl(data), undefined);
  }
});

test("rejects malformed PDF data and unsupported embedded formats", () => {
  for (const data of [
    "not valid base64!",
    "javascript:void(0)//report.pdf",
    "data:text/html;base64,SGVsbG8=",
    "data:application/pdf,plain text",
    "data:application/pdf;base64,!!!",
  ]) {
    assert.throws(() => createEmbeddedFileBlob(data, "application/pdf"));
  }
});

async function mountFile(t, content) {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  const render = async (value) => {
    await act(async () => root.render(createElement(OpenAIContentRenderer, { content: value })));
  };
  t.after(async () => {
    await act(async () => root.unmount());
    container.remove();
  });
  await render(content);
  return { container, root, render };
}

for (const mimeType of ["video/mp4", "video/webm"]) {
  test(`renders working embedded ${mimeType} downloads`, async (t) => {
    const bytes = new Uint8Array([0, 1, 128, 255]);
    const base64 = btoa(String.fromCharCode(...bytes));
    const fileUrl = `data:${mimeType};base64,${base64}`;
    for (const fields of [
      { type: "output_file", file_url: fileUrl, file_data: base64 },
      { type: "output_file", file_data: base64 },
      { type: "input_file", file_url: fileUrl },
    ]) {
      const { container } = await mountFile(t, {
        filename: `clip.${mimeType.split("/")[1]}`,
        mime_type: mimeType,
        ...fields,
      });
      const link = container.querySelector("a[download]");
      assert.ok(link);
      assert.ok(link.href.startsWith("blob:"));
      assert.equal(container.querySelector('[role="status"]'), null);
      const response = await fetch(link.href);
      assert.equal(response.headers.get("content-type"), mimeType);
      assert.deepEqual(new Uint8Array(await response.arrayBuffer()), bytes);
    }
  });
}

test("keeps embedded PDF opening working without accepting script links", async (t) => {
  const open = t.mock.method(window, "open", () => null);
  t.mock.method(console, "error", () => {});
  const { container, render } = await mountFile(t, {
    type: "output_file",
    filename: "report.pdf",
    mime_type: "application/pdf",
    file_data: btoa("%PDF-1.7\nexample\n%%EOF"),
  });
  const link = container.querySelector("a[download]");
  assert.ok(link.href.startsWith("blob:"));
  const button = [...container.querySelectorAll("button")]
    .find((button) => button.textContent === "Open in new tab");
  await act(async () => button.click());
  assert.deepEqual(open.mock.calls[0].arguments, [link.href, "_blank", "noopener,noreferrer"]);
  const blobUrl = link.href;
  await render({
    type: "output_file",
    filename: "report.pdf",
    mime_type: "application/pdf",
    file_url: "javascript:void(0)//report.pdf",
  });
  assert.equal(container.querySelector("a[download]"), null);
  assert.equal(button.disabled, true);
  await act(async () => button.click());
  assert.equal(open.mock.callCount(), 1);
  await assert.rejects(fetch(blobUrl));
});

test("releases embedded file links on replacement and unmount", async (t) => {
  const content = {
    type: "output_file",
    filename: "clip.mp4",
    mime_type: "video/mp4",
    file_data: btoa("first video"),
  };
  const { container, root, render } = await mountFile(t, content);
  const firstUrl = container.querySelector("a[download]").href;
  await render({ ...content, file_data: btoa("second video") });
  const secondUrl = container.querySelector("a[download]").href;
  assert.notEqual(secondUrl, firstUrl);
  await assert.rejects(fetch(firstUrl));
  assert.equal(await (await fetch(secondUrl)).text(), "second video");
  await act(async () => root.unmount());
  await assert.rejects(fetch(secondUrl));
});

test("removes an embedded link when replacement content has an unsupported type", async (t) => {
  t.mock.method(console, "error", () => {});
  const { container, render } = await mountFile(t, {
    type: "output_file",
    filename: "clip.mp4",
    mime_type: "video/mp4",
    file_data: btoa("video"),
  });
  const url = container.querySelector("a[download]").href;
  await render({
    type: "output_file",
    filename: "page.html",
    mime_type: "text/html",
    file_data: btoa("video"),
  });
  assert.equal(container.querySelector("a[download]"), null);
  assert.ok(container.textContent.includes("This file cannot be downloaded"));
  await assert.rejects(fetch(url));
});

test("keeps malformed and disallowed embedded files unavailable", async (t) => {
  const errors = t.mock.method(console, "error", () => {});
  for (const fields of [
    { mime_type: "video/mp4", file_data: "invalid base64!" },
    { mime_type: "text/html", file_url: `data:text/html;base64,${btoa("<p>example</p>")}` },
    { mime_type: "video/mp4", file_url: `data:video/webm;base64,${btoa("video")}` },
  ]) {
    const { container } = await mountFile(t, {
      type: "output_file",
      filename: "clip.mp4",
      ...fields,
    });
    assert.equal(container.querySelector("a[download]"), null);
    assert.ok(container.textContent.includes("This file cannot be downloaded"));
  }
  assert.equal(errors.mock.callCount(), 3);
});
