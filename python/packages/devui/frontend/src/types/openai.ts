/**
 * OpenAI Response API types for Agent Framework Server
 * Based on OpenAI's official response types
 */

// Core OpenAI Response Stream Event
export interface ResponseStreamEvent {
  type: string;
  item_id?: string;
  output_index?: number;
  content_index?: number;
  sequence_number?: number;

  // Different event types
  delta?: string; // For text delta events
  logprobs?: Record<string, unknown>[];

  // Meta info
  id?: string;
  object?: string;
  created_at?: number;
}

// Standard OpenAI Response Lifecycle Events
export interface ResponseCreatedEvent {
  type: "response.created";
  response: {
    id: string;
    status: "in_progress";
    created_at: number;
    output?: any[];
  };
  sequence_number?: number;
}

export interface ResponseInProgressEvent {
  type: "response.in_progress";
  response: {
    id: string;
    status: "in_progress";
  };
  sequence_number?: number;
}

export interface ResponseCompletedEvent {
  type: "response.completed";
  response: {
    id: string;
    status: "completed";
    usage?: any;  // Optional usage information
    model?: string;  // Optional model information
  };
  sequence_number?: number;
}

export interface ResponseFailedEvent {
  type: "response.failed";
  response: {
    id: string;
    status: "failed";
    error?: any;
  };
  sequence_number?: number;
}

// Custom Agent Framework OpenAI event types with structured data
export interface ResponseWorkflowEventComplete {
  type: "response.workflow_event.completed";
  data: {
    event_type: string;
    data?: Record<string, unknown>;
    executor_id?: string;
    timestamp: string;
  };
  executor_id?: string;
  item_id: string;
  output_index: number;
  sequence_number: number;
}


// Function call event types - matching actual backend output
export interface ResponseFunctionCallComplete {
  type: "response.function_call.complete";
  data: {
    name: string;
    arguments: string | object;
    call_id: string;
  };
  item_id?: string;
  output_index?: number;
  sequence_number?: number;
}

export interface ResponseFunctionCallDelta {
  type: "response.function_call.delta";
  data: {
    name?: string;
    call_id?: string;
  };
  item_id?: string;
  output_index?: number;
  sequence_number?: number;
}

export interface ResponseFunctionCallArgumentsDelta {
  type: "response.function_call_arguments.delta";
  delta: string;
  data?: {
    call_id?: string;
    arguments?: string;
  };
  item_id?: string;
  output_index?: number;
  sequence_number?: number;
}

// OpenAI Responses API - Function Tool Call Item
export interface ResponseFunctionToolCall {
  id: string; // Item ID
  call_id: string; // Call ID for pairing with results
  name: string; // Function name
  arguments: string; // JSON arguments
  type: "function_call";
  status?: "in_progress" | "completed" | "incomplete";
}

// DevUI Extension: Output item types for response.output_item.added events
export interface ResponseOutputImageItem {
  id: string;
  type: "output_image";
  image_url: string;
  alt_text?: string;
  mime_type: string;
}

export interface ResponseOutputFileItem {
  id: string;
  type: "output_file";
  filename: string;
  file_url?: string;
  file_data?: string;
  mime_type: string;
}

export interface ResponseOutputDataItem {
  id: string;
  type: "output_data";
  data: string;
  mime_type: string;
  description?: string;
}

// Workflow Item Types - flexible interface for any workflow item
export interface WorkflowItem {
  type: string;  // "executor_action", "workflow_action", "message", or any future type
  id: string;
  status?: "in_progress" | "completed" | "failed" | "cancelled";
  [key: string]: any;  // Allow any additional fields
}

// Executor Action Item (DevUI specific)
export interface ExecutorActionItem extends WorkflowItem {
  type: "executor_action";
  executor_id: string;
  metadata?: Record<string, any>;
  result?: any;
  error?: any;
}

// Type guard for executor actions
export function isExecutorAction(item: WorkflowItem): item is ExecutorActionItem {
  return item.type === "executor_action" && "executor_id" in item;
}

// Union of all possible output items
export type ResponseOutputItem =
  | ResponseFunctionToolCall
  | ResponseOutputImageItem
  | ResponseOutputFileItem
  | ResponseOutputDataItem
  | ExecutorActionItem
  | WorkflowItem;

// OpenAI Responses API - Output Item Added Event
// OpenAI standard: Output item added event (extended to support our output types)
export interface ResponseOutputItemAddedEvent {
  type: "response.output_item.added";
  item: ResponseOutputItem;
  output_index: number;
  sequence_number?: number;
}

export interface ResponseOutputItemDoneEvent {
  type: "response.output_item.done";
  item: ResponseOutputItem;
  output_index: number;
  sequence_number?: number;
}

// Trace event - matching actual backend output
export interface ResponseTraceEventComplete {
  type: "response.trace.completed";
  data: {
    operation_name?: string;
    duration_ms?: number;
    status?: string;
    attributes?: Record<string, unknown>;
    timestamp: string;
  };
  item_id?: string;
  output_index?: number;
  sequence_number?: number;
}

// New trace event format from backend
export interface ResponseTraceComplete {
  type: "response.trace.completed";
  data: {
    type?: string;
    span_id?: string;
    trace_id?: string;
    parent_span_id?: string | null;
    operation_name?: string;
    start_time?: number;
    end_time?: number;
    duration_ms?: number;
    attributes?: Record<string, unknown>;
    status?: string;
    session_id?: string | null;
    entity_id?: string;
    timestamp?: string;
  };
  item_id?: string;
  output_index?: number;
  sequence_number?: number;
}

// Error event - matching backend ResponseErrorEvent
export interface ResponseErrorEvent extends ResponseStreamEvent {
  type: "error";
  message: string;
  code?: string;
  param?: string;
  sequence_number: number;
}

// DevUI Extension: Function Approval Events
export interface ResponseFunctionApprovalRequestedEvent {
  type: "response.function_approval.requested";
  request_id: string;
  function_call: {
    id: string;
    name: string;
    arguments: Record<string, unknown>;
  };
  item_id: string;
  output_index: number;
  sequence_number: number;
}

export interface ResponseFunctionApprovalRespondedEvent {
  type: "response.function_approval.responded";
  request_id: string;
  approved: boolean;
  item_id: string;
  output_index: number;
  sequence_number: number;
}

// DevUI Extension: Function Result Complete
export interface ResponseFunctionResultComplete {
  type: "response.function_result.complete";
  call_id: string;
  output: string;
  status: "in_progress" | "completed" | "incomplete";
  item_id: string;
  output_index: number;
  sequence_number: number;
  timestamp?: string;  // Optional ISO timestamp for UI display
}

// DevUI Extension: Workflow Requests Human Input (HIL)
export interface ResponseRequestInfoEvent {
  type: "response.request_info.requested";
  request_id: string;
  source_executor_id: string;
  request_type: string;
  request_data: Record<string, unknown>;
  request_schema: Record<string, unknown>;
  item_id: string;
  output_index: number;
  sequence_number: number;
  timestamp: string;
}

// DevUI Extension: Turn Separator (UI-only event for grouping)
export interface TurnSeparatorEvent {
  type: "debug.turn_separator";
  timestamp: string;
  collapsed?: boolean;
}

// Union type for all structured events
export type StructuredEvent =
  | ResponseCreatedEvent
  | ResponseInProgressEvent
  | ResponseCompletedEvent
  | ResponseFailedEvent
  | ResponseWorkflowEventComplete
  | ResponseTraceEventComplete
  | ResponseTraceComplete
  | ResponseOutputItemAddedEvent
  | ResponseOutputItemDoneEvent
  | ResponseFunctionCallComplete
  | ResponseFunctionCallDelta
  | ResponseFunctionCallArgumentsDelta
  | ResponseFunctionResultComplete
  | ResponseRequestInfoEvent
  | ResponseErrorEvent
  | ResponseFunctionApprovalRequestedEvent
  | ResponseFunctionApprovalRespondedEvent
  | TurnSeparatorEvent;

// Extended stream event that includes our structured events
export type ExtendedResponseStreamEvent = ResponseStreamEvent | StructuredEvent;

// Text delta event - the main one we'll use
export interface ResponseTextDeltaEvent extends ResponseStreamEvent {
  type: "response.output_text.delta";
  delta: string;
  item_id: string;
  output_index: number;
  content_index: number;
  sequence_number: number;
  logprobs: Record<string, unknown>[];
}

// OpenAI Response for non-streaming
export interface OpenAIResponse {
  id: string;
  object: "response";
  created_at: number;
  model: string;
  output: ResponseOutputMessage[];
  usage: ResponseUsage;
  parallel_tool_calls: boolean;
  tool_choice: string;
  tools: Record<string, unknown>[];
}

export interface ResponseOutputMessage {
  type: "message";
  role: "assistant";
  content: ResponseOutputText[];
  id: string;
  status: "completed" | "failed" | "in_progress";
}

export interface ResponseOutputText {
  type: "output_text";
  text: string;
  annotations: Record<string, unknown>[];
}

export interface ResponseUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  input_tokens_details: {
    cached_tokens: number;
  };
  output_tokens_details: {
    reasoning_tokens: number;
  };
}


// Request format for Agent Framework
// AgentFrameworkRequest moved to agent-framework.ts to avoid conflicts

// Error response
export interface OpenAIError {
  error: {
    message: string;
    type: string;
    code?: string;
  };
}

// ============================================================================
// OpenAI Conversations API Types - for conversation history
// ============================================================================

// Message content types (what goes inside Message.content[])
export interface MessageTextContent {
  type: "text";
  text: string;
}

export interface MessageInputTextContent {
  type: "input_text";
  text: string;
}

export interface MessageOutputTextContent {
  type: "output_text";
  text: string;
  annotations?: any[];
  logprobs?: any[];
}

export interface MessageInputImage {
  type: "input_image";
  image_url: string;
  detail?: "low" | "high" | "auto";
  file_id?: string;
}

export interface MessageInputFile {
  type: "input_file";
  file_url?: string;
  file_data?: string;
  file_id?: string;
  filename?: string;
}

// DevUI Extension: Function approval request content (shown in chat)
export interface MessageFunctionApprovalRequestContent {
  type: "function_approval_request";
  request_id: string;
  status: "pending" | "approved" | "rejected";
  function_call: {
    id: string;
    name: string;
    arguments: Record<string, unknown>;
  };
}

// DevUI Extension: Function approval response content
export interface MessageFunctionApprovalResponseContent {
  type: "function_approval_response";
  request_id: string;
  approved: boolean;
  function_call: {
    id: string;
    name: string;
    arguments: Record<string, unknown>;
  };
}

// ============================================================================
// DevUI Extension: Output Content Types (Agent-Generated Media/Data)
// ============================================================================
// These extend the OpenAI Responses API to support rich content outputs
// that aren't natively supported (images, files, data). They mirror the
// input types but for agent outputs.

export interface MessageOutputImage {
  type: "output_image";
  image_url: string; // URL or data URI (data:image/png;base64,...)
  alt_text?: string;
  mime_type: string;
}

export interface MessageOutputFile {
  type: "output_file";
  filename: string;
  file_url?: string;
  file_data?: string; // base64
  mime_type: string;
}

export interface MessageOutputData {
  type: "output_data";
  data: string;
  mime_type: string;
  description?: string;
}

export type MessageContent =
  | MessageTextContent
  | MessageInputTextContent
  | MessageOutputTextContent
  | MessageInputImage
  | MessageInputFile
  | MessageOutputImage
  | MessageOutputFile
  | MessageOutputData
  | MessageFunctionApprovalRequestContent
  | MessageFunctionApprovalResponseContent;

// Message item (user/assistant messages with content)
export interface ConversationMessage {
  id: string;
  type: "message";
  role: "user" | "assistant" | "system" | "tool";
  content: MessageContent[];
  status: "in_progress" | "completed" | "incomplete";
  created_at?: number; // Unix timestamp in seconds - when this message was created
  usage?: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
}

// Function call item (separate from message)
export interface ConversationFunctionCall {
  id: string;
  type: "function_call";
  call_id: string;
  name: string;
  arguments: string;
  status: "in_progress" | "completed" | "incomplete";
  created_at?: number; // Unix timestamp in seconds - when this function call was made
}

// Function call output item
export interface ConversationFunctionCallOutput {
  id: string;
  type: "function_call_output";
  call_id: string;
  output: string;
  status?: "in_progress" | "completed" | "incomplete";
  created_at?: number; // Unix timestamp in seconds - when this function result was received
}

// Union of all conversation item types
export type ConversationItem =
  | ConversationMessage
  | ConversationFunctionCall
  | ConversationFunctionCallOutput;

// Conversation metadata
export interface Conversation {
  id: string;
  object: "conversation";
  created_at: number;
  metadata?: Record<string, string>;
}

// List response
export interface ConversationItemsListResponse {
  object: "list";
  data: ConversationItem[];
  has_more: boolean;
}
