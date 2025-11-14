/**
 * WorkflowView - Complete workflow execution interface
 * Features: Workflow visualization, input forms, execution monitoring
 */

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import {
  Play,
  Settings,
  RotateCcw,
  Info,
  Workflow as WorkflowIcon,
  RefreshCw,
  Loader2,
  Trash2,
  Plus,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { LoadingState } from "@/components/ui/loading-state";
import { WorkflowInputForm } from "./workflow-input-form";
import { HilInputModal } from "./hil-input-modal";
import { Button } from "@/components/ui/button";
import { WorkflowFlow } from "./workflow-flow";
import { WorkflowDetailsModal } from "./workflow-details-modal";
import { ExecutionTimeline } from "./execution-timeline";
import { apiClient } from "@/services/api";
import { useDevUIStore } from "@/stores/devuiStore";
import type {
  WorkflowInfo,
  ExtendedResponseStreamEvent,
  JSONSchemaProperty,
} from "@/types";
import type { ResponseRequestInfoEvent } from "@/types/openai";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogClose,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type DebugEventHandler = (event: ExtendedResponseStreamEvent | "clear") => void;

// Compact Checkpoint Selector Component (currently unused - commented out in JSX)
/*
interface CheckpointSelectorProps {
  conversationId: string | undefined;
  selectedCheckpoint: string | undefined;
  onCheckpointSelect: (checkpointId: string | undefined) => void;
}

function CheckpointSelector({
  conversationId,
  selectedCheckpoint,
  onCheckpointSelect,
}: CheckpointSelectorProps) {
  const [checkpoints, setCheckpoints] = useState<
    Array<{
      checkpoint_id: string;
      timestamp: number;
    }>
  >([]);
  const [loading, setLoading] = useState(false);
  const addToast = useDevUIStore((state) => state.addToast);

  // Load checkpoints when conversation changes
  useEffect(() => {
    if (!conversationId) {
      setCheckpoints([]);
      return;
    }

    const loadCheckpoints = async () => {
      setLoading(true);
      try {
        // Fetch conversation items and filter for checkpoints
        const response = await apiClient.listConversationItems(conversationId, {
          limit: 100,
        });
        const checkpointItems = response.data
          .filter((item: any) => item.type === "checkpoint")
          .map((item: any) => ({
            checkpoint_id: item.checkpoint_id,
            timestamp: item.timestamp,
          }));
        setCheckpoints(checkpointItems);
      } catch (error) {
        console.error("Failed to load checkpoints:", error);
      } finally {
        setLoading(false);
      }
    };

    loadCheckpoints();
  }, [conversationId]);

  const handleDelete = async (checkpointId: string, e: React.MouseEvent) => {
    e.stopPropagation();

    if (!confirm("Delete this checkpoint?")) return;

    try {
      // Delete through conversation items API
      const itemId = `checkpoint_${checkpointId}`;
      await apiClient.deleteConversationItem(conversationId!, itemId);
      addToast({ message: "Checkpoint deleted", type: "success" });
      setCheckpoints((prev) =>
        prev.filter((cp) => cp.checkpoint_id !== checkpointId)
      );
      if (selectedCheckpoint === checkpointId) {
        onCheckpointSelect(undefined);
      }
    } catch (error) {
      console.error("Failed to delete checkpoint:", error);
      addToast({ message: "Failed to delete checkpoint", type: "error" });
    }
  };

  if (!conversationId || checkpoints.length === 0) {
    return null; // Hide when no conversation or no checkpoints
  }

  return (
    <Select
      value={selectedCheckpoint || "none"}
      onValueChange={(value) =>
        onCheckpointSelect(value === "none" ? undefined : value)
      }
      disabled={loading}
    >
      <SelectTrigger className="w-[200px] h-9 text-xs">
        <SelectValue placeholder="Resume from..." />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="none">Start Fresh (No Checkpoint)</SelectItem>
        {checkpoints.map((cp) => (
          <div
            key={cp.checkpoint_id}
            className="flex items-center justify-between group"
          >
            <SelectItem value={cp.checkpoint_id} className="flex-1">
              Checkpoint {new Date(cp.timestamp * 1000).toLocaleString()}
            </SelectItem>
            <button
              onClick={(e) => handleDelete(cp.checkpoint_id, e)}
              className="p-1 opacity-0 group-hover:opacity-100 hover:text-red-600 transition-opacity"
              title="Delete checkpoint"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          </div>
        ))}
      </SelectContent>
    </Select>
  );
}
*/

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
  const [workflowLoadError, setWorkflowLoadError] = useState<string | null>(
    null
  );
  const [openAIEvents, setOpenAIEvents] = useState<
    ExtendedResponseStreamEvent[]
  >([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedExecutorId, setSelectedExecutorId] = useState<string | null>(
    null
  );
  const [detailsModalOpen, setDetailsModalOpen] = useState(false);
  const [isReloading, setIsReloading] = useState(false);
  const [showTimeline, setShowTimeline] = useState(false);
  const [timelineMinimized, setTimelineMinimized] = useState(false);
  const [workflowResult, setWorkflowResult] = useState<string>("");

  // HIL (Human-in-the-Loop) state
  const [pendingHilRequests, setPendingHilRequests] = useState<
    Array<{
      request_id: string;
      request_data: Record<string, unknown>;
      request_schema: JSONSchemaProperty;
    }>
  >([]);
  const [hilResponses, setHilResponses] = useState<
    Record<string, Record<string, unknown>>
  >({});
  const [showHilModal, setShowHilModal] = useState(false);

  // Track per-item outputs (keyed by item.id, not executor_id to handle multiple runs)
  const itemOutputs = useRef<Record<string, string>>({});
  const currentStreamingItemId = useRef<string | null>(null);
  const workflowMetadata = useRef<Record<string, unknown> | null>(null);

  // Session management from store (replaces old checkpoint management)
  const currentSession = useDevUIStore((state) => state.currentSession);
  const availableSessions = useDevUIStore((state) => state.availableSessions);
  const loadingSessions = useDevUIStore((state) => state.loadingSessions);
  const setCurrentSession = useDevUIStore((state) => state.setCurrentSession);
  const setAvailableSessions = useDevUIStore(
    (state) => state.setAvailableSessions
  );
  const setLoadingSessions = useDevUIStore((state) => state.setLoadingSessions);
  const addSession = useDevUIStore((state) => state.addSession);
  const removeSession = useDevUIStore((state) => state.removeSession);
  const addToast = useDevUIStore((state) => state.addToast);
  const runtime = useDevUIStore((state) => state.runtime);

  // Selected checkpoint for resume (local state)
  const [selectedCheckpointId, setSelectedCheckpointId] = useState<
    string | null
  >(null);

  // View options state
  const [viewOptions, setViewOptions] = useState(() => {
    const saved = localStorage.getItem("workflowViewOptions");
    const defaults = {
      showMinimap: false,
      showGrid: true,
      animateRun: false,
      consolidateBidirectionalEdges: true,
    };

    if (saved) {
      const parsed = JSON.parse(saved);
      // Merge with defaults to ensure new properties exist
      return { ...defaults, ...parsed };
    }

    return defaults;
  });

  // Layout direction state
  const [layoutDirection, setLayoutDirection] = useState<"LR" | "TB">(() => {
    const saved = localStorage.getItem("workflowLayoutDirection");
    return (saved as "LR" | "TB") || "LR";
  });

  // Save view options to localStorage
  useEffect(() => {
    localStorage.setItem("workflowViewOptions", JSON.stringify(viewOptions));
  }, [viewOptions]);

  // Save layout direction to localStorage
  useEffect(() => {
    localStorage.setItem("workflowLayoutDirection", layoutDirection);
  }, [layoutDirection]);

  // View option handlers
  const toggleViewOption = (key: keyof typeof viewOptions) => {
    setViewOptions((prev: typeof viewOptions) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  // Handle workflow reload (hot reload)
  const handleReloadEntity = async () => {
    if (isReloading || !selectedWorkflow) return;

    setIsReloading(true);
    const { addToast, updateWorkflow } = await import("@/stores").then((m) => ({
      addToast: m.useDevUIStore.getState().addToast,
      updateWorkflow: m.useDevUIStore.getState().updateWorkflow,
    }));

    try {
      // Call backend reload endpoint
      await apiClient.reloadEntity(selectedWorkflow.id);

      // Fetch updated workflow info
      const updatedWorkflow = await apiClient.getWorkflowInfo(
        selectedWorkflow.id
      );

      // Update store with fresh metadata
      updateWorkflow(updatedWorkflow);

      // Update local state
      setWorkflowInfo(updatedWorkflow);

      // Show success toast
      addToast({
        message: `${selectedWorkflow.name} has been reloaded successfully`,
        type: "success",
      });
    } catch (error) {
      // Show error toast
      const errorMessage =
        error instanceof Error ? error.message : "Failed to reload entity";
      addToast({
        message: `Failed to reload: ${errorMessage}`,
        type: "error",
        duration: 6000,
      });
    } finally {
      setIsReloading(false);
    }
  };

  // Load workflow info when selectedWorkflow changes
  useEffect(() => {
    const loadWorkflowInfo = async () => {
      if (selectedWorkflow.type !== "workflow") return;

      setWorkflowLoading(true);
      setWorkflowLoadError(null);
      try {
        const info = await apiClient.getWorkflowInfo(selectedWorkflow.id);
        setWorkflowInfo(info);
        setWorkflowLoadError(null);

        // Note: Checkpoints are now loaded per-session via WorkflowSessionManager
        // When user selects a session, checkpoints will be loaded for that session
      } catch (error) {
        setWorkflowInfo(null);
        const errorMessage =
          error instanceof Error ? error.message : String(error);
        setWorkflowLoadError(errorMessage);
        console.error("Error loading workflow info:", error);
      } finally {
        setWorkflowLoading(false);
      }
    };

    // Clear state when workflow changes
    setOpenAIEvents([]);
    setIsStreaming(false);
    setSelectedExecutorId(null);
    setShowTimeline(false);
    setWorkflowResult("");
    setWorkflowLoadError(null);
    itemOutputs.current = {};
    currentStreamingItemId.current = null;
    workflowMetadata.current = null;

    loadWorkflowInfo();
  }, [selectedWorkflow.id, selectedWorkflow.type]);

  // Load sessions when workflow is selected
  useEffect(() => {
    const loadSessions = async () => {
      if (!workflowInfo) return;

      setLoadingSessions(true);
      try {
        const response = await apiClient.listWorkflowSessions(workflowInfo.id);

        // If no sessions exist, auto-create one
        if (response.data.length === 0) {
          const newSession = await apiClient.createWorkflowSession(
            workflowInfo.id,
            {
              name: `Conversation ${new Date().toLocaleString()}`,
            }
          );
          setAvailableSessions([newSession]);
          setCurrentSession(newSession);
        } else {
          setAvailableSessions(response.data);
          // Auto-select first session if none selected
          if (!currentSession) {
            const firstSession = response.data[0];
            setCurrentSession(firstSession);
            await handleSessionChange(firstSession);
          }
        }
      } catch (error) {
        console.error("Failed to load sessions:", error);

        // Silently handle for .NET backend (doesn't support conversations yet)
        // Only show error for Python backend where this is unexpected
        if (runtime !== "dotnet") {
          addToast({
            message: "Failed to load sessions",
            type: "error"
          });
        }
      } finally {
        setLoadingSessions(false);
      }
    };

    loadSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowInfo?.id, runtime]);

  // Handle session change - just clear checkpoint selection
  const handleSessionChange = useCallback(
    async (session: typeof currentSession) => {
      if (!session || !workflowInfo) return;
      // Clear selected checkpoint when switching sessions
      // CheckpointSelector component will load checkpoints automatically
      setSelectedCheckpointId(null);
    },
    [workflowInfo]
  );

  // Handle session select from dropdown
  const handleSessionSelect = useCallback(
    async (sessionId: string) => {
      const session = availableSessions.find(
        (s) => s.conversation_id === sessionId
      );
      if (session) {
        setCurrentSession(session);
        await handleSessionChange(session);
      }
    },
    [availableSessions, setCurrentSession, handleSessionChange]
  );

  // Handle new session creation
  const handleNewSession = useCallback(async () => {
    if (!workflowInfo) return;

    try {
      const newSession = await apiClient.createWorkflowSession(
        workflowInfo.id,
        {
          name: `Conversation ${new Date().toLocaleString()}`,
        }
      );
      addSession(newSession);
      setCurrentSession(newSession);
      await handleSessionChange(newSession);
      addToast({ message: "New session created", type: "success" });
    } catch (error) {
      console.error("Failed to create session:", error);
      addToast({ message: "Failed to create session", type: "error" });
    }
  }, [
    workflowInfo,
    addSession,
    setCurrentSession,
    handleSessionChange,
    addToast,
  ]);

  // Handle session deletion
  const handleDeleteSession = useCallback(async () => {
    if (!currentSession || !workflowInfo) return;

    if (!confirm("Delete this session? All checkpoints will be lost.")) return;

    try {
      await apiClient.deleteWorkflowSession(
        workflowInfo.id,
        currentSession.conversation_id
      );
      removeSession(currentSession.conversation_id);
      addToast({ message: "Session deleted", type: "success" });
    } catch (error) {
      console.error("Failed to delete session:", error);
      addToast({ message: "Failed to delete session", type: "error" });
    }
  }, [currentSession, workflowInfo, removeSession, addToast]);

  const handleNodeSelect = (executorId: string) => {
    setSelectedExecutorId(executorId);
  };

  // Extract workflow and output item events from OpenAI events for executor tracking
  const workflowEvents = useMemo(() => {
    return openAIEvents.filter(
      (event) =>
        event.type === "response.output_item.added" ||
        event.type === "response.output_item.done" ||
        event.type === "response.created" ||
        event.type === "response.in_progress" ||
        event.type === "response.completed" ||
        event.type === "response.failed" ||
        event.type === "response.workflow_event.completed" ||
        // Fallback: some backends may emit .complete instead of .completed
        event.type === "response.workflow_event.complete"
    );
  }, [openAIEvents]);

  // Show timeline when first workflow event arrives
  useEffect(() => {
    if (workflowEvents.length > 0 && !showTimeline) {
      setShowTimeline(true);
    }
  }, [workflowEvents.length, showTimeline]);

  // Extract executor history from workflow events (filter out workflow-level events)
  const executorHistory = useMemo(() => {
    const history: Array<{
      executorId: string;
      message: string;
      timestamp: string;
      status: "running" | "completed" | "error";
    }> = [];

    workflowEvents.forEach((event) => {
      // Handle new standard OpenAI events
      if (
        event.type === "response.output_item.added" ||
        event.type === "response.output_item.done"
      ) {
        const item = (event as any).item;
        if (item && item.type === "executor_action" && item.executor_id) {
          history.push({
            executorId: item.executor_id,
            message:
              event.type === "response.output_item.added"
                ? "Executor started"
                : item.status === "completed"
                ? "Executor completed"
                : item.status === "failed"
                ? "Executor failed"
                : "Executor processing",
            timestamp: new Date().toISOString(),
            status:
              item.status === "completed"
                ? "completed"
                : item.status === "failed"
                ? "error"
                : "running",
          });
        }
      }
      // Fallback: handle .complete variant for backwards compatibility
      else if (
        event.type === "response.workflow_event.complete" &&
        "data" in event &&
        event.data &&
        typeof event.data === "object"
      ) {
        const data = event.data as Record<string, unknown>;
        if (data.executor_id != null) {
          history.push({
            executorId: String(data.executor_id),
            message: String(data.event_type || "Processing"),
            timestamp: String(data.timestamp || new Date().toISOString()),
            status: String(data.event_type || "").includes("Completed")
              ? "completed"
              : String(data.event_type || "").includes("Error")
              ? "error"
              : "running",
          });
        }
      }
    });

    return history;
  }, [workflowEvents]);

  // Track active executors
  const activeExecutors = useMemo(() => {
    if (!isStreaming) return [];
    const recent = executorHistory
      .filter((h) => h.status === "running")
      .slice(-2);
    return recent.map((h) => h.executorId);
  }, [executorHistory, isStreaming]);

  // Handle workflow data sending (structured input)
  const handleSendWorkflowData = useCallback(
    async (inputData: Record<string, unknown>) => {
      if (!selectedWorkflow || selectedWorkflow.type !== "workflow") return;

      setIsStreaming(true);
      setOpenAIEvents([]); // Clear previous OpenAI events for new execution

      // Clear per-item outputs and metadata for new run
      setWorkflowResult("");
      itemOutputs.current = {};
      currentStreamingItemId.current = null;
      workflowMetadata.current = null;

      // Clear debug panel events for new workflow run
      onDebugEvent("clear");

      try {
        const request = {
          input_data: inputData,
          conversation_id: currentSession?.conversation_id || undefined, // Pass session conversation_id for checkpoint support
          checkpoint_id: selectedCheckpointId || undefined, // Pass selected checkpoint if any
        };

        // Clear any previous streaming state before starting new workflow execution
        // Note: Workflows don't use conversation IDs, so we use workflow ID as the key
        apiClient.clearStreamingState(selectedWorkflow.id);

        // Use OpenAI-compatible API streaming - direct event handling
        const streamGenerator = apiClient.streamWorkflowExecutionOpenAI(
          selectedWorkflow.id,
          request
        );

        for await (const openAIEvent of streamGenerator) {
          // Store workflow-related events for tracking
          if (
            openAIEvent.type === "response.output_item.added" ||
            openAIEvent.type === "response.output_item.done" ||
            openAIEvent.type === "response.created" ||
            openAIEvent.type === "response.in_progress" ||
            openAIEvent.type === "response.completed" ||
            openAIEvent.type === "response.failed" ||
            openAIEvent.type === "response.workflow_event.completed" ||
            openAIEvent.type === "response.workflow_event.complete" // Fallback variant
          ) {
            setOpenAIEvents((prev) => {
              // Generate unique timestamp for each event
              const baseTimestamp = Math.floor(Date.now() / 1000);
              const lastTimestamp =
                prev.length > 0
                  ? (prev[prev.length - 1] as any)._uiTimestamp || 0
                  : 0;
              const uniqueTimestamp = Math.max(
                baseTimestamp,
                lastTimestamp + 1
              );

              return [
                ...prev,
                {
                  ...openAIEvent,
                  _uiTimestamp: uniqueTimestamp,
                } as ExtendedResponseStreamEvent & { _uiTimestamp: number },
              ];
            });
          }

          // Pass to debug panel
          onDebugEvent(openAIEvent);

          // Handle new standard OpenAI events
          if (openAIEvent.type === "response.output_item.added") {
            const item = (openAIEvent as any).item;

            // Handle executor action items
            if (
              item &&
              item.type === "executor_action" &&
              item.executor_id &&
              item.id
            ) {
              // Track this item ID as the current streaming target
              currentStreamingItemId.current = item.id;
              // Initialize output for this specific item (not executor!)
              if (!itemOutputs.current[item.id]) {
                itemOutputs.current[item.id] = "";
              }
            }

            // Handle message items from Magentic agents (Option A implementation)
            if (
              item &&
              item.type === "message" &&
              item.metadata?.source === "magentic" &&
              item.id
            ) {
              // Track this message ID as the current streaming target for Magentic agents
              currentStreamingItemId.current = item.id;
              // Initialize output for this message
              if (!itemOutputs.current[item.id]) {
                itemOutputs.current[item.id] = "";
              }
            }

            // Handle workflow output messages (from ctx.yield_output) - different from agent messages
            if (
              item &&
              item.type === "message" &&
              !item.metadata?.source &&
              item.content
            ) {
              // Extract text from message content
              for (const content of item.content) {
                if (content.type === "output_text" && content.text) {
                  // Append to workflow result (support multiple yield_output calls)
                  setWorkflowResult((prev) => {
                    if (prev && prev.length > 0) {
                      // If there's existing output, add separator
                      return prev + "\n\n" + content.text;
                    }
                    return content.text;
                  });

                  // Try to parse as JSON for structured metadata
                  try {
                    const parsed = JSON.parse(content.text);
                    if (typeof parsed === "object" && parsed !== null) {
                      workflowMetadata.current = parsed;
                    }
                  } catch {
                    // Not JSON, keep as text
                  }
                }
              }
            }
          }

          // Handle workflow completion
          if (openAIEvent.type === "response.completed") {
            // Workflow completed successfully
            // Final output is already in workflowResult from text streaming or output_item.added
          }

          // Handle workflow failure
          if (openAIEvent.type === "response.failed") {
            // Error will be displayed in timeline
          }

          // Fallback support for workflow_event format (used for unhandled event types)
          if (
            openAIEvent.type === "response.workflow_event.completed" &&
            "data" in openAIEvent &&
            openAIEvent.data
          ) {
            const data = openAIEvent.data as {
              event_type?: string;
              data?: unknown;
              executor_id?: string | null;
            };

            // Track when executor starts (fallback for old workflow_event format)
            if (
              data.event_type === "ExecutorInvokedEvent" &&
              data.executor_id
            ) {
              // Create synthetic item ID for fallback format (no real item.id available)
              const syntheticItemId = `fallback_${
                data.executor_id
              }_${Date.now()}`;
              currentStreamingItemId.current = syntheticItemId;
              // Initialize output for this item
              if (!itemOutputs.current[syntheticItemId]) {
                itemOutputs.current[syntheticItemId] = "";
              }
            }

            // Handle workflow completion and output events
            if (
              (data.event_type === "WorkflowCompletedEvent" ||
                data.event_type === "WorkflowOutputEvent") &&
              data.data
            ) {
              // Store object data for metadata
              if (typeof data.data === "object") {
                workflowMetadata.current = data.data as Record<string, unknown>;
              }
              currentStreamingItemId.current = null;
            }
          }

          // Handle text output - assign to current item (not executor!)
          if (
            openAIEvent.type === "response.output_text.delta" &&
            "delta" in openAIEvent &&
            openAIEvent.delta
          ) {
            // Determine which ITEM (specific run) owns this text
            const itemId = currentStreamingItemId.current;

            if (itemId) {
              // Initialize item output if needed
              if (!itemOutputs.current[itemId]) {
                itemOutputs.current[itemId] = "";
              }

              // Append to specific ITEM's output (not all runs of this executor!)
              itemOutputs.current[itemId] += openAIEvent.delta;
            }
          }

          // Handle HIL (Human-in-the-Loop) requests
          if (openAIEvent.type === "response.request_info.requested") {
            const hilEvent = openAIEvent as ResponseRequestInfoEvent;

            setPendingHilRequests((prev) => [
              ...prev,
              {
                request_id: hilEvent.request_id,
                request_data: hilEvent.request_data,
                request_schema:
                  hilEvent.request_schema as unknown as JSONSchemaProperty,
              },
            ]);

            // Initialize responses with default values from schema
            // For enum fields, set to first option; for other fields with defaults, use those
            const schema =
              hilEvent.request_schema as unknown as JSONSchemaProperty;
            const defaultValues: Record<string, unknown> = {};

            if (schema.properties) {
              Object.entries(schema.properties).forEach(
                ([fieldName, fieldSchema]) => {
                  const field = fieldSchema as JSONSchemaProperty;
                  // Set default for enum fields to first option
                  if (field.enum && field.enum.length > 0) {
                    defaultValues[fieldName] = field.enum[0];
                  }
                  // Use explicit default value if provided
                  else if (field.default !== undefined) {
                    defaultValues[fieldName] = field.default;
                  }
                }
              );
            }

            setHilResponses((prev) => ({
              ...prev,
              [hilEvent.request_id]: defaultValues,
            }));

            // Auto-show modal when first request arrives
            if (pendingHilRequests.length === 0) {
              setShowHilModal(true);
            }
          }

          // Handle errors (ResponseErrorEvent - fallback error format)
          if (openAIEvent.type === "error") {
            // Error will be displayed in timeline
            break;
          }
        }

        // Check if workflow ended with pending HIL requests
        if (pendingHilRequests.length > 0 && !showHilModal) {
          setShowHilModal(true);
        }

        setIsStreaming(false);
      } catch (error) {
        // Error will be displayed in timeline
        console.error("Workflow execution error:", error);
        setIsStreaming(false);
      }
    },
    [
      selectedWorkflow,
      onDebugEvent,
      workflowInfo,
      currentSession,
      selectedCheckpointId,
    ]
  );

  // Handle HIL response submission
  const handleSubmitHilResponses = useCallback(async () => {
    if (!selectedWorkflow || selectedWorkflow.type !== "workflow") return;

    setShowHilModal(false);
    setIsStreaming(true);

    try {
      // Create OpenAI request with workflow_hil_response content type
      const request = {
        input_data: [
          {
            type: "message",
            content: [
              {
                type: "workflow_hil_response",
                responses: hilResponses,
              },
            ],
          },
        ] as any, // OpenAI Responses API format, cast to satisfy TypeScript
        conversation_id: currentSession?.conversation_id || undefined,
        checkpoint_id: selectedCheckpointId || undefined, // Pass selected checkpoint
      };

      // Use OpenAI-compatible API streaming to continue workflow
      const streamGenerator = apiClient.streamWorkflowExecutionOpenAI(
        selectedWorkflow.id,
        request
      );

      for await (const openAIEvent of streamGenerator) {
        // Store workflow-related events
        if (
          openAIEvent.type === "response.output_item.added" ||
          openAIEvent.type === "response.output_item.done" ||
          openAIEvent.type === "response.created" ||
          openAIEvent.type === "response.in_progress" ||
          openAIEvent.type === "response.completed" ||
          openAIEvent.type === "response.failed" ||
          openAIEvent.type === "response.workflow_event.completed"
        ) {
          setOpenAIEvents((prev) => {
            // Generate unique timestamp for each event
            const baseTimestamp = Math.floor(Date.now() / 1000);
            const lastTimestamp =
              prev.length > 0
                ? (prev[prev.length - 1] as any)._uiTimestamp || 0
                : 0;
            const uniqueTimestamp = Math.max(baseTimestamp, lastTimestamp + 1);

            return [
              ...prev,
              {
                ...openAIEvent,
                _uiTimestamp: uniqueTimestamp,
              } as ExtendedResponseStreamEvent & { _uiTimestamp: number },
            ];
          });
        }

        // Pass to debug panel
        onDebugEvent(openAIEvent);

        // Handle workflow output items (from ctx.yield_output)
        if (openAIEvent.type === "response.output_item.added") {
          const item = (openAIEvent as any).item;

          // Handle executor action items
          if (
            item &&
            item.type === "executor_action" &&
            item.executor_id &&
            item.id
          ) {
            currentStreamingItemId.current = item.id;
            if (!itemOutputs.current[item.id]) {
              itemOutputs.current[item.id] = "";
            }
          }

          // Handle workflow output messages
          if (item && item.type === "message" && item.content) {
            // Extract text from message content
            for (const content of item.content) {
              if (content.type === "output_text" && content.text) {
                // Append to workflow result (support multiple yield_output calls)
                setWorkflowResult((prev) => {
                  if (prev && prev.length > 0) {
                    // If there's existing output, add separator
                    return prev + "\n\n" + content.text;
                  }
                  return content.text;
                });

                // Try to parse as JSON for structured metadata
                try {
                  const parsed = JSON.parse(content.text);
                  if (typeof parsed === "object" && parsed !== null) {
                    workflowMetadata.current = parsed;
                  }
                } catch {
                  // Not JSON, keep as text
                }
              }
            }
          }
        }

        // Handle text output - assign to current item (not executor!)
        if (
          openAIEvent.type === "response.output_text.delta" &&
          "delta" in openAIEvent &&
          openAIEvent.delta
        ) {
          const itemId = currentStreamingItemId.current;
          if (itemId) {
            if (!itemOutputs.current[itemId]) {
              itemOutputs.current[itemId] = "";
            }
            itemOutputs.current[itemId] += openAIEvent.delta;
          }
        }

        // Handle completion
        if (openAIEvent.type === "response.completed") {
          // Workflow completed successfully
        }

        // Handle errors
        if (openAIEvent.type === "response.failed") {
          // Error will be displayed in timeline
        }
      }

      // Clear HIL state after successful submission
      setPendingHilRequests([]);
      setHilResponses({});
      setIsStreaming(false);
    } catch (error) {
      // Error will be displayed in timeline
      console.error("HIL submission error:", error);
      setIsStreaming(false);
    }
  }, [
    selectedWorkflow,
    hilResponses,
    onDebugEvent,
    currentSession,
    selectedCheckpointId,
  ]);

  // Show loading state when workflow is being loaded
  if (workflowLoading) {
    return (
      <LoadingState
        message="Loading workflow..."
        description="Fetching workflow structure and configuration"
      />
    );
  }

  // Show error state if workflow failed to load
  if (workflowLoadError) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center max-w-md p-6">
          <div className="text-red-500 mb-4">
            <svg
              className="w-16 h-16 mx-auto"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <h3 className="text-lg font-semibold mb-2">
            Failed to Load Workflow
          </h3>
          <p className="text-sm text-muted-foreground mb-4">
            {workflowLoadError}
          </p>
          <p className="text-xs text-muted-foreground">
            This may not be a valid workflow entity. Check the file contains a
            workflow export.
          </p>
        </div>
      </div>
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
            <Button
              variant="ghost"
              size="sm"
              onClick={handleReloadEntity}
              disabled={
                isReloading || selectedWorkflow.metadata?.source === "in_memory"
              }
              className="h-6 w-6 p-0 flex-shrink-0"
              title={
                selectedWorkflow.metadata?.source === "in_memory"
                  ? "In-memory entities cannot be reloaded"
                  : isReloading
                  ? "Reloading..."
                  : "Reload entity code (hot reload)"
              }
            >
              <RefreshCw
                className={`h-4 w-4 ${isReloading ? "animate-spin" : ""}`}
              />
            </Button>
          </div>

          {/* Workflow Session & Checkpoint Controls - Compact header like agent view */}
          {workflowInfo && (
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 flex-shrink-0">
              {/* Session Dropdown */}
              <Select
                value={currentSession?.conversation_id || ""}
                onValueChange={handleSessionSelect}
                disabled={loadingSessions}
              >
                <SelectTrigger className="w-full sm:w-64">
                  <SelectValue
                    placeholder={
                      loadingSessions
                        ? "Loading..."
                        : availableSessions.length === 0
                        ? "No conversations"
                        : "Select conversation"
                    }
                  >
                    {currentSession && (
                      <div className="flex items-center gap-2 text-xs">
                        <span>
                          {currentSession.metadata.name ||
                            `Conversation ${currentSession.conversation_id.slice(
                              -8
                            )}`}
                        </span>
                      </div>
                    )}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {availableSessions.map((session) => (
                    <SelectItem
                      key={session.conversation_id}
                      value={session.conversation_id}
                    >
                      <div className="flex items-center justify-between w-full">
                        <span>
                          {session.metadata.name ||
                            `Conversation ${session.conversation_id.slice(-8)}`}
                        </span>
                        {session.created_at && (
                          <span className="text-xs text-muted-foreground ml-3">
                            {new Date(
                              session.created_at * 1000
                            ).toLocaleTimeString()}
                          </span>
                        )}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Delete Session Button */}
              <Button
                variant="ghost"
                size="sm"
                onClick={handleDeleteSession}
                disabled={!currentSession || loadingSessions}
                className="h-9 w-9 p-0"
                title="Delete current session"
              >
                <Trash2 className="h-4 w-4 " />
              </Button>

              {/* New Session Button */}
              <Button
                variant="ghost"
                size="sm"
                onClick={handleNewSession}
                disabled={loadingSessions}
                className="h-9 px-3"
                title="New session"
              >
                <Plus className="h-4 w-4" />
              </Button>

              {/* Checkpoint Dropdown */}
              {/* <CheckpointSelector
                conversationId={currentSession?.conversation_id}
                selectedCheckpoint={selectedCheckpointId || undefined}
                onCheckpointSelect={(checkpointId) => setSelectedCheckpointId(checkpointId || null)}
              /> */}

              {/* Run Button */}
              <RunWorkflowButton
                inputSchema={workflowInfo.input_schema}
                onRun={handleSendWorkflowData}
                isSubmitting={isStreaming}
                workflowState={
                  isStreaming
                    ? "running"
                    : executorHistory.length > 0
                    ? "completed"
                    : "ready"
                }
                executorHistory={executorHistory}
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

      {/* Side-by-side Layout: Workflow Graph (left) + Execution Timeline (right) */}
      <div className="flex-1 min-h-0 flex gap-0">
        {/* Left: Workflow Visualization */}
        <div className="flex-1 min-w-0 transition-all duration-300">
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
              timelineVisible={showTimeline}
            />
          )}
        </div>

        {/* Right: Execution Timeline - inflates from left on first event */}
        {showTimeline && (
          <div
            className="flex-shrink-0 overflow-hidden transition-all duration-300 ease-out border-l"
            style={{
              width: timelineMinimized ? "2.5rem" : "24rem",
            }}
          >
            {timelineMinimized ? (
              /* Minimized Timeline - Vertical Bar (fully clickable) */
              <div
                className="h-full w-10 bg-background flex flex-col items-center py-2 cursor-pointer hover:bg-accent/50 transition-colors"
                onClick={() => setTimelineMinimized(false)}
                title="Expand timeline"
              >
                {/* Expand button at top (visual affordance) */}
                <div className="h-8 w-8 flex items-center justify-center">
                  <ChevronLeft className="h-4 w-4 text-muted-foreground" />
                </div>

                {/* Text and count centered in middle */}
                <div className="flex-1 flex flex-col items-center justify-center gap-2 pointer-events-none">
                  <div
                    className="text-xs text-muted-foreground select-none"
                    style={{
                      writingMode: "vertical-rl",
                      transform: "rotate(180deg)",
                    }}
                  >
                    Execution Timeline
                  </div>
                  {workflowEvents.length > 0 && (
                    <div
                      className={`bg-primary text-primary-foreground rounded-full w-5 h-5 flex items-center justify-center ${
                        isStreaming ? "animate-pulse" : ""
                      }`}
                      style={{ fontSize: "10px" }}
                    >
                      {workflowEvents.length}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              /* Expanded Timeline */
              <div className="w-96 h-full flex flex-col">
                {/* Timeline Header with Count Badge and Minimize Button */}
                <div className="flex items-center justify-between p-2 border-b">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-medium">Execution Timeline</h3>
                    {workflowEvents.length > 0 && (
                      <div
                        className={`bg-primary text-primary-foreground rounded-full px-2 h-5 flex items-center justify-center ${
                          isStreaming ? "animate-pulse" : ""
                        }`}
                        style={{ fontSize: "11px", minWidth: "20px" }}
                      >
                        {workflowEvents.length}
                      </div>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setTimelineMinimized(true)}
                    className="h-8 w-8 p-0"
                    title="Minimize timeline"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
                {/* Timeline Content - No duplicate header */}
                <div className="flex-1 min-h-0 overflow-hidden">
                  <ExecutionTimeline
                    events={workflowEvents}
                    itemOutputs={itemOutputs.current}
                    currentExecutorId={
                      activeExecutors[activeExecutors.length - 1] || null
                    }
                    isStreaming={isStreaming}
                    onExecutorClick={handleNodeSelect}
                    selectedExecutorId={selectedExecutorId}
                    workflowResult={workflowResult}
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Workflow Details Modal */}
      <WorkflowDetailsModal
        workflow={selectedWorkflow}
        open={detailsModalOpen}
        onOpenChange={setDetailsModalOpen}
      />

      {/* HIL (Human-in-the-Loop) Input Modal */}
      <HilInputModal
        open={showHilModal}
        onOpenChange={setShowHilModal}
        requests={pendingHilRequests}
        responses={hilResponses}
        onResponseChange={(requestId, values) => {
          setHilResponses((prev) => ({
            ...prev,
            [requestId]: values,
          }));
        }}
        onSubmit={handleSubmitHilResponses}
        isSubmitting={isStreaming}
      />
    </div>
  );
}
