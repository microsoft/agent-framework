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

// Custom Agent Framework OpenAI event types with structured data
export interface ResponseWorkflowEventComplete {
  type: "response.workflow_event.complete";
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

export interface ResponseFunctionResultComplete {
  type: "response.function_result.complete";
  data: {
    call_id: string;
    result: unknown;
    status: "completed" | "failed";
    exception?: string;
    timestamp: string;
  };
  call_id: string;
  item_id: string;
  output_index: number;
  sequence_number: number;
}

// Removed - using ResponseTraceEventComplete defined below

export interface ResponseUsageEventComplete {
  type: "response.usage.complete";
  data: {
    usage_data: Record<string, unknown>;
    total_tokens: number;
    completion_tokens: number;
    prompt_tokens: number;
    timestamp: string;
  };
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

// Trace event - matching actual backend output
export interface ResponseTraceEventComplete {
  type: "response.trace_event.complete";
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
  type: "response.trace.complete";
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

// Union type for all structured events
export type StructuredEvent =
  | ResponseWorkflowEventComplete
  | ResponseFunctionResultComplete
  | ResponseTraceEventComplete
  | ResponseTraceComplete
  | ResponseUsageEventComplete
  | ResponseFunctionCallComplete
  | ResponseFunctionCallDelta
  | ResponseFunctionCallArgumentsDelta
  | ResponseErrorEvent;

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
