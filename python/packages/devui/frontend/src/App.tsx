/**
 * DevUI App - Minimal orchestrator for agent/workflow interactions
 * Features: Entity selection, layout management, debug coordination
 */

import { useState, useEffect, useCallback } from "react";
import { AppHeader } from "@/components/shared/app-header";
import { DebugPanel } from "@/components/shared/debug-panel";
import { SettingsModal } from "@/components/shared/settings-modal";
import { GalleryView } from "@/components/gallery";
import { AgentView } from "@/components/agent/agent-view";
import { WorkflowView } from "@/components/workflow/workflow-view";
import { LoadingState } from "@/components/ui/loading-state";
import { Toast } from "@/components/ui/toast";
import { apiClient } from "@/services/api";
import { PanelRightOpen, ChevronDown, ServerOff } from "lucide-react";
import type { SampleEntity } from "@/data/gallery";
import type {
  AgentInfo,
  WorkflowInfo,
  AppState,
  ExtendedResponseStreamEvent,
} from "@/types";
import { Button } from "./components/ui/button";

export default function App() {
  const [appState, setAppState] = useState<AppState>({
    agents: [],
    workflows: [],
    isLoading: true,
  });

  const [debugEvents, setDebugEvents] = useState<ExtendedResponseStreamEvent[]>(
    []
  );
  const [showDebugPanel, setShowDebugPanel] = useState(() => {
    const saved = localStorage.getItem("showDebugPanel");
    return saved !== null ? saved === "true" : true;
  });
  const [debugPanelWidth, setDebugPanelWidth] = useState(() => {
    const savedWidth = localStorage.getItem("debugPanelWidth");
    return savedWidth ? parseInt(savedWidth, 10) : 320;
  });
  const [isResizing, setIsResizing] = useState(false);
  const [showAboutModal, setShowAboutModal] = useState(false);
  const [showGallery, setShowGallery] = useState(false);
  const [addingEntityId, setAddingEntityId] = useState<string | null>(null);
  const [errorEntityId, setErrorEntityId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showEntityNotFoundToast, setShowEntityNotFoundToast] = useState(false);

  // Initialize app - load agents and workflows
  useEffect(() => {
    const loadData = async () => {
      try {
        const [agents, workflows] = await Promise.all([
          apiClient.getAgents(),
          apiClient.getWorkflows(),
        ]);

        // Check if there's an entity_id in the URL
        const urlParams = new URLSearchParams(window.location.search);
        const entityId = urlParams.get("entity_id");

        let selectedAgent: AgentInfo | WorkflowInfo | undefined;

        // Try to find entity from URL parameter first
        if (entityId) {
          selectedAgent =
            agents.find((a) => a.id === entityId) ||
            workflows.find((w) => w.id === entityId);

          // If entity not found but was requested, show notification
          if (!selectedAgent) {
            setShowEntityNotFoundToast(true);
          }
        }

        // Fallback to first available entity if URL entity not found
        if (!selectedAgent) {
          selectedAgent =
            agents.length > 0
              ? agents[0]
              : workflows.length > 0
              ? workflows[0]
              : undefined;

          // Update URL to match actual selected entity (or clear if none)
          if (selectedAgent) {
            const url = new URL(window.location.href);
            url.searchParams.set("entity_id", selectedAgent.id);
            window.history.replaceState({}, "", url);
          } else {
            // Clear entity_id if no entities available
            const url = new URL(window.location.href);
            url.searchParams.delete("entity_id");
            window.history.replaceState({}, "", url);
          }
        }

        setAppState((prev) => ({
          ...prev,
          agents,
          workflows,
          selectedAgent,
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

  // Save debug panel state to localStorage
  useEffect(() => {
    localStorage.setItem("showDebugPanel", showDebugPanel.toString());
  }, [showDebugPanel]);

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

  // Handle entity selection
  const handleEntitySelect = useCallback((item: AgentInfo | WorkflowInfo) => {
    setAppState((prev) => ({
      ...prev,
      selectedAgent: item,
      currentThread: undefined,
    }));

    // Update URL with selected entity ID
    const url = new URL(window.location.href);
    url.searchParams.set("entity_id", item.id);
    window.history.pushState({}, "", url);

    // Clear debug events when switching entities
    setDebugEvents([]);
  }, []);

  // Handle debug events from active view
  const handleDebugEvent = useCallback(
    (event: ExtendedResponseStreamEvent | "clear") => {
      if (event === "clear") {
        setDebugEvents([]);
      } else {
        setDebugEvents((prev) => [...prev, event]);
      }
    },
    []
  );

  // Handle adding sample entity
  const handleAddSample = useCallback(async (sample: SampleEntity) => {
    setAddingEntityId(sample.id);
    setErrorEntityId(null);
    setErrorMessage(null);

    try {
      // Call backend to fetch and add entity
      const newEntity = await apiClient.addEntity(sample.url, {
        source: "remote_gallery",
        originalUrl: sample.url,
        sampleId: sample.id,
      });

      // Convert backend entity to frontend format
      const convertedEntity = {
        id: newEntity.id,
        name: newEntity.name,
        description: newEntity.description,
        type: newEntity.type,
        source:
          (newEntity.source as "directory" | "in_memory" | "remote_gallery") ||
          "remote_gallery",
        has_env: false,
        module_path: undefined,
      };

      // Update app state
      if (newEntity.type === "agent") {
        const agentEntity = {
          ...convertedEntity,
          tools: (newEntity.tools || []).map((tool) =>
            typeof tool === "string" ? tool : JSON.stringify(tool)
          ),
        } as AgentInfo;

        setAppState((prev) => ({
          ...prev,
          agents: [...prev.agents, agentEntity],
          selectedAgent: agentEntity,
        }));

        // Update URL with new entity
        const url = new URL(window.location.href);
        url.searchParams.set("entity_id", agentEntity.id);
        window.history.pushState({}, "", url);
      } else {
        const workflowEntity = {
          ...convertedEntity,
          executors: (newEntity.tools || []).map((tool) =>
            typeof tool === "string" ? tool : JSON.stringify(tool)
          ),
          input_schema: { type: "string" },
          input_type_name: "Input",
          start_executor_id:
            newEntity.tools && newEntity.tools.length > 0
              ? typeof newEntity.tools[0] === "string"
                ? newEntity.tools[0]
                : JSON.stringify(newEntity.tools[0])
              : "unknown",
        } as WorkflowInfo;

        setAppState((prev) => ({
          ...prev,
          workflows: [...prev.workflows, workflowEntity],
          selectedAgent: workflowEntity,
        }));

        // Update URL with new entity
        const url = new URL(window.location.href);
        url.searchParams.set("entity_id", workflowEntity.id);
        window.history.pushState({}, "", url);
      }

      // Close gallery and clear debug events
      setShowGallery(false);
      setDebugEvents([]);
    } catch (error) {
      const errMsg =
        error instanceof Error ? error.message : "Failed to add sample entity";
      console.error("Failed to add sample entity:", errMsg);
      setErrorEntityId(sample.id);
      setErrorMessage(errMsg);
    } finally {
      setAddingEntityId(null);
    }
  }, []);

  const handleClearError = useCallback(() => {
    setErrorEntityId(null);
    setErrorMessage(null);
  }, []);

  // Handle removing entity
  const handleRemoveEntity = useCallback(
    async (entityId: string) => {
      try {
        await apiClient.removeEntity(entityId);

        // Update app state
        setAppState((prev) => ({
          ...prev,
          agents: prev.agents.filter((a) => a.id !== entityId),
          workflows: prev.workflows.filter((w) => w.id !== entityId),
          selectedAgent:
            prev.selectedAgent?.id === entityId
              ? undefined
              : prev.selectedAgent,
        }));

        // Update URL - clear entity_id if we removed the selected entity
        if (appState.selectedAgent?.id === entityId) {
          const url = new URL(window.location.href);
          url.searchParams.delete("entity_id");
          window.history.pushState({}, "", url);
          setDebugEvents([]);
        }
      } catch (error) {
        console.error("Failed to remove entity:", error);
      }
    },
    [appState.selectedAgent?.id]
  );

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
          onRemove={handleRemoveEntity}
          isLoading={false}
          onSettingsClick={() => setShowAboutModal(true)}
        />

        {/* Error Content */}
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="text-center space-y-6 max-w-2xl">
            {/* Icon */}
            <div className="flex justify-center">
              <div className="rounded-full bg-muted p-4 animate-pulse">
                <ServerOff className="h-12 w-12 text-muted-foreground" />
              </div>
            </div>

            {/* Heading */}
            <div className="space-y-2">
              <h2 className="text-2xl font-semibold text-foreground">
                Can't Connect to Backend
              </h2>
              <p className="text-muted-foreground text-base">
                No worries! Just start the DevUI backend server and you'll be
                good to go.
              </p>
            </div>

            {/* Command Instructions */}
            <div className="space-y-3">
              <div className="text-left bg-muted/50 rounded-lg p-4 space-y-3">
                <p className="text-sm font-medium text-foreground">
                  Start the backend:
                </p>
                <code className="block bg-background px-3 py-2 rounded border text-sm font-mono text-foreground">
                  devui ./agents --port 8080
                </code>
                <p className="text-xs text-muted-foreground">
                  Or launch programmatically with{" "}
                  <code className="text-xs">serve(entities=[agent])</code>
                </p>
              </div>

              <p className="text-xs text-muted-foreground">
                Default:{" "}
                <span className="font-mono">http://localhost:8080</span>
              </p>
            </div>

            {/* Error Details (Collapsible) */}
            {appState.error && (
              <details className="text-left group">
                <summary className="text-sm text-muted-foreground cursor-pointer hover:text-foreground flex items-center gap-2">
                  <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" />
                  Error details
                </summary>
                <p className="mt-2 text-xs text-muted-foreground font-mono bg-muted/30 p-3 rounded border">
                  {appState.error}
                </p>
              </details>
            )}

            {/* Retry Button */}
            <Button
              onClick={() => window.location.reload()}
              variant="default"
              className="mt-2"
            >
              Retry Connection
            </Button>
          </div>
        </div>

        {/* Settings Modal */}
        <SettingsModal open={showAboutModal} onOpenChange={setShowAboutModal} />
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
        onRemove={handleRemoveEntity}
        onBrowseGallery={() => setShowGallery(true)}
        isLoading={appState.isLoading}
        onSettingsClick={() => setShowAboutModal(true)}
      />

      {/* Main Content - Split Panel or Gallery */}
      <div className="flex flex-1 overflow-hidden">
        {showGallery ? (
          // Show gallery full screen (w-full ensures it takes entire width)
          <div className="flex-1 w-full">
            <GalleryView
              variant="route"
              onAdd={handleAddSample}
              addingEntityId={addingEntityId}
              errorEntityId={errorEntityId}
              errorMessage={errorMessage}
              onClearError={handleClearError}
              onClose={() => setShowGallery(false)}
              hasExistingEntities={
                appState.agents.length > 0 || appState.workflows.length > 0
              }
            />
          </div>
        ) : appState.agents.length === 0 && appState.workflows.length === 0 ? (
          // Empty state - show gallery inline (full width, no debug panel)
          <GalleryView
            variant="inline"
            onAdd={handleAddSample}
            addingEntityId={addingEntityId}
            errorEntityId={errorEntityId}
            errorMessage={errorMessage}
            onClearError={handleClearError}
          />
        ) : (
          <>
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

            {showDebugPanel ? (
              <>
                {/* Resize Handle */}
                <div
                  className={`w-1 cursor-col-resize flex-shrink-0 relative group transition-colors duration-200 ease-in-out ${
                    isResizing ? "bg-primary/40" : "bg-border hover:bg-primary/20"
                  }`}
                  onMouseDown={handleMouseDown}
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

                {/* Right Panel - Debug */}
                <div
                  className="flex-shrink-0"
                  style={{ width: `${debugPanelWidth}px` }}
                >
                  <DebugPanel
                    events={debugEvents}
                    isStreaming={false} // Each view manages its own streaming state
                    onClose={() => setShowDebugPanel(false)}
                  />
                </div>
              </>
            ) : (
              /* Button to reopen when closed */
              <div className="flex-shrink-0">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowDebugPanel(true)}
                  className="h-full w-10 rounded-none border-l"
                  title="Show debug panel"
                >
                  <PanelRightOpen className="h-4 w-4" />
                </Button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Settings Modal */}
      <SettingsModal open={showAboutModal} onOpenChange={setShowAboutModal} />

      {/* Toast Notification */}
      {showEntityNotFoundToast && (
        <Toast
          message="Entity not found. Showing first available entity instead."
          type="info"
          onClose={() => setShowEntityNotFoundToast(false)}
        />
      )}
    </div>
  );
}
