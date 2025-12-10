/**
 * RunWorkflowButton - Shared component for running workflows with checkpoint support
 * Features: Split button with dropdown for checkpoint selection, input validation, modal dialog
 */

import { useState, useEffect, useMemo } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogClose,
} from "@/components/ui/dialog";
import { WorkflowInputForm } from "./workflow-input-form";
import { ChatMessageInput } from "@/components/ui/chat-message-input";
import { isChatMessageSchema } from "@/utils/workflow-utils";
import {
  ChevronDown,
  Clock,
  Loader2,
  Play,
  RotateCcw,
  Settings,
  Square,
  RefreshCw,
} from "lucide-react";
import type { JSONSchemaProperty, CheckpointItem } from "@/types";
import type { ResponseInputContent } from "@/types/agent-framework";

export interface RunWorkflowButtonProps {
  inputSchema?: JSONSchemaProperty;
  onRun: (data: Record<string, unknown>, checkpointId?: string) => void;
  onCancel?: () => void;
  isSubmitting: boolean;
  isCancelling?: boolean;
  workflowState: "ready" | "running" | "completed" | "error" | "cancelled";
  checkpoints?: CheckpointItem[];
  // Optional prop to control whether to show checkpoints dropdown
  showCheckpoints?: boolean;
}

export function RunWorkflowButton({
  inputSchema,
  onRun,
  onCancel,
  isSubmitting,
  isCancelling = false,
  workflowState,
  checkpoints = [],
  showCheckpoints = true,
}: RunWorkflowButtonProps) {
  const [showModal, setShowModal] = useState(false);

  // Handle escape key to close modal
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && showModal) {
        setShowModal(false);
      }
    };

    if (showModal) {
      document.addEventListener("keydown", handleEscape);
      return () => document.removeEventListener("keydown", handleEscape);
    }
  }, [showModal]);

  // Analyze input requirements
  const inputAnalysis = useMemo(() => {
    // Check if this is a ChatMessage schema (for AgentExecutor workflows)
    const isChatMessage = isChatMessageSchema(inputSchema);

    if (!inputSchema)
      return {
        needsInput: false,
        hasDefaults: false,
        fieldCount: 0,
        canRunDirectly: true,
        isChatMessage: false,
      };

    if (inputSchema.type === "string") {
      return {
        needsInput: !inputSchema.default,
        hasDefaults: !!inputSchema.default,
        fieldCount: 1,
        canRunDirectly: !!inputSchema.default,
        isChatMessage: false,
      };
    }

    if (inputSchema.type === "object" && inputSchema.properties) {
      const properties = inputSchema.properties;
      const fields = Object.entries(properties);
      const fieldsWithDefaults = fields.filter(
        ([, schema]: [string, JSONSchemaProperty]) =>
          schema.default !== undefined ||
          (schema.enum && schema.enum.length > 0)
      );

      return {
        needsInput: fields.length > 0,
        hasDefaults: fieldsWithDefaults.length > 0,
        fieldCount: fields.length,
        canRunDirectly:
          fields.length === 0 || fieldsWithDefaults.length === fields.length,
        isChatMessage,
      };
    }

    return {
      needsInput: false,
      hasDefaults: false,
      fieldCount: 0,
      canRunDirectly: true,
      isChatMessage: false,
    };
  }, [inputSchema]);

  const handleDirectRun = () => {
    if (workflowState === "running" && onCancel) {
      onCancel();
    } else if (inputAnalysis.canRunDirectly) {
      // Build default data
      const defaultData: Record<string, unknown> = {};

      if (inputSchema?.type === "string" && inputSchema.default) {
        defaultData.input = inputSchema.default;
      } else if (inputSchema?.type === "object" && inputSchema.properties) {
        Object.entries(inputSchema.properties).forEach(
          ([key, schema]: [string, JSONSchemaProperty]) => {
            if (schema.default !== undefined) {
              defaultData[key] = schema.default;
            } else if (schema.enum && schema.enum.length > 0) {
              defaultData[key] = schema.enum[0];
            }
          }
        );
      }

      onRun(defaultData);
    } else {
      setShowModal(true);
    }
  };

  const handleRunFromCheckpoint = (checkpointId: string) => {
    if (inputAnalysis.canRunDirectly) {
      // Build default data
      const defaultData: Record<string, unknown> = {};

      if (inputSchema?.type === "string" && inputSchema.default) {
        defaultData.input = inputSchema.default;
      } else if (inputSchema?.type === "object" && inputSchema.properties) {
        Object.entries(inputSchema.properties).forEach(
          ([key, schema]: [string, JSONSchemaProperty]) => {
            if (schema.default !== undefined) {
              defaultData[key] = schema.default;
            } else if (schema.enum && schema.enum.length > 0) {
              defaultData[key] = schema.enum[0];
            }
          }
        );
      }

      onRun(defaultData, checkpointId);
    } else {
      // TODO: Pass checkpoint ID to modal for custom inputs
      setShowModal(true);
    }
  };

  const hasCheckpoints = showCheckpoints && checkpoints.length > 0;

  // Format checkpoint size for display
  const formatSize = (bytes?: number): string => {
    if (!bytes) return "";
    const kb = bytes / 1024;
    if (kb < 1) {
      return `${bytes} B`;
    } else if (kb < 1024) {
      return `${kb.toFixed(1)} KB`;
    } else {
      return `${(kb / 1024).toFixed(1)} MB`;
    }
  };

  // Build the button content based on state
  const getButtonContent = () => {
    const icon = isCancelling ? (
      <Loader2 className="w-4 h-4 animate-spin" />
    ) : workflowState === "running" && onCancel ? (
      <Square className="w-4 h-4 fill-current" />
    ) : workflowState === "running" ? (
      <Loader2 className="w-4 h-4 animate-spin" />
    ) : workflowState === "error" ? (
      <RotateCcw className="w-4 h-4" />
    ) : inputAnalysis.needsInput && !inputAnalysis.canRunDirectly ? (
      <Settings className="w-4 h-4" />
    ) : (
      <Play className="w-4 h-4" />
    );

    const text = isCancelling
      ? "Stopping..."
      : workflowState === "running" && onCancel
      ? "Stop"
      : workflowState === "running"
      ? "Running..."
      : workflowState === "completed"
      ? "Run Again"
      : workflowState === "error"
      ? "Retry"
      : inputAnalysis.fieldCount === 0
      ? "Run Workflow"
      : inputAnalysis.canRunDirectly
      ? "Run Workflow"
      : "Configure & Run";

    return { icon, text };
  };

  const { icon, text } = getButtonContent();
  const isDisabled = (workflowState === "running" && !onCancel) || isCancelling;
  const buttonVariant = workflowState === "error" ? "destructive" : "default";

  // Unified layout for both variants
  const renderButton = () => {
    // Always show split button if there are checkpoints OR if inputs need configuration
    const showDropdown = hasCheckpoints || inputAnalysis.needsInput;

    if (!showDropdown) {
      // Simple button - no dropdown needed
      return (
        <Button
          onClick={handleDirectRun}
          disabled={isDisabled}
          variant={buttonVariant}
          className="gap-2 w-full"
          title={
            workflowState === "running" && onCancel
              ? "Stop workflow execution"
              : undefined
          }
        >
          {icon}
          {text}
        </Button>
      );
    }

    // Split button with dropdown
    return (
      <DropdownMenu>
        <div className="flex w-full">
          <Button
            onClick={handleDirectRun}
            disabled={isDisabled}
            variant={buttonVariant}
            className="gap-2 rounded-r-none flex-1"
            title={
              workflowState === "running" && onCancel
                ? "Stop workflow execution"
                : undefined
            }
          >
            {icon}
            {text}
          </Button>
          <DropdownMenuTrigger asChild>
            <Button
              disabled={isDisabled}
              variant={buttonVariant}
              className="rounded-l-none border-l-0 px-2"
              title="More options"
            >
              <ChevronDown className="w-4 h-4" />
            </Button>
          </DropdownMenuTrigger>
        </div>
        <DropdownMenuContent
          align="end"
          className="w-80 max-h-[400px] overflow-y-auto"
        >
          {/* Run Fresh option - only show when checkpoints are enabled */}
          {hasCheckpoints && (
            <DropdownMenuItem onClick={handleDirectRun}>
              <Play className="w-4 h-4 mr-2" />
              Run Fresh
            </DropdownMenuItem>
          )}

          {/* Configure inputs option */}
          {inputAnalysis.needsInput && (
            <DropdownMenuItem onClick={() => setShowModal(true)}>
              <Settings className="w-4 h-4 mr-2" />
              Configure Inputs
            </DropdownMenuItem>
          )}

          {/* Checkpoint options */}
          {hasCheckpoints && (
            <>
              <DropdownMenuSeparator />
              <div className="px-2 py-1.5 text-xs text-muted-foreground">
                Resume from checkpoint
              </div>
              {checkpoints.map((checkpoint, index) => (
                <DropdownMenuItem
                  key={checkpoint.checkpoint_id}
                  onClick={() =>
                    handleRunFromCheckpoint(checkpoint.checkpoint_id)
                  }
                  className="flex flex-col items-start py-2"
                >
                  <div className="flex items-center gap-2 w-full">
                    <RefreshCw className="w-4 h-4 flex-shrink-0" />
                    <span className="font-medium">
                      {checkpoint.metadata.iteration_count === 0
                        ? "Initial State"
                        : `Step ${checkpoint.metadata.iteration_count}`}
                    </span>
                    {index === 0 && (
                      <Badge
                        variant="secondary"
                        className="text-[10px] h-4 px-1 ml-auto"
                      >
                        Latest
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground ml-6 mt-0.5">
                    <Clock className="w-3 h-3" />
                    <span>
                      {new Date(checkpoint.timestamp).toLocaleTimeString()}
                    </span>
                    {checkpoint.metadata.size_bytes && (
                      <>
                        <span>•</span>
                        <span>
                          {formatSize(checkpoint.metadata.size_bytes)}
                        </span>
                      </>
                    )}
                  </div>
                </DropdownMenuItem>
              ))}
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    );
  };

  return (
    <>
      {renderButton()}

      {/* Modal for input configuration */}
      {inputSchema && (
        <Dialog open={showModal} onOpenChange={setShowModal}>
          <DialogContent className="w-full min-w-[400px] max-w-md sm:max-w-lg md:max-w-2xl lg:max-w-4xl xl:max-w-5xl max-h-[90vh] flex flex-col">
            <DialogHeader className="px-8 pt-6">
              <DialogTitle>Configure Workflow Inputs</DialogTitle>
              <DialogClose onClose={() => setShowModal(false)} />
            </DialogHeader>

            <div className="px-8 py-4 border-b flex-shrink-0">
              <div className="text-sm text-muted-foreground">
                <div className="flex items-center gap-3">
                  <span className="font-medium">Input Type:</span>
                  <Badge variant="secondary">
                    {inputAnalysis.isChatMessage
                      ? "Chat Message"
                      : inputSchema.type === "string"
                      ? "Simple Text"
                      : "Structured Data"}
                  </Badge>
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto py-4 px-8">
              {inputAnalysis.isChatMessage ? (
                <ChatMessageInput
                  onSubmit={async (content: ResponseInputContent[]) => {
                    // Wrap in OpenAI message format (same structure as agent-view)
                    // This preserves multimodal content (images, files) for the backend
                    const openaiInput = [
                      { type: "message", role: "user", content },
                    ];
                    onRun(openaiInput as unknown as Record<string, unknown>);
                    setShowModal(false);
                  }}
                  isSubmitting={isSubmitting}
                  placeholder="Enter your message..."
                  entityName="workflow"
                  showFileUpload={true}
                />
              ) : (
                <WorkflowInputForm
                  inputSchema={inputSchema}
                  inputTypeName="Input"
                  onSubmit={(values) => {
                    onRun(values as Record<string, unknown>);
                    setShowModal(false);
                  }}
                  isSubmitting={isSubmitting}
                  className="embedded"
                />
              )}
            </div>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}
