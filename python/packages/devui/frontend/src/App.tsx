/**
 * DevUI App - Minimal orchestrator for agent/workflow interactions
 * Features: Entity selection, layout management, debug coordination
 */

import { useEffect, useCallback, useState } from "react";
import { AppHeader, DebugPanel, SettingsModal, DeploymentModal } from "@/components/layout";
import { GalleryView } from "@/components/features/gallery";
import { AgentView } from "@/components/features/agent";
import { WorkflowView } from "@/components/features/workflow";
import { Toast, ToastContainer } from "@/components/ui/toast";
import { apiClient } from "@/services/api";
import { PanelRightOpen, ChevronLeft, ChevronDown, ServerOff, Rocket, Lock } from "lucide-react";
import type {
  AgentInfo,
  WorkflowInfo,
  ExtendedResponseStreamEvent,
} from "@/types";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { useDevUIStore } from "@/stores";

export default function App() {
  // Local state for auth handling
  const [authRequired, setAuthRequired] = useState(false);
  const [authToken, setAuthToken] = useState("");
  const [isTestingToken, setIsTestingToken] = useState(false);
  const [authError, setAuthError] = useState("");

  // Entity state from Zustand
  const agents = useDevUIStore((state) => state.agents);
  const workflows = useDevUIStore((state) => state.workflows);
  const entities = useDevUIStore((state) => state.entities);
  const selectedAgent = useDevUIStore((state) => state.selectedAgent);
  const azureDeploymentEnabled = useDevUIStore((state) => state.azureDeploymentEnabled);
  const isLoadingEntities = useDevUIStore((state) => state.isLoadingEntities);
  const entityError = useDevUIStore((state) => state.entityError);

  // OpenAI proxy mode
  const oaiMode = useDevUIStore((state) => state.oaiMode);

  // UI mode
  const uiMode = useDevUIStore((state) => state.uiMode);

  // Entity actions
  const setAgents = useDevUIStore((state) => state.setAgents);
  const setWorkflows = useDevUIStore((state) => state.setWorkflows);
  const setEntities = useDevUIStore((state) => state.setEntities);
  const selectEntity = useDevUIStore((state) => state.selectEntity);
  const updateAgent = useDevUIStore((state) => state.updateAgent);
  const updateWorkflow = useDevUIStore((state) => state.updateWorkflow);
  const setIsLoadingEntities = useDevUIStore((state) => state.setIsLoadingEntities);
  const setEntityError = useDevUIStore((state) => state.setEntityError);

  // UI state from Zustand
  const showDebugPanel = useDevUIStore((state) => state.showDebugPanel);
  const debugPanelMinimized = useDevUIStore((state) => state.debugPanelMinimized);
  const debugPanelWidth = useDevUIStore((state) => state.debugPanelWidth);
  const debugEvents = useDevUIStore((state) => state.debugEvents);
  const isResizing = useDevUIStore((state) => state.isResizing);

  // UI actions
  const setShowDebugPanel = useDevUIStore((state) => state.setShowDebugPanel);
  const setDebugPanelMinimized = useDevUIStore((state) => state.setDebugPanelMinimized);
  const setDebugPanelWidth = useDevUIStore((state) => state.setDebugPanelWidth);
  const addDebugEvent = useDevUIStore((state) => state.addDebugEvent);
  const clearDebugEvents = useDevUIStore((state) => state.clearDebugEvents);
  const setIsResizing = useDevUIStore((state) => state.setIsResizing);

  // Modal state
  const showAboutModal = useDevUIStore((state) => state.showAboutModal);
  const showGallery = useDevUIStore((state) => state.showGallery);
  const showDeployModal = useDevUIStore((state) => state.showDeployModal);
  const showEntityNotFoundToast = useDevUIStore((state) => state.showEntityNotFoundToast);

  // Modal actions
  const setShowAboutModal = useDevUIStore((state) => state.setShowAboutModal);
  const setShowGallery = useDevUIStore((state) => state.setShowGallery);
  const setShowDeployModal = useDevUIStore((state) => state.setShowDeployModal);
  const setShowEntityNotFoundToast = useDevUIStore((state) => state.setShowEntityNotFoundToast);

  // Toast state and actions
  const toasts = useDevUIStore((state) => state.toasts);
  const removeToast = useDevUIStore((state) => state.removeToast);

  // Initialize app - load agents and workflows
  useEffect(() => {
    const loadData = async () => {
      try {
        // Fetch server metadata first (ui_mode, capabilities, auth status)
        const meta = await apiClient.getMeta();

        // Check if auth is required
        if (meta.auth_required) {
          setAuthRequired(true);

          // If we don't have a token, stop here and show auth UI
          if (!apiClient.getAuthToken()) {
            setEntityError("UNAUTHORIZED");
            setIsLoadingEntities(false);
            return;
          }
        }

        useDevUIStore.getState().setServerMeta({
          uiMode: meta.ui_mode,
          runtime: meta.runtime,
          capabilities: meta.capabilities,
          authRequired: meta.auth_required,
        });

        // Single API call instead of two parallel calls to same endpoint
        const { entities: allEntities, agents: agentList, workflows: workflowList } = await apiClient.getEntities();

        setEntities(allEntities);
        setAgents(agentList);
        setWorkflows(workflowList);

        // Check if there's an entity_id in the URL
        const urlParams = new URLSearchParams(window.location.search);
        const entityId = urlParams.get("entity_id");

        let selectedEntity: AgentInfo | WorkflowInfo | undefined;

        // Try to find entity from URL parameter first
        if (entityId) {
          selectedEntity = allEntities.find((e) => e.id === entityId);

          // If entity not found but was requested, show notification
          if (!selectedEntity) {
            setShowEntityNotFoundToast(true);
          }
        }

        // Fallback to first available entity if URL entity not found
        if (!selectedEntity) {
          // Use the first entity from the backend's original order
          // This respects the backend's intended display order
          selectedEntity = allEntities.length > 0 ? allEntities[0] : undefined;

          // Update URL to match actual selected entity (or clear if none)
          if (selectedEntity) {
            const url = new URL(window.location.href);
            url.searchParams.set("entity_id", selectedEntity.id);
            window.history.replaceState({}, "", url);
          } else {
            // Clear entity_id if no entities available
            const url = new URL(window.location.href);
            url.searchParams.delete("entity_id");
            window.history.replaceState({}, "", url);
          }
        }

        if (selectedEntity) {
          selectEntity(selectedEntity);

          // Load full info for the first entity immediately
          if (selectedEntity.metadata?.lazy_loaded === false) {
            try {
              if (selectedEntity.type === "agent") {
                const fullAgent = await apiClient.getAgentInfo(
                  selectedEntity.id
                );
                updateAgent(fullAgent);
              } else {
                const fullWorkflow = await apiClient.getWorkflowInfo(
                  selectedEntity.id
                );
                updateWorkflow(fullWorkflow);
              }
            } catch (error) {
              console.error(
                `Failed to load full info for first entity ${selectedEntity.id}:`,
                error
              );
            }
          }
        }

        setIsLoadingEntities(false);
      } catch (error) {
        console.error("Failed to load agents/workflows:", error);
        const errorMessage = error instanceof Error ? error.message : "Failed to load data";

        // Check if this is an auth error
        if (errorMessage === "UNAUTHORIZED") {
          setAuthRequired(true);
        }

        setEntityError(errorMessage);
        setIsLoadingEntities(false);
      }
    };

    loadData();
  }, [setAgents, setWorkflows, selectEntity, updateAgent, updateWorkflow, setIsLoadingEntities, setEntityError, setShowEntityNotFoundToast]);

  // Handle auth token submission
  const handleAuthTokenSubmit = useCallback(async () => {
    if (!authToken.trim()) return;

    setIsTestingToken(true);
    setAuthError("");

    try {
      // Set token in API client (stores in localStorage)
      apiClient.setAuthToken(authToken.trim());

      // Test the token with an actual PROTECTED endpoint (not /meta which is public)
      await apiClient.getEntities();

      // If successful, reload to initialize with new token
      window.location.reload();
    } catch (error) {
      // Token is invalid - clear it and show error
      apiClient.clearAuthToken();
      setIsTestingToken(false);

      const errorMsg = error instanceof Error ? error.message : "Unknown error";
      if (errorMsg === "UNAUTHORIZED") {
        setAuthError("Invalid token. Please check and try again.");
      } else {
        setAuthError(`Failed to connect: ${errorMsg}`);
      }
    }
  }, [authToken]);

  // Auto-switch from workflow to agent when OpenAI proxy mode is enabled
  useEffect(() => {
    if (oaiMode.enabled && selectedAgent?.type === "workflow") {
      // Workflows don't work with OpenAI proxy - switch to first available agent
      const firstAgent = agents[0];
      if (firstAgent) {
        selectEntity(firstAgent);
      }
    }
  }, [oaiMode.enabled, selectedAgent, agents, selectEntity]);

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

  // Handle entity selection - uses Zustand's selectEntity which handles ALL side effects
  const handleEntitySelect = useCallback(
    async (item: AgentInfo | WorkflowInfo) => {
      selectEntity(item); // This clears conversation state, debug events, and updates URL!

      // If entity is sparse (not fully loaded), load full details
      if (item.metadata?.lazy_loaded === false) {
        try {
          if (item.type === "agent") {
            const fullAgent = await apiClient.getAgentInfo(item.id);
            updateAgent(fullAgent);
          } else {
            const fullWorkflow = await apiClient.getWorkflowInfo(item.id);
            updateWorkflow(fullWorkflow);
          }
        } catch (error) {
          console.error(`Failed to load full info for ${item.id}:`, error);
        }
      }
    },
    [selectEntity, updateAgent, updateWorkflow]
  );

  // Handle debug events from active view
  const handleDebugEvent = useCallback(
    (event: ExtendedResponseStreamEvent | "clear") => {
      if (event === "clear") {
        clearDebugEvents();
      } else {
        addDebugEvent(event);
      }
    },
    [addDebugEvent, clearDebugEvents]
  );

  // Show loading state while initializing
  if (isLoadingEntities) {
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
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="text-lg font-medium">Initializing DevUI...</div>
            <div className="text-sm text-muted-foreground mt-2">Loading agents and workflows from your configuration</div>
          </div>
        </div>
      </div>
    );
  }

  // Show error state if loading failed
  if (entityError) {
    const currentBackendUrl = apiClient.getBaseUrl();
    const isAuthError = entityError === "UNAUTHORIZED" || authRequired;

    return (
      <div className="h-screen flex flex-col bg-background">
        <AppHeader
          agents={[]}
          workflows={[]}
          entities={[]}
          selectedItem={undefined}
          onSelect={() => {}}
          isLoading={false}
          onSettingsClick={() => setShowAboutModal(true)}
        />

        {/* Error Content */}
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="text-center space-y-6 max-w-2xl">
            {/* Icon */}
            <div className="flex justify-center">
              <div className="rounded-full bg-muted p-4 animate-pulse">
                {isAuthError ? (
                  <Lock className="h-12 w-12 text-muted-foreground" />
                ) : (
                  <ServerOff className="h-12 w-12 text-muted-foreground" />
                )}
              </div>
            </div>

            {/* Heading */}
            <div className="space-y-2">
              <h2 className="text-2xl font-semibold text-foreground">
                {isAuthError ? "Authentication Required" : "Can't Connect to Backend"}
              </h2>
              <p className="text-muted-foreground text-base">
                {isAuthError
                  ? "This backend requires a bearer token to access."
                  : "No worries! Just start the DevUI backend server and you'll be good to go."}
              </p>
            </div>

            {/* Auth Input or Command Instructions */}
            {isAuthError ? (
              <div className="space-y-4">
                <div className="text-left bg-muted/50 rounded-lg p-4 space-y-3">
                  <p className="text-sm font-medium text-foreground">
                    Enter Authentication Token
                  </p>
                  <Input
                    type="password"
                    placeholder="Paste token from server logs"
                    value={authToken}
                    onChange={(e) => setAuthToken(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !isTestingToken) {
                        handleAuthTokenSubmit();
                      }
                    }}
                    disabled={isTestingToken}
                    className="font-mono text-sm"
                  />
                  <Button
                    onClick={handleAuthTokenSubmit}
                    disabled={!authToken.trim() || isTestingToken}
                    className="w-full"
                  >
                    {isTestingToken ? "Verifying..." : "Connect"}
                  </Button>

                  {/* Error message */}
                  {authError && (
                    <p className="text-sm text-red-600 dark:text-red-400 text-center">
                      {authError}
                    </p>
                  )}
                </div>

                <details className="text-left group">
                  <summary className="text-sm text-muted-foreground cursor-pointer hover:text-foreground flex items-center gap-2 justify-center">
                    <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" />
                    Where do I find the token?
                  </summary>
                  <div className="mt-3 text-left bg-muted/30 rounded-lg p-3 space-y-2">
                    <p className="text-xs text-muted-foreground">
                      Look for this in your DevUI server startup logs:
                    </p>
                    <code className="block bg-background px-2 py-1 rounded text-xs font-mono text-foreground">
                      🔑 DEV TOKEN (localhost only, shown once):
                      <br />
                      &nbsp;&nbsp; abc123xyz...
                    </code>
                  </div>
                </details>
              </div>
            ) : (
              <>
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
                    <span className="font-mono">{currentBackendUrl}</span>
                  </p>
                </div>

                {/* Error Details (Collapsible) */}
                {entityError && (
                  <details className="text-left group">
                    <summary className="text-sm text-muted-foreground cursor-pointer hover:text-foreground flex items-center gap-2">
                      <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" />
                      Error details
                    </summary>
                    <p className="mt-2 text-xs text-muted-foreground font-mono bg-muted/30 p-3 rounded border">
                      {entityError}
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
              </>
            )}
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
        agents={agents}
        workflows={workflows}
        entities={entities}
        selectedItem={selectedAgent}
        onSelect={handleEntitySelect}
        onBrowseGallery={() => setShowGallery(true)}
        isLoading={isLoadingEntities}
        onSettingsClick={() => setShowAboutModal(true)}
      />

      {/* Main Content - Split Panel or Gallery */}
      <div className="flex flex-1 overflow-hidden">
        {showGallery ? (
          // Show gallery full screen (w-full ensures it takes entire width)
          <div className="flex-1 w-full">
            <GalleryView
              variant="route"
              onClose={() => setShowGallery(false)}
              hasExistingEntities={
                agents.length > 0 || workflows.length > 0
              }
            />
          </div>
        ) : agents.length === 0 && workflows.length === 0 ? (
          // Empty state - show gallery inline (full width, no debug panel)
          <GalleryView variant="inline" />
        ) : (
          <>
            {/* Left Panel - Main View */}
            <div className="flex-1 min-w-0">
              {selectedAgent ? (
                selectedAgent.type === "agent" ? (
                  <AgentView
                    selectedAgent={selectedAgent as AgentInfo}
                    onDebugEvent={handleDebugEvent}
                  />
                ) : (
                  <WorkflowView
                    selectedWorkflow={selectedAgent as WorkflowInfo}
                    onDebugEvent={handleDebugEvent}
                  />
                )
              ) : (
                <div className="flex-1 flex items-center justify-center text-muted-foreground">
                  Select an agent or workflow to get started.
                </div>
              )}
            </div>

            {uiMode === "developer" && showDebugPanel ? (
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
                  className="flex-shrink-0 flex flex-col h-[calc(100vh-3.7rem)]"
                  style={{ width: debugPanelMinimized ? '2.5rem' : `${debugPanelWidth}px` }}
                >
                  {debugPanelMinimized ? (
                    /* Minimized Debug Panel - Vertical Bar (fully clickable) */
                    <div
                      className="h-full w-10 bg-background border-l flex flex-col items-center py-2 cursor-pointer hover:bg-accent/50 transition-colors"
                      onClick={() => setDebugPanelMinimized(false)}
                      title="Expand debug panel"
                    >
                      {/* Expand button at top (visual affordance) */}
                      <div className="h-8 w-8 flex items-center justify-center">
                        <ChevronLeft className="h-4 w-4 text-muted-foreground" />
                      </div>

                      {/* Text and count centered in middle */}
                      <div className="flex-1 flex flex-col items-center justify-center gap-2 pointer-events-none">
                        <div
                          className="text-xs text-muted-foreground select-none"
                          style={{
                            writingMode: 'vertical-rl',
                            transform: 'rotate(180deg)'
                          }}
                        >
                          Debug Panel
                        </div>
                        {debugEvents.length > 0 && (
                          <div className="bg-primary text-primary-foreground rounded-full w-5 h-5 flex items-center justify-center"
                          style={{ fontSize: '10px' }}>
                            {debugEvents.length}
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (
                    <>
                      <DebugPanel
                        events={debugEvents}
                        isStreaming={false} // Each view manages its own streaming state
                        onMinimize={() => setDebugPanelMinimized(true)}
                      />

                      {/* Deploy Footer - Pinned to bottom */}
                      <div className="border-t bg-muted/30 px-3 py-2.5 flex-shrink-0">
                        <Button
                          onClick={() => setShowDeployModal(true)}
                          className="w-full"
                          variant="outline"
                          size="sm"
                        >
                          <Rocket className="h-3 w-3 mr-2 flex-shrink-0" />
                          <span className="truncate text-xs">
                            {azureDeploymentEnabled && selectedAgent?.deployment_supported
                              ? "Deploy to Azure"
                              : "Deployment Guide"}
                          </span>
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              </>
            ) : uiMode === "developer" ? (
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
            ) : null}
          </>
        )}
      </div>

      {/* Settings Modal */}
      <SettingsModal open={showAboutModal} onOpenChange={setShowAboutModal} />

      {/* Deployment Modal */}
      <DeploymentModal
        open={showDeployModal}
        onClose={() => setShowDeployModal(false)}
        agentName={selectedAgent?.name}
        entity={selectedAgent}
      />

      {/* Toast Notification */}
      {showEntityNotFoundToast && (
        <Toast
          message="Entity not found. Showing first available entity instead."
          type="info"
          onClose={() => setShowEntityNotFoundToast(false)}
        />
      )}

      {/* Toast Container for reload and other notifications */}
      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </div>
  );
}
