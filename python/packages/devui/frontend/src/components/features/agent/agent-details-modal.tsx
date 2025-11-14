/**
 * AgentDetailsModal - Responsive grid-based modal for displaying agent metadata
 */

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogClose,
} from "@/components/ui/dialog";
import {
  Bot,
  Package,
  FileText,
  FolderOpen,
  Database,
  Globe,
  CheckCircle,
  XCircle,
} from "lucide-react";
import type { AgentInfo } from "@/types";

interface AgentDetailsModalProps {
  agent: AgentInfo;
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

export function AgentDetailsModal({
  agent,
  open,
  onOpenChange,
}: AgentDetailsModalProps) {
  const sourceIcon =
    agent.source === "directory" ? (
      <FolderOpen className="h-4 w-4 text-muted-foreground" />
    ) : agent.source === "in_memory" ? (
      <Database className="h-4 w-4 text-muted-foreground" />
    ) : (
      <Globe className="h-4 w-4 text-muted-foreground" />
    );

  const sourceLabel =
    agent.source === "directory"
      ? "Local"
      : agent.source === "in_memory"
      ? "In-Memory"
      : "Gallery";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col">
        <DialogHeader className="px-6 pt-6 flex-shrink-0">
          <DialogTitle>Agent Details</DialogTitle>
          <DialogClose onClose={() => onOpenChange(false)} />
        </DialogHeader>

        <div className="px-6 pb-6 overflow-y-auto flex-1">
          {/* Header Section */}
          <div className="mb-6">
            <div className="flex items-center gap-3 mb-2">
              <Bot className="h-6 w-6 text-primary" />
              <h2 className="text-xl font-semibold text-foreground">
                {agent.name || agent.id}
              </h2>
            </div>
            {agent.description && (
              <p className="text-muted-foreground">{agent.description}</p>
            )}
          </div>

          <div className="h-px bg-border mb-6" />

          {/* Grid Layout for Metadata */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            {/* Model & Client */}
            {(agent.model_id || agent.chat_client_type) && (
              <DetailCard
                title="Model & Client"
                icon={<Bot className="h-4 w-4 text-muted-foreground" />}
              >
                <div className="space-y-1">
                  {agent.model_id && (
                    <div className="font-mono text-foreground">{agent.model_id}</div>
                  )}
                  {agent.chat_client_type && (
                    <div className="text-xs">({agent.chat_client_type})</div>
                  )}
                </div>
              </DetailCard>
            )}

            {/* Source */}
            <DetailCard title="Source" icon={sourceIcon}>
              <div className="space-y-1">
                <div className="text-foreground">{sourceLabel}</div>
                {agent.module_path && (
                  <div className="font-mono text-xs break-all">
                    {agent.module_path}
                  </div>
                )}
              </div>
            </DetailCard>

            {/* Environment */}
            <DetailCard
              title="Environment"
              icon={
                agent.has_env ? (
                  <XCircle className="h-4 w-4 text-orange-500" />
                ) : (
                  <CheckCircle className="h-4 w-4 text-green-500" />
                )
              }
              className="md:col-span-2"
            >
              <div
                className={
                  agent.has_env
                    ? "text-orange-600 dark:text-orange-400"
                    : "text-green-600 dark:text-green-400"
                }
              >
                {agent.has_env
                  ? "Requires environment variables"
                  : "No environment variables required"}
              </div>
            </DetailCard>
          </div>

          {/* Full Width Sections */}
          {agent.instructions && (
            <DetailCard
              title="Instructions"
              icon={<FileText className="h-4 w-4 text-muted-foreground" />}
              className="mb-4"
            >
              <div className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">
                {agent.instructions}
              </div>
            </DetailCard>
          )}

          {/* Tools and Middleware Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Tools */}
            {agent.tools && agent.tools.length > 0 && (
              <DetailCard
                title={`Tools (${agent.tools.length})`}
                icon={<Package className="h-4 w-4 text-muted-foreground" />}
              >
                <ul className="space-y-1">
                  {agent.tools.map((tool, index) => (
                    <li key={index} className="font-mono text-xs text-foreground">
                      • {tool}
                    </li>
                  ))}
                </ul>
              </DetailCard>
            )}

            {/* Middleware */}
            {agent.middleware && agent.middleware.length > 0 && (
              <DetailCard
                title={`Middleware (${agent.middleware.length})`}
                icon={<Package className="h-4 w-4 text-muted-foreground" />}
              >
                <ul className="space-y-1">
                  {agent.middleware.map((mw, index) => (
                    <li key={index} className="font-mono text-xs text-foreground">
                      • {mw}
                    </li>
                  ))}
                </ul>
              </DetailCard>
            )}

            {/* Context Providers */}
            {agent.context_providers && agent.context_providers.length > 0 && (
              <DetailCard
                title={`Context Providers (${agent.context_providers.length})`}
                icon={<Database className="h-4 w-4 text-muted-foreground" />}
                className={!agent.middleware || agent.middleware.length === 0 ? "md:col-start-2" : ""}
              >
                <ul className="space-y-1">
                  {agent.context_providers.map((cp, index) => (
                    <li key={index} className="font-mono text-xs text-foreground">
                      • {cp}
                    </li>
                  ))}
                </ul>
              </DetailCard>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
