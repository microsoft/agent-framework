/**
 * MessageRenderer - Main orchestrator for rendering message contents
 */

import { StreamingRenderer } from "./StreamingRenderer";
import { ContentRenderer } from "./ContentRenderer";
import type { MessageRendererProps } from "./types";

export function MessageRenderer({
  contents,
  isStreaming = false,
  className,
}: MessageRendererProps) {
  // If not streaming, render each content item individually
  if (!isStreaming) {
    return (
      <div className={className}>
        {contents.map((content, index) => (
          <ContentRenderer
            key={index}
            content={content}
            isStreaming={false}
            className={index > 0 ? "mt-2" : ""}
          />
        ))}
      </div>
    );
  }

  // For streaming, use the streaming renderer for smart accumulation
  return (
    <StreamingRenderer
      contents={contents}
      isStreaming={isStreaming}
      className={className}
    />
  );
}