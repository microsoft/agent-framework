/**
 * StreamingRenderer - Handles accumulation and display of streaming content
 */

import { useState, useEffect } from "react";
import { ContentRenderer } from "./ContentRenderer";
import type { Contents, MessageRenderState } from "./types";
import { isTextContent } from "@/types/agent-framework";

interface StreamingRendererProps {
  contents: Contents[];
  isStreaming?: boolean;
  className?: string;
}

export function StreamingRenderer({
  contents,
  isStreaming = false,
  className,
}: StreamingRendererProps) {
  const [renderState, setRenderState] = useState<MessageRenderState>({
    textAccumulator: "",
    dataContentItems: [],
    functionCalls: [],
    errors: [],
    isComplete: !isStreaming,
  });

  useEffect(() => {
    // Process and accumulate content
    let textAccumulator = "";
    const dataContentItems: Contents[] = [];
    const functionCalls: Contents[] = [];
    const errors: Contents[] = [];

    contents.forEach((content) => {
      if (isTextContent(content)) {
        textAccumulator += content.text;
      } else if (content.type === "data") {
        // Only show data content when streaming is complete or item is complete
        if (!isStreaming) {
          dataContentItems.push(content);
        }
      } else if (content.type === "function_call") {
        functionCalls.push(content);
      } else if (content.type === "error") {
        errors.push(content);
      } else {
        // Other content types (uri, function_result, etc.)
        dataContentItems.push(content);
      }
    });

    setRenderState({
      textAccumulator,
      dataContentItems,
      functionCalls,
      errors,
      isComplete: !isStreaming,
    });
  }, [contents, isStreaming]);

  const hasTextContent = renderState.textAccumulator.length > 0;
  const hasOtherContent =
    renderState.dataContentItems.length > 0 ||
    renderState.functionCalls.length > 0 ||
    renderState.errors.length > 0;

  return (
    <div className={className}>
      {/* Render accumulated text with streaming indicator */}
      {hasTextContent && (
        <div className="whitespace-pre-wrap break-words">
          {renderState.textAccumulator}
          {isStreaming && hasTextContent && (
            <span className="ml-1 inline-block h-2 w-2 animate-pulse rounded-full bg-current" />
          )}
        </div>
      )}

      {/* Render other content types when complete or non-data items immediately */}
      {hasOtherContent && (
        <div className="mt-2 space-y-2">
          {renderState.errors.map((content, index) => (
            <ContentRenderer key={`error-${index}`} content={content} />
          ))}

          {renderState.functionCalls.map((content, index) => (
            <ContentRenderer key={`function-${index}`} content={content} />
          ))}

          {renderState.dataContentItems.map((content, index) => (
            <ContentRenderer
              key={`data-${index}`}
              content={content}
              isStreaming={isStreaming}
            />
          ))}
        </div>
      )}

      {/* Show loading indicator when streaming and no text content yet */}
      {isStreaming && !hasTextContent && !hasOtherContent && (
        <div className="flex items-center space-x-1">
          <div className="flex space-x-1">
            <div className="h-2 w-2 animate-bounce rounded-full bg-current [animation-delay:-0.3s]" />
            <div className="h-2 w-2 animate-bounce rounded-full bg-current [animation-delay:-0.15s]" />
            <div className="h-2 w-2 animate-bounce rounded-full bg-current" />
          </div>
        </div>
      )}
    </div>
  );
}