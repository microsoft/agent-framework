/**
 * WorkflowView - Complete workflow execution interface
 * Features: Workflow visualization, input forms, execution monitoring
 */

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { CheckCircle, Clock, AlertCircle, Loader2 } from "lucide-react";
import { LoadingState } from "@/components/ui/loading-state";
import { WorkflowInputForm } from "@/components/workflow/workflow-input-form";
import { WorkflowFlow } from "@/components/workflow/workflow-flow";
import { useWorkflowEventCorrelation } from "@/hooks/useWorkflowEventCorrelation";
import { apiClient } from "@/services/api";
import type { WorkflowInfo, ExtendedResponseStreamEvent } from "@/types";
import type { ExecutorNodeData } from "@/components/workflow/executor-node";

type DebugEventHandler = (event: ExtendedResponseStreamEvent) => void;

interface WorkflowViewProps {
  selectedWorkflow: WorkflowInfo;
  onDebugEvent: DebugEventHandler;
}

export function WorkflowView({
  selectedWorkflow,
  onDebugEvent,
}: WorkflowViewProps) {
  const [workflowInfo, setWorkflowInfo] = useState<WorkflowInfo | null>(null);
  const [workflowLoading, setWorkflowLoading] = useState(false);
  const [openAIEvents, setOpenAIEvents] = useState<
    ExtendedResponseStreamEvent[]
  >([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedExecutor, setSelectedExecutor] =
    useState<ExecutorNodeData | null>(null);
  const [workflowResult, setWorkflowResult] = useState<string>("");
  const [workflowError, setWorkflowError] = useState<string>("");
  const accumulatedText = useRef<string>("");

  // Panel resize state
  const [bottomPanelHeight, setBottomPanelHeight] = useState(() => {
    const savedHeight = localStorage.getItem("workflowBottomPanelHeight");
    return savedHeight ? parseInt(savedHeight, 10) : 300;
  });
  const [isResizing, setIsResizing] = useState(false);

  const { selectExecutor, getExecutorData } = useWorkflowEventCorrelation(
    openAIEvents,
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
    setOpenAIEvents([]);
    setIsStreaming(false);
    setSelectedExecutor(null);
    setWorkflowResult("");
    setWorkflowError("");
    accumulatedText.current = "";

    loadWorkflowInfo();
  }, [selectedWorkflow.id, selectedWorkflow.type]);

  const handleNodeSelect = (executorId: string, data: ExecutorNodeData) => {
    setSelectedExecutor(data);
    selectExecutor(executorId);
  };

  // Extract workflow events from OpenAI events for executor tracking
  const workflowEvents = useMemo(() => {
    return openAIEvents.filter(
      (event) => event.type === "response.workflow_event.complete"
    );
  }, [openAIEvents]);

  // Extract executor history from workflow events
  const executorHistory = useMemo(() => {
    return workflowEvents.map((event) => {
      if ("data" in event && event.data && typeof event.data === "object") {
        const data = event.data as Record<string, unknown>;
        return {
          executorId: String(data.executor_id || "unknown"),
          message: String(data.event_type || "Processing"),
          timestamp: String(data.timestamp || new Date().toISOString()),
          status: String(data.event_type || "").includes("Completed")
            ? ("completed" as const)
            : String(data.event_type || "").includes("Error")
            ? ("error" as const)
            : ("running" as const),
        };
      }
      return {
        executorId: "unknown",
        message: "Processing",
        timestamp: new Date().toISOString(),
        status: "running" as const,
      };
    });
  }, [workflowEvents]);

  // Track active executors
  const activeExecutors = useMemo(() => {
    if (!isStreaming) return [];
    const recent = executorHistory
      .filter((h) => h.status === "running")
      .slice(-2);
    return recent.map((h) => h.executorId);
  }, [executorHistory, isStreaming]);

  // Save panel height to localStorage
  useEffect(() => {
    localStorage.setItem(
      "workflowBottomPanelHeight",
      bottomPanelHeight.toString()
    );
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
      setOpenAIEvents([]); // Clear previous OpenAI events for new execution
      setWorkflowResult("");
      setWorkflowError("");
      accumulatedText.current = "";

      try {
        const request = { input_data: inputData };

        // Use OpenAI-compatible API streaming - direct event handling
        const streamGenerator = apiClient.streamWorkflowExecutionOpenAI(
          selectedWorkflow.id,
          request
        );

        for await (const openAIEvent of streamGenerator) {
          // Store all events for processing
          setOpenAIEvents((prev) => [...prev, openAIEvent]);

          // Pass to debug panel
          onDebugEvent(openAIEvent);

          // Handle text output for workflow result
          if (
            openAIEvent.type === "response.output_text.delta" &&
            "delta" in openAIEvent &&
            openAIEvent.delta
          ) {
            accumulatedText.current += openAIEvent.delta;
            setWorkflowResult(accumulatedText.current);
          }

          // Handle workflow completion with final result
          if (
            openAIEvent.type === "response.workflow_event.complete" &&
            "data" in openAIEvent &&
            openAIEvent.data
          ) {
            const data = openAIEvent.data as { event_type?: string; data?: unknown };
            if (data.event_type === "WorkflowCompletedEvent" && data.data) {
              setWorkflowResult(String(data.data));
            }
          }

          // Handle errors
          if (openAIEvent.type === "error") {
            setWorkflowError(
              "error" in openAIEvent
                ? String(openAIEvent.error)
                : "Unknown error"
            );
            break;
          }
        }

        // Stream ended
        setIsStreaming(false);
      } catch (error) {
        console.error("Workflow execution failed:", error);
        setWorkflowError(
          error instanceof Error ? error.message : "Unknown error"
        );
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

  if (!workflowInfo?.workflow_dump && !executorHistory.length) {
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
                  !workflowError &&
                  executorHistory.length > 0 && (
                    <div className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400">
                      <CheckCircle className="w-4 h-4" />
                      Completed
                    </div>
                  )}
                {!isStreaming &&
                  !workflowError &&
                  executorHistory.length === 0 && (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Clock className="w-4 h-4" />
                      Ready
                    </div>
                  )}
                {workflowError && (
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
                events={openAIEvents}
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
        className={`h-1 cursor-row-resize flex-shrink-0 relative group transition-colors duration-200 ease-in-out ${
          isResizing ? "bg-primary/40" : "bg-border hover:bg-primary/20"
        }`}
        onMouseDown={handleMouseDown}
      >
        <div className="absolute inset-x-0 -top-2 -bottom-2 flex items-center justify-center">
          <div
            className={`w-12 h-1 rounded-full transition-all duration-200 ease-in-out ${
              isResizing
                ? "bg-primary shadow-lg shadow-primary/25"
                : "bg-primary/30 group-hover:bg-primary group-hover:shadow-md group-hover:shadow-primary/20"
            }`}
          ></div>
        </div>
      </div>

      {/* Bottom Panel - Execution Details & Controls */}
      <div
        className="flex-shrink-0 flex border-t"
        style={{ height: `${bottomPanelHeight}px` }}
      >
        {/* Left Half - Execution Details */}
        <div className="flex-1 min-w-0 p-4 overflow-auto">
          {selectedExecutor ||
          activeExecutors.length > 0 ||
          executorHistory.length > 0 ||
          workflowResult ||
          workflowError ? (
            <div className="h-full space-y-4">
              {/* Current/Last Executor Panel */}
              {(selectedExecutor ||
                activeExecutors.length > 0 ||
                executorHistory.length > 0) && (
                <div className="border border-border rounded bg-card shadow-sm">
                  <div className="border-b border-border px-4 py-3 bg-muted rounded-t">
                    <h4 className="text-sm font-medium text-foreground">
                      {selectedExecutor
                        ? `Executor: ${
                            selectedExecutor.name || selectedExecutor.executorId
                          }`
                        : isStreaming && activeExecutors.length > 0
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
                                  typeof selectedExecutor.outputData ===
                                    "string"
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
                          isStreaming && activeExecutors.length > 0
                            ? activeExecutors[activeExecutors.length - 1]
                            : executorHistory.length > 0
                            ? executorHistory[executorHistory.length - 1]
                                .executorId
                            : null;

                        if (!currentExecutorId) return null;

                        const executorData = getExecutorData(currentExecutorId);
                        const historyItem = executorHistory.find(
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
                                {isStreaming
                                  ? "Processing..."
                                  : historyItem.message}
                              </p>
                            )}

                          </div>
                        );
                      })()
                    )}
                  </div>
                </div>
              )}

              {/* Enhanced Result Display */}
              {workflowResult && (
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
                      {workflowResult}
                    </div>
                  </div>
                </div>
              )}

              {/* Enhanced Error Display */}
              {workflowError && (
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
                      {workflowError}
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
