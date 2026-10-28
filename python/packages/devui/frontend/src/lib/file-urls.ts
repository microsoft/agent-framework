// Copyright (c) Microsoft. All rights reserved.

export function getSafeFileUrl(value: string | undefined): string | undefined {
  if (!value || !URL.canParse(value)) return undefined;
  const url = new URL(value);
  return url.protocol === "https:" || url.protocol === "http:" ? url.href : undefined;
}

export function createPdfBlob(data: string): Blob {
  let base64 = data;
  if (/^data:/i.test(data)) {
    const match = /^data:application\/pdf;base64,([a-z0-9+/=\s]*)$/i.exec(data);
    if (!match) throw new Error("Unsupported embedded PDF format");
    base64 = match[1];
  }
  const binary = atob(base64);
  return new Blob(
    [Uint8Array.from(binary, (character) => character.charCodeAt(0))],
    { type: "application/pdf" },
  );
}
