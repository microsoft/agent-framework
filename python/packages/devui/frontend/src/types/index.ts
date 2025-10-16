/**
 * Core TypeScript types for DevUI Frontend
 * Matches backend API models for strict type safety
 */

export type AgentType = "agent" | "workflow";
export type AgentSource = "directory" | "in_memory" | "remote_gallery";
export type StreamEventType =
  | "agent_run_update"
  | "workflow_event"
  | "workflow_structure"
  | "completion"
  | "error"
  | "debug_trace"
  | "trace_span";

export interface EnvVarRequirement {
  name: string;
  description: string;
  required: boolean;
  example?: string;
}

export interface AgentInfo {
  id: string;
  name?: string;
  description?: string;
  type: AgentType;
  source: AgentSource;
  tools: string[];
  has_env: boolean;
  module_path?: string;
  required_env_vars?: EnvVarRequirement[];
  metadata?: Record<string, unknown>; // Backend metadata including lazy_loaded flag
  // Agent-specific fields
  instructions?: string;
  model?: string;
  chat_client_type?: string;
  context_providers?: string[];
  middleware?: string[];
}

// JSON Schema types for workflow input
export interface JSONSchemaProperty {
  type: "string" | "number" | "integer" | "boolean" | "array" | "object";
  description?: string;
  default?: unknown;
  enum?: string[];
  format?: string;
  properties?: Record<string, JSONSchemaProperty>;
  required?: string[];
  items?: JSONSchemaProperty;
}

export interface JSONSchema {
  type: "string" | "number" | "integer" | "boolean" | "array" | "object";
  description?: string;
  default?: unknown;
  enum?: string[];
  format?: string;
  properties?: Record<string, JSONSchemaProperty>;
  required?: string[];
  items?: JSONSchemaProperty;
}

export interface WorkflowInfo extends Omit<AgentInfo, "tools"> {
  executors: string[]; // List of executor IDs in this workflow
  workflow_dump?: import("./workflow").Workflow; // Typed workflow structure
  mermaid_diagram?: string;
  // Input specification for dynamic form generation
  input_schema: JSONSchema; // JSON Schema for workflow input
  input_type_name: string; // Human-readable input type name
  start_executor_id: string; // Entry point executor ID
}

// OpenAI Conversations API (standard)
export interface Conversation {
  id: string;
  object: "conversation";
  created_at: number;
  metadata?: Record<string, string>;
}

export interface RunAgentRequest {
  input: import("./agent-framework").ResponseInputParam;
  conversation_id?: string; // OpenAI standard conversation parameter
}

export interface RunWorkflowRequest {
  input_data: Record<string, unknown>;
  conversation_id?: string;
}

// Legacy types - DEPRECATED - use new structured events from openai.ts instead

// Re-export OpenAI types
export type {
  ResponseStreamEvent,
  ResponseTextDeltaEvent,
  OpenAIResponse,
  OpenAIError,
  // New structured event types
  ExtendedResponseStreamEvent,
  ResponseWorkflowEventComplete,
  ResponseTraceEventComplete,
  ResponseOutputItemAddedEvent,
  ResponseCompletedEvent,
  ResponseFunctionResultComplete,
  StructuredEvent,
} from "./openai";

// Re-export Agent Framework types
export type {
  AgentFrameworkRequest,
  AgentFrameworkExtraBody,
  ResponseInputParam,
  ResponseInputTextParam,
  ResponseInputImageParam,
  ResponseInputFileParam,
} from "./agent-framework";

export interface HealthResponse {
  status: "healthy";
  agents_dir?: string;
  version: string;
}

// Chat message types matching Agent Framework
export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  contents: import("./agent-framework").Contents[];
  timestamp: string;
  streaming?: boolean;
  author_name?: string;
  message_id?: string;
  error?: boolean; // Flag to indicate this is an error message
  usage?: {
    total_tokens: number;
    prompt_tokens: number;
    completion_tokens: number;
  };
}

// UI State types
export interface AppState {
  selectedAgent?: AgentInfo | WorkflowInfo;
  currentConversation?: Conversation;
  agents: AgentInfo[];
  workflows: WorkflowInfo[];
  isLoading: boolean;
  error?: string;
}

export interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
  // streamEvents removed - use OpenAI events directly instead
}

// DevUI-specific: Pending approval state
export interface PendingApproval {
  request_id: string;
  function_call: {
    id: string;
    name: string;
    arguments: Record<string, unknown>;
  };
}
