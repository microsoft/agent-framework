import { useMemo, useCallback, useEffect, memo } from "react";
import {
  MoreVertical,
  Map,
  Grid3X3,
  RotateCcw,
  Maximize,
  Shuffle,
  Zap,
  ArrowDown,
  ArrowLeftRight,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  useReactFlow,
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
  consolidateBidirectionalEdges,
  type NodeUpdate,
} from "@/utils/workflow-utils";
import type { ExtendedResponseStreamEvent } from "@/types";
import type { Workflow } from "@/types/workflow";

const nodeTypes: NodeTypes = {
  executor: ExecutorNode,
};

// ViewOptions panel component that renders inside ReactFlow
function ViewOptionsPanel({
  workflowDump,
  onNodeSelect,
  viewOptions,
  onToggleViewOption,
  layoutDirection,
  onLayoutDirectionChange,
}: {
  workflowDump?: Workflow;
  onNodeSelect?: (executorId: string, data: ExecutorNodeData) => void;
  viewOptions: { showMinimap: boolean; showGrid: boolean; animateRun: boolean; consolidateBidirectionalEdges: boolean };
  onToggleViewOption?: (key: keyof typeof viewOptions) => void;
  layoutDirection: "LR" | "TB";
  onLayoutDirectionChange?: (direction: "LR" | "TB") => void;
}) {
  const { fitView, setViewport, setNodes } = useReactFlow();

  const handleResetZoom = () => {
    setViewport({ x: 0, y: 0, zoom: 1 });
  };

  const handleFitToScreen = () => {
    fitView({ padding: 0.2 });
  };

  const handleAutoArrange = () => {
    if (!workflowDump) return;
    const currentNodes = convertWorkflowDumpToNodes(
      workflowDump,
      onNodeSelect,
      layoutDirection
    );
    const currentEdges = convertWorkflowDumpToEdges(workflowDump);
    const layoutedNodes = applyDagreLayout(
      currentNodes,
      currentEdges,
      layoutDirection
    );
    setNodes(layoutedNodes);
  };

  return (
    <div className="absolute top-4 right-4 z-10">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="h-8 w-8 p-0 bg-white/90 backdrop-blur-sm border-gray-200 shadow-sm hover:bg-white dark:bg-gray-800/90 dark:border-gray-600 dark:hover:bg-gray-800"
          >
            <MoreVertical className="h-4 w-4" />
            <span className="sr-only">View options</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuItem
            className="flex items-center justify-between"
            onClick={() => onToggleViewOption?.("showMinimap")}
          >
            <div className="flex items-center">
              <Map className="mr-2 h-4 w-4" />
              Show Minimap
            </div>
            <Checkbox checked={viewOptions.showMinimap} onChange={() => {}} />
          </DropdownMenuItem>
          <DropdownMenuItem
            className="flex items-center justify-between"
            onClick={() => onToggleViewOption?.("showGrid")}
          >
            <div className="flex items-center">
              <Grid3X3 className="mr-2 h-4 w-4" />
              Show Grid
            </div>
            <Checkbox checked={viewOptions.showGrid} onChange={() => {}} />
          </DropdownMenuItem>
          <DropdownMenuItem
            className="flex items-center justify-between"
            onClick={() => onToggleViewOption?.("animateRun")}
          >
            <div className="flex items-center">
              <Zap className="mr-2 h-4 w-4" />
              Animate Run
            </div>
            <Checkbox checked={viewOptions.animateRun} onChange={() => {}} />
          </DropdownMenuItem>
          <DropdownMenuItem
            className="flex items-center justify-between"
            onClick={() => onToggleViewOption?.("consolidateBidirectionalEdges")}
          >
            <div className="flex items-center">
              <ArrowLeftRight className="mr-2 h-4 w-4" />
              Merge Bidirectional Edges
            </div>
            <Checkbox checked={viewOptions.consolidateBidirectionalEdges} onChange={() => {}} />
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            className="flex items-center justify-between"
            onClick={() => {
              const newDirection = layoutDirection === "LR" ? "TB" : "LR";
              onLayoutDirectionChange?.(newDirection);
              // Re-apply layout with new direction
              if (workflowDump) {
                const currentNodes = convertWorkflowDumpToNodes(
                  workflowDump,
                  onNodeSelect,
                  newDirection
                );
                const currentEdges = convertWorkflowDumpToEdges(workflowDump);
                const layoutedNodes = applyDagreLayout(
                  currentNodes,
                  currentEdges,
                  newDirection
                );
                setNodes(layoutedNodes);
              }
            }}
          >
            <div className="flex items-center">
              <ArrowDown className="mr-2 h-4 w-4" />
              Vertical Layout
            </div>
            <Checkbox checked={layoutDirection === "TB"} onChange={() => {}} />
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={handleResetZoom}>
            <RotateCcw className="mr-2 h-4 w-4" />
            Reset Zoom
          </DropdownMenuItem>
          <DropdownMenuItem onClick={handleFitToScreen}>
            <Maximize className="mr-2 h-4 w-4" />
            Fit to Screen
          </DropdownMenuItem>
          <DropdownMenuItem onClick={handleAutoArrange}>
            <Shuffle className="mr-2 h-4 w-4" />
            Auto-arrange
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

interface WorkflowFlowProps {
  workflowDump?: Workflow;
  events: ExtendedResponseStreamEvent[];
  isStreaming: boolean;
  onNodeSelect?: (executorId: string, data: ExecutorNodeData) => void;
  className?: string;
  viewOptions?: {
    showMinimap: boolean;
    showGrid: boolean;
    animateRun: boolean;
    consolidateBidirectionalEdges: boolean;
  };
  onToggleViewOption?: (
    key: keyof NonNullable<WorkflowFlowProps["viewOptions"]>
  ) => void;
  layoutDirection?: "LR" | "TB";
  onLayoutDirectionChange?: (direction: "LR" | "TB") => void;
  timelineVisible?: boolean;
}

// Animation handler component that runs inside ReactFlow context
function WorkflowAnimationHandler({
  nodes,
  nodeUpdates,
  isStreaming,
  animateRun,
}: {
  nodes: Node<ExecutorNodeData>[];
  nodeUpdates: Record<string, NodeUpdate>;
  isStreaming: boolean;
  animateRun: boolean;
}) {
  const { fitView } = useReactFlow();

  // Smooth animation to center on running node when workflow starts/progresses
  useEffect(() => {
    if (!animateRun) return;

    if (isStreaming) {
      // Zoom in on running nodes during execution
      const runningNodes = nodes.filter(
        (node) => node.data.state === "running"
      );
      if (runningNodes.length > 0) {
        const targetNode = runningNodes[0];

        // Use fitView to smoothly focus on the running node with animation
        fitView({
          nodes: [targetNode],
          duration: 800,
          padding: 0.3,
          minZoom: 0.8,
          maxZoom: 1.5,
        });
      }
    } else if (nodes.length > 0) {
      // Zoom back out to show full workflow when execution completes
      fitView({
        duration: 1000,
        padding: 0.2,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeUpdates, isStreaming, animateRun, nodes]);

  return null; // This component doesn't render anything
}

// Timeline resize handler component that runs inside ReactFlow context
const TimelineResizeHandler = memo(({ timelineVisible }: { timelineVisible: boolean }) => {
  const { fitView } = useReactFlow();

  // Trigger fitView when timeline visibility changes to adjust ReactFlow viewport
  useEffect(() => {
    // Delay fitView to let CSS transition complete (timeline animation is 300ms)
    const timeoutId = setTimeout(() => {
      fitView({ padding: 0.2, duration: 300 });
    }, 350); // Slightly longer than timeline animation duration

    return () => clearTimeout(timeoutId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timelineVisible]); // Only trigger when timelineVisible changes, not fitView reference

  return null; // This component doesn't render anything
});

export const WorkflowFlow = memo(function WorkflowFlow({
  workflowDump,
  events,
  isStreaming,
  onNodeSelect,
  className = "",
  viewOptions = { showMinimap: false, showGrid: true, animateRun: true, consolidateBidirectionalEdges: true },
  onToggleViewOption,
  layoutDirection = "LR",
  onLayoutDirectionChange,
  timelineVisible = false,
}: WorkflowFlowProps) {
  // Create initial nodes and edges from workflow dump
  const { initialNodes, initialEdges } = useMemo(() => {
    if (!workflowDump) {
      return { initialNodes: [], initialEdges: [] };
    }

    const nodes = convertWorkflowDumpToNodes(
      workflowDump,
      onNodeSelect,
      layoutDirection
    );
    const edges = convertWorkflowDumpToEdges(workflowDump);

    // Apply bidirectional edge consolidation if enabled
    const finalEdges = viewOptions.consolidateBidirectionalEdges
      ? consolidateBidirectionalEdges(edges)
      : edges;

    // Apply auto-layout if we have nodes and edges
    const layoutedNodes =
      nodes.length > 0
        ? applyDagreLayout(nodes, finalEdges, layoutDirection)
        : nodes;

    return {
      initialNodes: layoutedNodes,
      initialEdges: finalEdges,
    };
  }, [workflowDump, onNodeSelect, layoutDirection, viewOptions.consolidateBidirectionalEdges]);

  const [nodes, setNodes, onNodesChange] =
    useNodesState<Node<ExecutorNodeData>>(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Process events and update node/edge states
  const nodeUpdates = useMemo(() => {
    return processWorkflowEvents(events, workflowDump?.start_executor_id);
  }, [events, workflowDump?.start_executor_id]);

  // Update nodes and edges with real-time state from events
  useMemo(() => {
    if (Object.keys(nodeUpdates).length > 0) {
      setNodes((currentNodes) =>
        updateNodesWithEvents(currentNodes, nodeUpdates)
      );
    } else if (events.length === 0) {
      // Reset all nodes to pending state when events are cleared
      setNodes((currentNodes) =>
        currentNodes.map((node) => ({
          ...node,
          data: {
            ...node.data,
            state: "pending" as const,
            outputData: undefined,
            error: undefined,
          },
        }))
      );
    }
  }, [nodeUpdates, setNodes, events.length]);

  // Update edges with sequence-based analysis (separate from nodeUpdates)
  useMemo(() => {
    if (events.length > 0) {
      setEdges((currentEdges) => {
        const updatedEdges = updateEdgesWithSequenceAnalysis(
          currentEdges,
          events
        );
        // Apply consolidation if enabled (preserves updated styling from sequence analysis)
        return viewOptions.consolidateBidirectionalEdges
          ? consolidateBidirectionalEdges(updatedEdges)
          : updatedEdges;
      });
    } else {
      // Reset all edges to default state when events are cleared
      setEdges((currentEdges) => {
        const resetEdges = currentEdges.map((edge) => ({
          ...edge,
          animated: false,
          style: {
            stroke: "#6b7280", // Gray
            strokeWidth: 2,
          },
        }));
        // Apply consolidation if enabled
        return viewOptions.consolidateBidirectionalEdges
          ? consolidateBidirectionalEdges(resetEdges)
          : resetEdges;
      });
    }
  }, [events, setEdges, viewOptions.consolidateBidirectionalEdges]);

  // Initialize nodes and edges when workflow structure OR consolidation setting changes
  useEffect(() => {
    if (initialNodes.length > 0) {
      setNodes(initialNodes);
      setEdges(initialEdges);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowDump, viewOptions.consolidateBidirectionalEdges]); // Re-initialize when workflow or consolidation toggle changes

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
        className={`flex items-center justify-center h-full bg-gray-50 dark:bg-gray-900 rounded border border-gray-200 dark:border-gray-700 ${className}`}
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
        className={`flex items-center justify-center h-full bg-gray-50 dark:bg-gray-900 rounded border border-gray-200 dark:border-gray-700 ${className}`}
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
        proOptions={{ hideAttribution: true }}
      >
        {viewOptions.showGrid && (
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1}
            color="#e5e7eb"
            className="dark:opacity-30"
          />
        )}
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
        {viewOptions.showMinimap && (
          <MiniMap
            nodeColor={(node: Node) => {
              const data = node.data as ExecutorNodeData;
              const state = data?.state;
              switch (state) {
                case "running":
                  return "#643FB2";
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
            className="dark:!bg-gray-800/90 dark:!border-gray-600"
          />
        )}
        <WorkflowAnimationHandler
          nodes={nodes}
          nodeUpdates={nodeUpdates}
          isStreaming={isStreaming}
          animateRun={viewOptions.animateRun}
        />
        <TimelineResizeHandler timelineVisible={timelineVisible} />
        <ViewOptionsPanel
          workflowDump={workflowDump}
          onNodeSelect={onNodeSelect}
          viewOptions={viewOptions}
          onToggleViewOption={onToggleViewOption}
          layoutDirection={layoutDirection}
          onLayoutDirectionChange={onLayoutDirectionChange}
        />
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
});
