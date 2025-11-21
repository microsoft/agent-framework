/**
 * DevUI Unified Store - Single source of truth for all app state
 * Organized into logical slices: entity, conversation, UI, gallery, modals
 */

import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";
import type {
  AgentInfo,
  WorkflowInfo,
  ExtendedResponseStreamEvent,
  Conversation,
  PendingApproval,
  OAIProxyMode,
  WorkflowSession,
  CheckpointInfo,
} from "@/types";
import type { ConversationItem } from "@/types/openai";
import type { AttachmentItem } from "@/components/ui/attachment-gallery";

// ========================================
// State Interface
// ========================================

interface DevUIState {
  // Entity Management Slice
  agents: AgentInfo[];
  workflows: WorkflowInfo[];
  entities: (AgentInfo | WorkflowInfo)[];  // Full list in backend order
  selectedAgent: AgentInfo | WorkflowInfo | undefined;
  isLoadingEntities: boolean;
  entityError: string | null;

  // Conversation Slice (per-agent state)
  currentConversation: Conversation | undefined;
  availableConversations: Conversation[];
  chatItems: ConversationItem[];
  isStreaming: boolean;
  isSubmitting: boolean;
  loadingConversations: boolean;
  inputValue: string;
  attachments: AttachmentItem[];
  conversationUsage: {
    total_tokens: number;
    message_count: number;
  };
  pendingApprovals: PendingApproval[];

  // Workflow Session Slice (workflow-specific session management)
  currentSession: WorkflowSession | undefined;
  availableSessions: WorkflowSession[];
  sessionCheckpoints: CheckpointInfo[];
  loadingSessions: boolean;
  loadingCheckpoints: boolean;

  // UI Slice
  showDebugPanel: boolean;
  debugPanelMinimized: boolean;
  debugPanelWidth: number;
  debugEvents: ExtendedResponseStreamEvent[];
  isResizing: boolean;

  // Modal Slice
  showAboutModal: boolean;
  showGallery: boolean;
  showDeployModal: boolean;
  showEntityNotFoundToast: boolean;

  // Toast Slice
  toasts: Array<{
    id: string;
    message: string;
    type: "info" | "success" | "warning" | "error";
    duration?: number;
  }>;

  // OpenAI Proxy Mode Slice
  oaiMode: OAIProxyMode;

  // Server Meta Slice
  uiMode: "developer" | "user";
  runtime: "python" | "dotnet";
  serverCapabilities: {
    tracing: boolean;
    openai_proxy: boolean;
    deployment: boolean;
  };
  authRequired: boolean;

  // Deployment Slice
  isDeploying: boolean;
  deploymentLogs: string[];
  lastDeployment: {
    url: string;
    authToken: string;
  } | null;
  azureDeploymentEnabled: boolean; // Feature flag for Azure deployment
}

// ========================================
// Actions Interface
// ========================================

interface DevUIActions {
  // Entity Actions
  setAgents: (agents: AgentInfo[]) => void;
  setWorkflows: (workflows: WorkflowInfo[]) => void;
  setEntities: (entities: (AgentInfo | WorkflowInfo)[]) => void;
  setSelectedAgent: (agent: AgentInfo | WorkflowInfo | undefined) => void;
  addAgent: (agent: AgentInfo) => void;
  addWorkflow: (workflow: WorkflowInfo) => void;
  updateAgent: (agent: AgentInfo) => void;
  updateWorkflow: (workflow: WorkflowInfo) => void;
  removeEntity: (entityId: string) => void;
  setEntityError: (error: string | null) => void;
  setIsLoadingEntities: (loading: boolean) => void;

  // Conversation Actions
  setCurrentConversation: (conv: Conversation | undefined) => void;
  setAvailableConversations: (convs: Conversation[]) => void;
  setChatItems: (items: ConversationItem[]) => void;
  setIsStreaming: (streaming: boolean) => void;
  setIsSubmitting: (submitting: boolean) => void;
  setLoadingConversations: (loading: boolean) => void;
  setInputValue: (value: string) => void;
  setAttachments: (files: AttachmentItem[]) => void;
  updateConversationUsage: (tokens: number) => void;
  setPendingApprovals: (approvals: PendingApproval[]) => void;

  // Workflow Session Actions
  setCurrentSession: (session: WorkflowSession | undefined) => void;
  setAvailableSessions: (sessions: WorkflowSession[]) => void;
  setSessionCheckpoints: (checkpoints: CheckpointInfo[]) => void;
  setLoadingSessions: (loading: boolean) => void;
  setLoadingCheckpoints: (loading: boolean) => void;
  addSession: (session: WorkflowSession) => void;
  removeSession: (conversationId: string) => void;

  // UI Actions
  setShowDebugPanel: (show: boolean) => void;
  setDebugPanelMinimized: (minimized: boolean) => void;
  setDebugPanelWidth: (width: number) => void;
  addDebugEvent: (event: ExtendedResponseStreamEvent) => void;
  clearDebugEvents: () => void;
  setIsResizing: (resizing: boolean) => void;

  // Modal Actions
  setShowAboutModal: (show: boolean) => void;
  setShowGallery: (show: boolean) => void;
  setShowDeployModal: (show: boolean) => void;
  setShowEntityNotFoundToast: (show: boolean) => void;

  // Toast Actions
  addToast: (toast: {
    message: string;
    type?: "info" | "success" | "warning" | "error";
    duration?: number;
  }) => void;
  removeToast: (id: string) => void;

  // OpenAI Proxy Mode Actions
  setOAIMode: (config: OAIProxyMode) => void;
  toggleOAIMode: () => void;

  // Server Meta Actions
  setServerMeta: (meta: { uiMode: "developer" | "user"; runtime: "python" | "dotnet"; capabilities: { tracing: boolean; openai_proxy: boolean; deployment: boolean }; authRequired: boolean }) => void;

  // Deployment Actions
  startDeployment: () => void;
  addDeploymentLog: (log: string) => void;
  setDeploymentResult: (result: { url: string; authToken: string }) => void;
  stopDeployment: () => void;
  clearDeploymentState: () => void;
  setAzureDeploymentEnabled: (enabled: boolean) => void;

  // Combined Actions (handle multiple state updates + side effects)
  selectEntity: (entity: AgentInfo | WorkflowInfo) => void;
}

type DevUIStore = DevUIState & DevUIActions;

// ========================================
// Store Implementation
// ========================================

export const useDevUIStore = create<DevUIStore>()(
  devtools(
    persist(
      (set) => ({
        // ========================================
        // Initial State
        // ========================================

        // Entity State
        agents: [],
        workflows: [],
        entities: [],
        selectedAgent: undefined,
        isLoadingEntities: true,
        entityError: null,

        // Conversation State
        currentConversation: undefined,
        availableConversations: [],
        chatItems: [],
        isStreaming: false,
        isSubmitting: false,
        loadingConversations: false,
        inputValue: "",
        attachments: [],
        conversationUsage: { total_tokens: 0, message_count: 0 },
        pendingApprovals: [],

        // Workflow Session State
        currentSession: undefined,
        availableSessions: [],
        sessionCheckpoints: [],
        loadingSessions: false,
        loadingCheckpoints: false,

        // UI State
        showDebugPanel: true,
        debugPanelMinimized: false,
        debugPanelWidth: 320,
        debugEvents: [],
        isResizing: false,

        // Modal State
        showAboutModal: false,
        showGallery: false,
        showDeployModal: false,
        showEntityNotFoundToast: false,

        // Toast State
        toasts: [],

        // OpenAI Proxy Mode State
        oaiMode: {
          enabled: false,
          model: "gpt-4o-mini", // Default to cheaper model
        },

        // Server Meta State
        uiMode: "developer", // Default to developer mode
        runtime: "python", // Default to Python runtime
        serverCapabilities: {
          tracing: false,
          openai_proxy: false,
          deployment: false,
        },
        authRequired: false,

        // Deployment State
        isDeploying: false,
        deploymentLogs: [],
        lastDeployment: null,
        azureDeploymentEnabled: false, // Default to disabled for safety

        // ========================================
        // Entity Actions
        // ========================================

        setAgents: (agents) => set({ agents }),
        setWorkflows: (workflows) => set({ workflows }),
        setEntities: (entities) => set({ entities }),
        setSelectedAgent: (agent) => set({ selectedAgent: agent }),
        addAgent: (agent) =>
          set((state) => ({ agents: [...state.agents, agent] })),
        addWorkflow: (workflow) =>
          set((state) => ({ workflows: [...state.workflows, workflow] })),
        updateAgent: (updatedAgent) =>
          set((state) => ({
            agents: state.agents.map((a) =>
              a.id === updatedAgent.id ? updatedAgent : a
            ),
            // Also update selectedAgent if it's the same one
            selectedAgent:
              state.selectedAgent?.id === updatedAgent.id &&
              state.selectedAgent.type === "agent"
                ? updatedAgent
                : state.selectedAgent,
          })),
        updateWorkflow: (updatedWorkflow) =>
          set((state) => ({
            workflows: state.workflows.map((w) =>
              w.id === updatedWorkflow.id ? updatedWorkflow : w
            ),
            // Also update selectedAgent if it's the same one
            selectedAgent:
              state.selectedAgent?.id === updatedWorkflow.id &&
              state.selectedAgent.type === "workflow"
                ? updatedWorkflow
                : state.selectedAgent,
          })),
        removeEntity: (entityId) =>
          set((state) => ({
            agents: state.agents.filter((a) => a.id !== entityId),
            workflows: state.workflows.filter((w) => w.id !== entityId),
            selectedAgent:
              state.selectedAgent?.id === entityId
                ? undefined
                : state.selectedAgent,
          })),
        setEntityError: (error) => set({ entityError: error }),
        setIsLoadingEntities: (loading) => set({ isLoadingEntities: loading }),

        // ========================================
        // Conversation Actions
        // ========================================

        setCurrentConversation: (conv) => set({ currentConversation: conv }),
        setAvailableConversations: (convs) =>
          set({ availableConversations: convs }),
        setChatItems: (items) => set({ chatItems: items }),
        setIsStreaming: (streaming) => set({ isStreaming: streaming }),
        setIsSubmitting: (submitting) => set({ isSubmitting: submitting }),
        setLoadingConversations: (loading) =>
          set({ loadingConversations: loading }),
        setInputValue: (value) => set({ inputValue: value }),
        setAttachments: (files) => set({ attachments: files }),
        updateConversationUsage: (tokens) =>
          set((state) => ({
            conversationUsage: {
              total_tokens: state.conversationUsage.total_tokens + tokens,
              message_count: state.conversationUsage.message_count + 1,
            },
          })),
        setPendingApprovals: (approvals) => set({ pendingApprovals: approvals }),

        // ========================================
        // Workflow Session Actions
        // ========================================

        setCurrentSession: (session) => set({ currentSession: session }),
        setAvailableSessions: (sessions) => set({ availableSessions: sessions }),
        setSessionCheckpoints: (checkpoints) =>
          set({ sessionCheckpoints: checkpoints }),
        setLoadingSessions: (loading) => set({ loadingSessions: loading }),
        setLoadingCheckpoints: (loading) => set({ loadingCheckpoints: loading }),
        addSession: (session) =>
          set((state) => ({
            availableSessions: [session, ...state.availableSessions],
          })),
        removeSession: (conversationId) =>
          set((state) => ({
            availableSessions: state.availableSessions.filter(
              (s) => s.conversation_id !== conversationId
            ),
            // Clear current session if it's the one being deleted
            currentSession:
              state.currentSession?.conversation_id === conversationId
                ? undefined
                : state.currentSession,
            // Clear checkpoints if they belong to deleted session
            sessionCheckpoints:
              state.currentSession?.conversation_id === conversationId
                ? []
                : state.sessionCheckpoints,
          })),

        // ========================================
        // UI Actions
        // ========================================

        setShowDebugPanel: (show) => set({ showDebugPanel: show }),
        setDebugPanelMinimized: (minimized) => set({ debugPanelMinimized: minimized }),
        setDebugPanelWidth: (width) => set({ debugPanelWidth: width }),
        addDebugEvent: (event) =>
          set((state) => {
            // Generate unique timestamp for each event
            // Use current time + small increment to ensure uniqueness even for rapid events
            const baseTimestamp = Math.floor(Date.now() / 1000);
            const lastTimestamp = state.debugEvents.length > 0
              ? (state.debugEvents[state.debugEvents.length - 1] as any)._uiTimestamp || 0
              : 0;
            // Ensure new timestamp is always greater than the last one
            const uniqueTimestamp = Math.max(baseTimestamp, lastTimestamp + 1);

            return {
              debugEvents: [
                ...state.debugEvents,
                {
                  ...event,
                  // Add UI display timestamp when event is received (Unix seconds)
                  // Each event gets a unique timestamp to preserve chronological order
                  _uiTimestamp: ('created_at' in event && event.created_at)
                    ? event.created_at
                    : uniqueTimestamp,
                } as ExtendedResponseStreamEvent & { _uiTimestamp: number },
              ],
            };
          }),
        clearDebugEvents: () => set({ debugEvents: [] }),
        setIsResizing: (resizing) => set({ isResizing: resizing }),

        // ========================================
        // Modal Actions
        // ========================================

        setShowAboutModal: (show) => set({ showAboutModal: show }),
        setShowGallery: (show) => set({ showGallery: show }),
        setShowDeployModal: (show) => set({ showDeployModal: show }),
        setShowEntityNotFoundToast: (show) =>
          set({ showEntityNotFoundToast: show }),

        // ========================================
        // Toast Actions
        // ========================================

        addToast: (toast) =>
          set((state) => ({
            toasts: [
              ...state.toasts,
              {
                id: `toast-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
                type: toast.type || "info",
                duration: toast.duration || 4000,
                ...toast,
              },
            ],
          })),

        removeToast: (id) =>
          set((state) => ({
            toasts: state.toasts.filter((t) => t.id !== id),
          })),

        // ========================================
        // OpenAI Proxy Mode Actions
        // ========================================

        setOAIMode: (config) =>
          set((state) => {
            // If enabling OAI mode, clear conversation state
            if (config.enabled && !state.oaiMode.enabled) {
              // Clear ALL conversation localStorage caches
              Object.keys(localStorage).forEach(key => {
                if (key.startsWith('devui_convs_')) {
                  localStorage.removeItem(key);
                }
              });

              return {
                oaiMode: config,
                // Clear conversation state when switching to OAI mode
                currentConversation: undefined,
                availableConversations: [],
                chatItems: [],
                inputValue: "",
                attachments: [],
                conversationUsage: { total_tokens: 0, message_count: 0 },
                isStreaming: false,
                isSubmitting: false,
                pendingApprovals: [],
                debugEvents: [],
              };
            }
            // If disabling OAI mode, also clear state
            if (!config.enabled && state.oaiMode.enabled) {
              // Clear ALL conversation localStorage caches
              Object.keys(localStorage).forEach(key => {
                if (key.startsWith('devui_convs_')) {
                  localStorage.removeItem(key);
                }
              });

              return {
                oaiMode: config,
                // Clear conversation state when switching back to local mode
                currentConversation: undefined,
                availableConversations: [],
                chatItems: [],
                inputValue: "",
                attachments: [],
                conversationUsage: { total_tokens: 0, message_count: 0 },
                isStreaming: false,
                isSubmitting: false,
                pendingApprovals: [],
                debugEvents: [],
              };
            }
            // Just update config (model, temperature, etc.) without clearing state
            return { oaiMode: config };
          }),

        toggleOAIMode: () =>
          set((state) => {
            const newEnabled = !state.oaiMode.enabled;
            return {
              oaiMode: { ...state.oaiMode, enabled: newEnabled },
              // Clear conversation state when toggling
              currentConversation: undefined,
              availableConversations: [],
              chatItems: [],
              inputValue: "",
              attachments: [],
              conversationUsage: { total_tokens: 0, message_count: 0 },
              isStreaming: false,
              isSubmitting: false,
              pendingApprovals: [],
              debugEvents: [],
            };
          }),

        // ========================================
        // Server Meta Actions
        // ========================================

        setServerMeta: (meta) =>
          set({
            uiMode: meta.uiMode,
            runtime: meta.runtime,
            serverCapabilities: meta.capabilities,
            authRequired: meta.authRequired,
          }),

        // ========================================
        // Deployment Actions
        // ========================================

        startDeployment: () =>
          set({
            isDeploying: true,
            deploymentLogs: [],
            lastDeployment: null,
          }),

        addDeploymentLog: (log) =>
          set((state) => ({
            deploymentLogs: [...state.deploymentLogs, log],
          })),

        setDeploymentResult: (result) =>
          set({
            isDeploying: false,
            lastDeployment: result,
          }),

        stopDeployment: () =>
          set({
            isDeploying: false,
          }),

        clearDeploymentState: () =>
          set({
            isDeploying: false,
            deploymentLogs: [],
            lastDeployment: null,
          }),

        setAzureDeploymentEnabled: (enabled) =>
          set({ azureDeploymentEnabled: enabled }),

        // ========================================
        // Combined Actions
        // ========================================

        /**
         * Select an entity (agent/workflow) and handle all side effects:
         * - Update selected entity
         * - Clear conversation state (FIXES THE BUG!)
         * - Clear session state (for workflows)
         * - Clear debug events
         * - Update URL
         */
        selectEntity: (entity) => {
          set({
            selectedAgent: entity,
            // CRITICAL: Clear all conversation state when switching entities
            currentConversation: undefined,
            availableConversations: [], // Let AgentView reload conversations
            chatItems: [],
            inputValue: "",
            attachments: [],
            conversationUsage: { total_tokens: 0, message_count: 0 },
            isStreaming: false,
            isSubmitting: false,
            pendingApprovals: [],
            // Clear workflow session state when switching entities
            currentSession: undefined,
            availableSessions: [], // Let WorkflowView reload sessions
            sessionCheckpoints: [],
            // Clear debug events when switching
            debugEvents: [],
          });

          // Update URL with selected entity ID
          const url = new URL(window.location.href);
          url.searchParams.set("entity_id", entity.id);
          window.history.pushState({}, "", url);
        },
      }),
      {
        name: "devui-storage",
        // Only persist UI preferences, not runtime state
        partialize: (state) => ({
          showDebugPanel: state.showDebugPanel,
          debugPanelMinimized: state.debugPanelMinimized,
          debugPanelWidth: state.debugPanelWidth,
          oaiMode: state.oaiMode, // Persist OpenAI proxy mode settings
          azureDeploymentEnabled: state.azureDeploymentEnabled, // Persist Azure deployment preference
        }),
      }
    ),
    { name: "DevUI Store" }
  )
);

// ========================================
// Usage Notes
// ========================================

/**
 * How to use the store:
 *
 * 1. For state access, use direct selectors:
 *    const agents = useDevUIStore((state) => state.agents);
 *
 * 2. For actions, extract them:
 *    const setAgents = useDevUIStore((state) => state.setAgents);
 *
 * 3. For combined state access (use sparingly, can cause unnecessary re-renders):
 *    const { agents, workflows } = useDevUIStore((state) => ({
 *      agents: state.agents,
 *      workflows: state.workflows
 *    }));
 *
 * 4. To access state outside React components:
 *    useDevUIStore.getState().agents
 *    useDevUIStore.getState().setAgents([...])
 */
