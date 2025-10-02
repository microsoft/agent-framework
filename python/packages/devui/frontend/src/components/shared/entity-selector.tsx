/**
 * EntitySelector - High-quality dropdown for selecting agents/workflows
 * Features: Type indicators, tool counts, keyboard navigation, search
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { ChevronDown, Bot, Workflow, FolderOpen, Database, Globe, X, Plus } from "lucide-react";
import type { AgentInfo, WorkflowInfo } from "@/types";

interface EntitySelectorProps {
  agents: AgentInfo[];
  workflows: WorkflowInfo[];
  selectedItem?: AgentInfo | WorkflowInfo;
  onSelect: (item: AgentInfo | WorkflowInfo) => void;
  onRemove?: (entityId: string) => void;
  onBrowseGallery?: () => void;
  isLoading?: boolean;
}

const getTypeIcon = (type: "agent" | "workflow") => {
  return type === "workflow" ? Workflow : Bot;
};

const getSourceIcon = (source: "directory" | "in_memory" | "remote_gallery") => {
  switch (source) {
    case "directory": return FolderOpen;
    case "in_memory": return Database;
    case "remote_gallery": return Globe;
    default: return Database;
  }
};

const getSourceLabel = (source: "directory" | "in_memory" | "remote_gallery") => {
  switch (source) {
    case "directory": return "Local";
    case "in_memory": return "Memory";
    case "remote_gallery": return "Gallery";
    default: return "Unknown";
  }
};

export function EntitySelector({
  agents,
  workflows,
  selectedItem,
  onSelect,
  onRemove,
  onBrowseGallery,
  isLoading = false,
}: EntitySelectorProps) {
  const [open, setOpen] = useState(false);

  const allItems = [...agents, ...workflows].sort(
    (a, b) => a.name?.localeCompare(b.name || a.id) || a.id.localeCompare(b.id)
  );

  const handleSelect = (item: AgentInfo | WorkflowInfo) => {
    onSelect(item);
    setOpen(false);
  };

  const TypeIcon = selectedItem ? getTypeIcon(selectedItem.type) : Bot;
  const displayName = selectedItem?.name || selectedItem?.id || "Select Agent or Workflow";
  const itemCount =
    selectedItem?.type === "workflow"
      ? (selectedItem as WorkflowInfo).executors?.length || 0
      : (selectedItem as AgentInfo)?.tools?.length || 0;
  const itemLabel = selectedItem?.type === "workflow" ? "executors" : "tools";

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          className="w-64 justify-between font-mono text-sm"
          disabled={isLoading}
        >
          {isLoading ? (
            <div className="flex items-center gap-2">
              <LoadingSpinner size="sm" />
              <span className="text-muted-foreground">Loading...</span>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2 min-w-0">
                <TypeIcon className="h-4 w-4 flex-shrink-0" />
                <span className="truncate">{displayName}</span>
                {selectedItem && (
                  <Badge variant="secondary" className="ml-auto flex-shrink-0">
                    {itemCount} {itemLabel}
                  </Badge>
                )}
              </div>
              <ChevronDown className="h-4 w-4 opacity-50" />
            </>
          )}
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent className="w-80 font-mono">
        {agents.length > 0 && (
          <>
            <DropdownMenuLabel className="flex items-center gap-2">
              <Bot className="h-4 w-4" />
              Agents ({agents.length})
            </DropdownMenuLabel>
            {agents.map((agent) => {
              const SourceIcon = getSourceIcon(agent.source);
              return (
                <DropdownMenuItem
                  key={agent.id}
                  className="cursor-pointer group"
                >
                  <div className="flex items-center justify-between w-full">
                    <div
                      className="flex items-center gap-2 min-w-0 flex-1"
                      onClick={() => handleSelect(agent)}
                    >
                      <Bot className="h-4 w-4 flex-shrink-0" />
                      <div className="min-w-0">
                        <div className="truncate font-medium">
                          {agent.name || agent.id}
                        </div>
                        {agent.description && (
                          <div className="text-xs text-muted-foreground truncate">
                            {agent.description}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <SourceIcon className="h-3 w-3 opacity-60" />
                      <Badge variant="outline" className="text-xs">
                        {getSourceLabel(agent.source)}
                      </Badge>
                      <Badge variant="outline" className="text-xs ml-1">
                        {agent.tools.length}
                      </Badge>

                      {/* Remove button for gallery entities */}
                      {agent.source === 'remote_gallery' && onRemove && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 w-6 p-0 opacity-0 group-hover:opacity-100 ml-1"
                          onClick={(e) => {
                            e.stopPropagation();
                            onRemove(agent.id);
                          }}
                        >
                          <X className="h-3 w-3 text-destructive" />
                        </Button>
                      )}
                    </div>
                  </div>
                </DropdownMenuItem>
              );
            })}
          </>
        )}

        {workflows.length > 0 && (
          <>
            {agents.length > 0 && <DropdownMenuSeparator />}
            <DropdownMenuLabel className="flex items-center gap-2">
              <Workflow className="h-4 w-4" />
              Workflows ({workflows.length})
            </DropdownMenuLabel>
            {workflows.map((workflow) => {
              const SourceIcon = getSourceIcon(workflow.source);
              return (
                <DropdownMenuItem
                  key={workflow.id}
                  className="cursor-pointer group"
                >
                  <div className="flex items-center justify-between w-full">
                    <div
                      className="flex items-center gap-2 min-w-0 flex-1"
                      onClick={() => handleSelect(workflow)}
                    >
                      <Workflow className="h-4 w-4 flex-shrink-0" />
                      <div className="min-w-0">
                        <div className="truncate font-medium">
                          {workflow.name || workflow.id}
                        </div>
                        {workflow.description && (
                          <div className="text-xs text-muted-foreground truncate">
                            {workflow.description}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <SourceIcon className="h-3 w-3 opacity-60" />
                      <Badge variant="outline" className="text-xs">
                        {getSourceLabel(workflow.source)}
                      </Badge>
                      <Badge variant="outline" className="text-xs ml-1">
                        {workflow.executors.length}
                      </Badge>

                      {/* Remove button for gallery entities */}
                      {workflow.source === 'remote_gallery' && onRemove && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 w-6 p-0 opacity-0 group-hover:opacity-100 ml-1"
                          onClick={(e) => {
                            e.stopPropagation();
                            onRemove(workflow.id);
                          }}
                        >
                          <X className="h-3 w-3 text-destructive" />
                        </Button>
                      )}
                    </div>
                  </div>
                </DropdownMenuItem>
              );
            })}
          </>
        )}

        {allItems.length === 0 && (
          <DropdownMenuItem disabled>
            <div className="text-center text-muted-foreground py-2">
              {isLoading ? "Loading agents and workflows..." : "No agents or workflows found"}
            </div>
          </DropdownMenuItem>
        )}

        {/* Browse Gallery option */}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="cursor-pointer text-primary"
          onClick={() => {
            onBrowseGallery?.();
            setOpen(false);
          }}
        >
          <Plus className="h-4 w-4 mr-2" />
          Browse Gallery
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}