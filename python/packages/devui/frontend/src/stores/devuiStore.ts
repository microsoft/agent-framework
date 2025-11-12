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

  // UI Slice
  showDebugPanel: boolean;
  debugPanelWidth: number;
  debugEvents: ExtendedResponseStreamEvent[];
  isResizing: boolean;

  // Modal Slice
  showAboutModal: boolean;
  showGallery: boolean;
  showDeployModal: boolean;
  showEntityNotFoundToast: boolean;
}

// ========================================
// Actions Interface
// ========================================

interface DevUIActions {
  // Entity Actions
  setAgents: (agents: AgentInfo[]) => void;
  setWorkflows: (workflows: WorkflowInfo[]) => void;
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

  // UI Actions
  setShowDebugPanel: (show: boolean) => void;
  setDebugPanelWidth: (width: number) => void;
  addDebugEvent: (event: ExtendedResponseStreamEvent) => void;
  clearDebugEvents: () => void;
  setIsResizing: (resizing: boolean) => void;

  // Modal Actions
  setShowAboutModal: (show: boolean) => void;
  setShowGallery: (show: boolean) => void;
  setShowDeployModal: (show: boolean) => void;
  setShowEntityNotFoundToast: (show: boolean) => void;

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

        // UI State
        showDebugPanel: true,
        debugPanelWidth: 320,
        debugEvents: [],
        isResizing: false,

        // Modal State
        showAboutModal: false,
        showGallery: false,
        showDeployModal: false,
        showEntityNotFoundToast: false,

        // ========================================
        // Entity Actions
        // ========================================

        setAgents: (agents) => set({ agents }),
        setWorkflows: (workflows) => set({ workflows }),
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
        // UI Actions
        // ========================================

        setShowDebugPanel: (show) => set({ showDebugPanel: show }),
        setDebugPanelWidth: (width) => set({ debugPanelWidth: width }),
        addDebugEvent: (event) =>
          set((state) => ({ debugEvents: [...state.debugEvents, event] })),
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
        // Combined Actions
        // ========================================

        /**
         * Select an entity (agent/workflow) and handle all side effects:
         * - Update selected entity
         * - Clear conversation state (FIXES THE BUG!)
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
          debugPanelWidth: state.debugPanelWidth,
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
