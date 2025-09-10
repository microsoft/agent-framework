import dagre from "dagre";
import type { Node, Edge } from "@xyflow/react";
import type { ExecutorNodeData, ExecutorState } from "@/components/workflow/executor-node";
import type { DebugStreamEvent } from "@/types/agent-framework";

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

export interface EdgeTraversal {
  sourceId: string;
  targetId: string;
  timestamp: string;
  status: "traversed" | "active" | "completed" | "failed";
}

/**
 * Convert workflow dump data to React Flow nodes
 */
export function convertWorkflowDumpToNodes(
  workflowDump: Record<string, unknown> | undefined,
  onNodeClick?: (executorId: string, data: ExecutorNodeData) => void
): Node<ExecutorNodeData>[] {
  if (!workflowDump) {
    console.warn("convertWorkflowDumpToNodes: workflowDump is undefined");
    return [];
  }

  // Handle different possible structures in workflow_dump
  const executors = getExecutorsFromDump(workflowDump);
  const startExecutorId = workflowDump.start_executor_id as string | undefined;
  
  if (!executors || !Array.isArray(executors) || executors.length === 0) {
    console.warn("No executors found in workflow dump. Available keys:", Object.keys(workflowDump));
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
      onNodeClick,
    },
  }));
  
  return nodes;
}

/**
 * Convert workflow dump data to React Flow edges
 */
export function convertWorkflowDumpToEdges(
  workflowDump: Record<string, unknown> | undefined
): Edge[] {
  if (!workflowDump) {
    console.warn("convertWorkflowDumpToEdges: workflowDump is undefined");
    return [];
  }

  const connections = getConnectionsFromDump(workflowDump);
  
  if (!connections || !Array.isArray(connections) || connections.length === 0) {
    console.warn("No connections found in workflow dump. Available keys:", Object.keys(workflowDump));
    return [];
  }

  const edges = connections.map((connection) => ({
    id: `${connection.source}-${connection.target}`,
    source: connection.source,
    target: connection.target,
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
function getExecutorsFromDump(workflowDump: Record<string, unknown>): WorkflowDumpExecutor[] {
  // First check if executors is an object (like in the actual dump structure)
  if (workflowDump.executors && typeof workflowDump.executors === "object" && !Array.isArray(workflowDump.executors)) {
    const executorsObj = workflowDump.executors as Record<string, RawExecutorData>;
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
    if (typeof value === "object" && value !== null && ("type" in value || "type_" in value)) {
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
function getConnectionsFromDump(workflowDump: Record<string, unknown>): WorkflowDumpConnection[] {
  // Handle edge_groups structure (actual dump format)
  if (workflowDump.edge_groups && Array.isArray(workflowDump.edge_groups)) {
    const connections: WorkflowDumpConnection[] = [];
    workflowDump.edge_groups.forEach((group: unknown) => {
      if (typeof group === "object" && group !== null && "edges" in group) {
        const edges = (group as { edges: unknown }).edges;
        if (Array.isArray(edges)) {
          edges.forEach((edge: unknown) => {
            if (typeof edge === "object" && edge !== null && "source_id" in edge && "target_id" in edge) {
              const edgeObj = edge as { source_id: string; target_id: string; condition_name?: string };
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
    return getConnectionsFromDump(workflowDump.config as Record<string, unknown>);
  }

  return [];
}

/**
 * Apply dagre layout to nodes and edges
 */
export function applyDagreLayout(
  nodes: Node<ExecutorNodeData>[],
  edges: Edge[],
  direction: "TB" | "LR" = "LR"
): Node<ExecutorNodeData>[] {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ 
    rankdir: direction,
    nodesep: 100,
    ranksep: 150,
  });

  // Add nodes to dagre
  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: 220, height: 120 });
  });

  // Add edges to dagre
  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  // Apply layout
  dagre.layout(dagreGraph);

  // Update node positions
  return nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - 110, // Center the node
        y: nodeWithPosition.y - 60,
      },
    };
  });
}

/**
 * Process workflow events and extract node updates
 */
export function processWorkflowEvents(events: DebugStreamEvent[]): Record<string, NodeUpdate> {
  const nodeUpdates: Record<string, NodeUpdate> = {};

  events.forEach((event) => {
    if (event.type === "workflow_event" && event.event?.executor_id) {
      const executorId = event.event.executor_id;
      const eventType = event.event.type;
      const eventData = event.event.data;

      let state: ExecutorState = "pending";
      let error: string | undefined;

      // Map event types to executor states
      if (eventType === "ExecutorInvokeEvent") {
        state = "running";
      } else if (eventType === "ExecutorCompletedEvent") {
        state = "completed";
      } else if (eventType?.includes("Error") || eventType?.includes("Failed")) {
        state = "failed";
        error = typeof eventData === "string" ? eventData : "Execution failed";
      } else if (eventType?.includes("Cancel")) {
        state = "cancelled";
      } else if (eventType === "WorkflowCompletedEvent") {
        state = "completed";
      }

      // Update the node state (keep most recent update per executor)
      nodeUpdates[executorId] = {
        nodeId: executorId,
        state,
        data: eventData,
        error,
        timestamp: event.timestamp,
      };
    }
  });

  console.log("Final node updates:", nodeUpdates);
  return nodeUpdates;
}

/**
 * Update node states based on event processing
 */
export function updateNodesWithEvents(
  nodes: Node<ExecutorNodeData>[],
  nodeUpdates: Record<string, NodeUpdate>
): Node<ExecutorNodeData>[] {
  console.log("updateNodesWithEvents called with:", { nodes: nodes.length, updates: Object.keys(nodeUpdates) });
  
  return nodes.map((node) => {
    const update = nodeUpdates[node.id];
    if (update) {
      console.log(`Updating node ${node.id}: ${node.data.state} → ${update.state}`);
      return {
        ...node,
        data: {
          ...node.data,
          state: update.state,
          outputData: update.data,
          error: update.error,
        },
      };
    }
    return node;
  });
}

/**
 * Detect edge traversals from event sequence
 */
export function detectEdgeTraversals(events: DebugStreamEvent[]): EdgeTraversal[] {
  const traversals: EdgeTraversal[] = [];
  
  // Filter and sort workflow events by timestamp
  const executorEvents = events
    .filter(e => e.type === "workflow_event" && e.event?.executor_id)
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  console.log("Processing executor events for edge traversal detection:", executorEvents.length);
  
  // Detect edge traversals from event sequence
  for (let i = 0; i < executorEvents.length - 1; i++) {
    const current = executorEvents[i];
    const next = executorEvents[i + 1];
    
    const currentEvent = current.event;
    const nextEvent = next.event;
    
    // Detect edge traversal: A completed → B invoked
    if (currentEvent?.type === "ExecutorCompletedEvent" && 
        nextEvent?.type === "ExecutorInvokeEvent" &&
        currentEvent.executor_id && nextEvent.executor_id &&
        currentEvent.executor_id !== nextEvent.executor_id) {
      
      const traversal: EdgeTraversal = {
        sourceId: currentEvent.executor_id,
        targetId: nextEvent.executor_id,
        timestamp: next.timestamp,
        status: "traversed"
      };
      
      traversals.push(traversal);
      console.log("Detected edge traversal:", `${traversal.sourceId} -> ${traversal.targetId}`);
    }
  }
  
  return traversals;
}


/**
 * Get executors that are currently in execution (invoked but not yet completed)
 */
export function getCurrentlyExecutingExecutors(events: DebugStreamEvent[]): string[] {
  const executorTimeline: Record<string, { lastEvent: string; timestamp: string }> = {};
  
  // Process events to find the most recent event for each executor
  events.forEach(event => {
    if (event.type === "workflow_event" && event.event?.executor_id) {
      const executorId = event.event.executor_id;
      const eventType = event.event.type;
      
      if (eventType === "ExecutorInvokeEvent" || eventType === "ExecutorCompletedEvent") {
        executorTimeline[executorId] = {
          lastEvent: eventType,
          timestamp: event.timestamp
        };
      }
    }
  });
  
  // Find executors that were invoked but haven't completed yet
  const currentlyExecuting = Object.entries(executorTimeline)
    .filter(([, timeline]) => timeline.lastEvent === "ExecutorInvokeEvent")
    .map(([executorId]) => executorId);
  
  console.log("⚡ Currently executing executors:", currentlyExecuting);
  console.log("📋 Executor timeline:", executorTimeline);
  return currentlyExecuting;
}

/**
 * Update edges with sequence-based animation
 */
export function updateEdgesWithSequenceAnalysis(
  edges: Edge[],
  events: DebugStreamEvent[]
): Edge[] {
  const traversals = detectEdgeTraversals(events);
  const currentlyExecuting = getCurrentlyExecutingExecutors(events);
  
  console.log("🔄 Updating edges with sequence analysis:", {
    totalEdges: edges.length,
    traversals: traversals.length,
    currentlyExecuting: currentlyExecuting.length
  });

  return edges.map(edge => {
    const traversal = traversals.find(t => 
      t.sourceId === edge.source && t.targetId === edge.target
    );
    
    const targetIsExecuting = currentlyExecuting.includes(edge.target);
    
    let style = { ...edge.style };
    let animated = false;
    
    // Priority 1: Currently active edge (traversed and target is executing)
    if (traversal && targetIsExecuting) {
      style = {
        stroke: "#3b82f6", // Blue
        strokeWidth: 3,
        strokeDasharray: "5,5"
      };
      animated = true;
      console.log(`🔥 Edge ${edge.id}: ACTIVE`, { 
        traversal: !!traversal, 
        targetIsExecuting,
        sourceId: edge.source,
        targetId: edge.target
      });
    }
    // Priority 2: Completed traversal (traversed and target no longer executing)
    else if (traversal && !targetIsExecuting) {
      style = {
        stroke: "#10b981", // Green
        strokeWidth: 2,
      };
      console.log(`✅ Edge ${edge.id}: COMPLETED (traversed + finished)`);
    }
    // Priority 3: Failed edge (target failed)
    else if (traversal && events.some(e => 
      e.type === "workflow_event" && 
      e.event?.executor_id === edge.target &&
      e.event?.type?.includes("Error")
    )) {
      style = {
        stroke: "#ef4444", // Red
        strokeWidth: 2,
        strokeDasharray: "3,3",
      };
      console.log(`❌ Edge ${edge.id}: FAILED`);
    }
    // Default: Not traversed
    else {
      style = {
        stroke: "#6b7280", // Gray
        strokeWidth: 2,
      };
      console.log(`⚪ Edge ${edge.id}: NOT_TRAVERSED`);
    }
    
    return {
      ...edge,
      style,
      animated,
    };
  });
}

/**
 * Update edges with animation based on execution state (DEPRECATED - use updateEdgesWithSequenceAnalysis)
 */
export function updateEdgesWithAnimation(
  edges: Edge[],
  nodeUpdates: Record<string, NodeUpdate>
): Edge[] {
  return edges.map((edge) => {
    const sourceUpdate = nodeUpdates[edge.source];
    const targetUpdate = nodeUpdates[edge.target];

    let style = { ...edge.style };
    let animated = false;

    // Animate edge if source is completed and target is running
    if (
      sourceUpdate?.state === "completed" &&
      targetUpdate?.state === "running"
    ) {
      style = {
        stroke: "#3b82f6",
        strokeWidth: 3,
        strokeDasharray: "5,5",
      };
      animated = true;
    }
    // Show completed edge if both source and target are completed
    else if (
      sourceUpdate?.state === "completed" &&
      targetUpdate?.state === "completed"
    ) {
      style = {
        stroke: "#10b981",
        strokeWidth: 2,
      };
    }
    // Show failed edge if target failed
    else if (targetUpdate?.state === "failed") {
      style = {
        stroke: "#ef4444",
        strokeWidth: 2,
        strokeDasharray: "3,3",
      };
    }
    // Show cancelled edge if target cancelled
    else if (targetUpdate?.state === "cancelled") {
      style = {
        stroke: "#f97316",
        strokeWidth: 2,
        strokeDasharray: "5,5",
      };
    }

    return {
      ...edge,
      style,
      animated,
    };
  });
}