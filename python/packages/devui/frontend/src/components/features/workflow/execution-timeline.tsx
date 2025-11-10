/**
 * ExecutionTimeline - Vertical timeline showing workflow executor runs
 * Features: Chronological executor execution, expandable output, bidirectional graph highlighting
 */

import { useState, useEffect, useMemo, useRef } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Loader2,
  CheckCircle,
  XCircle,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
} from "lucide-react";
import type { ExtendedResponseStreamEvent } from "@/types";
import type { ExecutorState } from "./executor-node";
import { truncateText } from "@/utils/workflow-utils";

interface ExecutorRun {
  executorId: string;
  executorName: string;
  itemId: string; // Unique ID for this specific run
  state: ExecutorState;
  output: string;
  error?: string;
  timestamp: number;
  runNumber: number; // For multiple runs of same executor
}

interface ExecutionTimelineProps {
  events: ExtendedResponseStreamEvent[];
  itemOutputs: Record<string, string>;
  currentExecutorId: string | null;
  isStreaming: boolean;
  onExecutorClick?: (executorId: string) => void;
  selectedExecutorId?: string | null;
  workflowResult?: string;
}

function getStateIcon(state: ExecutorState) {
  switch (state) {
    case "running":
      return <Loader2 className="w-4 h-4 text-[#643FB2] dark:text-[#8B5CF6] animate-spin" />;
    case "completed":
      return <CheckCircle className="w-4 h-4 text-green-500 dark:text-green-400" />;
    case "failed":
      return <XCircle className="w-4 h-4 text-red-500 dark:text-red-400" />;
    case "cancelled":
      return <AlertCircle className="w-4 h-4 text-orange-500 dark:text-orange-400" />;
    default:
      return <div className="w-4 h-4 rounded-full border-2 border-gray-400 dark:border-gray-500" />;
  }
}

function getStateBadgeClass(state: ExecutorState) {
  switch (state) {
    case "running":
      return "bg-[#643FB2]/10 text-[#643FB2] dark:bg-[#8B5CF6]/10 dark:text-[#8B5CF6] border-[#643FB2]/20 dark:border-[#8B5CF6]/20";
    case "completed":
      return "bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20";
    case "failed":
      return "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20";
    case "cancelled":
      return "bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/20";
    default:
      return "bg-gray-500/10 text-gray-600 dark:text-gray-400 border-gray-500/20";
  }
}

function ExecutorRunItem({
  run,
  isExpanded,
  onToggle,
  onClick,
  isSelected,
}: {
  run: ExecutorRun;
  isExpanded: boolean;
  onToggle: () => void;
  onClick: () => void;
  isSelected: boolean;
}) {
  const timestamp = new Date(run.timestamp).toLocaleTimeString();
  const hasOutput = run.output.trim().length > 0;
  const canExpand = hasOutput || run.error;
  const outputRef = useRef<HTMLPreElement>(null);

  // Auto-scroll output to bottom when content changes (during streaming)
  useEffect(() => {
    if (isExpanded && run.state === "running" && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [run.output, isExpanded, run.state]);

  return (
    <div
      className={`border rounded-lg transition-all ${
        isSelected
          ? "border-blue-500 dark:border-blue-400 bg-blue-500/5 dark:bg-blue-500/10"
          : "border-border hover:border-muted-foreground/30"
      }`}
    >
      {/* Header - Always Visible */}
      <div
        className="p-3 cursor-pointer"
        onClick={() => {
          onClick();
          if (canExpand) onToggle();
        }}
      >
        <div className="grid grid-cols-[auto_auto_1fr_auto] items-center gap-2 mb-1">
          <div className="w-3 text-muted-foreground">
            {canExpand && (
              <>
                {isExpanded ? (
                  <ChevronDown className="w-3 h-3" />
                ) : (
                  <ChevronRight className="w-3 h-3" />
                )}
              </>
            )}
          </div>
          <div>{getStateIcon(run.state)}</div>
          <span className="font-medium text-sm truncate overflow-hidden">
            {run.executorName}
          </span>
          {run.runNumber > 1 ? (
            <Badge variant="outline" className="text-xs whitespace-nowrap">
              Run #{run.runNumber}
            </Badge>
          ) : (
            <div></div>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground ml-5">
          <span className="font-mono">{timestamp}</span>
          <Badge
            variant="outline"
            className={`text-xs border ${getStateBadgeClass(run.state)}`}
          >
            {run.state}
          </Badge>
        </div>
      </div>

      {/* Expandable Content */}
      {isExpanded && canExpand && (
        <div className="border-t px-3 py-2 bg-muted/30">
          {run.error ? (
            <div className="space-y-1">
              <div className="text-xs font-medium text-red-600 dark:text-red-400">
                Error:
              </div>
              <pre className="text-xs bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded p-2 overflow-y-auto overflow-x-hidden max-h-40 whitespace-pre-wrap break-all">
                {run.error}
              </pre>
            </div>
          ) : (
            <div className="space-y-1">
              <div className="text-xs font-medium text-muted-foreground">
                Output:
              </div>
              <pre
                ref={outputRef}
                className="text-xs bg-background border rounded p-2 overflow-y-auto overflow-x-hidden max-h-60 whitespace-pre-wrap break-all"
              >
                {run.output}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ExecutionTimeline({
  events,
  itemOutputs,
  currentExecutorId,
  isStreaming,
  onExecutorClick,
  selectedExecutorId,
  workflowResult,
}: ExecutionTimelineProps) {
  const [expandedRuns, setExpandedRuns] = useState<Set<string>>(new Set());
  const [updateTrigger, setUpdateTrigger] = useState(0);
  const [copied, setCopied] = useState(false);
  const lastScrolledRunRef = useRef<string | null>(null);
  const timelineEndRef = useRef<HTMLDivElement>(null);

  // Force re-render when streaming to show updated outputs from itemOutputs ref
  // Note: itemOutputs is a ref (not state), so changes don't trigger re-renders automatically.
  // This polling approach ensures the UI updates during streaming. Could be optimized by:
  // 1. Converting itemOutputs to state (increases re-renders)
  // 2. Using requestAnimationFrame instead of setInterval
  // 3. Having parent component trigger updates via callback
  useEffect(() => {
    if (isStreaming) {
      const interval = setInterval(() => {
        setUpdateTrigger((prev) => prev + 1);
      }, 100); // Update 10 times per second during streaming
      return () => clearInterval(interval);
    }
  }, [isStreaming]);

  // Process events to extract executor runs - memoized to prevent recalculation
  const { executorRuns, executorRunCount } = useMemo(() => {
    const runs: ExecutorRun[] = [];
    const runCount = new Map<string, number>();

    events.forEach((event) => {
      // Extract UI timestamp (captured when event arrived, won't change on re-render)
      const uiTimestamp = ('_uiTimestamp' in event && typeof event._uiTimestamp === 'number')
        ? event._uiTimestamp * 1000
        : Date.now();

      // Handle new standard OpenAI events
      if (event.type === "response.output_item.added") {
        const item = (event as { item?: { type?: string; executor_id?: string; id?: string; created_at?: number; metadata?: any } }).item;

        // Handle both executor_action items AND message items from Magentic agents
        if (item && item.type === "executor_action" && item.executor_id && item.id) {
          const executorId = item.executor_id;
          const itemId = item.id;
          const runNumber = (runCount.get(executorId) || 0) + 1;
          runCount.set(executorId, runNumber);

          runs.push({
            executorId,
            executorName: truncateText(executorId, 35),
            itemId,
            state: "running",
            output: itemOutputs[itemId] || "",
            timestamp: uiTimestamp,
            runNumber,
          });
        } else if (item && item.type === "message" && item.metadata?.agent_id && item.metadata?.source === "magentic" && item.id) {
          // Handle message items from Magentic agents
          const executorId = item.metadata.agent_id;
          const itemId = item.id;
          const runNumber = (runCount.get(executorId) || 0) + 1;
          runCount.set(executorId, runNumber);

          runs.push({
            executorId,
            executorName: truncateText(executorId, 35),
            itemId,
            state: "running",
            output: itemOutputs[itemId] || "",
            timestamp: uiTimestamp,
            runNumber,
          });
        }
      }

      // Handle completion events
      if (event.type === "response.output_item.done") {
        const item = (event as { item?: { type?: string; executor_id?: string; id?: string; status?: string; error?: string; metadata?: any } }).item;

        // Handle both executor_action items AND message items from Magentic agents
        if (item && item.type === "executor_action" && item.executor_id && item.id) {
          const itemId = item.id;
          // Find the run by ITEM ID (not executor ID!) to handle multiple runs correctly
          const existingRun = runs.find((r) => r.itemId === itemId);

          if (existingRun) {
            existingRun.state =
              item.status === "completed"
                ? "completed"
                : item.status === "failed"
                ? "failed"
                : "completed";
            // Use item-specific output, not executor-wide output
            existingRun.output = itemOutputs[itemId] || "";
            if (item.status === "failed" && item.error) {
              existingRun.error = item.error;
            }
          }
        } else if (item && item.type === "message" && item.metadata?.agent_id && item.metadata?.source === "magentic" && item.id) {
          // Handle message completion from Magentic agents
          const itemId = item.id;
          const existingRun = runs.find((r) => r.itemId === itemId);

          if (existingRun) {
            existingRun.state = item.status === "completed" ? "completed" : "failed";
            existingRun.output = itemOutputs[itemId] || "";
          }
        }
      }

    // Fallback support for workflow_event format (used for unhandled event types and status/warning/error events)
    if (
      event.type === "response.workflow_event.completed" &&
      "data" in event &&
      event.data
    ) {
      const data = event.data as { executor_id?: string; event_type?: string; data?: unknown; timestamp?: string };
      const executorId = data.executor_id;
      if (!executorId) return;

      const eventType = data.event_type;

      if (eventType === "ExecutorInvokedEvent") {
        const runNumber = (runCount.get(executorId) || 0) + 1;
        runCount.set(executorId, runNumber);

        // Create synthetic item ID for fallback format (no real item.id from backend)
        const syntheticItemId = `fallback_${executorId}_${uiTimestamp}`;

        runs.push({
          executorId,
          executorName: truncateText(executorId, 35),
          itemId: syntheticItemId,
          state: "running",
          output: itemOutputs[syntheticItemId] || "",
          timestamp: uiTimestamp,
          runNumber,
        });
      } else if (eventType === "ExecutorCompletedEvent") {
        // Find the most recent running instance of this executor (search from end)
        let existingRun: ExecutorRun | undefined;
        for (let i = runs.length - 1; i >= 0; i--) {
          if (runs[i].executorId === executorId && runs[i].state === "running") {
            existingRun = runs[i];
            break;
          }
        }
        if (existingRun) {
          existingRun.state = "completed";
          existingRun.output = itemOutputs[existingRun.itemId] || "";
        }
      } else if (
        eventType?.includes("Error") ||
        eventType?.includes("Failed")
      ) {
        // Find the most recent running instance of this executor (search from end)
        let existingRun: ExecutorRun | undefined;
        for (let i = runs.length - 1; i >= 0; i--) {
          if (runs[i].executorId === executorId && runs[i].state === "running") {
            existingRun = runs[i];
            break;
          }
        }
        if (existingRun) {
          existingRun.state = "failed";
          existingRun.error =
            typeof data.data === "string" ? data.data : "Execution failed";
        }
      }
    }
  });

    // Update outputs for running executors using item-specific outputs
    // This ensures each run gets its own output, even for multiple runs of the same executor
    runs.forEach((run) => {
      if (run.state === "running" && itemOutputs[run.itemId]) {
        run.output = itemOutputs[run.itemId];
      }
    });

    return { executorRuns: runs, executorRunCount: runCount };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events, itemOutputs, updateTrigger]);

  // Auto-expand running executors
  useEffect(() => {
    if (currentExecutorId) {
      setExpandedRuns((prev) => {
        const next = new Set(prev);
        next.add(`${currentExecutorId}-${executorRunCount.get(currentExecutorId) || 1}`);
        return next;
      });
    }
  }, [currentExecutorId, executorRunCount]);

  // Auto-scroll to newest executor when it appears or changes
  useEffect(() => {
    if (executorRuns.length > 0 && isStreaming) {
      const latestRun = executorRuns[executorRuns.length - 1];
      const latestRunKey = `${latestRun.executorId}-${latestRun.runNumber}`;

      // Only scroll if this is a new run we haven't scrolled to yet
      if (latestRunKey !== lastScrolledRunRef.current) {
        lastScrolledRunRef.current = latestRunKey;

        // Scroll to the end of the timeline
        if (timelineEndRef.current) {
          timelineEndRef.current.scrollIntoView({
            behavior: 'smooth',
            block: 'end'
          });
        }
      }
    }
  }, [executorRuns, isStreaming]);

  // Auto-scroll to show workflow result when it appears (after streaming completes)
  useEffect(() => {
    if (workflowResult && !isStreaming && timelineEndRef.current) {
      // Small delay to ensure the result card is rendered before scrolling
      setTimeout(() => {
        timelineEndRef.current?.scrollIntoView({
          behavior: 'smooth',
          block: 'end'
        });
      }, 100);
    }
  }, [workflowResult, isStreaming]);

  const handleCopyAll = () => {
    const text = executorRuns
      .map((run) => {
        const timestamp = new Date(run.timestamp).toLocaleTimeString();
        const header = `[${timestamp}] ${run.executorName} (${run.state})`;
        const content = run.error || run.output || "(no output)";
        return `${header}\n${content}\n`;
      })
      .join("\n");

    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="h-full flex flex-col border-l bg-muted/30">
      {/* Header */}
      <div className="p-3 border-b bg-background flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm">Execution Timeline</span>
          <Badge variant="outline" className="text-xs">
            {executorRuns.length}
          </Badge>
          {isStreaming && (
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <div className="h-2 w-2 animate-pulse rounded-full bg-[#643FB2] dark:bg-[#8B5CF6]" />
              <span>Running</span>
            </div>
          )}
        </div>
        {executorRuns.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleCopyAll}
            className={`h-7 px-2 text-xs ${copied ? "text-green-600 dark:text-green-400" : ""}`}
          >
            {copied ? (
              <>
                <Check className="w-3 h-3 mr-1" />
                Copied!
              </>
            ) : (
              <>
                <Copy className="w-3 h-3 mr-1" />
                Copy All
              </>
            )}
          </Button>
        )}
      </div>

      {/* Timeline Content */}
      <ScrollArea className="flex-1">
        <div className="p-3 space-y-2">
          {executorRuns.length === 0 ? (
            <div className="text-center text-muted-foreground text-sm py-8">
              No executor runs yet. Start the workflow to see execution timeline.
            </div>
          ) : (
            executorRuns.map((run, index) => {
              const runKey = `${run.executorId}-${run.runNumber}`;
              return (
                <ExecutorRunItem
                  key={`${runKey}-${index}`}
                  run={run}
                  isExpanded={expandedRuns.has(runKey)}
                  onToggle={() => {
                    setExpandedRuns((prev) => {
                      const next = new Set(prev);
                      if (next.has(runKey)) {
                        next.delete(runKey);
                      } else {
                        next.add(runKey);
                      }
                      return next;
                    });
                  }}
                  onClick={() => onExecutorClick?.(run.executorId)}
                  isSelected={selectedExecutorId === run.executorId}
                />
              );
            })
          )}
          {/* Workflow final output card */}
          {workflowResult && workflowResult.trim().length > 0 && !isStreaming && (
            <div className="border rounded-lg border-green-500/40 bg-green-500/5 dark:bg-green-500/10">
              <div className="p-3 bg-green-500/10 border-b border-green-500/20">
                <div className="flex items-center gap-2 mb-1">
                  <CheckCircle className="w-4 h-4 text-green-500 dark:text-green-400" />
                  <span className="font-medium text-sm">Workflow Complete</span>
                </div>
              </div>
              <div className="border-t px-3 py-2 bg-muted/30">
                <div className="space-y-1">
                  <div className="text-xs font-medium text-muted-foreground">
                    Final Output:
                  </div>
                  <pre className="text-xs bg-background border rounded p-2 overflow-y-auto overflow-x-hidden max-h-60 whitespace-pre-wrap break-all">
                    {workflowResult}
                  </pre>
                </div>
              </div>
            </div>
          )}
          {/* Invisible element at the end for scroll target */}
          <div ref={timelineEndRef} />
        </div>
      </ScrollArea>
    </div>
  );
}
