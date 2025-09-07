import { useMemo, useState, useCallback } from "react";
import type { DebugStreamEvent } from "@/types/agent-framework";
import type { ExecutorNodeData } from "@/components/workflow/executor-node";

// Type for executor input/output data - can be various types based on workflow events
export type ExecutorData =
  | string
  | number
  | boolean
  | Record<string, unknown>
  | Array<unknown>
  | null
  | undefined;

export interface ExecutorExecutionData {
  executorId: string;
  state: ExecutorNodeData["state"];
  inputData?: ExecutorData;
  outputData?: ExecutorData;
  error?: string;
  startTime?: string;
  endTime?: string;
  duration?: number;
  events: DebugStreamEvent[];
}

export interface WorkflowExecutionState {
  isRunning: boolean;
  startTime?: string;
  endTime?: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  executors: Record<string, ExecutorExecutionData>;
  selectedExecutorId?: string;
}

export interface UseWorkflowEventCorrelationReturn {
  executionState: WorkflowExecutionState;
  selectExecutor: (executorId?: string) => void;
  getExecutorEvents: (executorId: string) => DebugStreamEvent[];
  getExecutorData: (executorId: string) => ExecutorExecutionData | undefined;
}

/**
 * Hook to correlate workflow events with executors and manage execution state
 */
export function useWorkflowEventCorrelation(
  events: DebugStreamEvent[],
  isStreaming: boolean
): UseWorkflowEventCorrelationReturn {
  const [selectedExecutorId, setSelectedExecutorId] = useState<string>();

  // Process events to determine overall workflow state and executor states
  const executionState = useMemo<WorkflowExecutionState>(() => {
    const executors: Record<string, ExecutorExecutionData> = {};
    let workflowStartTime: string | undefined;
    let workflowEndTime: string | undefined;
    let workflowStatus:
      | "pending"
      | "running"
      | "completed"
      | "failed"
      | "cancelled" = "pending";
    let hasWorkflowStarted = false;
    let hasWorkflowEnded = false;

    // Process events chronologically
    events.forEach((event) => {
      // Track workflow-level events
      if (event.type === "workflow_event" && event.event) {
        const eventType = event.event.type;

        if (eventType === "WorkflowStartedEvent") {
          workflowStartTime = event.timestamp;
          workflowStatus = "running";
          hasWorkflowStarted = true;
        } else if (eventType === "WorkflowCompletedEvent") {
          workflowEndTime = event.timestamp;
          workflowStatus = "completed";
          hasWorkflowEnded = true;
        } else if (
          eventType?.includes("Error") ||
          eventType?.includes("Failed")
        ) {
          workflowEndTime = event.timestamp;
          workflowStatus = "failed";
          hasWorkflowEnded = true;
        }

        // Track executor-specific events
        const executorId = event.event.executor_id;
        if (executorId) {
          if (!executors[executorId]) {
            executors[executorId] = {
              executorId,
              state: "pending",
              events: [],
            };
          }

          const executor = executors[executorId];
          executor.events.push(event);

          // Update executor state based on event type
          if (eventType === "ExecutorInvokeEvent") {
            executor.state = "running";
            executor.startTime = event.timestamp;
            executor.inputData = event.event.data as ExecutorData;
          } else if (eventType === "ExecutorCompletedEvent") {
            executor.state = "completed";
            executor.endTime = event.timestamp;
            executor.outputData = event.event.data as ExecutorData;

            // Calculate duration if we have both start and end times
            if (executor.startTime) {
              const start = new Date(executor.startTime).getTime();
              const end = new Date(event.timestamp).getTime();
              executor.duration = end - start;
            }
          } else if (
            eventType?.includes("Error") ||
            eventType?.includes("Failed")
          ) {
            executor.state = "failed";
            executor.endTime = event.timestamp;
            executor.error =
              typeof event.event.data === "string"
                ? event.event.data
                : "Execution failed";

            // Calculate duration if we have both start and end times
            if (executor.startTime) {
              const start = new Date(executor.startTime).getTime();
              const end = new Date(event.timestamp).getTime();
              executor.duration = end - start;
            }
          } else if (eventType?.includes("Cancel")) {
            executor.state = "cancelled";
            executor.endTime = event.timestamp;

            // Calculate duration if we have both start and end times
            if (executor.startTime) {
              const start = new Date(executor.startTime).getTime();
              const end = new Date(event.timestamp).getTime();
              executor.duration = end - start;
            }
          }
        }
      }
    });

    // Determine final workflow status based on streaming state and events
    if (isStreaming && !hasWorkflowEnded) {
      if (hasWorkflowStarted) {
        workflowStatus = "running";
      } else {
        workflowStatus = "pending";
      }
    } else if (!isStreaming && hasWorkflowStarted && !hasWorkflowEnded) {
      // If streaming stopped but no completion event, assume completed
      workflowStatus = "completed";
      workflowEndTime = events[events.length - 1]?.timestamp;
    }

    return {
      isRunning: isStreaming || workflowStatus === "running",
      startTime: workflowStartTime,
      endTime: workflowEndTime,
      status: workflowStatus,
      executors,
      selectedExecutorId,
    };
  }, [events, isStreaming, selectedExecutorId]);

  const selectExecutor = useCallback((executorId?: string) => {
    setSelectedExecutorId(executorId);
  }, []);

  const getExecutorEvents = useCallback(
    (executorId: string): DebugStreamEvent[] => {
      return executionState.executors[executorId]?.events || [];
    },
    [executionState.executors]
  );

  const getExecutorData = useCallback(
    (executorId: string): ExecutorExecutionData | undefined => {
      return executionState.executors[executorId];
    },
    [executionState.executors]
  );

  return {
    executionState,
    selectExecutor,
    getExecutorEvents,
    getExecutorData,
  };
}

/**
 * Utility function to format duration in human-readable form
 */
export function formatDuration(durationMs?: number): string {
  if (!durationMs) return "—";

  if (durationMs < 1000) {
    return `${Math.round(durationMs)}ms`;
  } else if (durationMs < 60000) {
    return `${(durationMs / 1000).toFixed(1)}s`;
  } else {
    const minutes = Math.floor(durationMs / 60000);
    const seconds = Math.floor((durationMs % 60000) / 1000);
    return `${minutes}m ${seconds}s`;
  }
}

/**
 * Utility function to get executor state summary
 */
export function getExecutorStateSummary(
  executors: Record<string, ExecutorExecutionData>
): {
  total: number;
  pending: number;
  running: number;
  completed: number;
  failed: number;
  cancelled: number;
} {
  const summary = {
    total: 0,
    pending: 0,
    running: 0,
    completed: 0,
    failed: 0,
    cancelled: 0,
  };

  Object.values(executors).forEach((executor) => {
    summary.total++;
    summary[executor.state]++;
  });

  return summary;
}
