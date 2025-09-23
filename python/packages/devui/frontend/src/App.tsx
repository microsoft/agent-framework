/**
 * DevUI App - Minimal orchestrator for agent/workflow interactions
 * Features: Entity selection, layout management, debug coordination
 */

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { AppHeader } from "@/components/shared/app-header";
import { DebugPanel } from "@/components/shared/debug-panel";
import { AboutModal } from "@/components/shared/about-modal";
import { AgentView } from "@/components/agent/agent-view";
import { WorkflowView } from "@/components/workflow/workflow-view";
import { LoadingState } from "@/components/ui/loading-state";
import { apiClient } from "@/services/api";
import { ChevronLeft } from "lucide-react";
import type {
  AgentInfo,
  WorkflowInfo,
  AppState,
  ExtendedResponseStreamEvent,
} from "@/types";

export default function App() {
  const [appState, setAppState] = useState<AppState>({
    agents: [],
    workflows: [],
    isLoading: true,
  });

  const [debugEvents, setDebugEvents] = useState<ExtendedResponseStreamEvent[]>(
    []
  );
  const [debugPanelOpen, setDebugPanelOpen] = useState(true);
  const [debugPanelWidth, setDebugPanelWidth] = useState(() => {
    // Initialize from localStorage or default to 320
    const savedWidth = localStorage.getItem("debugPanelWidth");
    return savedWidth ? parseInt(savedWidth, 10) : 320;
  });
  const [isResizing, setIsResizing] = useState(false);
  const [showAboutModal, setShowAboutModal] = useState(false);

  // Initialize app - load agents and workflows
  useEffect(() => {
    const loadData = async () => {
      try {
        // Load agents and workflows in parallel
        const [agents, workflows] = await Promise.all([
          apiClient.getAgents(),
          apiClient.getWorkflows(),
        ]);

        setAppState((prev) => ({
          ...prev,
          agents,
          workflows,
          selectedAgent:
            agents.length > 0
              ? agents[0]
              : workflows.length > 0
              ? workflows[0]
              : undefined,
          isLoading: false,
        }));
      } catch (error) {
        console.error("Failed to load agents/workflows:", error);
        setAppState((prev) => ({
          ...prev,
          error: error instanceof Error ? error.message : "Failed to load data",
          isLoading: false,
        }));
      }
    };

    loadData();
  }, []);

  // Save debug panel width to localStorage
  useEffect(() => {
    localStorage.setItem("debugPanelWidth", debugPanelWidth.toString());
  }, [debugPanelWidth]);

  // Handle resize drag
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      setIsResizing(true);

      const startX = e.clientX;
      const startWidth = debugPanelWidth;

      const handleMouseMove = (e: MouseEvent) => {
        const deltaX = startX - e.clientX; // Subtract because we're dragging from right
        const newWidth = Math.max(
          200,
          Math.min(window.innerWidth * 0.5, startWidth + deltaX)
        );
        setDebugPanelWidth(newWidth);
      };

      const handleMouseUp = () => {
        setIsResizing(false);
        document.removeEventListener("mousemove", handleMouseMove);
        document.removeEventListener("mouseup", handleMouseUp);
      };

      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
    },
    [debugPanelWidth]
  );

  // Handle double-click to collapse
  const handleDoubleClick = useCallback(() => {
    setDebugPanelOpen(false);
  }, []);

  // Handle entity selection
  const handleEntitySelect = useCallback((item: AgentInfo | WorkflowInfo) => {
    setAppState((prev) => ({
      ...prev,
      selectedAgent: item,
      currentThread: undefined,
    }));

    // Clear debug events when switching entities
    setDebugEvents([]);
  }, []);

  // Handle debug events from active view
  const handleDebugEvent = useCallback((event: ExtendedResponseStreamEvent | 'clear') => {
    if (event === 'clear') {
      setDebugEvents([]);
    } else {
      setDebugEvents((prev) => [...prev, event]);
    }
  }, []);

  // Show loading state while initializing
  if (appState.isLoading) {
    return (
      <div className="h-screen flex flex-col bg-background">
        {/* Top Bar - Skeleton */}
        <header className="flex h-14 items-center gap-4 border-b px-4">
          <div className="w-64 h-9 bg-muted animate-pulse rounded-md" />
          <div className="flex items-center gap-2 ml-auto">
            <div className="w-8 h-8 bg-muted animate-pulse rounded-md" />
            <div className="w-8 h-8 bg-muted animate-pulse rounded-md" />
          </div>
        </header>

        {/* Loading Content */}
        <LoadingState
          message="Initializing DevUI..."
          description="Loading agents and workflows from your configuration"
          fullPage={true}
        />
      </div>
    );
  }

  // Show error state if loading failed
  if (appState.error) {
    return (
      <div className="h-screen flex flex-col bg-background">
        <AppHeader
          agents={[]}
          workflows={[]}
          selectedItem={undefined}
          onSelect={() => {}}
          isLoading={false}
        />

        {/* Error Content */}
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-4 max-w-md">
            <div className="text-destructive text-lg font-medium">
              Failed to load entities
            </div>
            <p className="text-muted-foreground text-sm">{appState.error}</p>
            <Button onClick={() => window.location.reload()} variant="outline">
              Retry
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // Show empty state if no agents or workflows are available
  if (
    !appState.isLoading &&
    appState.agents.length === 0 &&
    appState.workflows.length === 0
  ) {
    return (
      <div className="h-screen flex flex-col bg-background">
        <AppHeader
          agents={[]}
          workflows={[]}
          selectedItem={undefined}
          onSelect={() => {}}
          isLoading={false}
        />

        {/* Empty State Content */}
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-4 max-w-md">
            <div className="text-lg font-medium">No entities configured</div>
            <p className="text-muted-foreground text-sm">
              No agents or workflows were found in your configuration. Please
              check your setup and ensure entities are properly configured.
            </p>
            <Button onClick={() => window.location.reload()} variant="outline">
              Retry
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-background max-h-screen">
      <AppHeader
        agents={appState.agents}
        workflows={appState.workflows}
        selectedItem={appState.selectedAgent}
        onSelect={handleEntitySelect}
        isLoading={appState.isLoading}
        onSettingsClick={() => setShowAboutModal(true)}
      />

      {/* Main Content - Split Panel */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Panel - Main View */}
        <div className="flex-1 min-w-0">
          {appState.selectedAgent ? (
            appState.selectedAgent.type === "agent" ? (
              <AgentView
                selectedAgent={appState.selectedAgent as AgentInfo}
                onDebugEvent={handleDebugEvent}
              />
            ) : (
              <WorkflowView
                selectedWorkflow={appState.selectedAgent as WorkflowInfo}
                onDebugEvent={handleDebugEvent}
              />
            )
          ) : (
            <div className="flex-1 flex items-center justify-center text-muted-foreground">
              Select an agent or workflow to get started.
            </div>
          )}
        </div>

        {/* Resize Handle */}
        {debugPanelOpen && (
          <div
            className={`w-1 cursor-col-resize flex-shrink-0 relative group transition-colors duration-200 ease-in-out ${
              isResizing ? "bg-primary/40" : "bg-border hover:bg-primary/20"
            }`}
            onMouseDown={handleMouseDown}
            onDoubleClick={handleDoubleClick}
          >
            <div className="absolute inset-y-0 -left-2 -right-2 flex items-center justify-center">
              <div
                className={`h-12 w-1 rounded-full transition-all duration-200 ease-in-out ${
                  isResizing
                    ? "bg-primary shadow-lg shadow-primary/25"
                    : "bg-primary/30 group-hover:bg-primary group-hover:shadow-md group-hover:shadow-primary/20"
                }`}
              ></div>
            </div>
          </div>
        )}

        {/* Button to reopen when closed */}
        {!debugPanelOpen && (
          <div className="flex-shrink-0">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setDebugPanelOpen(true)}
              className="h-full w-8 rounded-none border-l"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
          </div>
        )}

        {/* Right Panel - Debug */}
        {debugPanelOpen && (
          <div
            className="flex-shrink-0"
            style={{ width: `${debugPanelWidth}px` }}
          >
            <DebugPanel
              events={debugEvents}
              isStreaming={false} // Each view manages its own streaming state
            />
          </div>
        )}
      </div>

      {/* About Modal */}
      <AboutModal
        open={showAboutModal}
        onOpenChange={setShowAboutModal}
      />
    </div>
  );
}
