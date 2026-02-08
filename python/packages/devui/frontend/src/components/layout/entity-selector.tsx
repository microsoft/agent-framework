/**
 * EntitySelector - Dropdown for selecting agents/workflows
 * Features: Loading states, descriptions, lazy loading indicators
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
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { ChevronDown, Bot, Workflow, Plus, Loader2 } from "lucide-react";
import type { AgentInfo, WorkflowInfo } from "@/types";

interface EntitySelectorProps {
  agents: AgentInfo[];
  workflows: WorkflowInfo[];
  entities?: (AgentInfo | WorkflowInfo)[];  // Full list in backend order
  selectedItem?: AgentInfo | WorkflowInfo;
  onSelect: (item: AgentInfo | WorkflowInfo) => void;
  onBrowseGallery?: () => void;
  isLoading?: boolean;
}

const getTypeIcon = (type: "agent" | "workflow") => {
  return type === "workflow" ? Workflow : Bot;
};

export function EntitySelector({
  agents,
  workflows,
  entities,
  selectedItem,
  onSelect,
  onBrowseGallery,
  isLoading = false,
}: EntitySelectorProps) {
  const [open, setOpen] = useState(false);

  // Use entities if provided (preserves backend order), otherwise combine agents and workflows
  const allItems = entities || [...agents, ...workflows];

  const handleSelect = (item: AgentInfo | WorkflowInfo) => {
    onSelect(item);
    setOpen(false);
  };

  const TypeIcon = selectedItem ? getTypeIcon(selectedItem.type) : Bot;
  const displayName = selectedItem?.name || selectedItem?.id || "Select Agent or Workflow";
  const isLoaded = selectedItem?.metadata?.lazy_loaded !== false;

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
                {selectedItem && !isLoaded && (
                  <Loader2 className="h-3 w-3 text-muted-foreground animate-spin ml-auto flex-shrink-0" />
                )}
              </div>
              <ChevronDown className="h-4 w-4 opacity-50" />
            </>
          )}
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent className="w-80 font-mono">
        {/* Show items in backend order but with type grouping for clarity */}
        {(() => {
          // Group items by type while preserving order within each group
          const workflowItems = allItems.filter(item => item.type === "workflow");
          const agentItems = allItems.filter(item => item.type === "agent");

          // Determine which type appears first in backend order
          const firstItemType = allItems[0]?.type;

          return (
            <>
              {/* Show workflows first if they appear first, otherwise agents */}
              {firstItemType === "workflow" && workflowItems.length > 0 && (
                <>
                  <DropdownMenuLabel className="flex items-center gap-2">
                    <Workflow className="h-4 w-4" />
                    Workflows ({workflowItems.length})
                  </DropdownMenuLabel>
                  {workflowItems.map((item) => {
                    const isLoaded = item.metadata?.lazy_loaded !== false;
                    return (
                      <DropdownMenuItem
                        key={item.id}
                        className="cursor-pointer group"
                        onClick={() => handleSelect(item)}
                      >
                        <div className="flex items-center gap-2 min-w-0 flex-1">
                          <Workflow className="h-4 w-4 flex-shrink-0" />
                          <div className="min-w-0 flex-1">
                            <span className="truncate font-medium block">
                              {item.name || item.id}
                            </span>
                            {isLoaded && item.description && (
                              <div className="text-xs text-muted-foreground line-clamp-2">
                                {item.description}
                              </div>
                            )}
                          </div>
                        </div>
                      </DropdownMenuItem>
                    );
                  })}
                </>
              )}

              {/* Separator if both types exist */}
              {workflowItems.length > 0 && agentItems.length > 0 && <DropdownMenuSeparator />}

              {/* Agents section */}
              {agentItems.length > 0 && (
                <>
                  <DropdownMenuLabel className="flex items-center gap-2">
                    <Bot className="h-4 w-4" />
                    Agents ({agentItems.length})
                  </DropdownMenuLabel>
                  {agentItems.map((item) => {
                    const isLoaded = item.metadata?.lazy_loaded !== false;
                    return (
                      <DropdownMenuItem
                        key={item.id}
                        className="cursor-pointer group"
                        onClick={() => handleSelect(item)}
                      >
                        <div className="flex items-center gap-2 min-w-0 flex-1">
                          <Bot className="h-4 w-4 flex-shrink-0" />
                          <div className="min-w-0 flex-1">
                            <span className="truncate font-medium block">
                              {item.name || item.id}
                            </span>
                            {isLoaded && item.description && (
                              <div className="text-xs text-muted-foreground line-clamp-2">
                                {item.description}
                              </div>
                            )}
                          </div>
                        </div>
                      </DropdownMenuItem>
                    );
                  })}
                </>
              )}

              {/* Show workflows last if agents appear first */}
              {firstItemType === "agent" && workflowItems.length > 0 && (
                <>
                  {agentItems.length > 0 && <DropdownMenuSeparator />}
                  <DropdownMenuLabel className="flex items-center gap-2">
                    <Workflow className="h-4 w-4" />
                    Workflows ({workflowItems.length})
                  </DropdownMenuLabel>
                  {workflowItems.map((item) => {
                    const isLoaded = item.metadata?.lazy_loaded !== false;
                    return (
                      <DropdownMenuItem
                        key={item.id}
                        className="cursor-pointer group"
                        onClick={() => handleSelect(item)}
                      >
                        <div className="flex items-center gap-2 min-w-0 flex-1">
                          <Workflow className="h-4 w-4 flex-shrink-0" />
                          <div className="min-w-0 flex-1">
                            <span className="truncate font-medium block">
                              {item.name || item.id}
                            </span>
                            {isLoaded && item.description && (
                              <div className="text-xs text-muted-foreground line-clamp-2">
                                {item.description}
                              </div>
                            )}
                          </div>
                        </div>
                      </DropdownMenuItem>
                    );
                  })}
                </>
              )}
            </>
          );
        })()}

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