import { useMemo, useState, useCallback } from "react";
import type { ExtendedResponseStreamEvent } from "@/types";
// import type { ExecutorNodeData } from "@/components/workflow/executor-node";

// Type for executor input/output data - can be various types based on workflow events
export type ExecutorData =
  | string
  | number
  | boolean
  | Record<string, unknown>
  | null;

// State tracking for a specific executor
interface ExecutorState {
  executorId: string;
  state: "pending" | "running" | "completed" | "failed" | "cancelled";
  inputData?: ExecutorData;
  outputData?: ExecutorData;
  error?: string;
  timestamp: string;
}


interface WorkflowEventCorrelationResult {
  // State access
  isWorkflowRunning: boolean;
  selectedExecutorId: string | null;
  recentlyActive: string[];
  
  // Actions
  selectExecutor: (executorId: string) => void;
  getExecutorData: (executorId: string) => ExecutorState | null;
  getExecutorEvents: (executorId: string) => ExtendedResponseStreamEvent[];
}

// Hook for correlating workflow events with executor states
export function useWorkflowEventCorrelation(
  events: ExtendedResponseStreamEvent[],
  isStreaming: boolean
): WorkflowEventCorrelationResult {
  const [selectedExecutorId, setSelectedExecutorId] = useState<string | null>(null);

  // Process events into executor states
  const { executors, recentlyActive, isWorkflowRunning } = useMemo(() => {
    const executorMap: Record<string, ExecutorState> = {};
    const activeExecutors: string[] = [];
    let workflowActive = isStreaming;

    // Process workflow events
    events.forEach((event) => {
      if (event.type === "response.workflow_event.complete" && "data" in event && event.data) {
        const data = event.data as any;
        const executorId = data.executor_id;
        
        if (!executorId) return;

        // Initialize executor if not exists
        if (!executorMap[executorId]) {
          executorMap[executorId] = {
            executorId,
            state: "pending",
            timestamp: new Date().toISOString(),
          };
        }

        const executor = executorMap[executorId];
        const eventType = data.event_type;

        // Update state based on event type
        if (eventType === "ExecutorInvokedEvent") {
          executor.state = "running";
          executor.inputData = data.data;
          if (!activeExecutors.includes(executorId)) {
            activeExecutors.push(executorId);
          }
        } else if (eventType === "ExecutorCompletedEvent") {
          executor.state = "completed";
          executor.outputData = data.data;
        } else if (eventType?.includes("Error") || eventType?.includes("Failed")) {
          executor.state = "failed";
          executor.error = typeof data.data === "string" ? data.data : "Execution failed";
        } else if (eventType?.includes("Cancel")) {
          executor.state = "cancelled";
        }

        executor.timestamp = new Date().toISOString();
      }
    });

    return {
      executors: executorMap,
      recentlyActive: activeExecutors.slice(-3), // Keep last 3 active executors
      isWorkflowRunning: workflowActive,
    };
  }, [events, isStreaming]);

  const selectExecutor = useCallback((executorId: string) => {
    setSelectedExecutorId(executorId);
  }, []);

  const getExecutorData = useCallback((executorId: string): ExecutorState | null => {
    return executors[executorId] || null;
  }, [executors]);

  const getExecutorEvents = useCallback(
    (executorId: string): ExtendedResponseStreamEvent[] => {
      return events.filter((event) => {
        if (event.type === "response.workflow_event.complete" && "data" in event && event.data) {
          const data = event.data as any;
          return data.executor_id === executorId;
        }
        return false;
      });
    },
    [events]
  );

  return {
    isWorkflowRunning,
    selectedExecutorId,
    recentlyActive,
    selectExecutor,
    getExecutorData,
    getExecutorEvents,
  };
}