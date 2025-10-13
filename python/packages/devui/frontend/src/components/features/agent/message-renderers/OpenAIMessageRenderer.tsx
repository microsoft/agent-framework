/**
 * OpenAI Message Renderer - Renders OpenAI ConversationItem types
 * This replaces the legacy AgentFramework-based renderer
 */

import type { ConversationItem } from "@/types/openai";
import {
  OpenAIContentRenderer,
  FunctionCallRenderer,
  FunctionResultRenderer,
} from "./OpenAIContentRenderer";

interface OpenAIMessageRendererProps {
  item: ConversationItem;
  className?: string;
}

export function OpenAIMessageRenderer({
  item,
  className,
}: OpenAIMessageRendererProps) {
  // Handle message items (user/assistant with content)
  if (item.type === "message") {
    // Determine if message is actively streaming
    const isStreaming = item.status === "in_progress";
    const hasContent = item.content.length > 0;

    return (
      <div className={className}>
        {item.content.map((content, index) => (
          <OpenAIContentRenderer
            key={index}
            content={content}
            className={index > 0 ? "mt-2" : ""}
            isStreaming={isStreaming}
          />
        ))}

        {/* Show typing indicator when streaming with no content yet */}
        {isStreaming && !hasContent && (
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

  // Handle function call items
  if (item.type === "function_call") {
    return (
      <FunctionCallRenderer
        name={item.name}
        arguments={item.arguments}
        className={className}
      />
    );
  }

  // Handle function result items
  if (item.type === "function_call_output") {
    return (
      <FunctionResultRenderer
        output={item.output}
        call_id={item.call_id}
        className={className}
      />
    );
  }

  // Unknown item type
  return null;
}
