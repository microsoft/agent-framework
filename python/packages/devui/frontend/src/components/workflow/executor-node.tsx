import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  AlertCircle,
  Eye,
} from "lucide-react";
import { cn } from "@/lib/utils";

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
  onNodeClick?: (executorId: string, data: ExecutorNodeData) => void;
}

const getExecutorStateConfig = (state: ExecutorState) => {
  switch (state) {
    case "running":
      return {
        icon: Loader2,
        text: "Running",
        borderColor: "border-blue-500 dark:border-blue-400",
        iconColor: "text-blue-600 dark:text-blue-400",
        statusColor: "bg-blue-500 dark:bg-blue-400",
        animate: "animate-spin",
        glow: "shadow-lg shadow-blue-500/20",
      };
    case "completed":
      return {
        icon: CheckCircle,
        text: "Completed",
        borderColor: "border-green-500 dark:border-green-400",
        iconColor: "text-green-600 dark:text-green-400",
        statusColor: "bg-green-500 dark:bg-green-400",
        animate: "",
        glow: "shadow-lg shadow-green-500/20",
      };
    case "failed":
      return {
        icon: XCircle,
        text: "Failed",
        borderColor: "border-red-500 dark:border-red-400",
        iconColor: "text-red-600 dark:text-red-400",
        statusColor: "bg-red-500 dark:bg-red-400",
        animate: "",
        glow: "shadow-lg shadow-red-500/20",
      };
    case "cancelled":
      return {
        icon: AlertCircle,
        text: "Cancelled",
        borderColor: "border-orange-500 dark:border-orange-400",
        iconColor: "text-orange-600 dark:text-orange-400",
        statusColor: "bg-orange-500 dark:bg-orange-400",
        animate: "",
        glow: "shadow-lg shadow-orange-500/20",
      };
    case "pending":
    default:
      return {
        icon: Clock,
        text: "Pending",
        borderColor: "border-gray-300 dark:border-gray-600",
        iconColor: "text-gray-500 dark:text-gray-400",
        statusColor: "bg-gray-400 dark:bg-gray-500",
        animate: "",
        glow: "",
      };
  }
};

export const ExecutorNode = memo(({ data, selected }: NodeProps) => {
  const nodeData = data as ExecutorNodeData;
  const config = getExecutorStateConfig(nodeData.state);
  const IconComponent = config.icon;

  const handleClick = () => {
    nodeData.onNodeClick?.(nodeData.executorId, nodeData);
  };

  const hasData = nodeData.inputData || nodeData.outputData || nodeData.error;
  const isRunning = nodeData.state === "running";

  // Helper to safely render data
  const renderDataPreview = () => {
    if (nodeData.error && typeof nodeData.error === "string") {
      return (
        <div className="text-red-600 dark:text-red-400 font-medium">
          Error: {nodeData.error.substring(0, 40)}
          {nodeData.error.length > 40 && "..."}
        </div>
      );
    }

    if (nodeData.outputData) {
      try {
        const outputStr =
          typeof nodeData.outputData === "string"
            ? nodeData.outputData
            : JSON.stringify(nodeData.outputData);
        return (
          <div className="text-gray-600 dark:text-gray-300">
            Output: {outputStr.substring(0, 40)}
            {outputStr.length > 40 && "..."}
          </div>
        );
      } catch {
        return (
          <div className="text-gray-600 dark:text-gray-300">
            Output: [Unable to display]
          </div>
        );
      }
    }

    if (nodeData.inputData) {
      try {
        const inputStr =
          typeof nodeData.inputData === "string"
            ? nodeData.inputData
            : JSON.stringify(nodeData.inputData);
        return (
          <div className="text-gray-600 dark:text-gray-300">
            Input: {inputStr.substring(0, 40)}
            {inputStr.length > 40 && "..."}
          </div>
        );
      } catch {
        return (
          <div className="text-gray-600 dark:text-gray-300">
            Input: [Unable to display]
          </div>
        );
      }
    }

    return null;
  };

  return (
    <div
      className={cn(
        "group relative w-56 bg-card dark:bg-card rounded border-2 transition-all duration-200 cursor-pointer",
        config.borderColor,
        selected ? "ring-2 ring-blue-500 ring-offset-2" : "",
        isRunning ? config.glow : "shadow-sm hover:shadow-md",
        "hover:scale-[1.02]"
      )}
      onClick={handleClick}
    >
      {/* Only show target handle if not a start node */}
      {!nodeData.isStartNode && (
        <Handle
          type="target"
          position={Position.Left}
          className="!bg-accent !w-2 !h-5 !rounded-r-sm !-ml-1 !border-0 hover:!bg-accent/80 transition-colors"
        />
      )}

      {/* Only show source handle if not an end node */}
      {!nodeData.isEndNode && (
        <Handle
          type="source"
          position={Position.Right}
          className="!bg-accent !w-2 !h-5 !rounded-l-sm !-mr-1 !border-0 hover:!bg-accent/80 transition-colors"
        />
      )}

      <div className="p-4">
        {/* Header with icon and title */}
        <div className="flex items-start gap-3 mb-3">
          <div className="flex-shrink-0 mt-0.5">
            <IconComponent
              className={cn("w-5 h-5", config.iconColor, config.animate)}
            />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-medium text-sm text-gray-900 dark:text-gray-100 truncate">
              {nodeData.isStartNode && "🟢 "}
              {nodeData.isEndNode && "🔴 "}
              {nodeData.name || nodeData.executorId}
            </h3>
            {nodeData.executorType && (
              <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                {nodeData.executorType}
                {nodeData.isStartNode && " (Start)"}
                {nodeData.isEndNode && " (End)"}
              </p>
            )}
          </div>
          {hasData && (
            <div className="flex-shrink-0">
              <Eye className="w-4 h-4 text-gray-400 group-hover:text-gray-600 dark:group-hover:text-gray-300 transition-colors" />
            </div>
          )}
        </div>

        {/* State indicator */}
        <div className="flex items-center gap-2 mb-2">
          <div
            className={cn(
              "w-2 h-2 rounded-full",
              config.statusColor,
              config.animate
            )}
          />
          <span className={cn("text-xs font-medium", config.iconColor)}>
            {config.text}
          </span>
        </div>

        {/* Data preview */}
        {hasData && (
          <div className="mt-3 p-2 bg-gray-50 dark:bg-gray-800/50 rounded text-xs">
            {renderDataPreview()}
          </div>
        )}

        {/* Running animation overlay */}
        {isRunning && (
          <div className="absolute inset-0 rounded border-2 border-blue-500/30 dark:border-blue-400/30 animate-pulse pointer-events-none" />
        )}
      </div>
    </div>
  );
});

ExecutorNode.displayName = "ExecutorNode";
