/**
 * TypeScript interfaces matching OpenAI Responses API and Agent Framework Python types
 * Generated from OpenAI SDK and Agent Framework _types.py, _threads.py, and _events.py
 */

// OpenAI Responses API Types - EXACT match to OpenAI SDK
export interface ResponseInputTextParam {
  text: string;
  /** The type of the input item. Always `input_text`. */
  type: "input_text";
}

export interface ResponseInputImageParam {
  /** The detail level of the image to be sent to the model. One of `high`, `low`, or `auto`. Defaults to `auto`. */
  detail: "low" | "high" | "auto";
  /** The type of the input item. Always `input_image`. */
  type: "input_image";
  /** The ID of the file to be sent to the model. */
  file_id?: string;
  /** The URL of the image to be sent to the model. A fully qualified URL or base64 encoded image in a data URL. */
  image_url?: string;
}

export interface ResponseInputFileParam {
  /** The type of the input item. Always `input_file`. */
  type: "input_file";
  /** The content of the file to be sent to the model. */
  file_data: string;
  /** The ID of the file to be sent to the model. */
  file_id?: string;
  /** The URL of the file to be sent to the model. */
  file_url: string;
  /** The name of the file to be sent to the model. */
  filename: string;
}

// DevUI Extension: Function Approval Response Input
export interface ResponseInputFunctionApprovalParam {
  /** The type of the input item. Always `function_approval_response`. */
  type: "function_approval_response";
  /** The ID of the approval request being responded to. */
  request_id: string;
  /** Whether the function call is approved. */
  approved: boolean;
  /** The function call being approved/rejected. */
  function_call: {
    id: string;
    name: string;
    arguments: Record<string, unknown>;
  };
}

export type ResponseInputContent =
  | ResponseInputTextParam
  | ResponseInputImageParam
  | ResponseInputFileParam
  | ResponseInputFunctionApprovalParam;

export interface EasyInputMessage {
  type?: "message";
  role: "user" | "assistant" | "system" | "developer";
  content: string | ResponseInputContent[];
}

export type ResponseInputItem = EasyInputMessage;
export type ResponseInputParam = ResponseInputItem[];

// Agent Framework extension fields (matches backend AgentFrameworkExtraBody)
export interface AgentFrameworkExtraBody {
  entity_id: string;
  checkpoint_id?: string; // Optional checkpoint ID for workflow resume
  // input_data removed - now using standard input field for all data
}

// Agent Framework Request - OpenAI ResponseCreateParams with extensions
export interface AgentFrameworkRequest {
  model?: string;
  input: string | ResponseInputParam | Record<string, unknown>; // Union type matching OpenAI + dict for workflows
  stream?: boolean;

  // OpenAI conversation parameter (standard!)
  conversation?: string | { id: string };

  // Common OpenAI optional fields
  instructions?: string;
  metadata?: Record<string, unknown>;
  temperature?: number;
  max_output_tokens?: number;
  top_p?: number;
  tools?: Record<string, unknown>[];

  // Reasoning parameters (for o-series models)
  reasoning?: {
    effort?: "minimal" | "low" | "medium" | "high";
    summary?: "auto" | "concise" | "detailed";
  };

  // Agent Framework extension - strongly typed
  extra_body?: AgentFrameworkExtraBody;
  entity_id?: string; // Allow entity_id as top-level field too
}

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
  uri: string;
  media_type?: string;
}

export interface UriContent extends BaseContent {
  type: "uri";
  uri: string;
  media_type?: string;
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
  model_id?: string;
  created_at?: CreatedAtT;
  finish_reason?: FinishReason;
  additional_properties?: Record<string, unknown>;
  raw_representation?: unknown;
}

// Agent thread (internal AgentFramework type - not exposed via DevUI API)
// Note: DevUI uses OpenAI Conversations API. This type represents the internal
// AgentThread used by the framework for execution, wrapped by ConversationStore.
export interface AgentThread {
  service_thread_id?: string;
  message_store?: unknown; // ChatMessageStore - could be typed further if needed
}

// Workflow events
export interface WorkflowEvent {
  type?: string; // Event class name like "WorkflowOutputEvent", "WorkflowCompletedEvent", "ExecutorInvokedEvent", etc.
  data?: unknown;
  executor_id?: string; // Present for executor-related events
  source_executor_id?: string; // Present for WorkflowOutputEvent
}

export interface WorkflowStartedEvent extends WorkflowEvent {
  // Event-specific data for workflow start
  readonly event_type: "workflow_started";
}

export interface WorkflowCompletedEvent extends WorkflowEvent {
  // Event-specific data for workflow completion (legacy)
  readonly event_type: "workflow_completed";
}

export interface WorkflowOutputEvent extends WorkflowEvent {
  // Event-specific data for workflow output (new)
  readonly event_type: "workflow_output";
  source_executor_id: string; // ID of executor that yielded the output
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

// Helper type guards for Agent Framework content types
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
