/**
 * DebugPanel - Tabbed interface for OpenAI events, traces, and tool information
 * Features: Real-time event streaming, trace visualization, tool call details
 */

import { useRef, useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import {
  Activity,
  Search,
  Wrench,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Zap,
  MessageSquare,
  ChevronRight,
  ChevronDown,
  Info,
} from "lucide-react";
import type { ExtendedResponseStreamEvent } from "@/types";

// Type definitions for event data structures
interface EventDataBase {
  call_id?: string;
  executor_id?: string;
  timestamp?: string;
  [key: string]: unknown;
}

interface FunctionResultData extends EventDataBase {
  result?: unknown;
  status?: "completed" | "failed";
  exception?: string;
}

interface FunctionCallData extends EventDataBase {
  name?: string;
  arguments?: string | object;
  function?: unknown;
  tool_calls?: unknown[];
}

interface WorkflowEventData extends EventDataBase {
  event_type?: string;
  data?: Record<string, unknown>;
}

interface TraceEventData extends EventDataBase {
  operation_name?: string;
  duration_ms?: number;
  status?: string;
  attributes?: Record<string, unknown>;
  span_id?: string;
  trace_id?: string;
  parent_span_id?: string | null;
  start_time?: number;
  end_time?: number;
  entity_id?: string;
  session_id?: string | null;
}

interface DebugPanelProps {
  events: ExtendedResponseStreamEvent[];
  isStreaming?: boolean;
}

// Helper function to accumulate OpenAI events into meaningful units
function processEventsForDisplay(
  events: ExtendedResponseStreamEvent[]
): ExtendedResponseStreamEvent[] {
  const processedEvents: ExtendedResponseStreamEvent[] = [];
  const functionCalls = new Map<
    string,
    {
      name?: string;
      arguments: string;
      callId: string;
      timestamp: string;
    }
  >();
  const callIdToName = new Map<string, string>(); // Track call_id -> function name mappings
  let accumulatedText = "";
  const lastFunctionCallId: string | null = null; // Track the most recent function call

  for (const event of events) {
    // Always show completion, error, workflow events, and function results
    if (
      event.type === "response.done" ||
      event.type === "error" ||
      event.type === "response.workflow_event.complete" ||
      event.type === "response.trace_event.complete" ||
      event.type === "response.trace.complete" ||
      event.type === "response.function_result.complete"
    ) {
      // Flush any accumulated text before showing these events
      if (accumulatedText.trim()) {
        processedEvents.push({
          type: "response.output_text.delta",
          delta: accumulatedText.trim(),
        } as ExtendedResponseStreamEvent);
        accumulatedText = "";
      }

      // Extract function names from trace events
      if (
        (event.type === "response.trace_event.complete" ||
          event.type === "response.trace.complete") &&
        "data" in event
      ) {
        const traceData = event.data as TraceEventData;
        if (
          traceData.attributes &&
          traceData.attributes["gen_ai.output.messages"] &&
          typeof traceData.attributes["gen_ai.output.messages"] === "string"
        ) {
          try {
            const messages = JSON.parse(
              traceData.attributes["gen_ai.output.messages"] as string
            );
            for (const msg of messages) {
              if (msg.parts) {
                for (const part of msg.parts) {
                  if (part.type === "tool_call" && part.name && part.id) {
                    // Store the call_id -> function name mapping
                    callIdToName.set(part.id, part.name);
                  }
                }
              }
            }
          } catch {
            // Ignore parsing errors
          }
        }
      }

      // For function results, ensure we have the corresponding function call
      if (
        event.type === "response.function_result.complete" &&
        "data" in event
      ) {
        const resultData = event.data as FunctionResultData;
        const callId = resultData.call_id;

        // Only create function call event if we have actual argument data
        if (callId && functionCalls.has(callId)) {
          const call = functionCalls.get(callId)!;
          const functionName =
            callIdToName.get(callId) || call.name || "unknown";

          processedEvents.push({
            type: "response.function_call.complete",
            data: {
              name: functionName,
              arguments: call.arguments,
              call_id: call.callId,
            },
          } as ExtendedResponseStreamEvent);
          functionCalls.delete(callId);
        }
      }

      processedEvents.push(event);
      continue;
    }

    // Handle function call start events
    if (event.type === "response.function_call.delta" && "data" in event) {
      const callData = event.data as FunctionCallData;
      const callId = callData.call_id || `call_${Date.now()}`;

      // Initialize or update the function call
      if (!functionCalls.has(callId)) {
        functionCalls.set(callId, {
          name: callData.name || undefined,
          arguments: "",
          callId,
          timestamp: new Date().toISOString(),
        });
      }

      // Update name if provided
      if (callData.name && callData.name.trim()) {
        functionCalls.get(callId)!.name = callData.name.trim();
      }
      continue;
    }

    // Handle function call complete events that come directly (not generated by us)
    if (event.type === "response.function_call.complete" && "data" in event) {
      // This is already a complete function call event, just pass it through
      processedEvents.push(event);
      continue;
    }

    // Handle function call arguments accumulation - ACTUAL BACKEND FORMAT
    if (event.type === "response.function_call_arguments.delta") {
      let deltaData: string = "";
      let callId: string;

      // Extract delta from actual backend format
      if ("delta" in event && typeof event.delta === "string") {
        deltaData = event.delta;
      }

      // Use a simple tracking approach since backend doesn't provide call_id in argument deltas
      if (
        "data" in event &&
        event.data &&
        (event.data as EventDataBase).call_id
      ) {
        callId = String((event.data as EventDataBase).call_id);
      } else {
        callId = lastFunctionCallId || `call_${Date.now()}`;
      }

      if (deltaData && callId) {
        // Ensure we have a function call entry
        if (!functionCalls.has(callId)) {
          functionCalls.set(callId, {
            name: "unknown", // Backend doesn't provide function name in these events
            arguments: "",
            callId,
            timestamp: new Date().toISOString(),
          });
        }

        // Accumulate the delta
        const call = functionCalls.get(callId)!;

        // Skip the initial "{}" delta that backend sends
        if (deltaData === "{}" && call.arguments === "") {
          continue;
        }

        // Accumulate and clean up the delta
        let cleanedDelta = deltaData;
        try {
          // Remove extra quotes and escaping that backend adds
          cleanedDelta = deltaData.replace(/^"|"$/g, "").replace(/\\"/g, '"');
        } catch {
          cleanedDelta = deltaData;
        }
        call.arguments += cleanedDelta;
      }
      continue;
    }

    // Handle text delta events
    if (event.type === "response.output_text.delta" && "delta" in event) {
      accumulatedText += event.delta || "";

      // Only emit if we have substantial content AND hit a natural paragraph break
      // This makes the text accumulation much more aggressive
      if (
        accumulatedText.length > 100 &&
        (accumulatedText.includes("\n\n") ||
          accumulatedText.trim().match(/[.!?]\s*$/))
      ) {
        processedEvents.push({
          type: "response.output_text.delta",
          delta: accumulatedText.trim(),
        } as ExtendedResponseStreamEvent);
        accumulatedText = "";
      }
      continue;
    }

    // Handle usage events (skip them as they're noise)
    if (event.type === "response.usage.complete") {
      continue;
    }

    // Handle other event types - pass through
    processedEvents.push(event);
  }

  // Finalize any remaining function calls that didn't get results
  for (const [, call] of functionCalls) {
    if (call.arguments.trim() && call.arguments.trim().length > 2) {
      const functionName =
        callIdToName.get(call.callId) || call.name || "unknown";
      processedEvents.push({
        type: "response.function_call.complete",
        data: {
          name: functionName,
          arguments: call.arguments,
          call_id: call.callId,
        },
      } as ExtendedResponseStreamEvent);
    }
  }

  // Finalize any remaining text
  if (accumulatedText.trim()) {
    processedEvents.push({
      type: "response.output_text.delta",
      delta: accumulatedText.trim(),
    } as ExtendedResponseStreamEvent);
  }

  return processedEvents;
}

interface EventItemProps {
  event: ExtendedResponseStreamEvent;
}

function getEventSummary(event: ExtendedResponseStreamEvent): string {
  switch (event.type) {
    case "response.output_text.delta":
      if ("delta" in event) {
        const text = event.delta || "";
        return text.length > 60 ? `${text.slice(0, 60)}...` : text;
      }
      return "Text output";

    case "response.function_call.complete":
      if ("data" in event && event.data) {
        const data = event.data as FunctionCallData;

        // Try to extract function name from various possible locations
        let functionName = data.name || "unknown";

        // Use the function name as provided, no complex inference needed
        if (!functionName || functionName === "unknown") {
          functionName = "function_call";
        }

        const argsStr = data.arguments
          ? typeof data.arguments === "string"
            ? data.arguments.slice(0, 30)
            : JSON.stringify(data.arguments).slice(0, 30)
          : "";
        return `Calling ${functionName}(${argsStr}${
          argsStr.length >= 30 ? "..." : ""
        })`;
      }
      return "Function call";

    case "response.function_call_arguments.delta":
      if ("delta" in event && event.delta) {
        return `Function arg delta: ${event.delta.slice(0, 30)}${
          event.delta.length > 30 ? "..." : ""
        }`;
      }
      return "Function arguments...";

    case "response.function_result.complete":
      if ("data" in event && event.data) {
        const data = event.data as FunctionResultData;
        const resultStr = data.result
          ? typeof data.result === "string"
            ? data.result
            : JSON.stringify(data.result)
          : "no result";
        const truncated = resultStr.slice(0, 40);
        return `Tool result: ${truncated}${
          truncated.length >= 40 ? "..." : ""
        }`;
      }
      return "Function result";

    case "response.workflow_event.complete":
      if ("data" in event && event.data) {
        const data = event.data as WorkflowEventData;
        return `Executor: ${data.executor_id || "unknown"}`;
      }
      return "Workflow event";

    case "response.trace_event.complete":
    case "response.trace.complete":
      if ("data" in event && event.data) {
        const data = event.data as TraceEventData;
        return `Trace: ${data.operation_name || "unknown"}`;
      }
      return "Trace event";

    case "response.done":
      return "Response complete";

    case "error":
      // Extract actual error message from error events
      if ("message" in event && typeof event.message === "string") {
        return event.message;
      }
      return "Error occurred";

    default:
      return `${event.type}`;
  }
}

function getEventIcon(type: string) {
  switch (type) {
    case "response.output_text.delta":
      return MessageSquare;
    case "response.function_call.complete":
    case "response.function_call.delta":
    case "response.function_call_arguments.delta":
      return Wrench;
    case "response.function_result.complete":
      return CheckCircle2;
    case "response.workflow_event.complete":
      return Activity;
    case "response.trace_event.complete":
    case "response.trace.complete":
      return Search;
    case "response.done":
      return CheckCircle2;
    case "error":
      return XCircle;
    default:
      return AlertCircle;
  }
}

function getEventColor(type: string) {
  switch (type) {
    case "response.output_text.delta":
      return "text-gray-600 dark:text-gray-400";
    case "response.function_call.complete":
    case "response.function_call.delta":
    case "response.function_call_arguments.delta":
      return "text-blue-600 dark:text-blue-400";
    case "response.function_result.complete":
      return "text-green-600 dark:text-green-400";
    case "response.workflow_event.complete":
      return "text-purple-600 dark:text-purple-400";
    case "response.trace_event.complete":
    case "response.trace.complete":
      return "text-orange-600 dark:text-orange-400";
    case "response.done":
      return "text-green-600 dark:text-green-400";
    case "error":
      return "text-red-600 dark:text-red-400";
    default:
      return "text-gray-600 dark:text-gray-400";
  }
}

function EventItem({ event }: EventItemProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const Icon = getEventIcon(event.type);
  const colorClass = getEventColor(event.type);
  const timestamp = new Date().toLocaleTimeString();
  const summary = getEventSummary(event);

  // Determine if this event has expandable content
  const hasExpandableContent =
    (event.type === "response.function_call.complete" &&
      "data" in event &&
      event.data) ||
    (event.type === "response.function_result.complete" &&
      "data" in event &&
      event.data) ||
    (event.type === "response.workflow_event.complete" &&
      "data" in event &&
      event.data) ||
    (event.type === "response.trace_event.complete" &&
      "data" in event &&
      event.data) ||
    (event.type === "response.trace.complete" &&
      "data" in event &&
      event.data) ||
    (event.type === "response.output_text.delta" &&
      "delta" in event &&
      event.delta &&
      event.delta.length > 100) ||
    // Make error events expandable to show full error details
    event.type === "error";

  return (
    <div className="border-l-2 border-muted pl-3 py-2 hover:bg-muted/50 transition-colors">
      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
        <Icon className={`h-3 w-3 ${colorClass}`} />
        <span className="font-mono">{timestamp}</span>
        <Badge variant="outline" className="text-xs py-0">
          {event.type.replace("response.", "")}
        </Badge>
      </div>

      <div className="text-sm">
        <div
          className={`flex items-center gap-2 ${
            hasExpandableContent ? "cursor-pointer" : ""
          }`}
          onClick={() => hasExpandableContent && setIsExpanded(!isExpanded)}
        >
          {hasExpandableContent && (
            <div className="text-muted-foreground">
              {isExpanded ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
            </div>
          )}
          <div className="text-muted-foreground flex-1">
            {hasExpandableContent && summary.length > 80
              ? `${summary.slice(0, 80)}...`
              : summary}
          </div>
        </div>

        {/* Expandable content */}
        {isExpanded && hasExpandableContent && (
          <div className="mt-2 ml-5 p-3 bg-muted/30 rounded border">
            <EventExpandedContent event={event} />
          </div>
        )}
      </div>
    </div>
  );
}

function EventExpandedContent({
  event,
}: {
  event: ExtendedResponseStreamEvent;
}) {
  // Handle error events with detailed information
  if (event.type === "error") {
    const errorEvent = event as ExtendedResponseStreamEvent & {
      message?: string;
      code?: string;
      param?: string;
    };
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <XCircle className="h-4 w-4 text-red-500" />
          <span className="font-semibold text-sm">Error Details</span>
        </div>
        <div className="text-xs">
          {errorEvent.message && (
            <div className="mb-2">
              <span className="font-medium text-muted-foreground">
                Message:
              </span>
              <div className="mt-1">
                <pre className="text-xs bg-destructive/10 border border-destructive/30 rounded p-2 text-destructive whitespace-pre-wrap break-all">
                  {errorEvent.message}
                </pre>
              </div>
            </div>
          )}
          {errorEvent.code && (
            <div className="mb-2">
              <span className="font-medium text-muted-foreground">Code:</span>
              <span className="ml-2 font-mono text-xs">{errorEvent.code}</span>
            </div>
          )}
          {errorEvent.param && (
            <div className="mb-2">
              <span className="font-medium text-muted-foreground">
                Parameter:
              </span>
              <span className="ml-2 font-mono text-xs">{errorEvent.param}</span>
            </div>
          )}
          <div>
            <span className="font-medium text-muted-foreground">
              Raw Event:
            </span>
            <div className="mt-1">
              <pre className="text-xs bg-background border rounded p-2 whitespace-pre-wrap break-all max-h-32 overflow-auto">
                {JSON.stringify(event, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      </div>
    );
  }

  switch (event.type) {
    case "response.function_call.complete":
      if ("data" in event && event.data) {
        const data = event.data as FunctionCallData;
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Wrench className="h-4 w-4 text-blue-500" />
              <span className="font-semibold text-sm">Function Call</span>
            </div>
            <div className="grid grid-cols-1 gap-2 text-xs">
              <div>
                <span className="font-medium text-muted-foreground">
                  Function:
                </span>
                <span className="ml-2 font-mono bg-blue-100 dark:bg-blue-900 px-2 py-1 rounded">
                  {data.name || "unknown"}
                </span>
              </div>
              {data.call_id && (
                <div>
                  <span className="font-medium text-muted-foreground">
                    Call ID:
                  </span>
                  <span className="ml-2 font-mono text-xs">{data.call_id}</span>
                </div>
              )}
              {data.arguments && (
                <div>
                  <span className="font-medium text-muted-foreground">
                    Arguments:
                  </span>
                  <div className="mt-1 max-h-32 overflow-auto">
                    <pre className="text-xs bg-background border rounded p-2 whitespace-pre-wrap max-w-full break-all">
                      {typeof data.arguments === "string"
                        ? data.arguments
                        : JSON.stringify(data.arguments, null, 1)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          </div>
        );
      }
      break;

    case "response.function_result.complete":
      if ("data" in event && event.data) {
        const data = event.data as FunctionResultData;
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-green-500" />
              <span className="font-semibold text-sm">Function Result</span>
            </div>
            <div className="grid grid-cols-1 gap-2 text-xs">
              {data.call_id && (
                <div>
                  <span className="font-medium text-muted-foreground">
                    Call ID:
                  </span>
                  <span className="ml-2 font-mono text-xs">{data.call_id}</span>
                </div>
              )}
              <div>
                <span className="font-medium text-muted-foreground">
                  Status:
                </span>
                <span
                  className={`ml-2 px-2 py-1 rounded text-xs font-medium ${
                    data.status === "completed"
                      ? "bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200"
                      : "bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200"
                  }`}
                >
                  {data.status || "unknown"}
                </span>
              </div>
              {data.result !== undefined && (
                <div>
                  <span className="font-medium text-muted-foreground">
                    Result:
                  </span>
                  <div className="mt-1 max-h-32 overflow-auto">
                    <pre className="text-xs bg-background border rounded p-2 whitespace-pre-wrap max-w-full break-all">
                      {typeof data.result === "string"
                        ? data.result
                        : JSON.stringify(data.result, null, 1)}
                    </pre>
                  </div>
                </div>
              )}
              {data.exception !== null && data.exception !== undefined && (
                <div>
                  <span className="font-medium text-destructive">Error:</span>
                  <div className="mt-1">
                    <pre className="text-xs bg-destructive/10 border border-destructive/30 rounded p-2 text-destructive whitespace-pre-wrap break-all">
                      {data.exception}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          </div>
        );
      }
      break;

    case "response.workflow_event.complete":
      if ("data" in event && event.data) {
        const data = event.data as WorkflowEventData;
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-purple-500" />
              <span className="font-semibold text-sm">Workflow Event</span>
            </div>
            <div className="grid grid-cols-1 gap-2 text-xs">
              <div>
                <span className="font-medium text-muted-foreground">
                  Event Type:
                </span>
                <span className="ml-2 font-mono bg-purple-100 dark:bg-purple-900 px-2 py-1 rounded">
                  {data.event_type || "unknown"}
                </span>
              </div>
              {data.executor_id && (
                <div>
                  <span className="font-medium text-muted-foreground">
                    Executor:
                  </span>
                  <span className="ml-2 font-mono">{data.executor_id}</span>
                </div>
              )}
              {data.timestamp && (
                <div>
                  <span className="font-medium text-muted-foreground">
                    Timestamp:
                  </span>
                  <span className="ml-2 font-mono text-xs">
                    {data.timestamp}
                  </span>
                </div>
              )}
              {data.data && (
                <div>
                  <span className="font-medium text-muted-foreground">
                    Data:
                  </span>
                  <div className="mt-1 max-h-32 overflow-auto">
                    <pre className="text-xs bg-background border rounded p-2 whitespace-pre-wrap max-w-full break-all">
                      {typeof data.data === "string"
                        ? data.data
                        : JSON.stringify(data.data, null, 1)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          </div>
        );
      }
      break;

    case "response.trace_event.complete":
    case "response.trace.complete":
      if ("data" in event && event.data) {
        const data = event.data as TraceEventData;
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Search className="h-4 w-4 text-orange-500" />
              <span className="font-semibold text-sm">Trace Event</span>
            </div>
            <div className="grid grid-cols-1 gap-2 text-xs">
              <div>
                <span className="font-medium text-muted-foreground">
                  Operation:
                </span>
                <span className="ml-2 font-mono bg-orange-100 dark:bg-orange-900 px-2 py-1 rounded">
                  {data.operation_name || "unknown"}
                </span>
              </div>
              {data.span_id && (
                <div>
                  <span className="font-medium text-muted-foreground">
                    Span ID:
                  </span>
                  <span className="ml-2 font-mono text-xs">{data.span_id}</span>
                </div>
              )}
              {data.trace_id && (
                <div>
                  <span className="font-medium text-muted-foreground">
                    Trace ID:
                  </span>
                  <span className="ml-2 font-mono text-xs">
                    {data.trace_id}
                  </span>
                </div>
              )}
              {data.duration_ms && (
                <div>
                  <span className="font-medium text-muted-foreground">
                    Duration:
                  </span>
                  <span className="ml-2 font-mono text-xs">
                    {Number(data.duration_ms).toFixed(2)}ms
                  </span>
                </div>
              )}
              {data.status && (
                <div>
                  <span className="font-medium text-muted-foreground">
                    Status:
                  </span>
                  <span
                    className={`ml-2 px-2 py-1 rounded text-xs font-medium ${
                      data.status === "StatusCode.UNSET" || data.status === "OK"
                        ? "bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200"
                        : "bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200"
                    }`}
                  >
                    {data.status || "unknown"}
                  </span>
                </div>
              )}
              {data.entity_id && (
                <div>
                  <span className="font-medium text-muted-foreground">
                    Entity:
                  </span>
                  <span className="ml-2 font-mono text-xs">
                    {data.entity_id}
                  </span>
                </div>
              )}
              {data.attributes && Object.keys(data.attributes).length > 0 && (
                <div>
                  <span className="font-medium text-muted-foreground">
                    Attributes:
                  </span>
                  <div className="mt-1 max-h-32 overflow-auto">
                    <pre className="text-xs bg-background border rounded p-2 whitespace-pre-wrap break-all">
                      {(() => {
                        try {
                          // Try to pretty-print JSON, and unescape string values that contain JSON
                          const attrs = { ...data.attributes };
                          Object.keys(attrs).forEach((key) => {
                            if (
                              typeof attrs[key] === "string" &&
                              attrs[key].startsWith("[")
                            ) {
                              try {
                                attrs[key] = JSON.parse(attrs[key]);
                              } catch {
                                // Keep original if parsing fails
                              }
                            }
                          });
                          return JSON.stringify(attrs, null, 2);
                        } catch {
                          return JSON.stringify(data.attributes, null, 2);
                        }
                      })()}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          </div>
        );
      }
      break;

    case "response.output_text.delta":
      if ("delta" in event && event.delta) {
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-gray-500" />
              <span className="font-semibold text-sm">Text Output</span>
            </div>
            <div className="max-h-32 overflow-auto">
              <pre className="text-xs bg-background border rounded p-2 whitespace-pre-wrap max-w-full break-all">
                {event.delta}
              </pre>
            </div>
          </div>
        );
      }
      break;

    default:
      return (
        <div className="text-xs text-muted-foreground">
          <pre className="bg-background border rounded p-2 overflow-auto max-h-32">
            {JSON.stringify(event, null, 2)}
          </pre>
        </div>
      );
  }

  return null;
}

function EventsTab({
  events,
  isStreaming,
}: {
  events: ExtendedResponseStreamEvent[];
  isStreaming?: boolean;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Process events to accumulate tool calls and reduce noise
  const processedEvents = processEventsForDisplay(events);

  // Reverse events so latest appears at top
  const reversedEvents = [...processedEvents].reverse();

  return (
    <div className="h-full">
      <div className="flex items-center justify-between p-3 border-b">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4" />
          <span className="font-medium">Events</span>
          <Badge variant="outline">
            {processedEvents.length}
            {events.length > processedEvents.length
              ? ` (${events.length} raw)`
              : ""}
          </Badge>
        </div>
        {isStreaming && (
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <div className="h-2 w-2 animate-pulse rounded-full bg-green-500 dark:bg-green-400" />
            Streaming
          </div>
        )}
      </div>

      <ScrollArea ref={scrollRef}>
        <div className="p-3">
          {processedEvents.length === 0 ? (
            <div className="text-center text-muted-foreground text-sm py-8">
              {events.length === 0
                ? "No events yet. Start a conversation to see real-time events."
                : "Processing events... Accumulated events will appear here."}
            </div>
          ) : (
            <div className="space-y-2">
              {reversedEvents.map((event, index) => (
                <EventItem key={`${event.type}-${index}`} event={event} />
              ))}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

function TracesTab({ events }: { events: ExtendedResponseStreamEvent[] }) {
  // ONLY show actual trace events - handle both event type formats
  const traceEvents = events.filter(
    (e) =>
      e.type === "response.trace_event.complete" ||
      e.type === "response.trace.complete"
  );

  // Reverse to show latest traces at the top
  const reversedTraceEvents = [...traceEvents].reverse();

  return (
    <div className="h-full">
      <div className="flex items-center gap-2 p-3 border-b">
        <Search className="h-4 w-4" />
        <span className="font-medium">Traces</span>
        <Badge variant="outline">{traceEvents.length}</Badge>
      </div>

      <ScrollArea className="">
        <div className="p-3">
          {traceEvents.length === 0 ? (
            <div className="text-center text-muted-foreground text-sm py-8">
              No trace data available.
              <br />
              {events && events.length > 0 && (
                <div className="mt-3 text-xs border rounded p-2">
                  {" "}
                  <Info className="inline h-4 w-4 mr-1  " />
                  You may have to set the environment variable{" "}
                  <span className="font-mono bg-accent/10 px-1 rounded">
                    ENABLE_OTEL=true
                  </span>{" "}
                  to enable tracing.
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              {reversedTraceEvents.map((event, index) => (
                <TraceEventItem key={index} event={event} />
              ))}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

function TraceEventItem({ event }: { event: ExtendedResponseStreamEvent }) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (
    (event.type !== "response.trace_event.complete" &&
      event.type !== "response.trace.complete") ||
    !("data" in event)
  ) {
    return (
      <div className="border rounded p-3 text-red-600 dark:text-red-400 text-xs">
        Error: Expected trace event but got {event.type}
      </div>
    );
  }

  const data = event.data as TraceEventData;

  // Use actual trace timestamp if available, fallback to current time
  let timestamp = new Date().toLocaleTimeString();
  if (data.end_time) {
    timestamp = new Date(data.end_time * 1000).toLocaleTimeString();
  } else if (data.start_time) {
    timestamp = new Date(data.start_time * 1000).toLocaleTimeString();
  } else if (data.timestamp) {
    timestamp = new Date(data.timestamp).toLocaleTimeString();
  }

  const operationName = data.operation_name || "Unknown Operation";
  const duration = data.duration_ms
    ? `${Number(data.duration_ms).toFixed(1)}ms`
    : "";
  const entityId = data.entity_id || "";

  return (
    <div className="border-l-2 border-muted pl-3 py-2 hover:bg-muted/50 transition-colors">
      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
        <Search className="h-3 w-3 text-orange-600 dark:text-orange-400" />
        <span className="font-mono">{timestamp}</span>
        <Badge variant="outline" className="text-xs py-0">
          trace
        </Badge>
        {duration && (
          <Badge variant="secondary" className="text-xs py-0">
            {duration}
          </Badge>
        )}
      </div>

      <div className="text-sm">
        <div
          className="flex items-center gap-2 cursor-pointer"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <div className="text-muted-foreground">
            {isExpanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
          </div>
          <div className="text-muted-foreground flex-1">
            <span className="font-medium">{operationName}</span>
            {entityId && <span className="ml-2 text-xs">({entityId})</span>}
          </div>
        </div>

        {/* Expandable content */}
        {isExpanded && (
          <div className="mt-2 ml-5 p-3 bg-muted/30 rounded border">
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Search className="h-4 w-4 text-orange-500" />
                <span className="font-semibold text-sm">Trace Details</span>
              </div>
              <div className="grid grid-cols-1 gap-2 text-xs">
                <div>
                  <span className="font-medium text-muted-foreground">
                    Operation:
                  </span>
                  <span className="ml-2 font-mono bg-orange-100 dark:bg-orange-900 px-2 py-1 rounded">
                    {operationName}
                  </span>
                </div>
                {data.span_id && (
                  <div>
                    <span className="font-medium text-muted-foreground">
                      Span ID:
                    </span>
                    <span className="ml-2 font-mono text-xs">
                      {data.span_id}
                    </span>
                  </div>
                )}
                {data.trace_id && (
                  <div>
                    <span className="font-medium text-muted-foreground">
                      Trace ID:
                    </span>
                    <span className="ml-2 font-mono text-xs">
                      {data.trace_id}
                    </span>
                  </div>
                )}
                {data.parent_span_id && (
                  <div>
                    <span className="font-medium text-muted-foreground">
                      Parent Span:
                    </span>
                    <span className="ml-2 font-mono text-xs">
                      {data.parent_span_id}
                    </span>
                  </div>
                )}
                {data.duration_ms && (
                  <div>
                    <span className="font-medium text-muted-foreground">
                      Duration:
                    </span>
                    <span className="ml-2 font-mono text-xs">
                      {Number(data.duration_ms).toFixed(2)}ms
                    </span>
                  </div>
                )}
                {data.status && (
                  <div>
                    <span className="font-medium text-muted-foreground">
                      Status:
                    </span>
                    <span
                      className={`ml-2 px-2 py-1 rounded text-xs font-medium ${
                        data.status === "StatusCode.UNSET" ||
                        data.status === "OK"
                          ? "bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200"
                          : "bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200"
                      }`}
                    >
                      {data.status || "unknown"}
                    </span>
                  </div>
                )}
                {data.entity_id && (
                  <div>
                    <span className="font-medium text-muted-foreground">
                      Entity:
                    </span>
                    <span className="ml-2 font-mono text-xs">
                      {data.entity_id}
                    </span>
                  </div>
                )}
                {data.attributes && Object.keys(data.attributes).length > 0 && (
                  <div>
                    <span className="font-medium text-muted-foreground">
                      Attributes:
                    </span>
                    <div className="mt-1 max-h-32 overflow-auto">
                      <pre className="text-xs bg-background border rounded p-2 whitespace-pre-wrap max-w-full break-all">
                        {(() => {
                          try {
                            // Try to pretty-print JSON, and unescape string values that contain JSON
                            const attrs = { ...data.attributes };
                            Object.keys(attrs).forEach((key) => {
                              if (
                                typeof attrs[key] === "string" &&
                                attrs[key].startsWith("[")
                              ) {
                                try {
                                  attrs[key] = JSON.parse(attrs[key]);
                                } catch {
                                  // Keep original if parsing fails
                                }
                              }
                            });
                            return JSON.stringify(attrs, null, 2);
                          } catch {
                            return JSON.stringify(data.attributes, null, 2);
                          }
                        })()}
                      </pre>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ToolsTab({ events }: { events: ExtendedResponseStreamEvent[] }) {
  // Process events first to get clean tool calls
  const processedEvents = processEventsForDisplay(events);

  // Create call->result pairs in chronological order
  const toolEvents: ExtendedResponseStreamEvent[] = [];
  const functionCalls = processedEvents.filter(
    (event) => event.type === "response.function_call.complete"
  );
  const functionResults = events.filter(
    (event) => event.type === "response.function_result.complete"
  );

  // Create a map of call_id to results for easy lookup
  const resultsByCallId = new Map();
  functionResults.forEach((result) => {
    if (
      "data" in result &&
      result.data &&
      (result.data as EventDataBase).call_id
    ) {
      resultsByCallId.set(
        String((result.data as EventDataBase).call_id),
        result
      );
    }
  });

  // Add call->result pairs in chronological order
  functionCalls.forEach((call) => {
    toolEvents.push(call);

    // Find matching result and add it immediately after the call
    if ("data" in call && call.data && (call.data as EventDataBase).call_id) {
      const callId = String((call.data as EventDataBase).call_id);
      const matchingResult = resultsByCallId.get(callId);
      if (matchingResult) {
        toolEvents.push(matchingResult);
        resultsByCallId.delete(callId); // Remove so we don't add it again
      }
    }
  });

  // Add any orphaned results that didn't match calls
  resultsByCallId.forEach((result) => {
    toolEvents.push(result);
  });

  // Reverse to show latest tools at the top
  const reversedToolEvents = [...toolEvents].reverse();

  return (
    <div className="h-full">
      <div className="flex items-center gap-2 p-3 border-b">
        <Wrench className="h-4 w-4" />
        <span className="font-medium">Tools</span>
        <Badge variant="outline">{toolEvents.length}</Badge>
      </div>

      <ScrollArea>
        <div className="p-3">
          {toolEvents.length === 0 ? (
            <div className="text-center text-muted-foreground text-sm py-8">
              No tool executions yet. Tool calls will appear here during
              conversations.
            </div>
          ) : (
            <div className="space-y-3">
              {reversedToolEvents.map((event, index) => (
                <ToolEventItem key={index} event={event} />
              ))}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

function ToolEventItem({ event }: { event: ExtendedResponseStreamEvent }) {
  if (!("data" in event)) {
    return null;
  }

  const data = event.data as EventDataBase;
  const timestamp = new Date().toLocaleTimeString();

  // Check if this is a function call event
  const isFunctionCall = event.type === "response.function_call.complete";
  const isFunctionResult = event.type === "response.function_result.complete";

  if (!isFunctionCall && !isFunctionResult) {
    return null;
  }

  return (
    <div className="border rounded p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Zap className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />
          <span className="font-medium text-sm">
            {isFunctionCall ? "Tool Call" : "Tool Result"}
          </span>
          {isFunctionCall && data.name !== undefined && (
            <span className="text-xs text-muted-foreground">
              ({String(data.name)})
            </span>
          )}
        </div>
        <span className="text-xs text-muted-foreground font-mono">
          {timestamp}
        </span>
      </div>

      {/* Function Calls */}
      {isFunctionCall && (
        <div className="p-2 bg-blue-50 dark:bg-blue-950/50 border border-blue-200 dark:border-blue-800 rounded">
          <div className="flex items-center gap-2 mb-2">
            <Wrench className="h-3 w-3 text-blue-600 dark:text-blue-400" />
            <span className="text-xs font-mono bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 px-2 py-1 rounded">
              CALL
            </span>
            <span className="font-medium text-sm">
              {String(data.name || "unknown")}
            </span>
          </div>

          {data.arguments !== undefined && (
            <div className="text-xs">
              <span className="text-muted-foreground mb-1 block">
                Arguments:
              </span>
              <pre className="p-2 bg-background border rounded text-xs overflow-auto max-h-32 max-w-full break-all whitespace-pre-wrap">
                {typeof data.arguments === "string"
                  ? data.arguments
                  : JSON.stringify(data.arguments, null, 1)}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Function Results */}
      {isFunctionResult && (
        <div className="p-2 bg-green-50 dark:bg-green-950/50 border border-green-200 dark:border-green-800 rounded">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle2 className="h-3 w-3 text-green-600 dark:text-green-400" />
            <span className="text-xs font-mono bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 px-2 py-1 rounded">
              RESULT
            </span>
          </div>

          <div className="text-xs">
            <span className="text-muted-foreground mb-1 block">Result:</span>
            <pre className="p-2 bg-background border rounded text-xs overflow-auto max-h-32 max-w-full break-all whitespace-pre-wrap">
              {typeof data.result === "string"
                ? data.result
                : JSON.stringify(data.result, null, 1)}
            </pre>
          </div>

          {data.exception !== null && data.exception !== undefined && (
            <div className="mt-2 p-2 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 rounded">
              <span className="text-xs text-red-600 dark:text-red-400">
                Error: {String(data.exception)}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function DebugPanel({ events, isStreaming = false }: DebugPanelProps) {
  return (
    <div className=" overflow-auto h-[calc(100vh-3.7rem)] border-l">
      <Tabs defaultValue="events" className="h-full flex flex-col">
        <div className="px-3 pt-3">
          <TabsList className="w-full">
            <TabsTrigger value="events" className="flex-1">
              Events
            </TabsTrigger>
            <TabsTrigger value="traces" className="flex-1">
              Traces
            </TabsTrigger>
            <TabsTrigger value="tools" className="flex-1">
              Tools
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="events" className="flex-1 mt-0">
          <EventsTab events={events} isStreaming={isStreaming} />
        </TabsContent>

        <TabsContent value="traces" className="flex-1 mt-0">
          <TracesTab events={events} />
        </TabsContent>

        <TabsContent value="tools" className="flex-1 mt-0">
          <ToolsTab events={events} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
