/**
 * CheckpointInfoModal - Timeline view of workflow checkpoints
 */

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogClose,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Clock,
  MessageSquare,
  AlertCircle,
  Loader2,
  Package,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/services/api";
import type { CheckpointItem, WorkflowSession } from "@/types";

interface CheckpointInfoModalProps {
  session: WorkflowSession | null;
  checkpoints: CheckpointItem[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CheckpointInfoModal({
  session,
  checkpoints,
  open,
  onOpenChange,
}: CheckpointInfoModalProps) {
  const [selectedCheckpointId, setSelectedCheckpointId] = useState<string | null>(null);
  const [fullCheckpoint, setFullCheckpoint] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [jsonExpanded, setJsonExpanded] = useState(true);

  // Select first checkpoint when modal opens or checkpoints change
  useEffect(() => {
    if (open && checkpoints.length > 0) {
      // Only reset selection if current selection is invalid
      const currentSelectionValid = checkpoints.some(
        cp => cp.checkpoint_id === selectedCheckpointId
      );
      if (!currentSelectionValid) {
        setSelectedCheckpointId(checkpoints[0].checkpoint_id);
      }
    }
  }, [open, checkpoints]);

  // Load full checkpoint details
  useEffect(() => {
    if (!selectedCheckpointId || !session) return;

    const loadDetails = async () => {
      // Don't clear the previous checkpoint to avoid UI flash
      setLoading(true);
      try {
        const item = await apiClient.getConversationItem(
          session.conversation_id,
          `checkpoint_${selectedCheckpointId}`
        );
        setFullCheckpoint((item as CheckpointItem).metadata?.full_checkpoint);
      } catch (error) {
        console.error("Failed to load checkpoint:", error);
        setFullCheckpoint(null);
      } finally {
        setLoading(false);
      }
    };

    loadDetails();
  }, [selectedCheckpointId, session]);

  if (!session) return null;

  const selectedCheckpoint = checkpoints.find(
    (cp) => cp.checkpoint_id === selectedCheckpointId
  );

  const executorIds = fullCheckpoint?.shared_state?._executor_state
    ? Object.keys(fullCheckpoint.shared_state._executor_state)
    : [];
  const messageExecutors = fullCheckpoint?.messages
    ? Object.keys(fullCheckpoint.messages)
    : [];

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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[90vw] max-w-6xl min-w-[800px] h-[85vh] flex flex-col p-0">
        {/* Header */}
        <DialogHeader className="px-6 pt-6 pb-4 border-b flex-shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex-1">
              <DialogTitle>{session.metadata.name}</DialogTitle>
              <div className="text-sm text-muted-foreground mt-1">
                {checkpoints.length} checkpoint{checkpoints.length !== 1 ? "s" : ""}
              </div>
              <div className="text-xs text-muted-foreground mt-2 max-w-2xl">
                This is a read only view of the current checkpoint ids in the checkpoint storage for this workflow run.
              </div>
            </div>
            <DialogClose onClose={() => onOpenChange(false)} />
          </div>
        </DialogHeader>

        {/* Main Content - Timeline + Details */}
        <div className="flex-1 flex overflow-hidden min-h-0">
          {/* Timeline Sidebar */}
          <div className="w-80 border-r flex flex-col">
            <ScrollArea className="flex-1">
              <div className="p-4 space-y-2">
                {checkpoints.length === 0 ? (
                  <div className="text-center text-sm text-muted-foreground py-8">
                    No checkpoints yet
                  </div>
                ) : (
                  checkpoints.map((checkpoint, index) => {
                    const isSelected = checkpoint.checkpoint_id === selectedCheckpointId;
                    const hasHil = checkpoint.metadata.has_pending_hil;

                    return (
                      <div key={checkpoint.checkpoint_id} className="relative">
                        <button
                          onClick={() => setSelectedCheckpointId(checkpoint.checkpoint_id)}
                          className={cn(
                            "relative w-full text-left p-3 rounded-lg border transition-colors",
                            isSelected
                              ? "bg-primary/10 border-primary"
                              : "hover:bg-muted/50 border-transparent"
                          )}
                        >
                          <div className="flex items-start gap-3">
                            {/* Timeline Dot */}
                            <div className="flex flex-col items-center pt-1">
                              <div
                                className={cn(
                                  "w-2 h-2 rounded-full z-10",
                                  hasHil
                                    ? "bg-blue-500 ring-2 ring-blue-500/20"
                                    : "bg-muted-foreground/30"
                                )}
                              />
                            </div>

                            {/* Checkpoint Info */}
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-medium">
                                  {checkpoint.metadata.iteration_count === 0 ? "Initial State" : `Step ${checkpoint.metadata.iteration_count}`}
                                </span>
                                <span className="text-[10px] font-mono text-muted-foreground/70" title={checkpoint.checkpoint_id}>
                                  {checkpoint.checkpoint_id.slice(0, 8)}
                                </span>
                                {index === 0 && (
                                  <Badge variant="secondary" className="text-[10px] h-4 px-1">
                                    Latest
                                  </Badge>
                                )}
                                {hasHil && (
                                  <Badge variant="secondary" className="text-[10px] h-4 px-1.5">
                                    {checkpoint.metadata.pending_hil_count} HIL
                                  </Badge>
                                )}
                              </div>
                              <div className="flex items-center gap-3 text-xs text-muted-foreground mt-1">
                                <span>{new Date(checkpoint.timestamp).toLocaleTimeString()}</span>
                                {checkpoint.metadata.size_bytes && (
                                  <>
                                    <span>•</span>
                                    <span>{formatSize(checkpoint.metadata.size_bytes)}</span>
                                  </>
                                )}
                              </div>
                            </div>
                          </div>
                        </button>

                        {/* Connecting Line - positioned absolutely */}
                        {index < checkpoints.length - 1 && (
                          <div className="absolute left-[18px] top-[30px] w-px h-[calc(100%+8px)] bg-border" />
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </ScrollArea>
          </div>

          {/* Details Panel */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {!fullCheckpoint && !loading ? (
              <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
                Select a checkpoint to view details
              </div>
            ) : (
              <ScrollArea className="flex-1">
                <div className="p-6 space-y-6 relative">
                  {/* Loading overlay */}
                  {loading && (
                    <div className="absolute inset-0 bg-background/50 flex items-center justify-center z-10">
                      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                  )}
                  {/* Header */}
                  <div className="flex items-start justify-between pb-4 border-b">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <Clock className="h-4 w-4 text-muted-foreground" />
                        <span className="font-medium">
                          {selectedCheckpoint?.metadata.iteration_count === 0
                            ? "Initial State"
                            : `Step ${selectedCheckpoint?.metadata.iteration_count}`}
                        </span>
                        {selectedCheckpoint?.metadata.size_bytes && (
                          <span className="text-xs text-muted-foreground">
                            • {formatSize(selectedCheckpoint.metadata.size_bytes)}
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-muted-foreground">
                        {selectedCheckpoint &&
                          new Date(selectedCheckpoint.timestamp).toLocaleString()}
                      </div>
                      {selectedCheckpoint && (
                        <div className="text-xs font-mono text-muted-foreground/70 mt-1">
                          ID: {selectedCheckpoint.checkpoint_id}
                        </div>
                      )}
                    </div>
                    {selectedCheckpoint?.metadata.has_pending_hil && (
                      <Badge variant="secondary">
                        {selectedCheckpoint.metadata.pending_hil_count} HIL Pending
                      </Badge>
                    )}
                  </div>

                  {/* Executors */}
                  {executorIds.length > 0 && (
                    <div>
                      <div className="text-sm font-medium mb-3 flex items-center gap-2">
                        <Package className="h-4 w-4" />
                        Active Executors ({executorIds.length})
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {executorIds.map((execId) => (
                          <Badge key={execId} variant="outline" className="font-mono text-xs">
                            {execId}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Messages */}
                  {messageExecutors.length > 0 && (
                    <div>
                      <div className="text-sm font-medium mb-3 flex items-center gap-2">
                        <MessageSquare className="h-4 w-4" />
                        Messages
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        {messageExecutors.map((execId) => {
                          const count = (fullCheckpoint.messages[execId] as unknown[])?.length;
                          return (
                            <div key={execId} className="bg-muted/50 p-3 rounded-lg">
                              <div className="text-xs font-mono text-muted-foreground mb-1">
                                {execId}
                              </div>
                              <div className="font-medium">
                                {count} message{count !== 1 ? "s" : ""}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* HIL Requests */}
                  {fullCheckpoint?.pending_request_info_events &&
                    Object.keys(fullCheckpoint.pending_request_info_events).length > 0 && (
                      <div>
                        <div className="text-sm font-medium mb-3 flex items-center gap-2">
                          <AlertCircle className="h-4 w-4" />
                          Pending HIL Requests (
                          {Object.keys(fullCheckpoint.pending_request_info_events).length})
                        </div>
                        <div className="space-y-2">
                          {Object.entries(fullCheckpoint.pending_request_info_events).map(
                            ([reqId, reqData]: [string, any]) => (
                              <div
                                key={reqId}
                                className="bg-muted/50 border border-border p-3 rounded-lg"
                              >
                                <div className="flex items-center justify-between mb-2">
                                  <code className="text-xs bg-background px-2 py-1 rounded">
                                    {reqId.slice(0, 24)}...
                                  </code>
                                  <Badge variant="outline" className="text-xs">
                                    {reqData.source_executor_id}
                                  </Badge>
                                </div>
                                <div className="text-xs space-y-1">
                                  <div>
                                    <span className="text-muted-foreground">Request:</span>{" "}
                                    <code className="bg-background px-1 py-0.5 rounded">
                                      {reqData.request_type?.split(".").pop() || reqData.request_type}
                                    </code>
                                  </div>
                                  <div>
                                    <span className="text-muted-foreground">Response:</span>{" "}
                                    <code className="bg-background px-1 py-0.5 rounded">
                                      {reqData.response_type?.split(".").pop() || reqData.response_type}
                                    </code>
                                  </div>
                                </div>
                              </div>
                            )
                          )}
                        </div>
                      </div>
                    )}

                  {/* Shared State */}
                  <div>
                    <div className="text-sm font-medium mb-3">Shared State</div>
                    {fullCheckpoint?.shared_state && Object.keys(fullCheckpoint.shared_state).filter(
                      (k) => k !== "_executor_state"
                    ).length > 0 ? (
                      <div className="flex flex-wrap gap-2">
                        {Object.keys(fullCheckpoint.shared_state)
                          .filter((k) => k !== "_executor_state")
                          .map((key) => (
                            <Badge key={key} variant="secondary" className="font-mono text-xs">
                              {key}
                            </Badge>
                          ))}
                      </div>
                    ) : (
                      <div className="text-sm text-muted-foreground">No custom state</div>
                    )}
                  </div>

                  {/* Raw JSON (Collapsible) */}
                  <div className="border-t pt-6">
                    <button
                      onClick={() => setJsonExpanded(!jsonExpanded)}
                      className="flex items-center gap-2 text-sm font-medium hover:text-primary transition-colors w-full"
                    >
                      {jsonExpanded ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronRight className="h-4 w-4" />
                      )}
                      Raw JSON
                    </button>
                    {jsonExpanded && (
                      <pre className="mt-3 text-[10px] font-mono bg-muted p-4 rounded overflow-x-auto">
                        {JSON.stringify(fullCheckpoint, null, 2)}
                      </pre>
                    )}
                  </div>
                </div>
              </ScrollArea>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
