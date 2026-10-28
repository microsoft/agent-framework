// Copyright (c) Microsoft. All rights reserved.

import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

let server;
let getSafeFileUrl;
let createPdfBlob;
let OpenAIContentRenderer;

before(async () => {
  server = await createServer({
    configFile: false,
    root: fileURLToPath(new URL("..", import.meta.url)),
    resolve: { alias: { "@": fileURLToPath(new URL("../src", import.meta.url)) } },
    esbuild: { jsx: "automatic" },
    server: { middlewareMode: true, hmr: false, ws: false, watch: null },
    optimizeDeps: { noDiscovery: true, include: [] },
  });
  ({ getSafeFileUrl, createPdfBlob } = await server.ssrLoadModule("/src/lib/file-urls.ts"));
  ({ OpenAIContentRenderer } = await server.ssrLoadModule(
    "/src/components/features/agent/message-renderers/OpenAIContentRenderer.tsx",
  ));
});

after(async () => {
  await server?.close();
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
    const blob = createPdfBlob(data);
    assert.equal(blob.type, "application/pdf");
    assert.equal(await blob.text(), pdf);
    assert.equal(getSafeFileUrl(data), undefined);
  }
});

test("rejects malformed or non-PDF embedded formats", () => {
  for (const data of [
    "not valid base64!",
    "javascript:void(0)//report.pdf",
    "data:text/html;base64,SGVsbG8=",
    "data:application/pdf,plain text",
    "data:application/pdf;base64,!!!",
  ]) {
    assert.throws(() => createPdfBlob(data));
  }
});
