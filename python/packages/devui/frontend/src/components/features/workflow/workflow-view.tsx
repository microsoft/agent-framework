/**
 * WorkflowView - Complete workflow execution interface
 * Features: Workflow visualization, input forms, execution monitoring
 */

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import {
  CheckCircle,
  AlertCircle,
  Loader2,
  Play,
  Settings,
  RotateCcw,
  Info,
  Workflow as WorkflowIcon,
  Maximize2,
  ChevronsDown,
} from "lucide-react";
import { LoadingState } from "@/components/ui/loading-state";
import { WorkflowInputForm } from "./workflow-input-form";
import { Button } from "@/components/ui/button";
import { WorkflowFlow } from "./workflow-flow";
import { useWorkflowEventCorrelation } from "@/hooks/useWorkflowEventCorrelation";
import { WorkflowDetailsModal } from "./workflow-details-modal";
import { apiClient } from "@/services/api";
import type {
  WorkflowInfo,
  ExtendedResponseStreamEvent,
  JSONSchemaProperty,
} from "@/types";
import type { ExecutorNodeData } from "./executor-node";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogClose,
} from "@/components/ui/dialog";

type DebugEventHandler = (event: ExtendedResponseStreamEvent | "clear") => void;

// Smart Run Workflow Button Component
interface RunWorkflowButtonProps {
  inputSchema: JSONSchemaProperty;
  onRun: (data: Record<string, unknown>) => void;
  isSubmitting: boolean;
  workflowState: "ready" | "running" | "completed" | "error";
  executorHistory: Array<{
    executorId: string;
    message: string;
    timestamp: string;
    status: string;
  }>;
  workflowError?: string;
}

function RunWorkflowButton({
  inputSchema,
  onRun,
  isSubmitting,
  workflowState,
}: RunWorkflowButtonProps) {
  const [showModal, setShowModal] = useState(false);

  // Handle escape key to close modal
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && showModal) {
        setShowModal(false);
      }
    };

    if (showModal) {
      document.addEventListener("keydown", handleEscape);
      return () => document.removeEventListener("keydown", handleEscape);
    }
  }, [showModal]);

  // Analyze input requirements
  const inputAnalysis = useMemo(() => {
    if (!inputSchema)
      return { needsInput: false, hasDefaults: false, fieldCount: 0 };

    if (inputSchema.type === "string") {
      return {
        needsInput: !inputSchema.default,
        hasDefaults: !!inputSchema.default,
        fieldCount: 1,
        canRunDirectly: !!inputSchema.default,
      };
    }

    if (inputSchema.type === "object" && inputSchema.properties) {
      const properties = inputSchema.properties;
      const fields = Object.entries(properties);
      const fieldsWithDefaults = fields.filter(
        ([, schema]: [string, JSONSchemaProperty]) =>
          schema.default !== undefined ||
          (schema.enum && schema.enum.length > 0)
      );

      return {
        needsInput: fields.length > 0,
        hasDefaults: fieldsWithDefaults.length > 0,
        fieldCount: fields.length,
        canRunDirectly: fieldsWithDefaults.length === fields.length, // All fields have defaults
      };
    }

    return {
      needsInput: false,
      hasDefaults: false,
      fieldCount: 0,
      canRunDirectly: true,
    };
  }, [inputSchema]);

  const handleDirectRun = () => {
    if (inputAnalysis.canRunDirectly) {
      // Build default data
      const defaultData: Record<string, unknown> = {};

      if (inputSchema.type === "string" && inputSchema.default) {
        defaultData.input = inputSchema.default;
      } else if (inputSchema.type === "object" && inputSchema.properties) {
        Object.entries(inputSchema.properties).forEach(
          ([key, schema]: [string, JSONSchemaProperty]) => {
            if (schema.default !== undefined) {
              defaultData[key] = schema.default;
            } else if (schema.enum && schema.enum.length > 0) {
              defaultData[key] = schema.enum[0];
            }
          }
        );
      }

      onRun(defaultData);
    } else {
      setShowModal(true);
    }
  };

  const getButtonText = () => {
    if (workflowState === "running") return "Running...";
    if (workflowState === "completed") return "Run Again";
    if (workflowState === "error") return "Retry";
    if (inputAnalysis.fieldCount === 0) return "Run Workflow";
    if (inputAnalysis.canRunDirectly) return "Run Workflow";
    return "Configure & Run";
  };

  const getButtonIcon = () => {
    if (workflowState === "running")
      return <Loader2 className="w-4 h-4 animate-spin" />;
    if (workflowState === "error") return <RotateCcw className="w-4 h-4" />;
    if (inputAnalysis.needsInput && !inputAnalysis.canRunDirectly)
      return <Settings className="w-4 h-4" />;
    return <Play className="w-4 h-4" />;
  };

  const isButtonDisabled = workflowState === "running";
  const buttonVariant = workflowState === "error" ? "destructive" : "primary";

  return (
    <>
      <div className="flex items-center">
        {/* Split button group using proper Button components */}
        <div className="flex">
          {/* Main button */}
          <Button
            onClick={handleDirectRun}
            disabled={isButtonDisabled}
            variant={
              buttonVariant === "destructive" ? "destructive" : "default"
            }
            size="default"
            className={inputAnalysis.needsInput ? "rounded-r-none" : ""}
          >
            {getButtonIcon()}
            {getButtonText()}
          </Button>

          {/* Dropdown button - only show if inputs are available */}
          {inputAnalysis.needsInput && (
            <Button
              onClick={() => setShowModal(true)}
              disabled={isButtonDisabled}
              variant={
                buttonVariant === "destructive" ? "destructive" : "default"
              }
              size="default"
              className="rounded-l-none border-l-0 px-3"
              title="Configure workflow inputs - customize parameters before running"
            >
              <Settings className="w-4 h-4" />
              <span className="ml-1.5">Inputs</span>
            </Button>
          )}
        </div>
      </div>

      {/* Modal with proper Dialog component - matching WorkflowInputForm structure */}
      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="w-full min-w-[400px] max-w-md sm:max-w-lg md:max-w-2xl lg:max-w-4xl xl:max-w-5xl max-h-[90vh] flex flex-col">
          <DialogHeader className="px-8 pt-6">
            <DialogTitle>Configure Workflow Inputs</DialogTitle>
            <DialogClose onClose={() => setShowModal(false)} />
          </DialogHeader>

          {/* Form Info - matching the structure from WorkflowInputForm */}
          <div className="px-8 py-4 border-b flex-shrink-0">
            <div className="text-sm text-muted-foreground">
              <div className="flex items-center gap-3">
                <span className="font-medium">Input Type:</span>
                <code className="bg-muted px-3 py-1 text-xs font-mono">
                  {inputAnalysis.fieldCount === 0
                    ? "No Input"
                    : inputSchema.type === "string"
                    ? "String"
                    : "Object"}
                </code>
                {inputSchema.type === "object" && inputSchema.properties && (
                  <span className="text-xs text-muted-foreground">
                    {Object.keys(inputSchema.properties).length} field
                    {Object.keys(inputSchema.properties).length !== 1
                      ? "s"
                      : ""}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Scrollable Form Content - matching padding and structure */}
          <div className="px-8 py-6 overflow-y-auto flex-1 min-h-0">
            <WorkflowInputForm
              inputSchema={inputSchema}
              inputTypeName="Input"
              onSubmit={(data) => {
                onRun(data as Record<string, unknown>);
                setShowModal(false);
              }}
              isSubmitting={isSubmitting}
              className="embedded"
            />
          </div>

          {/* Footer - no additional buttons needed since WorkflowInputForm embedded mode has its own */}
        </DialogContent>
      </Dialog>
    </>
  );
}

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
  const [detailsModalOpen, setDetailsModalOpen] = useState(false);
  const [resultModalOpen, setResultModalOpen] = useState(false);
  const [errorModalOpen, setErrorModalOpen] = useState(false);
  const resultContentRef = useRef<HTMLDivElement>(null);
  const errorContentRef = useRef<HTMLDivElement>(null);
  const [isErrorScrollable, setIsErrorScrollable] = useState(false);

  // Track per-executor outputs and workflow metadata
  const executorOutputs = useRef<Record<string, string>>({});
  const currentStreamingExecutor = useRef<string | null>(null);
  const workflowMetadata = useRef<Record<string, unknown> | null>(null);

  // Panel resize state
  const [bottomPanelHeight, setBottomPanelHeight] = useState(() => {
    const savedHeight = localStorage.getItem("workflowBottomPanelHeight");
    return savedHeight ? parseInt(savedHeight, 10) : 300;
  });
  const [isResizing, setIsResizing] = useState(false);

  // View options state
  const [viewOptions, setViewOptions] = useState(() => {
    const saved = localStorage.getItem("workflowViewOptions");
    return saved
      ? JSON.parse(saved)
      : {
          showMinimap: false,
          showGrid: true,
          animateRun: false,
        };
  });

  // Layout direction state
  const [layoutDirection, setLayoutDirection] = useState<"LR" | "TB">(() => {
    const saved = localStorage.getItem("workflowLayoutDirection");
    return (saved as "LR" | "TB") || "LR";
  });

  const { selectExecutor, getExecutorData } = useWorkflowEventCorrelation(
    openAIEvents,
    isStreaming
  );

  // Save view options to localStorage
  useEffect(() => {
    localStorage.setItem("workflowViewOptions", JSON.stringify(viewOptions));
  }, [viewOptions]);

  // Save layout direction to localStorage
  useEffect(() => {
    localStorage.setItem("workflowLayoutDirection", layoutDirection);
  }, [layoutDirection]);

  // Auto-scroll output panel when new content arrives (if user is at bottom)
  useEffect(() => {
    const handleAutoScroll = () => {
      if (resultContentRef.current) {
        const container = resultContentRef.current;
        const isScrollable = container.scrollHeight > container.clientHeight;

        // Check if user is near the bottom (within 100px threshold)
        const scrollBottom =
          container.scrollHeight - container.scrollTop - container.clientHeight;
        const isNearBottom = scrollBottom < 100;

        // Auto-scroll smoothly if user is near bottom and content is streaming
        if (isStreaming && isNearBottom && isScrollable) {
          container.scrollTo({
            top: container.scrollHeight,
            behavior: "smooth",
          });
        }
      }
      if (errorContentRef.current) {
        const isScrollable =
          errorContentRef.current.scrollHeight >
          errorContentRef.current.clientHeight;
        setIsErrorScrollable(isScrollable);
      }
    };

    handleAutoScroll();
    // Recheck on window resize
    window.addEventListener("resize", handleAutoScroll);
    return () => window.removeEventListener("resize", handleAutoScroll);
  }, [workflowResult, workflowError, bottomPanelHeight, isStreaming]);

  // View option handlers
  const toggleViewOption = (key: keyof typeof viewOptions) => {
    setViewOptions((prev: typeof viewOptions) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  // Load workflow info when selectedWorkflow changes
  useEffect(() => {
    const loadWorkflowInfo = async () => {
      if (selectedWorkflow.type !== "workflow") return;

      setWorkflowLoading(true);
      try {
        const info = await apiClient.getWorkflowInfo(selectedWorkflow.id);
        setWorkflowInfo(info);
      } catch (error) {
        setWorkflowInfo(null);
        console.error("Error loading workflow info:", error);
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
    executorOutputs.current = {};
    currentStreamingExecutor.current = null;
    workflowMetadata.current = null;

    loadWorkflowInfo();
  }, [selectedWorkflow.id, selectedWorkflow.type]);

  const handleNodeSelect = (executorId: string, data: ExecutorNodeData) => {
    setSelectedExecutor(data);
    selectExecutor(executorId);

    // Update result display to show selected executor's output
    if (executorOutputs.current[executorId]) {
      // Show per-executor output if available
      setWorkflowResult(executorOutputs.current[executorId]);
    }
    // Note: For executors without output, we don't clear workflowResult
    // This preserves the workflow's final output for display
  };

  // Extract workflow events from OpenAI events for executor tracking
  const workflowEvents = useMemo(() => {
    return openAIEvents.filter(
      (event) => event.type === "response.workflow_event.complete"
    );
  }, [openAIEvents]);

  // Extract executor history from workflow events (filter out workflow-level events)
  const executorHistory = useMemo(() => {
    return workflowEvents
      .filter((event) => {
        if ("data" in event && event.data && typeof event.data === "object") {
          const data = event.data as Record<string, unknown>;
          // Filter out workflow-level events (those without executor_id)
          // These include: WorkflowStartedEvent, WorkflowOutputEvent, WorkflowStatusEvent, etc.
          return data.executor_id != null;
        }
        return false;
      })
      .map((event) => {
        if ("data" in event && event.data && typeof event.data === "object") {
          const data = event.data as Record<string, unknown>;
          return {
            executorId: String(data.executor_id),
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

      // Clear per-executor outputs and metadata for new run
      executorOutputs.current = {};
      currentStreamingExecutor.current = null;
      workflowMetadata.current = null;

      // Clear debug panel events for new workflow run
      onDebugEvent("clear");

      try {
        const request = { input_data: inputData };

        // Use OpenAI-compatible API streaming - direct event handling
        const streamGenerator = apiClient.streamWorkflowExecutionOpenAI(
          selectedWorkflow.id,
          request
        );

        for await (const openAIEvent of streamGenerator) {
          // Only store workflow events in state for performance
          // Text deltas are processed directly without state updates
          if (openAIEvent.type === "response.workflow_event.complete") {
            setOpenAIEvents((prev) => [...prev, openAIEvent]);
          }

          // Pass to debug panel
          onDebugEvent(openAIEvent);

          // Handle workflow events to track current executor
          if (
            openAIEvent.type === "response.workflow_event.complete" &&
            "data" in openAIEvent &&
            openAIEvent.data
          ) {
            const data = openAIEvent.data as {
              event_type?: string;
              data?: unknown;
              executor_id?: string | null;
            };

            // Track when executor starts (to know which executor is streaming)
            if (
              data.event_type === "ExecutorInvokedEvent" &&
              data.executor_id
            ) {
              currentStreamingExecutor.current = data.executor_id;
              // Initialize output for this executor if not exists
              if (!executorOutputs.current[data.executor_id]) {
                executorOutputs.current[data.executor_id] = "";
              }
            }

            // Handle workflow completion and output events
            if (
              (data.event_type === "WorkflowCompletedEvent" ||
                data.event_type === "WorkflowOutputEvent") &&
              data.data
            ) {
              // For workflows that don't emit text deltas (e.g., ctx.yield_output),
              // the WorkflowOutputEvent contains the final output
              if (typeof data.data === "string") {
                setWorkflowResult(data.data);
              } else {
                // Store object data and display as formatted JSON
                workflowMetadata.current = data.data as Record<string, unknown>;
                const jsonOutput = JSON.stringify(data.data, null, 2);
                setWorkflowResult(jsonOutput);
              }
              currentStreamingExecutor.current = null;
            }
          }

          // Handle text output - assign to current executor
          if (
            openAIEvent.type === "response.output_text.delta" &&
            "delta" in openAIEvent &&
            openAIEvent.delta
          ) {
            // Determine which executor owns this text
            const executorId = currentStreamingExecutor.current;

            if (executorId) {
              // Initialize executor output if needed
              if (!executorOutputs.current[executorId]) {
                executorOutputs.current[executorId] = "";
              }

              // Append to specific executor's output
              executorOutputs.current[executorId] += openAIEvent.delta;

              // Update display based on what should be shown
              if (
                selectedExecutor &&
                executorOutputs.current[selectedExecutor.executorId]
              ) {
                // If user has selected an executor, show that executor's output
                setWorkflowResult(
                  executorOutputs.current[selectedExecutor.executorId]
                );
              } else {
                // Otherwise show current streaming executor's output
                setWorkflowResult(executorOutputs.current[executorId]);
              }
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

        setIsStreaming(false);
      } catch (error) {
        setWorkflowError(
          error instanceof Error ? error.message : "Unknown error"
        );
        setIsStreaming(false);
      }
    },
    [selectedWorkflow, onDebugEvent, workflowInfo]
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
      {/* Header */}
      <div className="border-b pb-2 p-4 flex-shrink-0">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3 mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <h2 className="font-semibold text-sm truncate">
              <div className="flex items-center gap-2">
                <WorkflowIcon className="h-4 w-4 flex-shrink-0" />
                <span className="truncate">
                  {selectedWorkflow.name || selectedWorkflow.id}
                </span>
              </div>
            </h2>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setDetailsModalOpen(true)}
              className="h-6 w-6 p-0 flex-shrink-0"
              title="View workflow details"
            >
              <Info className="h-4 w-4" />
            </Button>
          </div>

          {/* Run Workflow Controls */}
          {workflowInfo && (
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 flex-shrink-0">
              <RunWorkflowButton
                inputSchema={workflowInfo.input_schema}
                onRun={handleSendWorkflowData}
                isSubmitting={isStreaming}
                workflowState={
                  isStreaming
                    ? "running"
                    : workflowError
                    ? "error"
                    : executorHistory.length > 0
                    ? "completed"
                    : "ready"
                }
                executorHistory={executorHistory}
                workflowError={workflowError}
              />
            </div>
          )}
        </div>

        {selectedWorkflow.description && (
          <p className="text-sm text-muted-foreground">
            {selectedWorkflow.description}
          </p>
        )}
      </div>

      {/* Workflow Visualization */}
      <div className="flex-1 min-h-0">
        {workflowInfo?.workflow_dump && (
          <WorkflowFlow
            workflowDump={workflowInfo.workflow_dump}
            events={workflowEvents}
            isStreaming={isStreaming}
            onNodeSelect={handleNodeSelect}
            className="h-full"
            viewOptions={viewOptions}
            onToggleViewOption={toggleViewOption}
            layoutDirection={layoutDirection}
            onLayoutDirectionChange={setLayoutDirection}
          />
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

      {/* Bottom Panel - Execution Details */}
      <div
        className="flex-shrink-0 border-t overflow-hidden"
        style={{ height: `${bottomPanelHeight}px` }}
      >
        {/* Full Width - Execution Details */}
        <div className="h-full flex gap-4 p-4">
          {selectedExecutor ||
          activeExecutors.length > 0 ||
          executorHistory.length > 0 ||
          workflowResult ||
          workflowError ? (
            <>
              {/* Current/Last Executor Panel */}
              {(selectedExecutor ||
                activeExecutors.length > 0 ||
                executorHistory.length > 0) && (
                <div
                  className={`border border-border rounded bg-card shadow-sm flex flex-col ${
                    workflowResult || workflowError ? "flex-1" : "w-full"
                  }`}
                >
                  <div className="border-b border-border px-4 py-3 bg-muted rounded-t flex-shrink-0">
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
                  <div className="p-4 overflow-auto flex-1">
                    {selectedExecutor ? (
                      <div className="space-y-3">
                        <div className="flex items-center gap-2">
                          <div
                            className={`w-3 h-3 rounded-full ${
                              selectedExecutor.state === "running"
                                ? "bg-[#643FB2] dark:bg-[#8B5CF6] animate-pulse"
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
                                    ? "bg-[#643FB2] dark:bg-[#8B5CF6] animate-pulse"
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

              {/* Output Panel - displays workflow execution results and streaming output */}
              {workflowResult &&
                (() => {
                  // Determine the panel state and styling
                  const isStreamingState =
                    isStreaming && currentStreamingExecutor.current;
                  const isSelectedExecutor = !isStreaming && selectedExecutor;

                  // Define theme based on state - use colors sparingly (borders/icons only, not text)
                  const theme = isStreamingState
                    ? {
                        // Purple theme when streaming (matches running node color #643FB2)
                        border: "border-[#643FB2]/40 dark:border-[#8B5CF6]/40",
                        bg: "bg-[#643FB2]/5 dark:bg-[#8B5CF6]/5",
                        headerBg: "bg-[#643FB2]/10 dark:bg-[#8B5CF6]/10",
                        icon: (
                          <Loader2 className="w-4 h-4 text-[#643FB2] dark:text-[#8B5CF6] animate-spin" />
                        ),
                        buttonBg: "bg-background dark:bg-background",
                        buttonBorder:
                          "border-[#643FB2]/30 dark:border-[#8B5CF6]/30",
                        buttonHover:
                          "hover:bg-[#643FB2]/10 dark:hover:bg-[#8B5CF6]/10",
                      }
                    : isSelectedExecutor
                    ? {
                        // Blue theme when executor selected (matches selected node ring blue-500)
                        border: "border-blue-500/40 dark:border-blue-500/40",
                        bg: "bg-blue-500/5 dark:bg-blue-500/5",
                        headerBg: "bg-blue-500/10 dark:bg-blue-500/10",
                        icon: (
                          <Info className="w-4 h-4 text-blue-500 dark:text-blue-400" />
                        ),
                        buttonBg: "bg-background dark:bg-background",
                        buttonBorder:
                          "border-blue-500/30 dark:border-blue-500/30",
                        buttonHover:
                          "hover:bg-blue-500/10 dark:hover:bg-blue-500/10",
                      }
                    : {
                        // Green theme when workflow complete (matches completed node green-500)
                        border: "border-green-500/40 dark:border-green-400/40",
                        bg: "bg-green-500/5 dark:bg-green-400/5",
                        headerBg: "bg-green-500/10 dark:bg-green-400/10",
                        icon: (
                          <CheckCircle className="w-4 h-4 text-green-500 dark:text-green-400" />
                        ),
                        buttonBg: "bg-background dark:bg-background",
                        buttonBorder:
                          "border-green-500/30 dark:border-green-400/30",
                        buttonHover:
                          "hover:bg-green-500/10 dark:hover:bg-green-400/10",
                      };

                  return (
                    <div
                      className={`border-2 ${theme.border} rounded ${theme.bg} shadow flex-1 flex flex-col min-w-0 relative`}
                    >
                      <div
                        className={`border-b ${theme.border} px-4 py-3 ${theme.headerBg} rounded-t flex-shrink-0`}
                      >
                        <div className="flex items-center gap-3">
                          {theme.icon}
                          <h4 className="text-sm font-semibold text-foreground">
                            {isStreamingState
                              ? `Output: ${currentStreamingExecutor.current}`
                              : isSelectedExecutor
                              ? `Output: ${selectedExecutor.executorId}`
                              : "Workflow Complete"}
                          </h4>
                        </div>
                      </div>
                      <div
                        ref={resultContentRef}
                        className="p-4 overflow-auto flex-1 min-h-0 relative"
                      >
                        <div className="text-foreground whitespace-pre-wrap break-words text-sm pb-12">
                          {workflowResult}
                        </div>
                      </div>
                      {/* Sticky "View Full" button - always visible at bottom-right */}
                      <div className="absolute bottom-3 right-3 pointer-events-auto">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setResultModalOpen(true)}
                          className={`h-8 px-3 ${theme.buttonBg} ${theme.buttonBorder} ${theme.buttonHover} shadow-md`}
                          title="Expand to full view"
                        >
                          <Maximize2 className="w-3.5 h-3.5 mr-1.5" />
                          View Full
                        </Button>
                      </div>
                    </div>
                  );
                })()}

              {/* Enhanced Error Display */}
              {workflowError && (
                <div className="border-2 border-destructive/70 rounded bg-destructive/5 shadow flex-1 flex flex-col min-w-0 relative">
                  <div className="border-b border-destructive/70 px-4 py-3 bg-destructive/10 rounded-t flex-shrink-0">
                    <div className="flex items-center gap-3">
                      <AlertCircle className="w-4 h-4 text-destructive" />
                      <h4 className="text-sm font-semibold text-destructive">
                        Workflow Failed
                      </h4>
                    </div>
                  </div>
                  <div
                    ref={errorContentRef}
                    className="p-4 overflow-auto flex-1 min-h-0 relative"
                  >
                    <div className="text-destructive whitespace-pre-wrap break-words text-sm pb-12">
                      {workflowError}
                    </div>
                  </div>
                  {/* Sticky "View Full" button - always visible at bottom-right */}
                  <div className="absolute bottom-3 right-3 pointer-events-auto">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setErrorModalOpen(true)}
                      className="h-8 px-3 bg-destructive/10 dark:bg-destructive/20 border-destructive/50 text-destructive hover:bg-destructive/20 dark:hover:bg-destructive/30 shadow-md"
                      title="Expand to full view"
                    >
                      <Maximize2 className="w-3.5 h-3.5 mr-1.5" />
                      View Full
                    </Button>
                  </div>
                  {/* Scroll indicator - only show when scrollable */}
                  {isErrorScrollable && (
                    <div className="absolute bottom-14 left-1/2 transform -translate-x-1/2 pointer-events-none">
                      <div className="bg-destructive/80 text-white px-2 py-1 rounded-full flex items-center gap-1 text-xs animate-bounce">
                        <ChevronsDown className="w-3 h-3" />
                        <span>Scroll for more</span>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="h-full flex items-center justify-center text-muted-foreground">
              <p>Select a workflow node (executor) to see execution details</p>
            </div>
          )}
        </div>
      </div>

      {/* Workflow Details Modal */}
      <WorkflowDetailsModal
        workflow={selectedWorkflow}
        open={detailsModalOpen}
        onOpenChange={setDetailsModalOpen}
      />

      {/* Result Full View Modal */}
      <Dialog open={resultModalOpen} onOpenChange={setResultModalOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col">
          <DialogHeader className="px-6 pt-6 flex-shrink-0">
            <DialogTitle className="flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
              Workflow Results
            </DialogTitle>
            <DialogClose onClose={() => setResultModalOpen(false)} />
          </DialogHeader>

          <div className="px-6 pb-6 overflow-y-auto flex-1">
            <div className="space-y-4">
              {/* Show per-executor outputs if we have multiple executors with output */}
              {Object.values(executorOutputs.current).some(
                (output) => output && output.trim().length > 0
              ) ? (
                Object.entries(executorOutputs.current).map(
                  ([executorId, output]) =>
                    output && (
                      <div
                        key={executorId}
                        className="border-2 border-emerald-300 dark:border-emerald-600 rounded overflow-hidden"
                      >
                        <div className="bg-emerald-100 dark:bg-emerald-900/50 px-4 py-2 border-b border-emerald-300 dark:border-emerald-600">
                          <h5 className="text-sm font-semibold text-emerald-800 dark:text-emerald-200">
                            {executorId}
                          </h5>
                        </div>
                        <div className="bg-emerald-50 dark:bg-emerald-950/50 p-4">
                          <div className="text-emerald-700 dark:text-emerald-300 whitespace-pre-wrap break-words text-sm font-mono">
                            {output}
                          </div>
                        </div>
                      </div>
                    )
                )
              ) : (
                /* Show workflow result for simple workflows without per-executor tracking */
                <div className="bg-emerald-50 dark:bg-emerald-950/50 rounded border-2 border-emerald-300 dark:border-emerald-600 p-6">
                  <div className="text-emerald-700 dark:text-emerald-300 whitespace-pre-wrap break-words text-sm font-mono">
                    {workflowResult || "No output available"}
                  </div>
                </div>
              )}

              {/* Show workflow output if available */}
              {workflowMetadata.current && (
                <div className="border-2 border-blue-300 dark:border-blue-600 rounded overflow-hidden">
                  <div className="bg-blue-100 dark:bg-blue-900/50 px-4 py-2 border-b border-blue-300 dark:border-blue-600">
                    <h5 className="text-sm font-semibold text-blue-800 dark:text-blue-200">
                      Workflow Output (Structured)
                    </h5>
                  </div>
                  <div className="bg-blue-50 dark:bg-blue-950/50 p-4">
                    <pre className="text-blue-700 dark:text-blue-300 whitespace-pre-wrap break-words text-xs font-mono">
                      {JSON.stringify(workflowMetadata.current, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Error Full View Modal */}
      <Dialog open={errorModalOpen} onOpenChange={setErrorModalOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col">
          <DialogHeader className="px-6 pt-6 flex-shrink-0">
            <DialogTitle className="flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-destructive" />
              Workflow Error
            </DialogTitle>
            <DialogClose onClose={() => setErrorModalOpen(false)} />
          </DialogHeader>

          <div className="px-6 pb-6 overflow-y-auto flex-1">
            <div className="bg-destructive/5 rounded border-2 border-destructive/70 p-6">
              <div className="text-destructive whitespace-pre-wrap break-words text-sm font-mono">
                {workflowError}
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
