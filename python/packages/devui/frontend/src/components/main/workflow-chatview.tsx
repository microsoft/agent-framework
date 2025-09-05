import { useMemo, useState } from "react";
import { MermaidDiagram } from "../workflow/MermaidDiagram";
import { CheckCircle, Clock, AlertCircle, Loader2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { WorkflowInfo } from "@/types";
import type { DebugStreamEvent } from "@/types/agent-framework";

interface WorkflowChatViewProps {
  workflowInfo?: WorkflowInfo | null;
  events: DebugStreamEvent[];
  isStreaming: boolean;
  onSendMessage?: (message: string) => void;
}

interface WorkflowExecution {
  mermaidDiagram?: string;
  workflowDump?: any;
  activeExecutors: string[];
  executorHistory: Array<{
    executorId: string;
    message: string;
    timestamp: string;
    status: "running" | "completed" | "error";
  }>;
  completionResult?: string;
  error?: string;
}

export function WorkflowChatView({
  workflowInfo,
  events,
  isStreaming,
  onSendMessage,
}: WorkflowChatViewProps) {
  const [inputValue, setInputValue] = useState("");

  const workflowExecution = useMemo((): WorkflowExecution => {
    // Use static workflow info first, fall back to streaming events
    let mermaidDiagram = workflowInfo?.mermaid_diagram;
    let workflowDump = workflowInfo?.workflow_dump;

    // Override with streaming data if available (for consistency)
    const structureEvent = events.find((e) => e.type === "workflow_structure");
    if (structureEvent?.mermaid_diagram) {
      mermaidDiagram = structureEvent.mermaid_diagram;
    }
    if (structureEvent?.workflow_dump) {
      workflowDump = structureEvent.workflow_dump;
    }

    // Track executor execution history
    const executorHistory: WorkflowExecution["executorHistory"] = [];
    const activeExecutors = new Set<string>();

    // Process workflow events to build execution history
    events.forEach((event) => {
      if (event.type === "workflow_event" && event.event) {
        // Check if this is an ExecutorEvent which has executor_id
        const executorId = 'executor_id' in event.event ? (event.event as any).executor_id as string : undefined;
        const eventData = event.event.data;

        if (executorId) {
          // Determine status based on event content
          let status: "running" | "completed" | "error" = "running";
          let message = "";

          if (typeof eventData === "string") {
            message = eventData;
            // Check if this looks like a completion message
            if (
              eventData.includes("completed") ||
              eventData.includes("processed") ||
              eventData.includes("success")
            ) {
              status = "completed";
            } else if (
              eventData.includes("error") ||
              eventData.includes("failed")
            ) {
              status = "error";
            }
          } else if (eventData && typeof eventData === "object") {
            message = JSON.stringify(eventData, null, 2);
          } else {
            message = "Processing...";
          }

          executorHistory.push({
            executorId,
            message,
            timestamp: event.timestamp || new Date().toISOString(),
            status,
          });

          // Track currently active executors (last few that are running)
          if (status === "running" || isStreaming) {
            activeExecutors.add(executorId);
          }
        }
      }
    });

    // Find completion result
    const completionEvent = events.find((e) => e.type === "completion");
    let completionResult = "";
    if (completionEvent?.event?.data) {
      completionResult =
        typeof completionEvent.event.data === "string"
          ? completionEvent.event.data
          : JSON.stringify(completionEvent.event.data);
    }

    // Find error
    const errorEvent = events.find((e) => e.type === "error");
    const error = errorEvent?.error;

    // For active executors, only show the most recent ones if streaming
    const activeExecutorsList = isStreaming
      ? Array.from(activeExecutors).slice(-2) // Show last 2 active
      : []; // Show none if not streaming

    return {
      mermaidDiagram,
      workflowDump,
      activeExecutors: activeExecutorsList,
      executorHistory,
      completionResult,
      error,
    };
  }, [workflowInfo, events, isStreaming]);

  if (
    !workflowExecution.mermaidDiagram &&
    !workflowExecution.executorHistory.length
  ) {
    return (
      <div className="flex items-center justify-center p-8 text-gray-500">
        <Loader2 className="w-6 h-6 animate-spin mr-2" />
        Initializing workflow...
      </div>
    );
  }

  return (
    <div className="workflow-chat-view space-y-6 p-4">
      {/* Workflow Diagram Section */}
      {workflowExecution.mermaidDiagram && (
        <div className="border rounded-lg bg-white shadow-sm">
          <div className="border-b px-4 py-3 bg-gray-50 rounded-t-lg">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-gray-900">
                Workflow Execution
              </h3>
              {isStreaming && (
                <div className="flex items-center gap-2 text-sm text-blue-600">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Running...
                </div>
              )}
              {!isStreaming && !workflowExecution.error && workflowExecution.executorHistory.length > 0 && (
                <div className="flex items-center gap-2 text-sm text-green-600">
                  <CheckCircle className="w-4 h-4" />
                  Completed
                </div>
              )}
              {!isStreaming && !workflowExecution.error && workflowExecution.executorHistory.length === 0 && (
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  <Clock className="w-4 h-4" />
                  Ready
                </div>
              )}
              {workflowExecution.error && (
                <div className="flex items-center gap-2 text-sm text-red-600">
                  <AlertCircle className="w-4 h-4" />
                  Error
                </div>
              )}
            </div>
          </div>
          <div className="p-4">
            <MermaidDiagram
              diagram={workflowExecution.mermaidDiagram}
              activeExecutors={workflowExecution.activeExecutors}
              className="max-w-full overflow-auto"
            />
          </div>
        </div>
      )}

      {/* Execution History */}
      {workflowExecution.executorHistory.length > 0 && (
        <div className="border rounded-lg bg-white shadow-sm">
          <div className="border-b px-4 py-3 bg-gray-50 rounded-t-lg">
            <h4 className="text-sm font-medium text-gray-900">
              Execution Steps
            </h4>
          </div>
          <div className="p-4 space-y-3 max-h-64 overflow-y-auto">
            {workflowExecution.executorHistory.map((step, index) => (
              <div key={index} className="flex items-start gap-3">
                <div className="flex-shrink-0 mt-1">
                  {step.status === "completed" && (
                    <CheckCircle className="w-4 h-4 text-green-500" />
                  )}
                  {step.status === "running" && (
                    <Clock className="w-4 h-4 text-blue-500" />
                  )}
                  {step.status === "error" && (
                    <AlertCircle className="w-4 h-4 text-red-500" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-gray-900">
                      {step.executorId}
                    </span>
                    <span className="text-xs text-gray-500">
                      {new Date(step.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 break-words">
                    {step.message}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Final Result */}
      {workflowExecution.completionResult && (
        <div className="border rounded-lg bg-green-50 border-green-200 shadow-sm">
          <div className="border-b border-green-200 px-4 py-3 bg-green-100 rounded-t-lg">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-green-600" />
              <h4 className="text-sm font-medium text-green-800">Result</h4>
            </div>
          </div>
          <div className="p-4">
            <p className="text-green-700 whitespace-pre-wrap break-words">
              {workflowExecution.completionResult}
            </p>
          </div>
        </div>
      )}

      {/* Error Display */}
      {workflowExecution.error && (
        <div className="border rounded-lg bg-red-50 border-red-200 shadow-sm">
          <div className="border-b border-red-200 px-4 py-3 bg-red-100 rounded-t-lg">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-red-600" />
              <h4 className="text-sm font-medium text-red-800">Error</h4>
            </div>
          </div>
          <div className="p-4">
            <p className="text-red-700 whitespace-pre-wrap break-words">
              {workflowExecution.error}
            </p>
          </div>
        </div>
      )}

      {/* Workflow Input */}
      {onSendMessage && (
        <div className="border-t bg-gray-50 p-4">
          <div className="flex items-center gap-2">
            <Input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={
                workflowInfo?.workflow_dump?.executors?.[workflowInfo.workflow_dump.start_executor_id]?.type_ === "SpamDetector" 
                  ? "Enter message to analyze (e.g., 'Hello, how are you today?')"
                  : "Enter workflow input..."
              }
              onKeyDown={(e) => {
                if (e.key === "Enter" && !isStreaming && inputValue.trim()) {
                  onSendMessage(inputValue.trim());
                  setInputValue("");
                }
              }}
              disabled={isStreaming}
            />
            <Button
              onClick={() => {
                if (inputValue.trim() && !isStreaming) {
                  onSendMessage(inputValue.trim());
                  setInputValue("");
                }
              }}
              disabled={!inputValue.trim() || isStreaming}
              size="sm"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
