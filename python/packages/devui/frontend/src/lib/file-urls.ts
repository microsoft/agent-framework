// Copyright (c) Microsoft. All rights reserved.

export function getSafeFileUrl(value: string | undefined): string | undefined {
  if (!value || !URL.canParse(value)) return undefined;
  const url = new URL(value);
  return url.protocol === "https:" || url.protocol === "http:" ? url.href : undefined;
}

export function createEmbeddedFileBlob(data: string, mimeType?: string): Blob {
  let base64 = data;
  if (/^data:/i.test(data)) {
    const match = /^data:([^;,]+);base64,([a-z0-9+/=\s]*)$/i.exec(data);
    if (!match) throw new Error("Unsupported embedded file format");
    const declaredMimeType = match[1].toLowerCase();
    if (mimeType && mimeType !== declaredMimeType) {
      throw new Error("Embedded file type does not match its declared type");
    }
    mimeType = declaredMimeType;
    base64 = match[2];
  }
  if (!mimeType || !["application/pdf", "video/mp4", "video/webm"].includes(mimeType)) {
    throw new Error("Unsupported embedded file type");
  }
  const binary = atob(base64);
  return new Blob(
    [Uint8Array.from(binary, (character) => character.charCodeAt(0))],
    { type: mimeType },
  );
}
