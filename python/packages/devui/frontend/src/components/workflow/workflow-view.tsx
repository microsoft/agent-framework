/**
 * WorkflowView - Complete workflow execution interface
 * Features: Workflow visualization, input forms, execution monitoring
 */

import { useState, useEffect, useMemo, useCallback } from "react";
import { CheckCircle, Clock, AlertCircle, Loader2 } from "lucide-react";
import { LoadingState } from "@/components/ui/loading-state";
import { WorkflowInputForm } from "@/components/workflow/workflow-input-form";
import { WorkflowFlow } from "@/components/workflow/workflow-flow";
import { useWorkflowEventCorrelation } from "@/hooks/useWorkflowEventCorrelation";
import { apiClient } from "@/services/api";
import type { DebugEventHandler } from "@/components/shared/chat-base";
import type { WorkflowInfo } from "@/types";
import type { DebugStreamEvent } from "@/types/agent-framework";
import type { ExecutorNodeData } from "@/components/workflow/executor-node";

interface WorkflowViewProps {
  selectedWorkflow: WorkflowInfo;
  onDebugEvent: DebugEventHandler;
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

export function WorkflowView({
  selectedWorkflow,
  onDebugEvent,
}: WorkflowViewProps) {
  const [workflowInfo, setWorkflowInfo] = useState<WorkflowInfo | null>(null);
  const [workflowLoading, setWorkflowLoading] = useState(false);
  const [events, setEvents] = useState<DebugStreamEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedExecutor, setSelectedExecutor] =
    useState<ExecutorNodeData | null>(null);

  // Panel resize state
  const [bottomPanelHeight, setBottomPanelHeight] = useState(() => {
    const savedHeight = localStorage.getItem("workflowBottomPanelHeight");
    return savedHeight ? parseInt(savedHeight, 10) : 300;
  });
  const [isResizing, setIsResizing] = useState(false);

  const { selectExecutor, getExecutorData } = useWorkflowEventCorrelation(
    events,
    isStreaming
  );

  // Load workflow info when selectedWorkflow changes
  useEffect(() => {
    const loadWorkflowInfo = async () => {
      if (selectedWorkflow.type !== "workflow") return;

      setWorkflowLoading(true);
      try {
        const info = await apiClient.getWorkflowInfo(selectedWorkflow.id);
        setWorkflowInfo(info);
      } catch (error) {
        console.error("Failed to load workflow info:", error);
        setWorkflowInfo(null);
      } finally {
        setWorkflowLoading(false);
      }
    };

    // Clear state when workflow changes
    setEvents([]);
    setIsStreaming(false);
    setSelectedExecutor(null);

    loadWorkflowInfo();
  }, [selectedWorkflow.id]);

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

  // Save panel height to localStorage
  useEffect(() => {
    localStorage.setItem("workflowBottomPanelHeight", bottomPanelHeight.toString());
  }, [bottomPanelHeight]);

  // Handle resize drag
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      setIsResizing(true);

      const startY = e.clientY;
      const startHeight = bottomPanelHeight;

      const handleMouseMove = (e: MouseEvent) => {
        const deltaY = startY - e.clientY;
        const newHeight = Math.max(
          200,
          Math.min(window.innerHeight * 0.6, startHeight + deltaY)
        );
        setBottomPanelHeight(newHeight);
      };

      const handleMouseUp = () => {
        setIsResizing(false);
        document.removeEventListener("mousemove", handleMouseMove);
        document.removeEventListener("mouseup", handleMouseUp);
      };

      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
    },
    [bottomPanelHeight]
  );

  // Handle workflow data sending (structured input)
  const handleSendWorkflowData = useCallback(
    async (inputData: Record<string, unknown>) => {
      if (!selectedWorkflow || selectedWorkflow.type !== "workflow") return;

      setIsStreaming(true);
      setEvents([]); // Clear previous events for new execution

      try {
        const request = { input_data: inputData };

        // Use workflow-specific API streaming
        const streamGenerator = apiClient.streamWorkflowExecution(
          selectedWorkflow.id,
          request
        );

        for await (const event of streamGenerator) {
          // Add event to local state
          setEvents((prev) => [...prev, event]);

          // Emit debug event to parent
          onDebugEvent(event);

          // Handle completion
          if (event.type === "completion") {
            setIsStreaming(false);
            break;
          }

          // Handle errors
          if (event.type === "error") {
            setIsStreaming(false);
            break;
          }
        }
      } catch (error) {
        console.error("Workflow execution failed:", error);
        setEvents((prev) => [
          ...prev,
          {
            type: "error",
            error: error instanceof Error ? error.message : "Unknown error",
            timestamp: new Date().toISOString(),
          },
        ]);
        setIsStreaming(false);
      }
    },
    [selectedWorkflow, onDebugEvent]
  );

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
    <div className="workflow-view flex flex-col h-full">
      {/* Top Panel - Workflow Visualization */}
      <div className="flex-1 min-h-0 p-4">
        {/* Workflow Diagram Section */}
        {workflowInfo?.workflow_dump && (
          <div className="border border-border rounded bg-card shadow-sm h-full flex flex-col">
            <div className="border-b border-border px-4 py-3 bg-muted rounded-t flex-shrink-0">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium text-foreground">
                  Workflow Visualization
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
            <div className="flex-1 min-h-0">
              <WorkflowFlow
                workflowDump={workflowInfo.workflow_dump}
                events={events}
                isStreaming={isStreaming}
                onNodeSelect={handleNodeSelect}
                className="h-full"
              />
            </div>
          </div>
        )}

      </div>

      {/* Resize Handle */}
      <div
        className={`h-1 bg-border hover:bg-accent cursor-row-resize flex-shrink-0 relative group ${
          isResizing ? "bg-accent" : ""
        }`}
        onMouseDown={handleMouseDown}
      >
        <div className="absolute inset-x-0 -top-1 -bottom-1 flex items-center justify-center">
          <div className="w-12 rounded-lg bg-primary h-2"></div>
        </div>
      </div>

      {/* Bottom Panel - Execution Details & Controls */}
      <div
        className="flex-shrink-0 flex border-t"
        style={{ height: `${bottomPanelHeight}px` }}
      >
        {/* Left Half - Execution Details */}
        <div className="flex-1 min-w-0 p-4 overflow-auto">
          {(selectedExecutor ||
            workflowExecution.activeExecutors.length > 0 ||
            workflowExecution.executorHistory.length > 0 ||
            workflowExecution.completionResult ||
            workflowExecution.error) ? (
            <div className="h-full space-y-4">
              {/* Current/Last Executor Panel */}
              {(selectedExecutor ||
                workflowExecution.activeExecutors.length > 0 ||
                workflowExecution.executorHistory.length > 0) && (
                <div className="border border-border rounded bg-card shadow-sm">
                  <div className="border-b border-border px-4 py-3 bg-muted rounded-t">
                    <h4 className="text-sm font-medium text-foreground">
                      {selectedExecutor
                        ? `Executor: ${
                            selectedExecutor.name || selectedExecutor.executorId
                          }`
                        : isStreaming && workflowExecution.activeExecutors.length > 0
                        ? "Current Executor"
                        : "Last Executor"}
                    </h4>
                  </div>
                  <div className="p-4">
                    {selectedExecutor ? (
                      <div className="space-y-3">
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
                              <pre className="text-xs bg-muted p-2 rounded overflow-x-auto max-h-24">
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
                              <pre className="text-xs bg-muted p-2 rounded overflow-x-auto max-h-24">
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
                          ← Back to current executor
                        </button>
                      </div>
                    ) : (
                      (() => {
                        const currentExecutorId =
                          isStreaming && workflowExecution.activeExecutors.length > 0
                            ? workflowExecution.activeExecutors[
                                workflowExecution.activeExecutors.length - 1
                              ]
                            : workflowExecution.executorHistory.length > 0
                            ? workflowExecution.executorHistory[
                                workflowExecution.executorHistory.length - 1
                              ].executorId
                            : null;

                        if (!currentExecutorId) return null;

                        const executorData = getExecutorData(currentExecutorId);
                        const historyItem = workflowExecution.executorHistory.find(
                          (h) => h.executorId === currentExecutorId
                        );

                        return (
                          <div
                            className="space-y-3 cursor-pointer hover:bg-muted/30 p-2 rounded transition-colors"
                            onClick={() => {
                              if (executorData) {
                                setSelectedExecutor({
                                  executorId: executorData.executorId,
                                  state: executorData.state,
                                  inputData: executorData.inputData,
                                  outputData: executorData.outputData,
                                  error: executorData.error,
                                  name: undefined,
                                  executorType: undefined,
                                  isSelected: true,
                                  isStartNode: false,
                                  onNodeClick: undefined,
                                });
                              }
                            }}
                          >
                            <div className="flex items-center gap-2">
                              <div
                                className={`w-3 h-3 rounded-full ${
                                  isStreaming
                                    ? "bg-blue-500 dark:bg-blue-400 animate-pulse"
                                    : historyItem?.status === "completed"
                                    ? "bg-green-500 dark:bg-green-400"
                                    : historyItem?.status === "error"
                                    ? "bg-red-500 dark:bg-red-400"
                                    : "bg-gray-400 dark:bg-gray-500"
                                }`}
                              />
                              <span className="text-sm font-medium text-foreground">
                                {currentExecutorId}
                              </span>
                              {historyItem && (
                                <span className="text-xs text-muted-foreground">
                                  {new Date(
                                    historyItem.timestamp
                                  ).toLocaleTimeString()}
                                </span>
                              )}
                            </div>

                            {historyItem && (
                              <p className="text-sm text-muted-foreground">
                                {isStreaming ? "Processing..." : historyItem.message}
                              </p>
                            )}

                            <p className="text-xs text-muted-foreground">
                              Click to view details
                            </p>
                          </div>
                        );
                      })()
                    )}
                  </div>
                </div>
              )}

              {/* Enhanced Result Display */}
              {workflowExecution.completionResult && (
                <div className="border-2 border-emerald-300 dark:border-emerald-600 rounded bg-emerald-50 dark:bg-emerald-950/50 shadow">
                  <div className="border-b border-emerald-300 dark:border-emerald-600 px-4 py-3 bg-emerald-100 dark:bg-emerald-900/50 rounded-t">
                    <div className="flex items-center gap-3">
                      <CheckCircle className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                      <h4 className="text-sm font-semibold text-emerald-800 dark:text-emerald-200">
                        Workflow Complete
                      </h4>
                    </div>
                  </div>
                  <div className="p-4">
                    <div className="text-emerald-700 dark:text-emerald-300 whitespace-pre-wrap break-words text-sm">
                      {workflowExecution.completionResult}
                    </div>
                  </div>
                </div>
              )}

              {/* Enhanced Error Display */}
              {workflowExecution.error && (
                <div className="border-2 border-destructive/70 rounded bg-destructive/5 shadow">
                  <div className="border-b border-destructive/70 px-4 py-3 bg-destructive/10 rounded-t">
                    <div className="flex items-center gap-3">
                      <AlertCircle className="w-4 h-4 text-destructive" />
                      <h4 className="text-sm font-semibold text-destructive">
                        Workflow Failed
                      </h4>
                    </div>
                  </div>
                  <div className="p-4">
                    <div className="text-destructive whitespace-pre-wrap break-words text-sm">
                      {workflowExecution.error}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="h-full flex items-center justify-center text-muted-foreground">
              <p>Select a workflow to see execution details</p>
            </div>
          )}
        </div>

        {/* Right Half - Input Form */}
        {workflowInfo && (
          <div className="flex-shrink-0 border-l" style={{ width: "400px" }}>
            <WorkflowInputForm
              inputSchema={workflowInfo.input_schema}
              inputTypeName={workflowInfo.input_type_name}
              onSubmit={(formData) => {
                if (typeof formData === "object" && formData !== null) {
                  handleSendWorkflowData(formData as Record<string, unknown>);
                }
              }}
              isSubmitting={isStreaming}
            />
          </div>
        )}
      </div>
    </div>
  );
}
