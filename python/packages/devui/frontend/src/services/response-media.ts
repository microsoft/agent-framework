import type { MessageContent, ResponseOutputItem, ResponseOutputMessage } from "@/types/openai";

type MediaContent = Extract<MessageContent, { type: "output_file" | "output_image" | "output_data" }> & { id?: string };

function isMedia(item: MessageContent | ResponseOutputItem): item is MediaContent {
  return item.type === "output_file" || item.type === "output_image" || item.type === "output_data";
}

function isMessage(item: ResponseOutputItem): item is ResponseOutputMessage {
  return item.type === "message" && Array.isArray(item.content);
}

function sameMedia(left: MediaContent, right: MediaContent): boolean {
  if (left.id && right.id) return left.id === right.id;
  if (left.type === "output_file" && right.type === "output_file") {
    return left.file_url === right.file_url && left.file_data === right.file_data &&
      left.filename === right.filename && left.mime_type === right.mime_type;
  }
  if (left.type === "output_image" && right.type === "output_image") {
    return left.image_url === right.image_url && left.mime_type === right.mime_type;
  }
  return left.type === "output_data" && right.type === "output_data" &&
    left.data === right.data && left.mime_type === right.mime_type;
}

/** Reconcile live items and final response media without caching binary data in localStorage. */
export function appendResponseMedia(
  content: MessageContent[],
  output: ResponseOutputItem[],
  allowAutoPlay = false,
): MessageContent[] {
  const next = [...content];
  for (const item of output) {
    const media = isMedia(item) ? [item] : isMessage(item) ? item.content.filter(isMedia) : [];
    for (const part of media) {
      if (next.some((existing) => isMedia(existing) && sameMedia(existing, part))) continue;
      const isFirstAudio = part.type === "output_file" && part.mime_type.startsWith("audio/") &&
        !next.some((existing) => existing.type === "output_file" && existing.mime_type.startsWith("audio/"));
      next.push(part.type === "output_file" ? { ...part, auto_play: allowAutoPlay && isFirstAudio } : part);
    }
  }
  return next;
}
