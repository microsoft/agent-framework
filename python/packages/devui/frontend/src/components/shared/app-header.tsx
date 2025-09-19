/**
 * AppHeader - Global application header
 * Features: Entity selection, global settings, theme toggle
 */

import { Button } from "@/components/ui/button";
import { EntitySelector } from "@/components/shared/entity-selector";
import { ModeToggle } from "@/components/mode-toggle";
import { Settings } from "lucide-react";
import type { AgentInfo, WorkflowInfo } from "@/types";

interface AppHeaderProps {
  agents: AgentInfo[];
  workflows: WorkflowInfo[];
  selectedItem?: AgentInfo | WorkflowInfo;
  onSelect: (item: AgentInfo | WorkflowInfo) => void;
  isLoading?: boolean;
  onSettingsClick?: () => void;
}

export function AppHeader({
  agents,
  workflows,
  selectedItem,
  onSelect,
  isLoading = false,
  onSettingsClick,
}: AppHeaderProps) {
  return (
    <header className="flex h-14 items-center gap-4 border-b px-4">
      <div className="font-semibold">Dev UI</div>
      <EntitySelector
        agents={agents}
        workflows={workflows}
        selectedItem={selectedItem}
        onSelect={onSelect}
        isLoading={isLoading}
      />

      <div className="flex items-center gap-2 ml-auto">
        <ModeToggle />
        <Button variant="ghost" size="sm" onClick={onSettingsClick}>
          <Settings className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}