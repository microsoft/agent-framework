/**
 * ContextInspector - Token usage visualization and context analysis
 *
 * Features:
 * - Stacked bar chart showing input/output tokens per turn
 * - Composition view showing what fills the context (system, user, assistant, tools)
 * - Per-turn vs cumulative modes
 * - Summary statistics (total, average, peak)
 * - Pure CSS visualization (no external charting library)
 */

import { useState, useMemo } from "react";
import { useDevUIStore } from "@/stores/devuiStore";
import {
  BarChart3,
  Layers,
  Info,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { ExtendedResponseStreamEvent } from "@/types";
import {
  TraceAttributes,
  type TypedTraceAttributes,
  type TraceMessage,
  parseTraceMessages,
  isTextPart,
  isToolCallPart,
  isToolResultPart,
} from "@/types/openai";

// Trace data interface matching debug-panel types
interface TraceEventData {
  operation_name?: string;
  duration_ms?: number;
  status?: string;
  attributes?: TypedTraceAttributes;
  span_id?: string;
  trace_id?: string;
  parent_span_id?: string | null;
  start_time?: number;
  end_time?: number;
  entity_id?: string;
  response_id?: string | null;
}

// Context composition breakdown
interface ContextComposition {
  system: number;      // character count
  user: number;
  assistant: number;
  toolCalls: number;   // function definitions + arguments
  toolResults: number; // function outputs
  total: number;
}

// Turn data extracted from traces
interface TurnData {
  response_id: string;
  timestamp: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  model?: string;
  entity_id?: string;
  duration_ms: number;
  composition: ContextComposition;
}

// Props for the component
interface ContextInspectorProps {
  events: ExtendedResponseStreamEvent[];
}

// Parse message content to extract composition using typed TraceMessage format
function parseComposition(messagesJson: string | unknown): ContextComposition {
  const composition: ContextComposition = {
    system: 0,
    user: 0,
    assistant: 0,
    toolCalls: 0,
    toolResults: 0,
    total: 0,
  };

  try {
    // Use the typed parser for string input
    let messages: TraceMessage[];

    if (typeof messagesJson === "string") {
      messages = parseTraceMessages(messagesJson);
    } else if (Array.isArray(messagesJson)) {
      messages = messagesJson as TraceMessage[];
    } else {
      return composition;
    }

    for (const message of messages) {
      if (!message || typeof message !== "object") continue;

      const role = message.role;
      const parts = message.parts;

      // Calculate character count for this message
      let charCount = 0;

      // Handle parts array (Agent Framework format)
      // Using type guards for type-safe access to part properties
      if (Array.isArray(parts)) {
        for (const part of parts) {
          if (!part || typeof part !== "object") continue;

          if (isTextPart(part)) {
            // Text content can be in either 'content' or 'text' field
            const text = part.content || part.text || "";
            charCount += text.length;
          } else if (isToolCallPart(part)) {
            // Tool call includes name and arguments
            const name = part.name || "";
            const args = part.arguments || "";
            composition.toolCalls += name.length + args.length;
          } else if (isToolResultPart(part)) {
            // Tool result - check both 'result' and 'response' fields
            const result = part.result || part.response || "";
            composition.toolResults += result.length;
          }
        }
      }

      // Categorize by role
      if (role === "system") {
        composition.system += charCount;
      } else if (role === "user") {
        composition.user += charCount;
      } else if (role === "assistant") {
        composition.assistant += charCount;
      } else if (role === "tool") {
        composition.toolResults += charCount;
      }
    }

    composition.total =
      composition.system +
      composition.user +
      composition.assistant +
      composition.toolCalls +
      composition.toolResults;

  } catch {
    // Parsing failed, return empty composition
  }

  return composition;
}

// Extract turn data from trace events
function extractTurnData(events: ExtendedResponseStreamEvent[]): TurnData[] {
  const traceEvents = events.filter(e => e.type === "response.trace.completed");

  // Group by response_id
  const byResponseId = new Map<string, TraceEventData[]>();

  for (const event of traceEvents) {
    if (!("data" in event)) continue;
    const data = event.data as TraceEventData;
    const responseId = data.response_id || "unknown";

    if (!byResponseId.has(responseId)) {
      byResponseId.set(responseId, []);
    }
    byResponseId.get(responseId)!.push(data);
  }

  const turns: TurnData[] = [];

  for (const [responseId, traces] of byResponseId) {
    let inputTokens = 0;
    let outputTokens = 0;
    let model: string | undefined;
    let timestamp = Date.now() / 1000;
    let entity_id: string | undefined;
    let totalDuration = 0;
    let composition: ContextComposition = {
      system: 0, user: 0, assistant: 0, toolCalls: 0, toolResults: 0, total: 0
    };

    for (const trace of traces) {
      const attrs = trace.attributes || {};

      // Get token counts using typed attribute keys
      const traceInput = attrs[TraceAttributes.INPUT_TOKENS];
      const traceOutput = attrs[TraceAttributes.OUTPUT_TOKENS];

      if (traceInput !== undefined) {
        inputTokens += Number(traceInput);
      }
      if (traceOutput !== undefined) {
        outputTokens += Number(traceOutput);
      }

      // Get model using typed attribute key
      if (attrs[TraceAttributes.MODEL]) {
        model = String(attrs[TraceAttributes.MODEL]);
      }

      // Get timestamp
      if (trace.start_time && trace.start_time < timestamp) {
        timestamp = trace.start_time;
      }

      // Get entity_id
      if (trace.entity_id) {
        entity_id = trace.entity_id;
      }

      // Sum durations
      if (trace.duration_ms) {
        totalDuration += Number(trace.duration_ms);
      }

      // Parse composition from input messages using typed attribute key
      const inputMessages = attrs[TraceAttributes.INPUT_MESSAGES];
      if (inputMessages && composition.total === 0) {
        composition = parseComposition(inputMessages);
      }

      // Also check for system instructions using typed attribute key
      const systemInstructions = attrs[TraceAttributes.SYSTEM_INSTRUCTIONS];
      if (systemInstructions && typeof systemInstructions === "string" && composition.system === 0) {
        composition.system = systemInstructions.length;
        composition.total += systemInstructions.length;
      }
    }

    // Only include turns that have token data
    if (inputTokens > 0 || outputTokens > 0) {
      turns.push({
        response_id: responseId,
        timestamp,
        input_tokens: inputTokens,
        output_tokens: outputTokens,
        total_tokens: inputTokens + outputTokens,
        model,
        entity_id,
        duration_ms: totalDuration,
        composition,
      });
    }
  }

  // Sort by timestamp (oldest first)
  turns.sort((a, b) => a.timestamp - b.timestamp);

  return turns;
}

// Calculate summary stats
function calculateStats(turns: TurnData[]) {
  if (turns.length === 0) {
    return {
      totalInput: 0,
      totalOutput: 0,
      totalTokens: 0,
      avgInput: 0,
      avgOutput: 0,
      avgTotal: 0,
      peakInput: 0,
      peakOutput: 0,
      peakTotal: 0,
      turnCount: 0,
    };
  }

  const totalInput = turns.reduce((sum, t) => sum + t.input_tokens, 0);
  const totalOutput = turns.reduce((sum, t) => sum + t.output_tokens, 0);
  const totalTokens = totalInput + totalOutput;

  const peakInput = Math.max(...turns.map(t => t.input_tokens));
  const peakOutput = Math.max(...turns.map(t => t.output_tokens));
  const peakTotal = Math.max(...turns.map(t => t.total_tokens));

  return {
    totalInput,
    totalOutput,
    totalTokens,
    avgInput: Math.round(totalInput / turns.length),
    avgOutput: Math.round(totalOutput / turns.length),
    avgTotal: Math.round(totalTokens / turns.length),
    peakInput,
    peakOutput,
    peakTotal,
    turnCount: turns.length,
  };
}

// Aggregate composition across all turns
function aggregateComposition(turns: TurnData[]): ContextComposition {
  return turns.reduce(
    (acc, turn) => ({
      system: acc.system + turn.composition.system,
      user: acc.user + turn.composition.user,
      assistant: acc.assistant + turn.composition.assistant,
      toolCalls: acc.toolCalls + turn.composition.toolCalls,
      toolResults: acc.toolResults + turn.composition.toolResults,
      total: acc.total + turn.composition.total,
    }),
    { system: 0, user: 0, assistant: 0, toolCalls: 0, toolResults: 0, total: 0 }
  );
}

// Format large numbers with K suffix
function formatTokenCount(n: number): string {
  if (n >= 1000) {
    return `${(n / 1000).toFixed(1)}k`;
  }
  return String(n);
}

// Color constants - single source of truth for all visualizations
const SEGMENT_COLORS = {
  // Token segments
  input: "bg-blue-500 dark:bg-blue-600",
  output: "bg-emerald-500 dark:bg-emerald-600",
  // Composition segments
  system: "bg-purple-500 dark:bg-purple-600",
  user: "bg-blue-500 dark:bg-blue-600",
  assistant: "bg-emerald-500 dark:bg-emerald-600",
  toolCalls: "bg-amber-500 dark:bg-amber-600",
  toolResults: "bg-orange-500 dark:bg-orange-600",
} as const;

// Segment definition for the unified bar component
interface BarSegment {
  key: string;
  value: number;
  color: string;
  label: string;
}

// Unified segmented bar component with tooltips
// Replaces both TokenBar and CompositionBar for consistency and maintainability
function SegmentedBar({
  segments,
  maxValue,
  height = 20,
  renderLabel,
}: {
  segments: BarSegment[];
  maxValue: number;
  height?: number;
  renderLabel?: (total: number, segments: BarSegment[]) => React.ReactNode;
}) {
  const total = segments.reduce((sum, s) => sum + s.value, 0);

  if (total === 0) {
    return (
      <div className="flex items-center gap-2 w-full">
        <div
          className="rounded bg-muted/30 flex-1"
          style={{ height: `${height}px` }}
        />
      </div>
    );
  }

  // When maxValue is 0, use full width (100%) - focus on ratios within the bar
  // When maxValue > 0, scale relative to max - focus on size comparison
  const widthPercent = maxValue > 0 ? (total / maxValue) * 100 : 100;

  // Pre-compute segment metadata for tooltips
  const segmentsWithMeta = segments
    .filter(s => s.value > 0)
    .map(seg => ({
      ...seg,
      percent: Math.round((seg.value / total) * 100),
    }));

  return (
    <div className="flex items-center gap-2 w-full">
      <div
        className="relative rounded overflow-hidden bg-muted/30 flex-1"
        style={{ height: `${height}px` }}
      >
        <TooltipProvider delayDuration={150}>
          <div
            className="h-full flex transition-all duration-300"
            style={{ width: `${widthPercent}%` }}
          >
            {segmentsWithMeta.map((seg) => (
              <Tooltip key={seg.key}>
                <TooltipTrigger asChild>
                  <div
                    className={`h-full ${seg.color} transition-all duration-150 hover:brightness-110 hover:scale-y-[1.15] origin-bottom cursor-default`}
                    style={{ width: `${(seg.value / total) * 100}%` }}
                  />
                </TooltipTrigger>
                <TooltipContent side="top" className="text-xs">
                  <div className="flex items-center gap-1.5">
                    <div className={`w-2 h-2 rounded-sm ${seg.color} flex-shrink-0`} />
                    <span className="font-medium">{seg.label}</span>
                    <span className="opacity-80">{formatTokenCount(seg.value)} ({seg.percent}%)</span>
                  </div>
                </TooltipContent>
              </Tooltip>
            ))}
          </div>
        </TooltipProvider>
      </div>

      {renderLabel?.(total, segments)}
    </div>
  );
}

// Helper to create token segments (input/output)
function createTokenSegments(input: number, output: number): BarSegment[] {
  return [
    { key: "input", value: input, color: SEGMENT_COLORS.input, label: "Input" },
    { key: "output", value: output, color: SEGMENT_COLORS.output, label: "Output" },
  ];
}

// Helper to create composition segments
function createCompositionSegments(composition: ContextComposition): BarSegment[] {
  return [
    { key: "system", value: composition.system, color: SEGMENT_COLORS.system, label: "System" },
    { key: "user", value: composition.user, color: SEGMENT_COLORS.user, label: "User" },
    { key: "assistant", value: composition.assistant, color: SEGMENT_COLORS.assistant, label: "Assistant" },
    { key: "toolCalls", value: composition.toolCalls, color: SEGMENT_COLORS.toolCalls, label: "Tool Calls" },
    { key: "toolResults", value: composition.toolResults, color: SEGMENT_COLORS.toolResults, label: "Tool Results" },
  ];
}

// Composition breakdown list
function CompositionBreakdown({
  composition,
  className = "",
}: {
  composition: ContextComposition;
  className?: string;
}) {
  const { system, user, assistant, toolCalls, toolResults, total } = composition;

  if (total === 0) {
    return (
      <div className={`text-xs text-muted-foreground ${className}`}>
        No composition data available
      </div>
    );
  }

  const items = [
    { label: "System", value: system, color: SEGMENT_COLORS.system },
    { label: "User", value: user, color: SEGMENT_COLORS.user },
    { label: "Assistant", value: assistant, color: SEGMENT_COLORS.assistant },
    { label: "Tool Calls", value: toolCalls, color: SEGMENT_COLORS.toolCalls },
    { label: "Tool Results", value: toolResults, color: SEGMENT_COLORS.toolResults },
  ].filter(item => item.value > 0);

  return (
    <div className={`space-y-1.5 ${className}`}>
      {items.map((item) => {
        const percent = Math.round((item.value / total) * 100);
        return (
          <div key={item.label} className="flex items-center gap-2 text-xs">
            <div className={`w-2 h-2 rounded-sm ${item.color}`} />
            <span className="text-muted-foreground w-20">{item.label}</span>
            <div className="flex-1 h-3 bg-muted/30 rounded overflow-hidden">
              <div
                className={`h-full ${item.color} transition-all duration-300`}
                style={{ width: `${percent}%` }}
              />
            </div>
            <span className="font-mono w-10 text-right text-muted-foreground">
              {percent}%
            </span>
          </div>
        );
      })}
    </div>
  );
}

// Turn row component
function TurnRow({
  turn,
  index,
  maxValue,
  maxCompositionValue,
  cumulativeInput,
  cumulativeOutput,
  cumulativeComposition,
  showCumulative,
  viewMode,
}: {
  turn: TurnData;
  index: number;
  maxValue: number;
  maxCompositionValue: number;
  cumulativeInput: number;
  cumulativeOutput: number;
  cumulativeComposition: ContextComposition;
  showCumulative: boolean;
  viewMode: "tokens" | "composition";
}) {
  const [isExpanded, setIsExpanded] = useState(false);

  const displayInput = showCumulative ? cumulativeInput : turn.input_tokens;
  const displayOutput = showCumulative ? cumulativeOutput : turn.output_tokens;
  const displayComposition = showCumulative ? cumulativeComposition : turn.composition;

  const timestamp = new Date(turn.timestamp * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <div className="border-b border-muted/50 last:border-0">
      <div
        className="flex items-center gap-3 py-2 px-2 hover:bg-muted/30 cursor-pointer transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {/* Turn number */}
        <div className="w-6 h-6 rounded-full bg-muted flex items-center justify-center text-xs font-medium flex-shrink-0">
          {index + 1}
        </div>

        {/* Bar */}
        <div className="flex-1 min-w-0">
          {viewMode === "tokens" ? (
            <SegmentedBar
              segments={createTokenSegments(displayInput, displayOutput)}
              maxValue={maxValue}
              height={20}
              renderLabel={(_, segs) => (
                <div className="flex items-center gap-1 text-xs font-mono text-muted-foreground min-w-[80px] justify-end">
                  <span className="text-blue-600 dark:text-blue-400">↑{formatTokenCount(segs[0]?.value || 0)}</span>
                  <span>/</span>
                  <span className="text-emerald-600 dark:text-emerald-400">↓{formatTokenCount(segs[1]?.value || 0)}</span>
                </div>
              )}
            />
          ) : (
            <SegmentedBar
              segments={createCompositionSegments(displayComposition)}
              maxValue={maxCompositionValue}
              height={20}
              renderLabel={(total) => (
                <div className="text-xs font-mono text-muted-foreground min-w-[50px] text-right">
                  {formatTokenCount(Math.round(total / 4))}~
                </div>
              )}
            />
          )}
        </div>

        {/* Expand icon */}
        <div className="text-muted-foreground flex-shrink-0">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </div>
      </div>

      {/* Expanded details */}
      {isExpanded && (
        <div className="pb-3">
          {/* Connector line */}
          <div className="flex items-start gap-3 px-2">
            <div className="w-6 flex justify-center flex-shrink-0">
              <div className="w-px h-full bg-muted" />
            </div>
            <div className="flex-1 min-w-0">
              {/* L-connector and composition */}
              <div className="flex items-start gap-2">
                <div className="text-muted-foreground text-xs mt-1">└─</div>
                <div className="flex-1 space-y-3">
                  {/* Basic info */}
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    <div>Time: <span className="font-mono text-foreground">{timestamp}</span></div>
                    <div>Duration: <span className="font-mono text-foreground">{turn.duration_ms.toFixed(0)}ms</span></div>
                    {turn.model && (
                      <div>Model: <span className="font-mono text-foreground">{turn.model}</span></div>
                    )}
                    {turn.entity_id && (
                      <div>Entity: <span className="font-mono text-foreground">{turn.entity_id}</span></div>
                    )}
                  </div>

                  {/* Token counts - shown in tokens mode */}
                  {viewMode === "tokens" && (
                    <div className="flex gap-4 text-xs">
                      <div>
                        <span className="text-blue-600 dark:text-blue-400">Input:</span>{" "}
                        <span className="font-mono">{turn.input_tokens.toLocaleString()}</span>
                      </div>
                      <div>
                        <span className="text-emerald-600 dark:text-emerald-400">Output:</span>{" "}
                        <span className="font-mono">{turn.output_tokens.toLocaleString()}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Total:</span>{" "}
                        <span className="font-mono">{turn.total_tokens.toLocaleString()}</span>
                      </div>
                    </div>
                  )}

                  {/* Composition breakdown - shown in composition mode */}
                  {viewMode === "composition" && turn.composition.total > 0 && (
                    <div>
                      <div className="text-xs text-muted-foreground mb-2 flex items-center gap-1">
                        <Info className="h-3 w-3" />
                        Context Composition (estimated from ~{formatTokenCount(Math.round(turn.composition.total / 4))} tokens)
                      </div>
                      <CompositionBreakdown composition={turn.composition} />
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Summary stats card
function StatCard({
  label,
  value,
  icon: Icon,
  color = "default",
}: {
  label: string;
  value: string | number;
  icon: typeof BarChart3;
  color?: "default" | "blue" | "green";
}) {
  const colorClass = {
    default: "text-muted-foreground",
    blue: "text-blue-600 dark:text-blue-400",
    green: "text-emerald-600 dark:text-emerald-400",
  }[color];

  return (
    <div className="flex items-center gap-2 p-2 bg-muted/30 rounded">
      <Icon className={`h-4 w-4 ${colorClass}`} />
      <div className="flex-1 min-w-0">
        <div className="text-xs text-muted-foreground truncate">{label}</div>
        <div className="font-mono text-sm font-medium">{value}</div>
      </div>
    </div>
  );
}

// Main component
export function ContextInspector({ events }: ContextInspectorProps) {
  // Use persisted store state instead of local useState
  const viewMode = useDevUIStore((state) => state.contextInspectorViewMode);
  const setViewMode = useDevUIStore((state) => state.setContextInspectorViewMode);
  const showCumulative = useDevUIStore((state) => state.contextInspectorCumulative);
  const setShowCumulative = useDevUIStore((state) => state.setContextInspectorCumulative);

  // Extract turn data from traces
  const turns = useMemo(() => extractTurnData(events), [events]);

  // Calculate stats
  const stats = useMemo(() => calculateStats(turns), [turns]);

  // Aggregate composition
  const totalComposition = useMemo(() => aggregateComposition(turns), [turns]);

  // Calculate max value for bar scaling (tokens)
  // In non-cumulative mode, use 0 to signal full-width bars (focus on ratios)
  // In cumulative mode, scale relative to total (focus on growth)
  const maxValue = useMemo(() => {
    if (turns.length === 0) return 0;

    if (showCumulative) {
      return stats.totalTokens;
    } else {
      // Return 0 to signal "use full width" - each bar shows its own ratio
      return 0;
    }
  }, [turns, showCumulative, stats.totalTokens]);

  // Calculate max value for composition bar scaling
  // Same logic: full-width in non-cumulative, scaled in cumulative
  const maxCompositionValue = useMemo(() => {
    if (turns.length === 0) return 0;

    if (showCumulative) {
      return totalComposition.total;
    } else {
      // Return 0 to signal "use full width"
      return 0;
    }
  }, [turns, showCumulative, totalComposition.total]);

  // Calculate cumulative values for tokens and composition
  const cumulativeData = useMemo(() => {
    let cumInput = 0;
    let cumOutput = 0;
    let cumComposition: ContextComposition = {
      system: 0, user: 0, assistant: 0, toolCalls: 0, toolResults: 0, total: 0
    };

    return turns.map(t => {
      cumInput += t.input_tokens;
      cumOutput += t.output_tokens;
      cumComposition = {
        system: cumComposition.system + t.composition.system,
        user: cumComposition.user + t.composition.user,
        assistant: cumComposition.assistant + t.composition.assistant,
        toolCalls: cumComposition.toolCalls + t.composition.toolCalls,
        toolResults: cumComposition.toolResults + t.composition.toolResults,
        total: cumComposition.total + t.composition.total,
      };
      return {
        input: cumInput,
        output: cumOutput,
        composition: { ...cumComposition }
      };
    });
  }, [turns]);

  // No data state
  if (turns.length === 0) {
    return (
      <div className="flex flex-col items-center text-center p-6 pt-9">
        <BarChart3 className="h-8 w-8 text-muted-foreground mb-3" />
        <div className="text-sm font-medium mb-1">No Data</div>
        <div className="text-xs text-muted-foreground max-w-[200px]">
          Run{" "}
          <span className="font-mono bg-accent/10 px-1 rounded">
            devui --instrumentation
          </span>{" "}
          and start a conversation.
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-3 border-b flex-shrink-0 space-y-2">
        {/* Title row */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            <span className="font-medium text-sm">Context Inspector</span>
            <Badge variant="outline" className="text-xs">
              {turns.length} turn{turns.length !== 1 ? "s" : ""}
            </Badge>
          </div>

          {/* Cumulative checkbox */}
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
            <Checkbox
              checked={showCumulative}
              onCheckedChange={(checked) => setShowCumulative(checked === true)}
              className="h-3.5 w-3.5"
            />
            <span>Cumulative</span>
          </label>
        </div>

        {/* View mode segmented control */}
        <div className="flex items-center bg-muted rounded-md p-1">
          <button
            onClick={() => setViewMode("tokens")}
            className={`flex-1 px-3 py-1.5 text-xs rounded transition-colors ${
              viewMode === "tokens"
                ? "bg-background shadow-sm font-medium"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Tokens
          </button>
          <button
            onClick={() => setViewMode("composition")}
            className={`flex-1 px-3 py-1.5 text-xs rounded transition-colors ${
              viewMode === "composition"
                ? "bg-background shadow-sm font-medium"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Composition
          </button>
        </div>

        {/* View mode description */}
        <div className="text-xs text-muted-foreground">
          {viewMode === "tokens"
            ? "Token usage per turn"
            : "Context breakdown by message type (chars)"}
        </div>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-3 space-y-4">
          {/* Legend */}
          <div className="flex items-center gap-4 text-xs px-1 flex-wrap">
            {viewMode === "tokens" ? (
              <>
                <div className="flex items-center gap-1.5">
                  <div className={`w-3 h-3 rounded ${SEGMENT_COLORS.input}`} />
                  <span className="text-muted-foreground">Input (↑)</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className={`w-3 h-3 rounded ${SEGMENT_COLORS.output}`} />
                  <span className="text-muted-foreground">Output (↓)</span>
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center gap-1.5">
                  <div className={`w-2.5 h-2.5 rounded-sm ${SEGMENT_COLORS.system}`} />
                  <span className="text-muted-foreground">System</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className={`w-2.5 h-2.5 rounded-sm ${SEGMENT_COLORS.user}`} />
                  <span className="text-muted-foreground">User</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className={`w-2.5 h-2.5 rounded-sm ${SEGMENT_COLORS.assistant}`} />
                  <span className="text-muted-foreground">Assistant</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className={`w-2.5 h-2.5 rounded-sm ${SEGMENT_COLORS.toolCalls}`} />
                  <span className="text-muted-foreground">Tools</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className={`w-2.5 h-2.5 rounded-sm ${SEGMENT_COLORS.toolResults}`} />
                  <span className="text-muted-foreground">Results</span>
                </div>
              </>
            )}
            <div className="flex-1" />
            <div className="flex items-center gap-1 text-muted-foreground">
              <Info className="h-3 w-3" />
              <span>Click for details</span>
            </div>
          </div>

          {/* Turn bars */}
          <div className="border rounded-lg overflow-hidden">
            {turns.map((turn, index) => (
              <TurnRow
                key={turn.response_id}
                turn={turn}
                index={index}
                maxValue={maxValue}
                maxCompositionValue={maxCompositionValue}
                cumulativeInput={cumulativeData[index]?.input || 0}
                cumulativeOutput={cumulativeData[index]?.output || 0}
                cumulativeComposition={cumulativeData[index]?.composition || turn.composition}
                showCumulative={showCumulative}
                viewMode={viewMode}
              />
            ))}
          </div>

          {/* Session summary */}
          <div className="border rounded-lg overflow-hidden">
            <div className="p-3 bg-muted/30 border-b">
              <span className="text-xs font-medium">Session Summary</span>
            </div>

            <div className="p-3 space-y-3">
              {/* Token summary cards */}
              <div className="grid grid-cols-3 gap-2">
                <StatCard
                  label="Total Tokens"
                  value={formatTokenCount(stats.totalTokens)}
                  icon={Layers}
                />
                <StatCard
                  label="Input"
                  value={formatTokenCount(stats.totalInput)}
                  icon={BarChart3}
                  color="blue"
                />
                <StatCard
                  label="Output"
                  value={formatTokenCount(stats.totalOutput)}
                  icon={BarChart3}
                  color="green"
                />
              </div>

              {/* Per-turn statistics (only for multi-turn sessions) */}
              {turns.length > 1 && (
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs pt-2 border-t border-muted/50">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Avg per turn:</span>
                    <span className="font-mono">{formatTokenCount(stats.avgTotal)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Peak turn:</span>
                    <span className="font-mono">{formatTokenCount(stats.peakTotal)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Avg input:</span>
                    <span className="font-mono text-blue-600 dark:text-blue-400">{formatTokenCount(stats.avgInput)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Avg output:</span>
                    <span className="font-mono text-emerald-600 dark:text-emerald-400">{formatTokenCount(stats.avgOutput)}</span>
                  </div>
                </div>
              )}

              {/* Total composition */}
              {totalComposition.total > 0 && (
                <div className="pt-3 border-t border-muted/50">
                  <div className="flex items-start gap-2">
                    <div className="text-muted-foreground text-xs mt-0.5">└─</div>
                    <div className="flex-1">
                      <div className="text-xs text-muted-foreground mb-2 flex items-center gap-1">
                        <Info className="h-3 w-3" />
                        Total Composition (all turns)
                      </div>
                      <CompositionBreakdown composition={totalComposition} />
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}
