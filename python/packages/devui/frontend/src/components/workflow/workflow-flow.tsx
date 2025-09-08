import { useMemo, useCallback, useEffect } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
  type NodeTypes,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ExecutorNode, type ExecutorNodeData } from "./executor-node";
import {
  convertWorkflowDumpToNodes,
  convertWorkflowDumpToEdges,
  applyDagreLayout,
  processWorkflowEvents,
  updateNodesWithEvents,
  updateEdgesWithSequenceAnalysis,
} from "@/utils/workflow-utils";
import type { DebugStreamEvent } from "@/types/agent-framework";

const nodeTypes: NodeTypes = {
  executor: ExecutorNode,
};

interface WorkflowFlowProps {
  workflowDump?: Record<string, unknown>;
  events: DebugStreamEvent[];
  isStreaming: boolean;
  onNodeSelect?: (executorId: string, data: ExecutorNodeData) => void;
  className?: string;
}

export function WorkflowFlow({
  workflowDump,
  events,
  isStreaming,
  onNodeSelect,
  className = "",
}: WorkflowFlowProps) {
  // Create initial nodes and edges from workflow dump
  const { initialNodes, initialEdges } = useMemo(() => {
    if (!workflowDump) {
      return { initialNodes: [], initialEdges: [] };
    }

    const nodes = convertWorkflowDumpToNodes(workflowDump, onNodeSelect);
    const edges = convertWorkflowDumpToEdges(workflowDump);

    // Apply auto-layout if we have nodes and edges
    const layoutedNodes =
      nodes.length > 0 ? applyDagreLayout(nodes, edges, "LR") : nodes;

    return {
      initialNodes: layoutedNodes,
      initialEdges: edges,
    };
  }, [workflowDump, onNodeSelect]);

  const [nodes, setNodes, onNodesChange] =
    useNodesState<Node<ExecutorNodeData>>(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Process events and update node/edge states
  const nodeUpdates = useMemo(() => {
    return processWorkflowEvents(events);
  }, [events]);

  // Update nodes and edges with real-time state from events
  useMemo(() => {
    if (Object.keys(nodeUpdates).length > 0) {
      setNodes((currentNodes) =>
        updateNodesWithEvents(currentNodes, nodeUpdates)
      );
    }
  }, [nodeUpdates, setNodes]);

  // Update edges with sequence-based analysis (separate from nodeUpdates)
  useMemo(() => {
    if (events.length > 0) {
      setEdges((currentEdges) =>
        updateEdgesWithSequenceAnalysis(currentEdges, events)
      );
    }
  }, [events, setEdges]);

  // Initialize nodes only when workflow structure changes (not on state updates)
  useEffect(() => {
    if (initialNodes.length > 0) {
      setNodes(initialNodes);
      setEdges(initialEdges);
    }
  }, [workflowDump]); // Only re-initialize when workflowDump changes, not on every initialNodes change

  const onNodeClick = useCallback(
    (event: React.MouseEvent, node: Node<ExecutorNodeData>) => {
      event.stopPropagation();
      onNodeSelect?.(node.data.executorId, node.data);
    },
    [onNodeSelect]
  );

  if (!workflowDump) {
    return (
      <div
        className={`flex items-center justify-center h-full bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 ${className}`}
      >
        <div className="text-center text-gray-500 dark:text-gray-400">
          <div className="text-lg font-medium mb-2">No Workflow Data</div>
          <div className="text-sm">Workflow dump is not available.</div>
        </div>
      </div>
    );
  }

  if (initialNodes.length === 0) {
    return (
      <div
        className={`flex items-center justify-center h-full bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 ${className}`}
      >
        <div className="text-center text-gray-500 dark:text-gray-400">
          <div className="text-lg font-medium mb-2">No Executors Found</div>
          <div className="text-sm">
            Could not extract executors from workflow dump.
          </div>
          <details className="mt-2 text-xs">
            <summary className="cursor-pointer">Debug Info</summary>
            <pre className="mt-1 p-2 bg-gray-100 dark:bg-gray-800 rounded text-left overflow-auto">
              {JSON.stringify(workflowDump, null, 2)}
            </pre>
          </details>
        </div>
      </div>
    );
  }

  return (
    <div className={`h-full w-full ${className}`}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        maxZoom={1.5}
        defaultEdgeOptions={{
          type: "default",
          animated: false,
          style: { stroke: "#6b7280", strokeWidth: 2 },
        }}
        nodesDraggable={!isStreaming} // Disable dragging during execution
        nodesConnectable={false} // Disable connecting nodes
        elementsSelectable={true}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="#e5e7eb"
          className="dark:opacity-30"
        />
        <Controls
          position="bottom-left"
          showInteractive={false}
          style={{
            backgroundColor: "rgba(255, 255, 255, 0.9)",
            border: "1px solid #e5e7eb",
            borderRadius: "3px",
          }}
          className="dark:!bg-gray-800/90 dark:!border-gray-600"
        />
        {/* <MiniMap
          nodeColor={(node: Node) => {
            const data = node.data as ExecutorNodeData;
            const state = data?.state;
            switch (state) {
              case "running":
                return "#3b82f6";
              case "completed":
                return "#10b981";
              case "failed":
                return "#ef4444";
              case "cancelled":
                return "#f97316";
              default:
                return "#6b7280";
            }
          }}
          maskColor="rgba(0, 0, 0, 0.1)"
          position="bottom-right"
          style={{
            backgroundColor: "rgba(255, 255, 255, 0.9)",
            border: "1px solid #e5e7eb",
            borderRadius: "8px",
          }}
        /> */}
      </ReactFlow>

      {/* CSS for custom edge animations and dark theme controls */}
      <style>{`
        .react-flow__edge-path {
          transition: stroke 0.3s ease, stroke-width 0.3s ease;
        }
        .react-flow__edge.animated .react-flow__edge-path {
          stroke-dasharray: 5 5;
          animation: dash 1s linear infinite;
        }
        @keyframes dash {
          0% { stroke-dashoffset: 0; }
          100% { stroke-dashoffset: -10; }
        }
        
        /* Dark theme styles for React Flow controls */
        .dark .react-flow__controls {
          background-color: rgba(31, 41, 55, 0.9) !important;
          border-color: rgb(75, 85, 99) !important;
        }
        .dark .react-flow__controls-button {
          background-color: rgba(31, 41, 55, 0.9) !important;
          border-color: rgb(75, 85, 99) !important;
          color: rgb(229, 231, 235) !important;
        }
        .dark .react-flow__controls-button:hover {
          background-color: rgba(55, 65, 81, 0.9) !important;
          color: rgb(255, 255, 255) !important;
        }
        .dark .react-flow__controls-button svg {
          fill: rgb(229, 231, 235) !important;
        }
        .dark .react-flow__controls-button:hover svg {
          fill: rgb(255, 255, 255) !important;
        }
      `}</style>
    </div>
  );
}
