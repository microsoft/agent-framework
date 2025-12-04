/**
 * WorkflowView - Complete workflow execution interface
 * Features: Workflow visualization, input forms, execution monitoring
 */

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { useCancellableRequest, isAbortError } from "@/hooks";
import {
  Info,
  Workflow as WorkflowIcon,
  RefreshCw,
  Trash2,
  Plus,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  Send,
} from "lucide-react";
import { LoadingState } from "@/components/ui/loading-state";
import { RunWorkflowButton } from "./run-workflow-button";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { WorkflowFlow } from "./workflow-flow";
import { WorkflowDetailsModal } from "./workflow-details-modal";
import { CheckpointInfoModal } from "./checkpoint-info-modal";
import { ExecutionTimeline } from "./execution-timeline";
import { validateSchemaForm } from "./schema-form-renderer";
import { apiClient } from "@/services/api";
import { useDevUIStore } from "@/stores/devuiStore";
import type {
  WorkflowInfo,
  ExtendedResponseStreamEvent,
  JSONSchemaProperty,
  CheckpointItem,
} from "@/types";
import type { ResponseRequestInfoEvent } from "@/types/openai";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type DebugEventHandler = (event: ExtendedResponseStreamEvent | "clear") => void;

interface WorkflowViewProps {
  selectedWorkflow: WorkflowInfo;
  onDebugEvent: DebugEventHandler;
}

// TODO: CheckpointSelector is not currently used but may be needed for checkpoint resumption feature
// Smart Run Workflow Button Component moved to separate file

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
  const [wasCancelled, setWasCancelled] = useState(false);
  const [selectedExecutorId, setSelectedExecutorId] = useState<string | null>(
    null
  );
  const [detailsModalOpen, setDetailsModalOpen] = useState(false);
  const [checkpointInfoModalOpen, setCheckpointInfoModalOpen] = useState(false);
  const [isReloading, setIsReloading] = useState(false);
  const [timelineMinimized, setTimelineMinimized] = useState(false);
  const [workflowResult, setWorkflowResult] = useState<string>("");
  const [sessionCheckpoints, setSessionCheckpoints] = useState<CheckpointItem[]>([]);

  // Use the cancellation hook
  const { isCancelling, createAbortSignal, handleCancel, resetCancelling } =
    useCancellableRequest();

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
    return (saved as "LR" | "TB") || "TB";
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
    // Timeline stays visible (we changed this to always show)
    setWorkflowResult("");
    setWorkflowLoadError(null);
    itemOutputs.current = {};
    currentStreamingItemId.current = null;
    workflowMetadata.current = null;

    loadWorkflowInfo();
  }, [selectedWorkflow.id, selectedWorkflow.type]);

  // Load sessions when workflow is selected
  const loadSessions = useCallback(async () => {
    if (!workflowInfo) return;

    setLoadingSessions(true);
    try {
      const response = await apiClient.listWorkflowSessions(workflowInfo.id);

      // If no sessions exist, auto-create one
      if (response.data.length === 0) {
        const newSession = await apiClient.createWorkflowSession(
          workflowInfo.id,
          {
            name: `Checkpoint Storage ${new Date().toLocaleString()}`,
          }
        );
        setAvailableSessions([newSession]);
        setCurrentSession(newSession);
      } else {
        // Sort by created_at descending (most recent first)
        const sortedSessions = [...response.data].sort((a, b) => b.created_at - a.created_at);

        setAvailableSessions(sortedSessions);

        // Auto-select most recent session if none selected (but keep current if it exists)
        if (!currentSession) {
          const firstSession = sortedSessions[0];
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
          type: "error",
        });
      }
    } finally {
      setLoadingSessions(false);
    }
    // Note: handleSessionChange is intentionally omitted from dependencies to avoid circular dependency.
    // It's only called conditionally on initial session selection, not on every loadSessions call.
  }, [workflowInfo, currentSession, runtime, addToast, setAvailableSessions, setCurrentSession]);

  useEffect(() => {
    loadSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowInfo?.id, runtime]);

  // Load checkpoint items for current session (for checkpoint info modal)
  const loadCheckpoints = useCallback(async () => {
    if (!currentSession) {
      setSessionCheckpoints([]);
      return;
    }

    try {
      const response = await apiClient.listConversationItems(
        currentSession.conversation_id,
        { limit: 100 }
      );
      const checkpointItems = response.data.filter(
        (item: any) => item.type === "checkpoint"
      ) as CheckpointItem[];
      setSessionCheckpoints(checkpointItems);
    } catch (error) {
      console.error(`Failed to load checkpoints for session ${currentSession.conversation_id}:`, error);
      setSessionCheckpoints([]);
    }
  }, [currentSession]);

  // Only load checkpoints when modal opens or session changes while modal is open
  useEffect(() => {
    if (checkpointInfoModalOpen && currentSession) {
      loadCheckpoints();
    }
  }, [checkpointInfoModalOpen, currentSession, loadCheckpoints]);

  // Handle session change - reset workflow view state
  const handleSessionChange = useCallback(
    async (session: typeof currentSession) => {
      if (!session || !workflowInfo) return;

      // Reset workflow view state when switching checkpoint storages
      setOpenAIEvents([]);
      setIsStreaming(false);
      setWasCancelled(false);
      setSelectedExecutorId(null);
      setTimelineMinimized(false);
      setWorkflowResult("");
      setPendingHilRequests([]);
      setHilResponses({});
      itemOutputs.current = {};
      currentStreamingItemId.current = null;
      workflowMetadata.current = null;
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
          name: `Checkpoint Storage ${new Date().toLocaleString()}`,
        }
      );

      // Debug logging
      console.log("[WorkflowView] Created new session:", newSession.conversation_id);
      console.log("[WorkflowView] Previous session:", currentSession?.conversation_id);

      addSession(newSession);
      setCurrentSession(newSession);
      await handleSessionChange(newSession);

      // Force a small delay to ensure state is updated
      await new Promise(resolve => setTimeout(resolve, 100));

      addToast({ message: "New checkpoint storage created", type: "success" });
    } catch (error) {
      console.error("Failed to create checkpoint storage:", error);
      addToast({ message: "Failed to create checkpoint storage", type: "error" });
    }
  }, [
    workflowInfo,
    currentSession,
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

  // Timeline is now always visible, no need to control visibility

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
        const item = (
          event as
            | import("@/types/openai").ResponseOutputItemAddedEvent
            | import("@/types/openai").ResponseOutputItemDoneEvent
        ).item;
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
    async (inputData: Record<string, unknown>, checkpointId?: string) => {
      if (!selectedWorkflow || selectedWorkflow.type !== "workflow") return;

      setIsStreaming(true);
      setWasCancelled(false); // Reset cancelled state for new run
      setOpenAIEvents([]); // Clear previous OpenAI events for new execution

      // Clear per-item outputs and metadata for new run
      setWorkflowResult("");
      itemOutputs.current = {};
      currentStreamingItemId.current = null;
      workflowMetadata.current = null;

      // Clear HIL state for new workflow run
      setPendingHilRequests([]);
      setHilResponses({});

      // Clear debug panel events for new workflow run
      onDebugEvent("clear");

      // Create new AbortController for this request
      const signal = createAbortSignal();

      try {
        // Debug logging to track conversation ID usage
        console.log("[WorkflowView] Running workflow with:");
        console.log("  - Current session ID:", currentSession?.conversation_id);
        console.log("  - Input data:", inputData);

        const request = {
          input_data: inputData,
          conversation_id: currentSession?.conversation_id || undefined, // Pass session conversation_id for checkpoint support
          checkpoint_id: checkpointId, // Pass checkpoint ID when resuming from a checkpoint
        };

        // Clear any previous streaming state before starting new workflow execution
        // Use conversation ID if available, otherwise use workflow ID
        if (currentSession?.conversation_id) {
          apiClient.clearStreamingState(currentSession.conversation_id);
        } else {
          apiClient.clearStreamingState(selectedWorkflow.id);
        }

        // Use OpenAI-compatible API streaming - direct event handling
        const streamGenerator = apiClient.streamWorkflowExecutionOpenAI(
          selectedWorkflow.id,
          request,
          signal
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
                  ? (prev[prev.length - 1] as { _uiTimestamp?: number })
                      ._uiTimestamp || 0
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
            const item = (
              openAIEvent as import("@/types/openai").ResponseOutputItemAddedEvent
            ).item;

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
            // Use the item_id from the event itself (for concurrent workflows)
            // Fall back to currentStreamingItemId for backwards compatibility
            const itemId =
              openAIEvent.item_id || currentStreamingItemId.current;

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
          }

          // Handle errors (ResponseErrorEvent - fallback error format)
          if (openAIEvent.type === "error") {
            // Error will be displayed in timeline
            break;
          }
        }

        setIsStreaming(false);
      } catch (error) {
        // Handle abort separately - don't show error message
        if (isAbortError(error)) {
          // User cancelled - just stop gracefully
          console.log("Workflow execution cancelled by user");
          setWasCancelled(true); // Mark as cancelled for UI feedback
          // Leave the last state visible to show where workflow was when cancelled
          // Clear any pending HIL requests since workflow is cancelled
          setPendingHilRequests([]);
          setHilResponses({});
        } else {
          // Other errors - log them
          console.error("Workflow execution error:", error);
        }
        setIsStreaming(false);
        resetCancelling();
      }
    },
    [
      selectedWorkflow,
      onDebugEvent,
      currentSession,
      createAbortSignal,
      resetCancelling,
    ]
  );

  // Check if all HIL responses are valid
  const areAllHilResponsesValid = useCallback(() => {
    // Check each pending request has a valid response
    for (const request of pendingHilRequests) {
      const response = hilResponses[request.request_id] || {};
      // Use the same validation logic as HilTimelineItem
      if (!validateSchemaForm(request.request_schema, response)) {
        return false;
      }
    }
    return true;
  }, [pendingHilRequests, hilResponses]);

  // Handle HIL response submission
  const handleSubmitHilResponses = useCallback(async () => {
    if (!selectedWorkflow || selectedWorkflow.type !== "workflow") return;

    // Only submit if ALL forms are valid
    if (!areAllHilResponsesValid()) {
      console.warn("Cannot submit: Not all HIL forms are valid");
      return;
    }

    setIsStreaming(true);

    // Clear pending HIL requests immediately after submission
    // They've been submitted, so we shouldn't show them anymore
    setPendingHilRequests([]);
    setHilResponses({});

    // Create new AbortController for HIL submission
    const signal = createAbortSignal();

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
        ] as unknown as Record<string, unknown>, // OpenAI Responses API format, cast to satisfy RunWorkflowRequest type
        conversation_id: currentSession?.conversation_id || undefined,
        // checkpoint_id: undefined, // Checkpoint functionality currently disabled
      };

      // Use OpenAI-compatible API streaming to continue workflow
      const streamGenerator = apiClient.streamWorkflowExecutionOpenAI(
        selectedWorkflow.id,
        request,
        signal
      );

      // Track if new HIL requests arrive during response processing
      let newHilRequestsArrived = false;
      const newHilRequests: typeof pendingHilRequests = [];

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
                ? (prev[prev.length - 1] as { _uiTimestamp?: number })
                    ._uiTimestamp || 0
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

        // Check for new HIL requests after sending responses - handles multi-round HIL
        if (openAIEvent.type === "response.request_info.requested") {
          const hilEvent = openAIEvent as ResponseRequestInfoEvent;
          newHilRequestsArrived = true;

          // Cast to the correct type for setPendingHilRequests
          const typedHilEvent = {
            request_id: hilEvent.request_id,
            request_data: hilEvent.request_data,
            request_schema:
              hilEvent.request_schema as unknown as JSONSchemaProperty,
          };

          // Collect new requests (don't update state yet)
          newHilRequests.push(typedHilEvent);

          // Initialize response data with defaults from schema
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
        }

        // Handle workflow output items (from ctx.yield_output)
        if (openAIEvent.type === "response.output_item.added") {
          const item = (
            openAIEvent as import("@/types/openai").ResponseOutputItemAddedEvent
          ).item;

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
          // Workflow completed successfully - refetch checkpoints
          await loadCheckpoints();
        }

        // Handle errors
        if (openAIEvent.type === "response.failed") {
          // Error will be displayed in timeline - refetch checkpoints
          await loadCheckpoints();
        }
      }

      // Handle new HIL requests if any arrived during processing
      if (newHilRequestsArrived) {
        // Set the new pending requests
        setPendingHilRequests(newHilRequests);
        // Note: HIL responses are already initialized when requests arrive (lines 1198-1201)
        // No need to reinitialize them here
      }

      // Stream is done - refetch checkpoints to update badge count
      setIsStreaming(false);
      await loadCheckpoints();
    } catch (error) {
      // Handle abort separately
      if (isAbortError(error)) {
        console.log("HIL submission cancelled by user");
        setWasCancelled(true); // Mark as cancelled for UI feedback
      } else {
        // Other errors
        console.error("HIL submission error:", error);
      }
      setIsStreaming(false);
      resetCancelling();
      // Refetch checkpoints even on error/cancel
      await loadCheckpoints();
    }
  }, [
    selectedWorkflow,
    hilResponses,
    onDebugEvent,
    currentSession,
    areAllHilResponsesValid,
    createAbortSignal,
    resetCancelling,
    loadCheckpoints,
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
            {/* Only show reload button for directory-based entities */}
            {selectedWorkflow.source !== "in_memory" && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleReloadEntity}
                disabled={isReloading}
                className="h-6 w-6 p-0 flex-shrink-0"
                title={
                  isReloading
                    ? "Reloading..."
                    : "Reload entity code (hot reload)"
                }
              >
                <RefreshCw
                  className={`h-4 w-4 ${isReloading ? "animate-spin" : ""}`}
                />
              </Button>
            )}
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
                        ? "No checkpoint storages"
                        : "Select checkpoint storage"
                    }
                  >
                    {currentSession && (
                      <div className="flex items-center gap-2 text-xs">
                        <span className="truncate">
                          {currentSession.metadata.name ||
                            `Checkpoint Storage ${currentSession.conversation_id.slice(
                              -8
                            )}`}
                        </span>
                        {currentSession.metadata.checkpoint_summary && currentSession.metadata.checkpoint_summary.count > 0 && (
                          <div className="flex items-center gap-1 flex-shrink-0">
                            <Badge variant="secondary" className="h-4 px-1.5 text-[10px]">
                              {currentSession.metadata.checkpoint_summary.count}
                            </Badge>
                            {currentSession.metadata.checkpoint_summary.has_pending_hil && (
                              <Badge variant="secondary" className="h-4 px-1.5 text-[10px]">
                                HIL
                              </Badge>
                            )}
                          </div>
                        )}
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
                      <div className="flex items-center justify-between w-full gap-2">
                        <span className="truncate">
                          {session.metadata.name ||
                            `Checkpoint Storage ${session.conversation_id.slice(-8)}`}
                        </span>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          {session.created_at && (
                            <span className="text-xs text-muted-foreground">
                              {new Date(
                                session.created_at * 1000
                              ).toLocaleTimeString()}
                            </span>
                          )}
                          {session.metadata.checkpoint_summary && session.metadata.checkpoint_summary.count > 0 && (
                            <>
                              <Badge variant="secondary" className="h-4 px-1.5 text-[10px]">
                                {session.metadata.checkpoint_summary.count}
                              </Badge>
                              {session.metadata.checkpoint_summary.has_pending_hil && (
                                <Badge variant="secondary" className="h-4 px-1.5 text-[10px]">
                                  HIL
                                </Badge>
                              )}
                            </>
                          )}
                        </div>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Checkpoint Info Button */}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setCheckpointInfoModalOpen(true)}
                disabled={!currentSession}
                className="h-9 w-9 p-0 flex-shrink-0"
                title="View checkpoint details"
              >
                <Info className="h-4 w-4" />
              </Button>

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

              {/* Run Button - only show when timeline is minimized */}
              {timelineMinimized && (
                <RunWorkflowButton
                  inputSchema={workflowInfo.input_schema}
                  onRun={handleSendWorkflowData}
                  onCancel={handleCancel}
                  isSubmitting={isStreaming}
                  isCancelling={isCancelling}
                  workflowState={
                    isStreaming
                      ? "running"
                      : executorHistory.length > 0
                      ? "completed"
                      : "ready"
                  }
                  checkpoints={sessionCheckpoints}
                  showCheckpoints={false}
                />
              )}
            </div>
          )}
        </div>

        {selectedWorkflow.description && (
          <p className="text-sm text-muted-foreground">
            {selectedWorkflow.description}
          </p>
        )}
      </div>

      {/* HIL Warning Bar */}
      {pendingHilRequests.length > 0 && (
        <div className="bg-orange-100 dark:bg-orange-950/30 border-b border-orange-300 dark:border-orange-800 px-4 py-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-orange-600 dark:text-orange-400" />
              <span className="text-sm font-medium text-orange-900 dark:text-orange-100">
                Workflow is waiting for your input ({pendingHilRequests.length}{" "}
                request{pendingHilRequests.length > 1 ? "s" : ""})
              </span>
            </div>
            <div className="flex items-center gap-2">
              {pendingHilRequests.length > 1 && (
                <Button
                  size="sm"
                  onClick={handleSubmitHilResponses}
                  disabled={!areAllHilResponsesValid() || isStreaming}
                  className="gap-1"
                >
                  <Send className="w-3.5 h-3.5" />
                  Submit All
                </Button>
              )}
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  // Scroll to HIL form in timeline
                  const hilForm = document.querySelector("[data-hil-form]");
                  hilForm?.scrollIntoView({
                    behavior: "smooth",
                    block: "center",
                  });
                }}
                className="text-orange-700 hover:text-orange-900 dark:text-orange-400 dark:hover:text-orange-200"
              >
                Jump to input →
              </Button>
            </div>
          </div>
        </div>
      )}

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
              timelineVisible={true}
            />
          )}
        </div>

        {/* Right: Execution Timeline - inflates from left on first event */}
        <div
            className="flex-shrink-0 overflow-hidden transition-all duration-300 ease-out border-l"
            style={{
              width: timelineMinimized ? "2.5rem" : "28rem", // Increased width for better form display
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
              <div className="w-[28rem] h-full flex flex-col">
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
                    pendingHilRequests={pendingHilRequests}
                    hilResponses={hilResponses}
                    onHilResponseChange={(requestId, values) => {
                      setHilResponses((prev) => ({
                        ...prev,
                        [requestId]: values,
                      }));
                    }}
                    onHilSubmit={handleSubmitHilResponses}
                    isSubmittingHil={isStreaming}
                    // New props for bottom control
                    inputSchema={workflowInfo?.input_schema}
                    onRun={(data, checkpointId) => {
                      // Use the form data from timeline
                      handleSendWorkflowData(data, checkpointId);
                    }}
                    onCancel={handleCancel}
                    isCancelling={isCancelling}
                    workflowState={
                      isStreaming
                        ? "running"
                        : wasCancelled
                        ? "cancelled"
                        : executorHistory.length > 0
                        ? "completed"
                        : "ready"
                    }
                    wasCancelled={wasCancelled}
                    checkpoints={sessionCheckpoints}
                  />
                </div>
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

      {/* Checkpoint Info Modal */}
      <CheckpointInfoModal
        session={currentSession || null}
        checkpoints={sessionCheckpoints}
        open={checkpointInfoModalOpen}
        onOpenChange={setCheckpointInfoModalOpen}
      />
    </div>
  );
}
