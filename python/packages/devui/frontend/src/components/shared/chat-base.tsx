/**
 * ChatBase - Shared streaming logic and utilities
 * Common patterns used by both agent and workflow views
 */

import { useRef, useCallback } from "react";
import type { ChatMessage, DebugStreamEvent } from "@/types";
import type { AgentRunResponseUpdate } from "@/types/agent-framework";
import {
  isTextContent,
  isFunctionCallContent,
  isFunctionResultContent,
} from "@/types/agent-framework";

// Function call accumulator to handle streaming function arguments
interface FunctionCallAccumulator {
  [callId: string]: {
    name: string;
    arguments: string;
    isComplete: boolean;
  };
}

// Helper to extract text content from AgentRunResponseUpdate with proper function call accumulation
export function extractMessageContent(
  update: AgentRunResponseUpdate,
  functionCallAccumulator: { current: FunctionCallAccumulator }
): string {
  if (!update) return "";

  // Use the text property if available (concatenated text from all TextContent)
  if (update.text && typeof update.text === "string") {
    return update.text;
  }

  // Fallback to manual extraction
  if (!update.contents || !Array.isArray(update.contents)) {
    return "";
  }

  const textParts: string[] = [];

  for (const content of update.contents) {
    if (isTextContent(content)) {
      textParts.push(content.text);
    } else if (isFunctionCallContent(content)) {
      // Accumulate function call arguments by call_id
      const callId = content.call_id;
      const name = content.name || "";
      const args = content.arguments || "";

      if (!functionCallAccumulator.current[callId]) {
        functionCallAccumulator.current[callId] = {
          name,
          arguments: "",
          isComplete: false,
        };
      }

      // Accumulate arguments
      if (typeof args === "string") {
        functionCallAccumulator.current[callId].arguments += args;
      } else if (args !== null && args !== undefined) {
        // If we get a complete object, stringify it
        functionCallAccumulator.current[callId].arguments =
          JSON.stringify(args);
        functionCallAccumulator.current[callId].isComplete = true;
      }

      // Update name if provided (sometimes name comes later)
      if (name) {
        functionCallAccumulator.current[callId].name = name;
      }

      // Try to parse arguments to see if they're complete JSON
      const accumulated = functionCallAccumulator.current[callId];
      let isValidJson = false;
      try {
        if (accumulated.arguments.trim()) {
          JSON.parse(accumulated.arguments);
          isValidJson = true;
          accumulated.isComplete = true;
        }
      } catch {
        // Not complete JSON yet, continue accumulating
      }

      // Only show function call if we have complete arguments or it's marked complete
      if (accumulated.isComplete && accumulated.name) {
        textParts.push(`Calling ${accumulated.name}(${accumulated.arguments})`);
      } else if (isValidJson && accumulated.name) {
        textParts.push(`Calling ${accumulated.name}(${accumulated.arguments})`);
      }
      // If incomplete, don't add anything to textParts yet
    } else if (isFunctionResultContent(content)) {
      // Tool results are already shown in the debug panel, so we don't include them in main chat
      // textParts.push(`Tool result: ${content.result}`);
    }
  }

  const result = textParts.join("\n");
  return result;
}

// Helper to update rich message contents by accumulating text chunks
export function updateRichMessageContents(
  existingContents: ChatMessage["contents"], 
  newChunk: string
): ChatMessage["contents"] {
  if (!newChunk) return existingContents;

  const updatedContents = [...existingContents];
  
  // Find existing text content to accumulate into
  const textContentIndex = updatedContents.findIndex(content => content.type === "text");
  
  if (textContentIndex >= 0) {
    // Update existing text content
    const existingTextContent = updatedContents[textContentIndex];
    if (existingTextContent.type === "text") {
      updatedContents[textContentIndex] = {
        ...existingTextContent,
        text: (existingTextContent.text || "") + newChunk,
      };
    }
  } else {
    // Add new text content
    updatedContents.push({
      type: "text",
      text: newChunk,
    } as import("@/types/agent-framework").TextContent);
  }
  
  return updatedContents;
}

// Hook for managing function call accumulator
export function useFunctionCallAccumulator() {
  const functionCallAccumulator = useRef<FunctionCallAccumulator>({});
  
  const clearAccumulator = useCallback(() => {
    functionCallAccumulator.current = {};
  }, []);
  
  return { functionCallAccumulator, clearAccumulator };
}

// Common debug event handler type
export type DebugEventHandler = (event: DebugStreamEvent) => void;