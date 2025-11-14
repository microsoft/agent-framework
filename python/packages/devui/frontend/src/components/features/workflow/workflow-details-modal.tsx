/**
 * WorkflowDetailsModal - Responsive grid-based modal for displaying workflow metadata
 */

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogClose,
} from "@/components/ui/dialog";
import {
  Workflow as WorkflowIcon,
  Package,
  FolderOpen,
  Database,
  Globe,
  CheckCircle,
  XCircle,
  PlayCircle,
} from "lucide-react";
import type { WorkflowInfo } from "@/types";

interface WorkflowDetailsModalProps {
  workflow: WorkflowInfo;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface DetailCardProps {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

function DetailCard({ title, icon, children, className = "" }: DetailCardProps) {
  return (
    <div className={`border rounded-lg p-4 bg-card ${className}`}>
      <div className="flex items-center gap-2 mb-3">
        {icon}
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      </div>
      <div className="text-sm text-muted-foreground">{children}</div>
    </div>
  );
}

export function WorkflowDetailsModal({
  workflow,
  open,
  onOpenChange,
}: WorkflowDetailsModalProps) {
  const sourceIcon =
    workflow.source === "directory" ? (
      <FolderOpen className="h-4 w-4 text-muted-foreground" />
    ) : workflow.source === "in_memory" ? (
      <Database className="h-4 w-4 text-muted-foreground" />
    ) : (
      <Globe className="h-4 w-4 text-muted-foreground" />
    );

  const sourceLabel =
    workflow.source === "directory"
      ? "Local"
      : workflow.source === "in_memory"
        ? "In-Memory"
        : "Gallery";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col">
        <DialogHeader className="px-6 pt-6 flex-shrink-0">
          <DialogTitle>Workflow Details</DialogTitle>
          <DialogClose onClose={() => onOpenChange(false)} />
        </DialogHeader>

        <div className="px-6 pb-6 overflow-y-auto flex-1">
          {/* Header Section */}
          <div className="mb-6">
            <div className="flex items-center gap-3 mb-2">
              <WorkflowIcon className="h-6 w-6 text-primary" />
              <h2 className="text-xl font-semibold text-foreground">
                {workflow.name || workflow.id}
              </h2>
            </div>
            {workflow.description && (
              <p className="text-muted-foreground">{workflow.description}</p>
            )}
          </div>

          <div className="h-px bg-border mb-6" />

          {/* Grid Layout for Metadata */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            {/* Start Executor */}
            <DetailCard
              title="Start Executor"
              icon={<PlayCircle className="h-4 w-4 text-muted-foreground" />}
            >
              <div className="font-mono text-foreground">
                {workflow.start_executor_id}
              </div>
            </DetailCard>

            {/* Source */}
            <DetailCard title="Source" icon={sourceIcon}>
              <div className="space-y-1">
                <div className="text-foreground">{sourceLabel}</div>
                {workflow.module_path && (
                  <div className="font-mono text-xs break-all">
                    {workflow.module_path}
                  </div>
                )}
              </div>
            </DetailCard>

            {/* Environment */}
            <DetailCard
              title="Environment"
              icon={
                workflow.has_env ? (
                  <XCircle className="h-4 w-4 text-orange-500" />
                ) : (
                  <CheckCircle className="h-4 w-4 text-green-500" />
                )
              }
              className="md:col-span-2"
            >
              <div
                className={
                  workflow.has_env
                    ? "text-orange-600 dark:text-orange-400"
                    : "text-green-600 dark:text-green-400"
                }
              >
                {workflow.has_env
                  ? "Requires environment variables"
                  : "No environment variables required"}
              </div>
            </DetailCard>
          </div>

          {/* Executors */}
          <DetailCard
            title={`Executors (${workflow.executors.length})`}
            icon={<Package className="h-4 w-4 text-muted-foreground" />}
          >
            {workflow.executors.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {workflow.executors.map((executor, index) => (
                  <div
                    key={index}
                    className="font-mono text-xs text-foreground bg-muted px-2 py-1 rounded truncate"
                    title={executor}
                  >
                    {executor}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-muted-foreground">No executors configured</div>
            )}
          </DetailCard>
        </div>
      </DialogContent>
    </Dialog>
  );
}
