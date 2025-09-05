/**
 * DebugPanel - Tabbed interface for events, traces, and tool information
 * Features: Real-time event streaming, trace visualization, tool call details
 */

import { useRef, useEffect } from "react";
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
  Play,
} from "lucide-react";
import type { DebugStreamEvent } from "@/types";
import type {
  AgentRunResponseUpdate,
  SpanEvent,
} from "@/types/agent-framework";
import {
  isTextContent,
  isFunctionCallContent,
  isFunctionResultContent,
} from "@/types/agent-framework";

// Type for span events with proper structure
interface DebugPanelProps {
  events: DebugStreamEvent[];
  isStreaming?: boolean;
}

// Helper function to accumulate events into meaningful units
function processEventsForDisplay(
  events: DebugStreamEvent[]
): DebugStreamEvent[] {
  const processedEvents: DebugStreamEvent[] = [];
  let currentToolCall: {
    name?: string;
    arguments?: string | object;
    callId?: string;
    timestamp: string;
  } | null = null;
  let accumulatedText = "";
  let lastTextTimestamp = "";

  for (const event of events) {
    // Always show completion, error, and workflow events
    if (
      event.type === "completion" ||
      event.type === "error" ||
      event.type === "workflow_event"
    ) {
      // Flush any accumulated text before showing these events
      if (accumulatedText.trim()) {
        processedEvents.push({
          type: "agent_run_update",
          timestamp: lastTextTimestamp,
          update: {
            contents: [{ type: "text", text: accumulatedText.trim() }],
          },
        } as DebugStreamEvent);
        accumulatedText = "";
      }
      processedEvents.push(event);
      continue;
    }

    if (event.type === "agent_run_update" && event.update?.contents) {
      const contents = event.update.contents;

      // Handle function calls - accumulate until we have a complete call
      const functionCalls = contents.filter(isFunctionCallContent);
      if (functionCalls.length > 0) {
        const call = functionCalls[0];

        // If this is a new function call (has a name), finalize any previous call
        if (call.name && call.name.trim()) {
          if (currentToolCall && currentToolCall.name) {
            // Emit the previous complete tool call
            processedEvents.push({
              type: "agent_run_update",
              timestamp: currentToolCall.timestamp,
              update: {
                contents: [
                  {
                    type: "function_call",
                    name: currentToolCall.name,
                    arguments: currentToolCall.arguments,
                    call_id: currentToolCall.callId,
                  },
                ],
              },
            } as DebugStreamEvent);
          }

          // Start new tool call
          currentToolCall = {
            name: call.name,
            arguments: call.arguments || "",
            callId: call.call_id,
            timestamp: event.timestamp,
          };
        } else if (currentToolCall && call.arguments) {
          // Accumulate arguments for current tool call
          if (
            typeof currentToolCall.arguments === "string" &&
            typeof call.arguments === "string"
          ) {
            currentToolCall.arguments += call.arguments;
          } else {
            currentToolCall.arguments = call.arguments;
          }
        }
        continue;
      }

      // Handle function results - always show these
      const functionResults = contents.filter(isFunctionResultContent);
      if (functionResults.length > 0) {
        // Finalize any pending tool call first
        if (currentToolCall && currentToolCall.name) {
          processedEvents.push({
            type: "agent_run_update",
            timestamp: currentToolCall.timestamp,
            update: {
              contents: [
                {
                  type: "function_call",
                  name: currentToolCall.name,
                  arguments: currentToolCall.arguments,
                  call_id: currentToolCall.callId,
                },
              ],
            },
          } as DebugStreamEvent);
          currentToolCall = null;
        }

        processedEvents.push(event);
        continue;
      }

      // Handle text content - accumulate until we have substantial content
      const textContents = contents.filter(isTextContent);
      if (textContents.length > 0) {
        const newText = textContents.map((c) => c.text).join("");
        accumulatedText += newText;
        lastTextTimestamp = event.timestamp;

        // Only emit if we have substantial content AND hit a natural paragraph break
        // This makes the text accumulation much more aggressive
        if (
          accumulatedText.length > 100 &&
          (accumulatedText.includes("\n\n") ||
            accumulatedText.trim().match(/[.!?]\s*$/))
        ) {
          processedEvents.push({
            type: "agent_run_update",
            timestamp: lastTextTimestamp,
            update: {
              contents: [{ type: "text", text: accumulatedText.trim() }],
            },
          } as DebugStreamEvent);
          accumulatedText = "";
        }
        continue;
      }

      // Handle other content types - but filter out usage events which are noise
      const otherContents = contents.filter(
        (c) =>
          !isTextContent(c) &&
          !isFunctionCallContent(c) &&
          !isFunctionResultContent(c)
      );

      if (otherContents.length > 0) {
        // Skip usage events as they're just noise - filter them out
        const nonUsageContents = otherContents.filter(
          (c) => c.type !== "usage"
        );

        if (nonUsageContents.length > 0) {
          processedEvents.push({
            ...event,
            update: {
              ...event.update,
              contents: nonUsageContents,
            },
          });
        }
      }
    }
  }

  // Finalize any remaining accumulated content
  if (currentToolCall && currentToolCall.name) {
    processedEvents.push({
      type: "agent_run_update",
      timestamp: currentToolCall.timestamp,
      update: {
        contents: [
          {
            type: "function_call",
            name: currentToolCall.name,
            arguments: currentToolCall.arguments,
            call_id: currentToolCall.callId,
          },
        ],
      },
    } as DebugStreamEvent);
  }

  if (accumulatedText.trim()) {
    processedEvents.push({
      type: "agent_run_update",
      timestamp: lastTextTimestamp,
      update: {
        contents: [{ type: "text", text: accumulatedText.trim() }],
      },
    } as DebugStreamEvent);
  }

  return processedEvents;
}

interface EventItemProps {
  event: DebugStreamEvent;
}

function getUpdateSummary(update: AgentRunResponseUpdate): string {
  if (!update || !update.contents) return "Update received";

  const contents = update.contents;

  // Look for function calls first (most important to show)
  const functionCalls = contents.filter(isFunctionCallContent);
  if (functionCalls.length > 0) {
    const call = functionCalls[0];
    const argsStr =
      typeof call.arguments === "string"
        ? call.arguments.slice(0, 30)
        : JSON.stringify(call.arguments).slice(0, 30);
    return `Calling ${call.name}(${argsStr}${
      argsStr.length >= 30 ? "..." : ""
    })`;
  }

  // Look for function results
  const functionResults = contents.filter(isFunctionResultContent);
  if (functionResults.length > 0) {
    const result = functionResults[0];
    const resultStr =
      typeof result.result === "string"
        ? result.result
        : JSON.stringify(result.result);
    const truncated = resultStr.slice(0, 40);
    return `Tool result: ${truncated}${truncated.length >= 40 ? "..." : ""}`;
  }

  // Look for text content
  const textContents = contents.filter(isTextContent);
  if (textContents.length > 0) {
    const text = textContents.map((c) => c.text).join(" ");
    return text.length > 60 ? `${text.slice(0, 60)}...` : text;
  }

  // Show other content types
  if (contents.length > 0) {
    const types = contents.map((c) => c.type).join(", ");
    return `Content: ${types}`;
  }

  return "Content update";
}

function getEventSummary(event: unknown): string {
  if (!event || typeof event !== "object") return "Event received";

  // Try to extract meaningful info from workflow event
  const eventObj = event as Record<string, unknown>;

  if (eventObj.executor_id) {
    return `Executor: ${eventObj.executor_id}`;
  }

  if (eventObj.data) {
    const data = eventObj.data;
    if (typeof data === "string") {
      return `${data.slice(0, 50)}${data.length > 50 ? "..." : ""}`;
    }
    return `Workflow event with data`;
  }

  return "Workflow event";
}

function getEventIcon(type: DebugStreamEvent["type"]) {
  switch (type) {
    case "agent_run_update":
      return Activity;
    case "workflow_event":
      return Activity;
    case "completion":
      return CheckCircle2;
    case "error":
      return XCircle;
    case "debug_trace":
      return Search;
    default:
      return AlertCircle;
  }
}

function getEventColor(type: DebugStreamEvent["type"]) {
  switch (type) {
    case "agent_run_update":
      return "text-blue-600 dark:text-blue-400";
    case "workflow_event":
      return "text-purple-600 dark:text-purple-400";
    case "completion":
      return "text-green-600 dark:text-green-400";
    case "error":
      return "text-red-600 dark:text-red-400";
    case "debug_trace":
      return "text-orange-600 dark:text-orange-400";
    default:
      return "text-gray-600 dark:text-gray-400";
  }
}

function EventItem({ event }: EventItemProps) {
  const Icon = getEventIcon(event.type);
  const colorClass = getEventColor(event.type);
  const timestamp = new Date(event.timestamp).toLocaleTimeString();

  return (
    <div className="border-l-2 border-muted pl-3 py-2 hover:bg-muted/50 transition-colors">
      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
        <Icon className={`h-3 w-3 ${colorClass}`} />
        <span className="font-mono">{timestamp}</span>
        <Badge variant="outline" className="text-xs py-0">
          {event.type}
        </Badge>
      </div>

      <div className="text-sm flex items-center gap-2">
        {event.error ? (
          <>
            <XCircle className="h-3 w-3 text-red-600 dark:text-red-400 flex-shrink-0" />
            <div className="text-red-600 dark:text-red-400">{event.error}</div>
          </>
        ) : event.update ? (
          <>
            {(() => {
              const update = event.update;
              if (!update.contents)
                return (
                  <Activity className="h-3 w-3 text-muted-foreground flex-shrink-0" />
                );

              const hasFunctionCall = update.contents.some(
                isFunctionCallContent
              );
              const hasFunctionResult = update.contents.some(
                isFunctionResultContent
              );
              const hasText = update.contents.some(isTextContent);

              if (hasFunctionCall)
                return (
                  <Wrench className="h-3 w-3 text-blue-600 dark:text-blue-400 flex-shrink-0" />
                );
              if (hasFunctionResult)
                return (
                  <CheckCircle2 className="h-3 w-3 text-green-600 dark:text-green-400 flex-shrink-0" />
                );
              if (hasText)
                return (
                  <MessageSquare className="h-3 w-3 text-gray-600 dark:text-gray-400 flex-shrink-0" />
                );
              return (
                <Activity className="h-3 w-3 text-muted-foreground flex-shrink-0" />
              );
            })()}
            <div className="text-muted-foreground">
              {getUpdateSummary(event.update)}
            </div>
          </>
        ) : event.event ? (
          <>
            <Play className="h-3 w-3 text-purple-600 dark:text-purple-400 flex-shrink-0" />
            <div className="text-muted-foreground">
              {getEventSummary(event.event)}
            </div>
          </>
        ) : (
          <>
            <CheckCircle2 className="h-3 w-3 text-green-600 dark:text-green-400 flex-shrink-0" />
            <div className="text-muted-foreground">Completed</div>
          </>
        )}
      </div>
    </div>
  );
}

function EventsTab({
  events,
  isStreaming,
}: {
  events: DebugStreamEvent[];
  isStreaming?: boolean;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Process events to accumulate tool calls and reduce noise
  const processedEvents = processEventsForDisplay(events);

  // Auto-scroll to bottom for new events
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [processedEvents]);

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
              {processedEvents.map((event, index) => (
                <EventItem key={`${event.timestamp}-${index}`} event={event} />
              ))}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

function TracesTab({ events }: { events: DebugStreamEvent[] }) {
  // ONLY show actual OpenTelemetry trace spans - no debug metadata events
  const traceEvents = events.filter((e) => e.type === "trace_span");

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
              No trace data available. Enable trace capture in options.
            </div>
          ) : (
            <div className="space-y-3">
              {traceEvents.map((event, index) => (
                <TraceSpanItem key={index} event={event} />
              ))}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

function TraceSpanItem({ event }: { event: DebugStreamEvent }) {
  // This function should only be called with trace_span events
  if (!event.trace_span) {
    return (
      <div className="border rounded p-3 text-red-600 dark:text-red-400 text-xs">
        Error: Expected trace_span event but got {event.type}
      </div>
    );
  }

  const span = event.trace_span;
  console.log("Rendering TraceSpanItem for span:", span);
  return (
    <div className="border rounded p-3">
      <div className="flex flex-col gap-2 mb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <Activity className="h-4 w-4 text-blue-600 dark:text-blue-400 flex-shrink-0" />
            <span className="font-medium text-sm truncate">
              {span.operation_name}
            </span>
          </div>
          <span className="text-xs text-muted-foreground font-mono flex-shrink-0">
            {new Date(event.timestamp).toLocaleTimeString()}
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {span.duration_ms && (
            <Badge variant="secondary" className="text-xs">
              {span.duration_ms.toFixed(1)}ms
            </Badge>
          )}
          {span.status === "StatusCode.OK" || span.status === "OK" ? (
            <div className="flex items-center gap-1 text-xs">
              <div className="h-2 w-2 rounded-full bg-green-500" />
              <span className="text-green-700 dark:text-green-400 font-medium">
                {span.status}
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-1 text-xs">
              <div
                className={`h-2 w-2 rounded-full ${
                  span.status?.includes("ERROR") ||
                  span.status?.includes("FAIL")
                    ? "bg-red-500"
                    : "bg-gray-400"
                }`}
              />
              <span
                className={`font-medium ${
                  span.status?.includes("ERROR") ||
                  span.status?.includes("FAIL")
                    ? "text-red-700 dark:text-red-400"
                    : "text-gray-600 dark:text-gray-400"
                }`}
              >
                {span.status}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Span hierarchy */}
      {span.parent_span_id && (
        <div className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground mb-2">
          <span>↳ Child of</span>
          <code className="bg-muted px-1 rounded text-xs break-all">
            {span.parent_span_id.slice(-8)}
          </code>
        </div>
      )}

      {/* Key attributes */}
      {Object.keys(span.attributes).length > 0 && (
        <div className="mb-2">
          <div className="text-xs font-medium text-muted-foreground mb-1">
            Attributes:
          </div>
          <div className="space-y-1 text-xs">
            {Object.entries(span.attributes)
              .slice(0, 3)
              .map(([key, value]) => (
                <div key={key} className="flex flex-col sm:flex-row sm:gap-2">
                  <span className="font-mono text-muted-foreground flex-shrink-0">
                    {key}:
                  </span>
                  <span className="font-mono break-all">{String(value)}</span>
                </div>
              ))}
            {Object.keys(span.attributes).length > 3 && (
              <div className="text-muted-foreground">
                +{Object.keys(span.attributes).length - 3} more
              </div>
            )}
          </div>
        </div>
      )}

      {/* Span events */}
      {span.events && span.events.length > 0 && (
        <div className="mb-2">
          <div className="text-xs font-medium text-muted-foreground mb-1">
            Events ({span.events.length}):
          </div>
          <div className="space-y-1">
            {span.events.slice(0, 2).map((spanEvent, idx) => {
              const typedSpanEvent = spanEvent as SpanEvent;
              return (
                <div key={idx} className="text-xs bg-muted p-2 rounded">
                  <span className="font-medium">{typedSpanEvent.name}</span>
                  {typedSpanEvent.attributes &&
                    typeof typedSpanEvent.attributes === "object" &&
                    typedSpanEvent.attributes !== null &&
                    Object.keys(typedSpanEvent.attributes).length > 0 && (
                      <div className="text-muted-foreground mt-1">
                        {Object.entries(typedSpanEvent.attributes)
                          .slice(0, 2)
                          .map(([key, value]) => (
                            <div key={key}>
                              {key}: {String(value)}
                            </div>
                          ))}
                      </div>
                    )}
                </div>
              );
            })}
            {span.events.length > 2 && (
              <div className="text-xs text-muted-foreground">
                ... and {span.events.length - 2} more events
              </div>
            )}
          </div>
        </div>
      )}

      {/* Raw data toggle */}
      {span.raw_span && (
        <details className="text-xs">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
            Raw OpenTelemetry Data
          </summary>
          <pre className="mt-2 p-2 bg-muted rounded text-xs overflow-auto max-h-32">
            {JSON.stringify(span.raw_span, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}

function ToolsTab({ events }: { events: DebugStreamEvent[] }) {
  // Process events first to get clean tool calls
  const processedEvents = processEventsForDisplay(events);

  // Extract tool-related events using proper type checking
  const toolEvents = processedEvents.filter((event) => {
    if (event.type !== "agent_run_update" || !event.update) return false;

    const update = event.update;
    if (!update.contents) return false;

    // Check if this update contains function calls or results
    return update.contents.some(
      (content) =>
        isFunctionCallContent(content) || isFunctionResultContent(content)
    );
  });

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
              {toolEvents.map((event, index) => {
                const update = event.update!;
                const functionCalls = update.contents.filter(
                  isFunctionCallContent
                );
                const functionResults = update.contents.filter(
                  isFunctionResultContent
                );

                return (
                  <div key={index} className="border rounded p-3">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Zap className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />
                        <span className="font-medium text-sm">
                          Tool Activity
                        </span>
                      </div>
                      <span className="text-xs text-muted-foreground font-mono">
                        {new Date(event.timestamp).toLocaleTimeString()}
                      </span>
                    </div>

                    {/* Function Calls */}
                    {functionCalls.map((call, callIndex) => (
                      <div
                        key={`call-${callIndex}`}
                        className="mb-3 p-2 bg-blue-50 dark:bg-blue-950/50 border border-blue-200 dark:border-blue-800 rounded"
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <Wrench className="h-3 w-3 text-blue-600 dark:text-blue-400" />
                          <span className="text-xs font-mono bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 px-2 py-1 rounded">
                            CALL
                          </span>
                          <span className="font-medium text-sm">
                            {call.name}
                          </span>
                        </div>

                        {call.arguments && (
                          <div className="text-xs">
                            <span className="text-muted-foreground">
                              Arguments:
                            </span>
                            <pre className="mt-1 p-2 bg-background border rounded text-xs overflow-auto">
                              {typeof call.arguments === "string"
                                ? call.arguments
                                : JSON.stringify(call.arguments, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    ))}

                    {/* Function Results */}
                    {functionResults.map((result, resultIndex) => (
                      <div
                        key={`result-${resultIndex}`}
                        className="mb-2 p-2 bg-green-50 dark:bg-green-950/50 border border-green-200 dark:border-green-800 rounded"
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <CheckCircle2 className="h-3 w-3 text-green-600 dark:text-green-400" />
                          <span className="text-xs font-mono bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 px-2 py-1 rounded">
                            RESULT
                          </span>
                        </div>

                        <div className="text-xs">
                          <pre className="mt-1 p-2 bg-background border rounded text-xs overflow-auto max-h-32">
                            {typeof result.result === "string"
                              ? result.result
                              : JSON.stringify(result.result, null, 2)}
                          </pre>
                        </div>

                        {result.exception ? (
                          <div className="mt-2 p-2 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 rounded">
                            <span className="text-xs text-red-600 dark:text-red-400">
                              Error: {String(result.exception)}
                            </span>
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </ScrollArea>
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
