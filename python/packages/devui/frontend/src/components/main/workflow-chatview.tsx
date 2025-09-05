import { useMemo, useState } from "react";
import { CheckCircle, Clock, AlertCircle, Loader2, Send, Construction } from "lucide-react";
import { LoadingState } from "@/components/ui/loading-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { WorkflowInfo } from "@/types";
import type { DebugStreamEvent } from "@/types/agent-framework";

interface WorkflowChatViewProps {
  workflowInfo?: WorkflowInfo | null;
  workflowLoading?: boolean;
  events: DebugStreamEvent[];
  isStreaming: boolean;
  onSendMessage?: (message: string) => void;
}

interface WorkflowExecution {
  mermaidDiagram?: string;
  workflowDump?: any;
  activeExecutors: string[];
  executorHistory: Array<{
    executorId: string;
    message: string;
    timestamp: string;
    status: "running" | "completed" | "error";
  }>;
  completionResult?: string;
  error?: string;
}

export function WorkflowChatView({
  workflowInfo,
  workflowLoading = false,
  events,
  isStreaming,
  onSendMessage,
}: WorkflowChatViewProps) {
  const [inputValue, setInputValue] = useState("");

  const workflowExecution = useMemo((): WorkflowExecution => {
    // Use static workflow info first, fall back to streaming events
    let mermaidDiagram = workflowInfo?.mermaid_diagram;
    let workflowDump = workflowInfo?.workflow_dump;

    // Override with streaming data if available (for consistency)
    const structureEvent = events.find((e) => e.type === "workflow_structure");
    if (structureEvent?.mermaid_diagram) {
      mermaidDiagram = structureEvent.mermaid_diagram;
    }
    if (structureEvent?.workflow_dump) {
      workflowDump = structureEvent.workflow_dump;
    }

    // Track executor execution history
    const executorHistory: WorkflowExecution["executorHistory"] = [];
    const activeExecutors = new Set<string>();

    // Process workflow events to build execution history
    events.forEach((event) => {
      if (event.type === "workflow_event" && event.event) {
        // Check if this is an ExecutorEvent which has executor_id
        const executorId =
          "executor_id" in event.event
            ? ((event.event as any).executor_id as string)
            : undefined;
        const eventData = event.event.data;

        if (executorId) {
          // Determine status based on event content
          let status: "running" | "completed" | "error" = "running";
          let message = "";

          if (typeof eventData === "string") {
            message = eventData;
            // Check if this looks like a completion message
            if (
              eventData.includes("completed") ||
              eventData.includes("processed") ||
              eventData.includes("success")
            ) {
              status = "completed";
            } else if (
              eventData.includes("error") ||
              eventData.includes("failed")
            ) {
              status = "error";
            }
          } else if (eventData && typeof eventData === "object") {
            message = JSON.stringify(eventData, null, 2);
          } else {
            message = "Processing...";
          }

          executorHistory.push({
            executorId,
            message,
            timestamp: event.timestamp || new Date().toISOString(),
            status,
          });

          // Track currently active executors (last few that are running)
          if (status === "running" || isStreaming) {
            activeExecutors.add(executorId);
          }
        }
      }
    });

    // Find completion result
    const completionEvent = events.find((e) => e.type === "completion");
    let completionResult = "";
    if (completionEvent?.event?.data) {
      completionResult =
        typeof completionEvent.event.data === "string"
          ? completionEvent.event.data
          : JSON.stringify(completionEvent.event.data);
    }

    // Find error
    const errorEvent = events.find((e) => e.type === "error");
    const error = errorEvent?.error;

    // For active executors, only show the most recent ones if streaming
    const activeExecutorsList = isStreaming
      ? Array.from(activeExecutors).slice(-2) // Show last 2 active
      : []; // Show none if not streaming

    return {
      mermaidDiagram,
      workflowDump,
      activeExecutors: activeExecutorsList,
      executorHistory,
      completionResult,
      error,
    };
  }, [workflowInfo, events, isStreaming]);

  // Show loading state when workflow is being loaded
  if (workflowLoading) {
    return (
      <LoadingState
        message="Loading workflow..."
        description="Fetching workflow structure and configuration"
      />
    );
  }

  if (
    !workflowExecution.mermaidDiagram &&
    !workflowExecution.executorHistory.length
  ) {
    return (
      <LoadingState
        message="Initializing workflow..."
        description="Setting up workflow execution environment"
      />
    );
  }

  return (
    <div className="workflow-chat-view space-y-6 p-4">
      {/* Workflow Diagram Section */}
      {workflowExecution.mermaidDiagram && (
        <div className="border border-border rounded-lg bg-card shadow-sm">
          <div className="border-b border-border px-4 py-3 bg-muted rounded-t-lg">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-foreground">
                Workflow Execution
              </h3>
              {isStreaming && (
                <div className="flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Running...
                </div>
              )}
              {!isStreaming &&
                !workflowExecution.error &&
                workflowExecution.executorHistory.length > 0 && (
                  <div className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400">
                    <CheckCircle className="w-4 h-4" />
                    Completed
                  </div>
                )}
              {!isStreaming &&
                !workflowExecution.error &&
                workflowExecution.executorHistory.length === 0 && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Clock className="w-4 h-4" />
                    Ready
                  </div>
                )}
              {workflowExecution.error && (
                <div className="flex items-center gap-2 text-sm text-destructive">
                  <AlertCircle className="w-4 h-4" />
                  Error
                </div>
              )}
            </div>
          </div>
          <div className="p-4">
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <Construction className="w-12 h-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-medium text-foreground mb-2">
                Workflow Visualization Coming Soon
              </h3>
              <p className="text-sm text-muted-foreground max-w-md">
                We're working on an interactive workflow diagram to help you visualize execution flow. 
                For now, you can track progress in the execution steps below.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Execution History */}
      {workflowExecution.executorHistory.length > 0 && (
        <div className="border border-border rounded-lg bg-card shadow-sm">
          <div className="border-b border-border px-4 py-3 bg-muted rounded-t-lg">
            <h4 className="text-sm font-medium text-foreground">
              Execution Steps
            </h4>
          </div>
          <div className="p-4 space-y-3 max-h-64 overflow-y-auto">
            {workflowExecution.executorHistory.map((step, index) => (
              <div key={index} className="flex items-start gap-3">
                <div className="flex-shrink-0 mt-1">
                  {step.status === "completed" && (
                    <CheckCircle className="w-4 h-4 text-emerald-500 dark:text-emerald-400" />
                  )}
                  {step.status === "running" && (
                    <Clock className="w-4 h-4 text-blue-500 dark:text-blue-400" />
                  )}
                  {step.status === "error" && (
                    <AlertCircle className="w-4 h-4 text-destructive" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-foreground">
                      {step.executorId}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {new Date(step.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground break-words">
                    {step.message}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Final Result */}
      {workflowExecution.completionResult && (
        <div className="border border-emerald-200 rounded-lg bg-emerald-50 dark:bg-emerald-950/50 dark:border-emerald-800 shadow-sm">
          <div className="border-b border-emerald-200 dark:border-emerald-800 px-4 py-3 bg-emerald-100 dark:bg-emerald-900/50 rounded-t-lg">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
              <h4 className="text-sm font-medium text-emerald-800 dark:text-emerald-200">
                Result
              </h4>
            </div>
          </div>
          <div className="p-4">
            <p className="text-emerald-700 dark:text-emerald-300 whitespace-pre-wrap break-words">
              {workflowExecution.completionResult}
            </p>
          </div>
        </div>
      )}

      {/* Error Display */}
      {workflowExecution.error && (
        <div className="border border-destructive/50 rounded-lg bg-destructive/5 shadow-sm">
          <div className="border-b border-destructive/50 px-4 py-3 bg-destructive/10 rounded-t-lg">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-destructive" />
              <h4 className="text-sm font-medium text-destructive">Error</h4>
            </div>
          </div>
          <div className="p-4">
            <p className="text-destructive whitespace-pre-wrap break-words">
              {workflowExecution.error}
            </p>
          </div>
        </div>
      )}

      {/* Workflow Input */}
      {onSendMessage && (
        <div className="border-t border-border bg-muted p-4">
          <div className="flex items-center gap-2">
            <Input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={
                workflowInfo?.workflow_dump?.executors?.[
                  workflowInfo.workflow_dump.start_executor_id
                ]?.type_ === "SpamDetector"
                  ? "Enter message to analyze (e.g., 'Hello, how are you today?')"
                  : "Enter workflow input..."
              }
              onKeyDown={(e) => {
                if (e.key === "Enter" && !isStreaming && inputValue.trim()) {
                  onSendMessage(inputValue.trim());
                  setInputValue("");
                }
              }}
              disabled={isStreaming}
            />
            <Button
              onClick={() => {
                if (inputValue.trim() && !isStreaming) {
                  onSendMessage(inputValue.trim());
                  setInputValue("");
                }
              }}
              disabled={!inputValue.trim() || isStreaming}
              size="sm"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
