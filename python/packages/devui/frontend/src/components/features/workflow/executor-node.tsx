import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
  Workflow,
  Home,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { truncateText } from "@/utils/workflow-utils";

export type ExecutorState =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface ExecutorNodeData extends Record<string, unknown> {
  executorId: string;
  executorType?: string;
  name?: string;
  state: ExecutorState;
  inputData?: unknown;
  outputData?: unknown;
  error?: string;
  isSelected?: boolean;
  isStartNode?: boolean;
  isEndNode?: boolean;
  layoutDirection?: "LR" | "TB";
  onNodeClick?: (executorId: string, data: ExecutorNodeData) => void;
}

const getExecutorStateConfig = (state: ExecutorState) => {
  switch (state) {
    case "running":
      return {
        borderColor: "border-[#643FB2] dark:border-[#8B5CF6]",
        glow: "shadow-lg shadow-[#643FB2]/20",
        badgeColor: "bg-[#643FB2] dark:bg-[#8B5CF6]",
      };
    case "completed":
      return {
        borderColor: "border-green-500 dark:border-green-400",
        glow: "shadow-lg shadow-green-500/20",
        badgeColor: "bg-green-500 dark:bg-green-400",
      };
    case "failed":
      return {
        borderColor: "border-red-500 dark:border-red-400",
        glow: "shadow-lg shadow-red-500/20",
        badgeColor: "bg-red-500 dark:bg-red-400",
      };
    case "cancelled":
      return {
        borderColor: "border-orange-500 dark:border-orange-400",
        glow: "shadow-lg shadow-orange-500/20",
        badgeColor: "bg-orange-500 dark:bg-orange-400",
      };
    case "pending":
    default:
      return {
        borderColor: "border-gray-300 dark:border-gray-600",
        glow: "",
        badgeColor: "bg-gray-400 dark:bg-gray-500",
      };
  }
};

export const ExecutorNode = memo(({ data, selected }: NodeProps) => {
  const nodeData = data as ExecutorNodeData;
  const config = getExecutorStateConfig(nodeData.state);

  const hasData = nodeData.inputData || nodeData.outputData || nodeData.error;
  const isRunning = nodeData.state === "running";

  // Determine handle positions based on layout direction
  const isVertical = nodeData.layoutDirection === "TB";
  const targetPosition = isVertical ? Position.Top : Position.Left;
  const sourcePosition = isVertical ? Position.Bottom : Position.Right;

  // Helper to safely render data with full details
  const renderDataDetails = () => {
    const details = [];

    if (nodeData.error && typeof nodeData.error === "string") {
      // Truncate error to first 150 characters for node display
      const truncatedError = truncateText(nodeData.error, 150);
      details.push(
        <div key="error" className="mb-2">
          <div className="text-xs font-medium text-red-600 dark:text-red-400 mb-1">Error:</div>
          <div className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/20 p-2 rounded border border-red-200 dark:border-red-800 break-words">
            {truncatedError}
          </div>
        </div>
      );
    }

    if (nodeData.outputData) {
      try {
        const outputStr =
          typeof nodeData.outputData === "string"
            ? nodeData.outputData
            : JSON.stringify(nodeData.outputData, null, 2);
        details.push(
          <div key="output" className="mb-2">
            <div className="text-xs font-medium text-green-600 dark:text-green-400 mb-1">Output:</div>
            <div className="text-xs text-gray-700 dark:text-gray-300 bg-green-50 dark:bg-green-950/20 p-2 rounded border border-green-200 dark:border-green-800 max-h-20 overflow-auto">
              <pre className="whitespace-pre-wrap font-mono">{outputStr}</pre>
            </div>
          </div>
        );
      } catch {
        details.push(
          <div key="output" className="mb-2">
            <div className="text-xs font-medium text-green-600 dark:text-green-400 mb-1">Output:</div>
            <div className="text-xs text-gray-600 dark:text-gray-400 bg-green-50 dark:bg-green-950/20 p-2 rounded border border-green-200 dark:border-green-800">
              [Unable to display output data]
            </div>
          </div>
        );
      }
    }

    if (nodeData.inputData) {
      try {
        const inputStr =
          typeof nodeData.inputData === "string"
            ? nodeData.inputData
            : JSON.stringify(nodeData.inputData, null, 2);
        details.push(
          <div key="input" className="mb-2">
            <div className="text-xs font-medium text-blue-600 dark:text-blue-400 mb-1">Input:</div>
            <div className="text-xs text-gray-700 dark:text-gray-300 bg-blue-50 dark:bg-blue-950/20 p-2 rounded border border-blue-200 dark:border-blue-800 max-h-20 overflow-auto">
              <pre className="whitespace-pre-wrap font-mono">{inputStr}</pre>
            </div>
          </div>
        );
      } catch {
        details.push(
          <div key="input" className="mb-2">
            <div className="text-xs font-medium text-blue-600 dark:text-blue-400 mb-1">Input:</div>
            <div className="text-xs text-gray-600 dark:text-gray-400 bg-blue-50 dark:bg-blue-950/20 p-2 rounded border border-blue-200 dark:border-blue-800">
              [Unable to display input data]
            </div>
          </div>
        );
      }
    }

    return details.length > 0 ? details : null;
  };

  return (
    <div
      className={cn(
        "group relative w-64 bg-card dark:bg-card rounded border-2 transition-all duration-200",
        config.borderColor,
        selected ? "ring-2 ring-blue-500 ring-offset-2" : "",
        isRunning ? config.glow : "shadow-sm",
      )}
    >
      {/* Small circular handles - always render both to support any edge configuration */}
      <Handle
        type="target"
        position={targetPosition}
        id="target"
        className="!w-2 !h-2 !rounded-full !border !border-gray-600 dark:!border-gray-500 transition-colors !min-w-0 !min-h-0"
        style={{
          backgroundColor: nodeData.state === "running" ? "#643FB2" :
                         nodeData.state === "completed" ? "#10b981" :
                         nodeData.state === "failed" ? "#ef4444" :
                         nodeData.state === "cancelled" ? "#f97316" : "#4b5563"
        }}
      />

      <Handle
        type="source"
        position={sourcePosition}
        id="source"
        className="!w-2 !h-2 !rounded-full !border !border-gray-600 dark:!border-gray-500 transition-colors !min-w-0 !min-h-0"
        style={{
          backgroundColor: nodeData.state === "running" ? "#643FB2" :
                         nodeData.state === "completed" ? "#10b981" :
                         nodeData.state === "failed" ? "#ef4444" :
                         nodeData.state === "cancelled" ? "#f97316" : "#4b5563"
        }}
      />

      <div className="p-3">
        {/* Header with icon and title */}
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 relative">
            {/* Icon container with dark background */}
            <div className="w-10 h-10 rounded-lg bg-gray-900/90 dark:bg-gray-800/90 flex items-center justify-center">
              {nodeData.isStartNode ? (
                <Home className="w-5 h-5 text-[#643FB2] dark:text-[#8B5CF6]" />
              ) : (
                <Workflow className="w-5 h-5 text-gray-300 dark:text-gray-400" />
              )}
            </div>
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <h3 className="font-medium text-sm text-gray-900 dark:text-gray-100 truncate">
                {nodeData.name || nodeData.executorId}
              </h3>
              {isRunning && (
                <Loader2 className="w-4 h-4 text-[#643FB2] dark:text-[#8B5CF6] animate-spin flex-shrink-0" />
              )}
            </div>
            {nodeData.executorType && (
              <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">
                {nodeData.executorType}
              </p>
            )}
          </div>
        </div>

        {/* Data details */}
        {hasData && (
          <div className="mt-3">
            {renderDataDetails()}
          </div>
        )}

        {/* Running animation overlay */}
        {isRunning && (
          <div className="absolute inset-0 rounded border-2 border-[#643FB2]/30 dark:border-[#8B5CF6]/30 animate-pulse pointer-events-none" />
        )}
      </div>
    </div>
  );
});

ExecutorNode.displayName = "ExecutorNode";
