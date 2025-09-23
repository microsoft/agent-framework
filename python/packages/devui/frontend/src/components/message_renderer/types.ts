/**
 * Types for message rendering components
 */

// Re-export and extend types from agent-framework
import type {
  Contents,
  TextContent,
  DataContent,
  UriContent,
  FunctionCallContent,
  FunctionResultContent,
  ErrorContent,
  AgentRunResponseUpdate,
} from "@/types/agent-framework";

export type {
  Contents,
  TextContent,
  DataContent,
  UriContent,
  FunctionCallContent,
  FunctionResultContent,
  ErrorContent,
  AgentRunResponseUpdate,
};

// UI-specific types for message rendering
export interface MessageRenderState {
  // Track accumulated content during streaming
  textAccumulator: string;
  dataContentItems: Contents[];
  functionCalls: Contents[];
  errors: Contents[];
  isComplete: boolean;
}

export interface RenderProps {
  content: Contents;
  isStreaming?: boolean;
  className?: string;
}

export interface MessageRendererProps {
  contents: Contents[];
  isStreaming?: boolean;
  className?: string;
}