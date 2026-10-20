// Copyright (c) Microsoft. All rights reserved.

import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

let server;
let appendResponseMedia;

before(async () => {
  server = await createServer({
    configFile: false,
    root: fileURLToPath(new URL("..", import.meta.url)),
    server: { middlewareMode: true, hmr: false, ws: false, watch: null },
    optimizeDeps: { noDiscovery: true, include: [] },
  });
  ({ appendResponseMedia } = await server.ssrLoadModule("/src/services/response-media.ts"));
});

after(async () => { await server?.close(); });

const audio = {
  id: "audio-1", type: "output_file", filename: "speech.wav",
  mime_type: "audio/wav", file_url: "data:audio/wav;base64,UklGRg==",
};
const image = { id: "image-1", type: "output_image", mime_type: "image/png", image_url: "image.png" };
const text = { type: "text", text: "Answer" };

test("recovers final response media after refresh without losing text or autoplaying history", () => {
  const result = appendResponseMedia([text], [audio, image]);
  assert.deepEqual(result, [text, { ...audio, auto_play: false }, image]);
});

test("reconciles live and completed output once while allowing distinct identical audio items", () => {
  const live = appendResponseMedia([text], [audio], true);
  const result = appendResponseMedia(live, [audio, { ...audio, id: "audio-2" }, image], true);
  assert.deepEqual(result, [
    text, { ...audio, auto_play: true }, { ...audio, id: "audio-2", auto_play: false }, image,
  ]);
  assert.deepEqual(live, [text, { ...audio, auto_play: true }]);
});

test("accepts nested media and legacy content without IDs without duplicating it", () => {
  const { id: _id, ...legacyAudio } = audio;
  const output = [{ type: "message", content: [text, legacyAudio] }];
  const first = appendResponseMedia([], output);
  assert.deepEqual(appendResponseMedia(first, [audio]), [{ ...legacyAudio, auto_play: false }]);
});
