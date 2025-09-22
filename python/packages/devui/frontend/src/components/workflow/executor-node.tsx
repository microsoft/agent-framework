import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  AlertCircle,
  Play,
  Flag,
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

  const hasData = nodeData.inputData || nodeData.outputData || nodeData.error;
  const isRunning = nodeData.state === "running";

  // Helper to safely render data with full details
  const renderDataDetails = () => {
    const details = [];

    if (nodeData.error && typeof nodeData.error === "string") {
      details.push(
        <div key="error" className="mb-2">
          <div className="text-xs font-medium text-red-600 dark:text-red-400 mb-1">Error:</div>
          <div className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/20 p-2 rounded border border-red-200 dark:border-red-800">
            {nodeData.error}
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
      {/* Start/End Badge */}
      {(nodeData.isStartNode || nodeData.isEndNode) && (
        <div className={cn(
          "absolute -top-6 left-2 px-2 py-1 rounded-t text-xs font-medium text-white flex items-center gap-1 z-10 shadow-sm",
          nodeData.isStartNode ? "bg-green-600" : "bg-red-600"
        )}>
          {nodeData.isStartNode ? (
            <>
              <Play className="w-3 h-3" />
              START
            </>
          ) : (
            <>
              <Flag className="w-3 h-3" />
              END
            </>
          )}
        </div>
      )}
      {/* Only show target handle if not a start node */}
      {!nodeData.isStartNode && (
        <Handle
          type="target"
          position={Position.Left}
          className="!w-2 !h-5 !rounded-r-sm !-ml-1 !border-0 transition-colors"
          style={{
            backgroundColor: nodeData.state === "running" ? "#3b82f6" :
                           nodeData.state === "completed" ? "#10b981" :
                           nodeData.state === "failed" ? "#ef4444" :
                           nodeData.state === "cancelled" ? "#f97316" : "#9ca3af"
          }}
        />
      )}

      {/* Only show source handle if not an end node */}
      {!nodeData.isEndNode && (
        <Handle
          type="source"
          position={Position.Right}
          className="!w-2 !h-5 !rounded-l-sm !-mr-1 !border-0 transition-colors"
          style={{
            backgroundColor: nodeData.state === "running" ? "#3b82f6" :
                           nodeData.state === "completed" ? "#10b981" :
                           nodeData.state === "failed" ? "#ef4444" :
                           nodeData.state === "cancelled" ? "#f97316" : "#9ca3af"
          }}
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
              {nodeData.name || nodeData.executorId}
            </h3>
            {nodeData.executorType && (
              <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                {nodeData.executorType}
              </p>
            )}
          </div>
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

        {/* Data details */}
        {hasData && (
          <div className="mt-3">
            {renderDataDetails()}
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
