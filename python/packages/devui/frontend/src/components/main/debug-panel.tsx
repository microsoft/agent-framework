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

// Helper function to determine if an event is significant enough to show
function isSignificantEvent(event: DebugStreamEvent): boolean {
  // Always show completion and error events
  if (event.type === "completion" || event.type === "error") return true;

  // Always show workflow events
  if (event.type === "workflow_event") return true;

  // For agent_run_update events, filter out small text-only updates
  if (event.type === "agent_run_update" && event.update) {
    const update = event.update;
    if (!update.contents || update.contents.length === 0) return false;

    // Show function results (always significant)
    const hasFunctionResult = update.contents.some(isFunctionResultContent);
    if (hasFunctionResult) return true;

    // For function calls, only show if they have a name (indicating start of call)
    // This filters out the streaming fragments that only have partial arguments
    const hasFunctionCall = update.contents.some(
      (content) =>
        isFunctionCallContent(content) &&
        content.name &&
        content.name.trim() !== ""
    );
    if (hasFunctionCall) return true;

    // For text content, only show if it's substantial (>10 chars) or is the first text in a sequence
    const textContents = update.contents.filter(isTextContent);
    if (textContents.length > 0) {
      const totalText = textContents.map((c) => c.text).join("");
      return (
        totalText.length > 10 ||
        totalText.trim().endsWith("\n") ||
        totalText.includes("\n")
      );
    }

    // Show other content types (data, uri, etc.)
    return update.contents.some((c) => !isTextContent(c));
  }

  return true;
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
      return "text-blue-600";
    case "workflow_event":
      return "text-purple-600";
    case "completion":
      return "text-green-600";
    case "error":
      return "text-red-600";
    case "debug_trace":
      return "text-orange-600";
    default:
      return "text-gray-600";
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
            <XCircle className="h-3 w-3 text-red-600 flex-shrink-0" />
            <div className="text-red-600">{event.error}</div>
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
                  <Wrench className="h-3 w-3 text-blue-600 flex-shrink-0" />
                );
              if (hasFunctionResult)
                return (
                  <CheckCircle2 className="h-3 w-3 text-green-600 flex-shrink-0" />
                );
              if (hasText)
                return (
                  <MessageSquare className="h-3 w-3 text-gray-600 flex-shrink-0" />
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
            <Play className="h-3 w-3 text-purple-600 flex-shrink-0" />
            <div className="text-muted-foreground">
              {getEventSummary(event.event)}
            </div>
          </>
        ) : (
          <>
            <CheckCircle2 className="h-3 w-3 text-green-600 flex-shrink-0" />
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

  // Filter events to show only significant ones to reduce noise
  const significantEvents = events.filter(isSignificantEvent);

  // Auto-scroll to bottom for new events
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [significantEvents]);

  return (
    <div className="h-full">
      <div className="flex items-center justify-between p-3 border-b">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4" />
          <span className="font-medium">Events</span>
          <Badge variant="outline">
            {significantEvents.length}
            {events.length > significantEvents.length
              ? `/${events.length}`
              : ""}
          </Badge>
        </div>
        {isStreaming && (
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <div className="h-2 w-2 animate-pulse rounded-full bg-green-500" />
            Streaming
          </div>
        )}
      </div>

      <ScrollArea ref={scrollRef}>
        <div className="p-3">
          {significantEvents.length === 0 ? (
            <div className="text-center text-muted-foreground text-sm py-8">
              {events.length === 0
                ? "No events yet. Start a conversation to see real-time events."
                : `${events.length} events filtered out (too small). Major events will appear here.`}
            </div>
          ) : (
            <div className="space-y-2">
              {significantEvents.map((event, index) => (
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
      <div className="border rounded p-3 text-red-600 text-xs">
        Error: Expected trace_span event but got {event.type}
      </div>
    );
  }

  const span = event.trace_span;

  return (
    <div className="border rounded p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-blue-600" />
          <span className="font-medium text-sm">{span.operation_name}</span>
          {span.duration_ms && (
            <Badge variant="secondary" className="text-xs">
              {span.duration_ms.toFixed(1)}ms
            </Badge>
          )}
          <Badge
            variant={span.status === "OK" ? "default" : "destructive"}
            className="text-xs"
          >
            {span.status}
          </Badge>
        </div>
        <span className="text-xs text-muted-foreground font-mono">
          {new Date(event.timestamp).toLocaleTimeString()}
        </span>
      </div>

      {/* Span hierarchy */}
      {span.parent_span_id && (
        <div className="flex items-center gap-1 text-xs text-muted-foreground mb-2">
          <span>↳ Child of</span>
          <code className="bg-muted px-1 rounded text-xs">
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
          <div className="grid gap-1 text-xs">
            {Object.entries(span.attributes)
              .slice(0, 3)
              .map(([key, value]) => (
                <div key={key} className="flex gap-2">
                  <span className="font-mono text-muted-foreground min-w-0 flex-shrink-0">
                    {key}:
                  </span>
                  <span className="font-mono truncate">{String(value)}</span>
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
  // Extract tool-related events using proper type checking
  const toolEvents = events.filter((event) => {
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
                        <Zap className="h-4 w-4 text-yellow-600" />
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
                        className="mb-3 p-2 bg-blue-50 rounded"
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <Wrench className="h-3 w-3 text-blue-600" />
                          <span className="text-xs font-mono bg-blue-100 px-2 py-1 rounded">
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
                            <pre className="mt-1 p-2 bg-white rounded text-xs overflow-auto">
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
                        className="mb-2 p-2 bg-green-50 rounded"
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <CheckCircle2 className="h-3 w-3 text-green-600" />
                          <span className="text-xs font-mono bg-green-100 px-2 py-1 rounded">
                            RESULT
                          </span>
                        </div>

                        <div className="text-xs">
                          <pre className="mt-1 p-2 bg-white rounded text-xs overflow-auto max-h-32">
                            {typeof result.result === "string"
                              ? result.result
                              : JSON.stringify(result.result, null, 2)}
                          </pre>
                        </div>

                        {result.exception ? (
                          <div className="mt-2 p-2 bg-red-50 rounded">
                            <span className="text-xs text-red-600">
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
