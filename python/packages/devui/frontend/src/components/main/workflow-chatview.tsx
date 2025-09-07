import { useMemo, useState } from "react";
import { CheckCircle, Clock, AlertCircle, Loader2 } from "lucide-react";
import { LoadingState } from "@/components/ui/loading-state";
import { WorkflowInputForm } from "@/components/forms/workflow-input-form";
import { WorkflowFlow } from "@/components/workflow/workflow-flow";
import { useWorkflowEventCorrelation } from "@/hooks/useWorkflowEventCorrelation";
import type { WorkflowInfo } from "@/types";
import type { DebugStreamEvent } from "@/types/agent-framework";
import type { ExecutorNodeData } from "@/components/workflow/executor-node";

interface WorkflowChatViewProps {
  workflowInfo?: WorkflowInfo | null;
  workflowLoading?: boolean;
  events: DebugStreamEvent[];
  isStreaming: boolean;
  onSendMessage?: (message: string) => void;
}

interface WorkflowExecution {
  workflowDump?: Record<string, unknown>;
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
  const [selectedExecutor, setSelectedExecutor] =
    useState<ExecutorNodeData | null>(null);
  const { selectExecutor, getExecutorData } = useWorkflowEventCorrelation(
    events,
    isStreaming
  );

  const handleNodeSelect = (executorId: string, data: ExecutorNodeData) => {
    setSelectedExecutor(data);
    selectExecutor(executorId);
  };

  const workflowExecution = useMemo((): WorkflowExecution => {
    // Use static workflow info first, fall back to streaming events
    let workflowDump = workflowInfo?.workflow_dump;

    // Override with streaming data if available (for consistency)
    const structureEvent = events.find((e) => e.type === "workflow_structure");
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
            ? (event.event as { executor_id: string }).executor_id
            : undefined;
        const eventData = event.event.data;

        if (executorId) {
          // Determine status and message based on event type and content
          let status: "running" | "completed" | "error" = "running";
          let message = "";

          const eventType = event.event.type;

          // Handle based on event type
          if (eventType === "ExecutorInvokeEvent") {
            status = "running";
            message = "Started processing";
          } else if (eventType === "ExecutorCompletedEvent") {
            status = "completed";
            message = "Finished processing";
          } else if (eventType === "WorkflowCompletedEvent") {
            status = "completed";
            message =
              typeof eventData === "string" ? eventData : "Workflow completed";
          } else if (eventType?.includes("Error")) {
            status = "error";
            message =
              typeof eventData === "string" ? eventData : "Error occurred";
          } else {
            // Fallback to content-based determination
            if (typeof eventData === "string") {
              message = eventData;
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
              try {
                message = JSON.stringify(eventData, null, 2);
              } catch {
                message = "[Unable to display event data]";
              }
            } else {
              message = eventType || "Processing...";
            }
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
    const completionEvent = events.find(
      (e) =>
        e.type === "completion" ||
        (e.type === "workflow_event" &&
          e.event?.type === "WorkflowCompletedEvent")
    );
    let completionResult = "";
    if (completionEvent?.event?.data) {
      completionResult =
        typeof completionEvent.event.data === "string"
          ? completionEvent.event.data
          : (() => {
              try {
                return JSON.stringify(completionEvent.event.data);
              } catch {
                return "[Unable to display completion data]";
              }
            })();
    }

    // Find error
    const errorEvent = events.find((e) => e.type === "error");
    const error = errorEvent?.error;

    // For active executors, only show the most recent ones if streaming
    const activeExecutorsList = isStreaming
      ? Array.from(activeExecutors).slice(-2) // Show last 2 active
      : []; // Show none if not streaming

    return {
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
    !workflowInfo?.workflow_dump &&
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
    <div className="workflow-chat-view flex flex-col h-full">
      {/* Top Section: Workflow Visualization (60% height) */}
      <div className="flex-1 min-h-0 space-y-6 p-4 overflow-auto">
        {/* Workflow Diagram Section */}
        {workflowInfo?.workflow_dump && (
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
            <div className="p-0 h-96">
              <WorkflowFlow
                workflowDump={workflowInfo.workflow_dump}
                events={events}
                isStreaming={isStreaming}
                onNodeSelect={handleNodeSelect}
                className="rounded-b-lg"
              />
            </div>
          </div>
        )}

        {/* Execution History and Selected Node Details */}
        {(workflowExecution.executorHistory.length > 0 || selectedExecutor) && (
          <div className="border border-border rounded-lg bg-card shadow-sm">
            <div className="border-b border-border px-4 py-3 bg-muted rounded-t-lg">
              <h4 className="text-sm font-medium text-foreground">
                {selectedExecutor
                  ? `Executor: ${
                      selectedExecutor.name || selectedExecutor.executorId
                    }`
                  : "Execution Steps"}
              </h4>
            </div>
            <div className="p-4 space-y-3 max-h-64 overflow-y-auto">
              {selectedExecutor ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-2">
                    <div
                      className={`w-3 h-3 rounded-full ${
                        selectedExecutor.state === "running"
                          ? "bg-blue-500 dark:bg-blue-400 animate-pulse"
                          : selectedExecutor.state === "completed"
                          ? "bg-green-500 dark:bg-green-400"
                          : selectedExecutor.state === "failed"
                          ? "bg-red-500 dark:bg-red-400"
                          : selectedExecutor.state === "cancelled"
                          ? "bg-orange-500 dark:bg-orange-400"
                          : "bg-gray-400 dark:bg-gray-500"
                      }`}
                    />
                    <span className="text-sm font-medium capitalize text-foreground">
                      {selectedExecutor.state}
                    </span>
                    {selectedExecutor.executorType && (
                      <span className="text-xs text-muted-foreground">
                        ({selectedExecutor.executorType})
                      </span>
                    )}
                  </div>
                  {selectedExecutor.inputData !== undefined &&
                    selectedExecutor.inputData !== null && (
                      <div>
                        <h5 className="text-xs font-medium text-foreground mb-1">
                          Input Data:
                        </h5>
                        <pre className="text-xs bg-muted p-2 rounded overflow-x-auto">
                          {String(
                            typeof selectedExecutor.inputData === "string"
                              ? selectedExecutor.inputData
                              : (() => {
                                  try {
                                    return JSON.stringify(
                                      selectedExecutor.inputData,
                                      null,
                                      2
                                    );
                                  } catch {
                                    return "[Unable to display data]";
                                  }
                                })()
                          )}
                        </pre>
                      </div>
                    )}
                  {selectedExecutor.outputData !== undefined &&
                    selectedExecutor.outputData !== null && (
                      <div>
                        <h5 className="text-xs font-medium text-foreground mb-1">
                          Output Data:
                        </h5>
                        <pre className="text-xs bg-muted p-2 rounded overflow-x-auto">
                          {String(
                            typeof selectedExecutor.outputData === "string"
                              ? selectedExecutor.outputData
                              : (() => {
                                  try {
                                    return JSON.stringify(
                                      selectedExecutor.outputData,
                                      null,
                                      2
                                    );
                                  } catch {
                                    return "[Unable to display data]";
                                  }
                                })()
                          )}
                        </pre>
                      </div>
                    )}
                  {selectedExecutor.error && (
                    <div>
                      <h5 className="text-xs font-medium text-destructive mb-1">
                        Error:
                      </h5>
                      <pre className="text-xs bg-destructive/10 text-destructive p-2 rounded overflow-x-auto">
                        {selectedExecutor.error}
                      </pre>
                    </div>
                  )}
                  <button
                    onClick={() => setSelectedExecutor(null)}
                    className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    ← Back to execution steps
                  </button>
                </div>
              ) : (
                workflowExecution.executorHistory.map((step, index) => (
                  <div
                    key={index}
                    className="flex items-start gap-3 cursor-pointer hover:bg-muted/50 p-2 rounded transition-colors"
                    onClick={() => {
                      const executorData = getExecutorData(step.executorId);
                      if (executorData) {
                        setSelectedExecutor({
                          executorId: executorData.executorId,
                          state: executorData.state,
                          inputData: executorData.inputData,
                          outputData: executorData.outputData,
                          error: executorData.error,
                          // Set default values for ExecutorNodeData properties not in ExecutorExecutionData
                          name: undefined,
                          executorType: undefined,
                          isSelected: true,
                          isStartNode: false,
                          onNodeClick: undefined,
                        });
                      }
                    }}
                  >
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
                ))
              )}
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
      </div>

      {/* Bottom Section: Workflow Input Form (40% height) */}
      {onSendMessage && workflowInfo && (
        <div className="flex-shrink-0">
          <WorkflowInputForm
            inputSchema={workflowInfo.input_schema}
            inputTypeName={workflowInfo.input_type_name}
            onSubmit={(formData) => {
              // Convert formData to string for onSendMessage
              const message =
                typeof formData === "string"
                  ? formData
                  : (() => {
                      try {
                        return JSON.stringify(formData);
                      } catch {
                        return "[Unable to serialize form data]";
                      }
                    })();
              onSendMessage(message);
            }}
            isSubmitting={isStreaming}
          />
        </div>
      )}
    </div>
  );
}
