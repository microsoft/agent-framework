/**
 * Core TypeScript types for DevUI Frontend
 * Matches backend API models for strict type safety
 */

export type AgentType = "agent" | "workflow";
export type AgentSource = "directory" | "in_memory";
export type StreamEventType =
  | "agent_run_update"
  | "workflow_event"
  | "workflow_structure"
  | "completion"
  | "error"
  | "debug_trace"
  | "trace_span";

export interface AgentInfo {
  id: string;
  name?: string;
  description?: string;
  type: AgentType;
  source: AgentSource;
  tools: string[];
  has_env: boolean;
  module_path?: string;
}

export interface WorkflowInfo extends AgentInfo {
  workflow_dump?: any; // Raw workflow.model_dump() - zero abstraction
  mermaid_diagram?: string;
}

export interface ThreadInfo {
  id: string;
  agent_id: string;
  created_at: string;
  message_count: number;
}

export interface SessionInfo {
  thread_id: string;
  agent_id: string;
  created_at: string;
  messages: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
}

export interface RunAgentRequest {
  message: string;
  thread_id?: string;
  options?: Record<string, unknown>;
}

// Re-export from agent-framework types with proper typing
export type {
  DebugStreamEvent,
  AgentRunResponseUpdate,
  WorkflowEvent,
} from "./agent-framework";

export interface HealthResponse {
  status: "healthy";
  agents_dir?: string;
  version: string;
}

// Chat message types for UI
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  streaming?: boolean;
}

// UI State types
export interface AppState {
  selectedAgent?: AgentInfo;
  currentThread?: ThreadInfo;
  agents: AgentInfo[];
  workflows: AgentInfo[];
  isLoading: boolean;
  error?: string;
}

export interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
  streamEvents: import("./agent-framework").DebugStreamEvent[];
}
