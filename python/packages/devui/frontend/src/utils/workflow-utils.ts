import { applySimpleLayout } from "./simple-layout";
import type { Node, Edge } from "@xyflow/react";
import type {
  ExecutorNodeData,
  ExecutorState,
} from "@/components/features/workflow/executor-node";
import type {
  ExtendedResponseStreamEvent,
  ResponseWorkflowEventComplete,
} from "@/types";
import type { Workflow } from "@/types/workflow";
import { getTypedWorkflow } from "@/types/workflow";

/**
 * Truncates text that exceeds the maximum length and appends ellipsis
 * @param text - The text to truncate
 * @param maxLength - Maximum length before truncation (default: 50)
 * @param ellipsis - String to append when truncated (default: '...')
 * @returns Truncated text with ellipsis if it exceeds maxLength, otherwise original text
 *
 * @example
 * truncateText('Hello World', 5) // 'Hello...'
 * truncateText('Short', 10) // 'Short'
 * truncateText('workflow_assistant_43ca50a006aa425e96e8fcf54206a7e3', 35) // 'workflow_assistant_43ca50a006aa4...'
 */
export function truncateText(text: string, maxLength: number = 50, ellipsis: string = '...'): string {
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength) + ellipsis;
}

export interface WorkflowDumpExecutor {
  id: string;
  type: string;
  name?: string;
  description?: string;
  config?: Record<string, unknown>;
}

interface RawExecutorData {
  type_?: string;
  type?: string;
  name?: string;
  description?: string;
  config?: Record<string, unknown>;
}

export interface WorkflowDumpConnection {
  source: string;
  target: string;
  condition?: string;
}

export interface WorkflowDump {
  executors?: WorkflowDumpExecutor[];
  connections?: WorkflowDumpConnection[];
  start_executor?: string;
  end_executors?: string[];
  [key: string]: unknown; // Allow for additional properties
}

export interface NodeUpdate {
  nodeId: string;
  state: ExecutorState;
  data?: unknown;
  error?: string;
  timestamp: string;
}

/**
 * Convert workflow dump data to React Flow nodes
 */
export function convertWorkflowDumpToNodes(
  workflowDump: Workflow | Record<string, unknown> | undefined,
  onNodeClick?: (executorId: string, data: ExecutorNodeData) => void,
  layoutDirection?: "LR" | "TB"
): Node<ExecutorNodeData>[] {
  if (!workflowDump) {
    console.warn("convertWorkflowDumpToNodes: workflowDump is undefined");
    return [];
  }

  // Try to get typed workflow first, then fall back to generic handling
  const typedWorkflow = getTypedWorkflow(workflowDump);

  let executors: WorkflowDumpExecutor[];
  let startExecutorId: string | undefined;

  if (typedWorkflow) {
    // Use typed workflow structure
    executors = Object.values(typedWorkflow.executors).map((executor) => ({
      id: executor.id,
      type: executor.type,
      name:
        ((executor as Record<string, unknown>).name as string) || executor.id,
      description: (executor as Record<string, unknown>).description as string,
      config: (executor as Record<string, unknown>).config as Record<
        string,
        unknown
      >,
    }));
    startExecutorId = typedWorkflow.start_executor_id;
  } else {
    // Fall back to generic handling for backwards compatibility
    executors = getExecutorsFromDump(workflowDump as Record<string, unknown>);
    const workflowDumpRecord = workflowDump as Record<string, unknown>;
    startExecutorId = workflowDumpRecord?.start_executor_id as
      | string
      | undefined;
  }

  if (!executors || !Array.isArray(executors) || executors.length === 0) {
    console.warn(
      "No executors found in workflow dump. Available keys:",
      Object.keys(workflowDump)
    );
    return [];
  }

  const nodes = executors.map((executor) => ({
    id: executor.id,
    type: "executor",
    position: { x: 0, y: 0 }, // Will be set by layout algorithm
    data: {
      executorId: executor.id,
      executorType: executor.type,
      name: executor.name || executor.id,
      state: "pending" as ExecutorState,
      isStartNode: executor.id === startExecutorId,
      layoutDirection: layoutDirection || "LR",
      onNodeClick,
    },
  }));

  return nodes;
}

/**
 * Convert workflow dump data to React Flow edges
 */
export function convertWorkflowDumpToEdges(
  workflowDump: Workflow | Record<string, unknown> | undefined
): Edge[] {
  if (!workflowDump) {
    console.warn("convertWorkflowDumpToEdges: workflowDump is undefined");
    return [];
  }

  // Try to get typed workflow first, then fall back to generic handling
  const typedWorkflow = getTypedWorkflow(workflowDump);

  let connections: WorkflowDumpConnection[];

  if (typedWorkflow) {
    // Use typed workflow structure to extract connections from edge_groups
    connections = [];
    typedWorkflow.edge_groups.forEach((group) => {
      group.edges.forEach((edge) => {
        connections.push({
          source: edge.source_id,
          target: edge.target_id,
          condition: edge.condition_name,
        });
      });
    });
  } else {
    // Fall back to generic handling for backwards compatibility
    connections = getConnectionsFromDump(
      workflowDump as Record<string, unknown>
    );
  }

  if (!connections || !Array.isArray(connections) || connections.length === 0) {
    console.warn(
      "No connections found in workflow dump. Available keys:",
      Object.keys(workflowDump)
    );
    return [];
  }

  const edges = connections.map((connection) => ({
    id: `${connection.source}-${connection.target}`,
    source: connection.source,
    target: connection.target,
    sourceHandle: "source",
    targetHandle: "target",
    type: "default",
    animated: false,
    style: {
      stroke: "#6b7280",
      strokeWidth: 2,
    },
  }));

  return edges;
}

/**
 * Extract executors from workflow dump - handles different possible structures
 */
function getExecutorsFromDump(
  workflowDump: Record<string, unknown>
): WorkflowDumpExecutor[] {
  // First check if executors is an object (like in the actual dump structure)
  if (
    workflowDump.executors &&
    typeof workflowDump.executors === "object" &&
    !Array.isArray(workflowDump.executors)
  ) {
    const executorsObj = workflowDump.executors as Record<
      string,
      RawExecutorData
    >;
    return Object.entries(executorsObj).map(([id, executor]) => ({
      id,
      type: executor.type_ || executor.type || "executor",
      name: executor.name || id,
      description: executor.description,
      config: executor.config,
    }));
  }

  // Try different possible keys where executors might be stored as arrays
  const possibleKeys = ["executors", "agents", "steps", "nodes"];

  for (const key of possibleKeys) {
    if (workflowDump[key] && Array.isArray(workflowDump[key])) {
      return workflowDump[key] as WorkflowDumpExecutor[];
    }
  }

  // If no direct array, try to extract from nested structures
  if (workflowDump.config && typeof workflowDump.config === "object") {
    return getExecutorsFromDump(workflowDump.config as Record<string, unknown>);
  }

  // Fallback: create executors from any object keys that look like executor IDs
  const executors: WorkflowDumpExecutor[] = [];
  Object.entries(workflowDump).forEach(([key, value]) => {
    if (
      typeof value === "object" &&
      value !== null &&
      ("type" in value || "type_" in value)
    ) {
      const rawExecutor = value as RawExecutorData;
      executors.push({
        id: key,
        type: rawExecutor.type_ || rawExecutor.type || "executor",
        name: rawExecutor.name || key,
        description: rawExecutor.description,
        config: rawExecutor.config,
      });
    }
  });

  return executors;
}

/**
 * Extract connections from workflow dump - handles different possible structures
 */
function getConnectionsFromDump(
  workflowDump: Record<string, unknown>
): WorkflowDumpConnection[] {
  // Handle edge_groups structure (actual dump format)
  if (workflowDump.edge_groups && Array.isArray(workflowDump.edge_groups)) {
    const connections: WorkflowDumpConnection[] = [];
    workflowDump.edge_groups.forEach((group: unknown) => {
      if (typeof group === "object" && group !== null && "edges" in group) {
        const edges = (group as { edges: unknown }).edges;
        if (Array.isArray(edges)) {
          edges.forEach((edge: unknown) => {
            if (
              typeof edge === "object" &&
              edge !== null &&
              "source_id" in edge &&
              "target_id" in edge
            ) {
              const edgeObj = edge as {
                source_id: string;
                target_id: string;
                condition_name?: string;
              };
              connections.push({
                source: edgeObj.source_id,
                target: edgeObj.target_id,
                condition: edgeObj.condition_name || undefined,
              });
            }
          });
        }
      }
    });
    return connections;
  }

  // Try different possible keys where connections might be stored
  const possibleKeys = ["connections", "edges", "transitions", "links"];

  for (const key of possibleKeys) {
    if (workflowDump[key] && Array.isArray(workflowDump[key])) {
      return workflowDump[key] as WorkflowDumpConnection[];
    }
  }

  // If no direct array, try to extract from nested structures
  if (workflowDump.config && typeof workflowDump.config === "object") {
    return getConnectionsFromDump(
      workflowDump.config as Record<string, unknown>
    );
  }

  return [];
}

/**
 * Apply auto-layout to nodes using a lightweight algorithm
 * Replaces dagre to eliminate 4.88MB lodash dependency
 */
export function applyDagreLayout(
  nodes: Node<ExecutorNodeData>[],
  edges: Edge[],
  direction: "TB" | "LR" = "LR"
): Node<ExecutorNodeData>[] {
  return applySimpleLayout(nodes, edges, direction);
}

/**
 * Process workflow events and extract node updates
 * Handles both standard OpenAI events and fallback workflow_event format
 */
export function processWorkflowEvents(
  events: ExtendedResponseStreamEvent[],
  startExecutorId?: string
): Record<string, NodeUpdate> {
  const nodeUpdates: Record<string, NodeUpdate> = {};
  let hasWorkflowStarted = false;

  // Track the latest item ID for each executor to handle multiple runs
  const latestItemIds: Record<string, string> = {};

  events.forEach((event) => {
    // Handle new standard OpenAI events
    if (event.type === "response.output_item.added" || event.type === "response.output_item.done") {
      const item = (event as any).item;
      if (item && item.type === "executor_action" && item.executor_id) {
        const executorId = item.executor_id;
        const itemId = item.id;

        // Track the latest item ID for this executor
        if (event.type === "response.output_item.added") {
          latestItemIds[executorId] = itemId;
        }

        // Only process this event if it's for the latest item ID of this executor
        // This prevents older "done" events from overwriting newer "added" events
        const isLatestItem = latestItemIds[executorId] === itemId;

        if (!isLatestItem && event.type === "response.output_item.done") {
          return; // Skip this old completion event
        }

        let state: ExecutorState = "pending";
        let error: string | undefined;

        if (event.type === "response.output_item.added") {
          state = "running";
        } else if (event.type === "response.output_item.done") {
          if (item.status === "completed") {
            state = "completed";
          } else if (item.status === "failed") {
            state = "failed";
            error = item.error ? (typeof item.error === "string" ? item.error : JSON.stringify(item.error)) : "Execution failed";
          } else if (item.status === "cancelled") {
            state = "cancelled";
          }
        }

        nodeUpdates[executorId] = {
          nodeId: executorId,
          state,
          data: item.result,
          error,
          timestamp: new Date().toISOString(),
        };
      }
    }
    // Handle workflow lifecycle events
    else if (event.type === "response.created" || event.type === "response.in_progress") {
      hasWorkflowStarted = true;
    }
    // Handle workflow event format
    else if (
      event.type === "response.workflow_event.completed" &&
      "data" in event &&
      event.data
    ) {
      const workflowEvent = event as ResponseWorkflowEventComplete;
      const data = workflowEvent.data;
      const executorId = data.executor_id;
      const eventType = data.event_type;
      const eventData = data.data;

      let state: ExecutorState = "pending";
      let error: string | undefined;

      // Map event types to executor states
      if (eventType === "ExecutorInvokedEvent") {
        state = "running";
      } else if (eventType === "ExecutorCompletedEvent") {
        state = "completed";
      } else if (
        eventType?.includes("Error") ||
        eventType?.includes("Failed")
      ) {
        state = "failed";
        error = typeof eventData === "string" ? eventData : "Execution failed";
      } else if (eventType?.includes("Cancel")) {
        state = "cancelled";
      } else if (eventType === "WorkflowCompletedEvent" || eventType === "WorkflowOutputEvent") {
        state = "completed";
      } else if (eventType === "WorkflowStartedEvent") {
        // Mark that workflow has started - we'll set start node to running
        hasWorkflowStarted = true;
      }

      // Update the node state (keep most recent update per executor)
      if (executorId) {
        nodeUpdates[executorId] = {
          nodeId: executorId,
          state,
          data: eventData,
          error,
          timestamp: new Date().toISOString(),
        };
      }
    }
  });

  // FALLBACK LOGIC: If workflow has started and we have a start executor, set it to running
  // ONLY if it hasn't received any explicit executor events
  // This prevents overwriting the actual state after the executor has run
  if (hasWorkflowStarted && startExecutorId && !nodeUpdates[startExecutorId]) {
    // Additional check: only set to running if we don't have completion/failure events for this executor
    // This prevents setting to "running" after the executor has already completed
    const hasCompletionEvent = events.some((event) => {
      if (event.type === "response.output_item.done") {
        const item = (event as any).item;
        return item && item.type === "executor_action" && item.executor_id === startExecutorId;
      }
      if (event.type === "response.workflow_event.completed" && "data" in event && event.data) {
        const data = event.data as any;
        return data.executor_id === startExecutorId &&
               (data.event_type === "ExecutorCompletedEvent" ||
                data.event_type === "ExecutorFailedEvent" ||
                data.event_type?.includes("Error") ||
                data.event_type?.includes("Failed"));
      }
      return false;
    });

    // Only set to running if the executor hasn't completed yet
    if (!hasCompletionEvent) {
      nodeUpdates[startExecutorId] = {
        nodeId: startExecutorId,
        state: "running",
        data: undefined,
        error: undefined,
        timestamp: new Date().toISOString(),
      };
    }
  }

  return nodeUpdates;
}

/**
 * Update node states based on event processing
 */
export function updateNodesWithEvents(
  nodes: Node<ExecutorNodeData>[],
  nodeUpdates: Record<string, NodeUpdate>
): Node<ExecutorNodeData>[] {
  return nodes.map((node) => {
    const update = nodeUpdates[node.id];
    if (update) {
      return {
        ...node,
        data: {
          ...node.data,
          state: update.state,
          outputData: update.data,
          error: update.error,
          // Preserve layoutDirection
          layoutDirection: node.data.layoutDirection,
        },
      };
    }
    return node;
  });
}

/**
 * Get executors that are currently in execution (invoked but not yet completed)
 */
export function getCurrentlyExecutingExecutors(
  events: ExtendedResponseStreamEvent[]
): string[] {
  const executorTimeline: Record<
    string,
    { lastEvent: string; timestamp: string }
  > = {};

  // Process events to find the most recent event for each executor
  events.forEach((event) => {
    // Handle new standard OpenAI events
    if (event.type === "response.output_item.added" || event.type === "response.output_item.done") {
      const item = (event as any).item;
      if (item && item.type === "executor_action" && item.executor_id) {
        const executorId = item.executor_id;

        executorTimeline[executorId] = {
          lastEvent: event.type === "response.output_item.added" ? "ExecutorInvokedEvent" : "ExecutorCompletedEvent",
          timestamp: new Date().toISOString(),
        };
      }
    }
    // Handle workflow event format
    else if (
      event.type === "response.workflow_event.completed" &&
      "data" in event &&
      event.data
    ) {
      const workflowEvent = event as ResponseWorkflowEventComplete;
      const data = workflowEvent.data;
      const executorId = data.executor_id;
      const eventType = data.event_type;

      if (
        executorId &&
        (eventType === "ExecutorInvokedEvent" ||
          eventType === "ExecutorCompletedEvent")
      ) {
        executorTimeline[executorId] = {
          lastEvent: eventType,
          timestamp: new Date().toISOString(),
        };
      }
    }
  });

  // Find executors that were invoked but haven't completed yet
  const currentlyExecuting = Object.entries(executorTimeline)
    .filter(([, timeline]) => timeline.lastEvent === "ExecutorInvokedEvent")
    .map(([executorId]) => executorId);

  return currentlyExecuting;
}

/**
 * Update edges with sequence-based animation
 */
export function updateEdgesWithSequenceAnalysis(
  edges: Edge[],
  events: ExtendedResponseStreamEvent[]
): Edge[] {
  const currentlyExecuting = getCurrentlyExecutingExecutors(events);

  // Build simple state tracking for each executor
  const executorStates: Record<
    string,
    { completed: boolean; invoked: boolean }
  > = {};

  events.forEach((event) => {
    if (
      event.type === "response.workflow_event.completed" &&
      "data" in event &&
      event.data
    ) {
      const workflowEvent = event as ResponseWorkflowEventComplete;
      const data = workflowEvent.data;
      const executorId = data.executor_id;
      const eventType = data.event_type;

      if (executorId && eventType) {
        if (!executorStates[executorId]) {
          executorStates[executorId] = { completed: false, invoked: false };
        }

        if (eventType === "ExecutorInvokedEvent") {
          executorStates[executorId].invoked = true;
        } else if (eventType === "ExecutorCompletedEvent") {
          executorStates[executorId].completed = true;
        }
      }
    }
  });

  return edges.map((edge) => {
    const sourceState = executorStates[edge.source];
    const targetState = executorStates[edge.target];
    const targetIsExecuting = currentlyExecuting.includes(edge.target);

    let style = { ...edge.style };
    let animated = false;

    // Active edge: source completed and target is currently executing
    if (sourceState?.completed && targetIsExecuting) {
      style = {
        stroke: "#643FB2", // Purple accent
        strokeWidth: 3,
        strokeDasharray: "5,5",
      };
      animated = true;
    }
    // Completed edge: both source and target have completed
    else if (sourceState?.completed && targetState?.completed) {
      style = {
        stroke: "#10b981", // Green
        strokeWidth: 2,
      };
    }
    // Invoked edge: source completed and target invoked (but not necessarily executing)
    else if (sourceState?.completed && targetState?.invoked) {
      style = {
        stroke: "#f59e0b", // Orange
        strokeWidth: 2,
      };
    }
    // Default: Not traversed
    else {
      style = {
        stroke: "#6b7280", // Gray
        strokeWidth: 2,
      };
    }

    return {
      ...edge,
      style,
      animated,
    };
  });
}

/**
 * Consolidate bidirectional edges into single edges with arrows on both ends
 * This reduces visual clutter when edges go in both directions between nodes
 *
 * Smart handle selection algorithm:
 * The current implementation keeps whichever edge was encountered first in the array.
 * Since edges are typically created in workflow definition order (following the primary flow),
 * this naturally keeps the "forward" edge and discards the "backward" one.
 *
 * For example, if the workflow defines:
 * 1. coordinator → planner (primary flow)
 * 2. planner → coordinator (feedback loop)
 *
 * We keep edge #1 and add bidirectional arrows. This ensures the edge follows
 * the natural output→input handle connection of the primary flow direction.
 *
 * React Flow will automatically route the edge to avoid overlaps, and the
 * bidirectional arrows indicate that communication flows both ways.
 */
export function consolidateBidirectionalEdges(edges: Edge[]): Edge[] {
  const edgeMap = new Map<string, Edge>();
  const bidirectionalKeys = new Set<string>();

  edges.forEach(edge => {
    const forwardKey = `${edge.source}-${edge.target}`;
    const reverseKey = `${edge.target}-${edge.source}`;

    // Check if we already have the reverse edge
    if (edgeMap.has(reverseKey)) {
      // Mark both keys as bidirectional
      bidirectionalKeys.add(reverseKey);
      bidirectionalKeys.add(forwardKey);

      // Update the existing reverse edge to be bidirectional
      const existingEdge = edgeMap.get(reverseKey)!;

      // Keep the existing edge's handles (they follow the primary workflow direction)
      // Add bidirectional arrows to show two-way communication
      edgeMap.set(reverseKey, {
        ...existingEdge,
        markerStart: {
          type: 'arrow' as const,
          width: 20,
          height: 20,
        },
        markerEnd: {
          type: 'arrow' as const,
          width: 20,
          height: 20,
        },
        data: {
          ...existingEdge.data,
          isBidirectional: true,
        },
      });
    } else if (!bidirectionalKeys.has(forwardKey)) {
      // Only add if this isn't the reverse of a bidirectional pair
      edgeMap.set(forwardKey, edge);
    }
  });

  return Array.from(edgeMap.values());
}
