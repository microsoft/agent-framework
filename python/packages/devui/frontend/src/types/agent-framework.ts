/**
 * TypeScript interfaces matching Agent Framework Python types
 * Generated from Agent Framework _types.py, _threads.py, and _events.py
 */

// Base types
export type Role = "system" | "user" | "assistant" | "tool";
export type FinishReason = "content_filter" | "length" | "stop" | "tool_calls";
export type CreatedAtT = string; // ISO timestamp

// Content type discriminator
export type ContentType =
  | "text"
  | "function_call"
  | "function_result"
  | "text_reasoning"
  | "data"
  | "uri"
  | "error"
  | "usage"
  | "hosted_file"
  | "hosted_vector_store";

// Base content interface
export interface BaseContent {
  type: ContentType;
  annotations?: unknown[];
  additional_properties?: Record<string, unknown>;
  raw_representation?: unknown;
}

// Specific content types
export interface TextContent extends BaseContent {
  type: "text";
  text: string;
}

export interface FunctionCallContent extends BaseContent {
  type: "function_call";
  call_id: string;
  name: string;
  arguments?: string | Record<string, unknown>;
  exception?: unknown;
}

export interface FunctionResultContent extends BaseContent {
  type: "function_result";
  call_id: string;
  result?: unknown;
  exception?: unknown;
}

export interface TextReasoningContent extends BaseContent {
  type: "text_reasoning";
  text: string;
  reasoning: string;
}

export interface DataContent extends BaseContent {
  type: "data";
  data: unknown;
  mime_type?: string;
}

export interface UriContent extends BaseContent {
  type: "uri";
  uri: string;
  mime_type?: string;
}

export interface ErrorContent extends BaseContent {
  type: "error";
  error: string;
  error_code?: string;
}

export interface UsageContent extends BaseContent {
  type: "usage";
  usage_data: unknown;
}

export interface HostedFileContent extends BaseContent {
  type: "hosted_file";
  file_id: string;
}

export interface HostedVectorStoreContent extends BaseContent {
  type: "hosted_vector_store";
  vector_store_id: string;
}

// Union type for all content
export type Contents =
  | TextContent
  | FunctionCallContent
  | FunctionResultContent
  | TextReasoningContent
  | DataContent
  | UriContent
  | ErrorContent
  | UsageContent
  | HostedFileContent
  | HostedVectorStoreContent;

// Usage details
export interface UsageDetails {
  completion_tokens?: number;
  prompt_tokens?: number;
  total_tokens?: number;
  additional_properties?: Record<string, unknown>;
}

// Agent run response update (streaming)
export interface AgentRunResponseUpdate {
  contents: Contents[];
  role?: Role;
  author_name?: string;
  response_id?: string;
  message_id?: string;
  created_at?: CreatedAtT;
  additional_properties?: Record<string, unknown>;
  raw_representation?: unknown;
  // Additional property that may be present (concatenated text from all TextContent)
  text?: string;
}

// Agent run response (final)
export interface AgentRunResponse {
  messages: ChatMessage[];
  response_id?: string;
  created_at?: CreatedAtT;
  usage_details?: UsageDetails;
  raw_representation?: unknown;
  additional_properties?: Record<string, unknown>;
}

// Chat message
export interface ChatMessage {
  contents: Contents[];
  role?: Role;
  author_name?: string;
  message_id?: string;
  created_at?: CreatedAtT;
  additional_properties?: Record<string, unknown>;
  raw_representation?: unknown;
}

// Chat response update (model client streaming)
export interface ChatResponseUpdate {
  contents: Contents[];
  role?: Role;
  author_name?: string;
  response_id?: string;
  message_id?: string;
  conversation_id?: string;
  ai_model_id?: string;
  created_at?: CreatedAtT;
  finish_reason?: FinishReason;
  additional_properties?: Record<string, unknown>;
  raw_representation?: unknown;
}

// Agent thread
export interface AgentThread {
  service_thread_id?: string;
  message_store?: unknown; // ChatMessageStore - could be typed further if needed
}

// Workflow events
export interface WorkflowEvent {
  type?: string; // Event class name like "WorkflowCompletedEvent", "ExecutorInvokeEvent", etc.
  data?: unknown;
  executor_id?: string; // Present for executor-related events
}

export interface WorkflowStartedEvent extends WorkflowEvent {
  // Event-specific data for workflow start
  readonly event_type: "workflow_started";
}

export interface WorkflowCompletedEvent extends WorkflowEvent {
  // Event-specific data for workflow completion
  readonly event_type: "workflow_completed";
}

export interface WorkflowWarningEvent extends WorkflowEvent {
  data: string; // Warning message
}

export interface WorkflowErrorEvent extends WorkflowEvent {
  data: Error; // Exception
}

export interface ExecutorEvent extends WorkflowEvent {
  executor_id: string;
}

export interface AgentRunUpdateEvent extends ExecutorEvent {
  data?: AgentRunResponseUpdate;
}

export interface AgentRunEvent extends ExecutorEvent {
  data?: AgentRunResponse;
}

// Span event structure (from OpenTelemetry)
export interface SpanEvent {
  name: string;
  timestamp: number;
  attributes: Record<string, unknown>;
}

// Trace span for streaming
export interface TraceSpan {
  span_id: string;
  parent_span_id?: string;
  operation_name: string;
  start_time: number;
  end_time?: number;
  duration_ms?: number;
  attributes: Record<string, unknown>;
  events: SpanEvent[];
  status: string;
  raw_span?: Record<string, unknown>;
}

// Debug stream event wrapper (from devui)
export interface DebugStreamEvent {
  type:
    | "agent_run_update"
    | "workflow_event"
    | "workflow_structure"
    | "completion"
    | "error"
    | "debug_trace"
    | "trace_span";
  update?: AgentRunResponseUpdate; // Now properly typed!
  event?: WorkflowEvent; // Now properly typed!
  trace_span?: TraceSpan; // Real-time trace span
  // Workflow structure data
  workflow_dump?: import("./workflow").Workflow;
  mermaid_diagram?: string;
  timestamp: string;
  debug_metadata?: Record<string, unknown>; // Will be removed
  error?: string;
  thread_id?: string;
}

// Helper type guards
export function isTextContent(content: Contents): content is TextContent {
  return content.type === "text";
}

export function isFunctionCallContent(
  content: Contents
): content is FunctionCallContent {
  return content.type === "function_call";
}

export function isFunctionResultContent(
  content: Contents
): content is FunctionResultContent {
  return content.type === "function_result";
}

export function isAgentRunUpdateEvent(
  event: DebugStreamEvent
): event is DebugStreamEvent & { update: AgentRunResponseUpdate } {
  return event.type === "agent_run_update" && event.update != null;
}

export function isWorkflowEvent(
  event: DebugStreamEvent
): event is DebugStreamEvent & { event: WorkflowEvent } {
  return event.type === "workflow_event" && event.event != null;
}

export function isTraceSpanEvent(
  event: DebugStreamEvent
): event is DebugStreamEvent & { trace_span: TraceSpan } {
  return event.type === "trace_span" && event.trace_span != null;
}
