/**
 * Workflow Conversation Manager Component
 * Handles conversation selection, creation, and deletion for workflow executions
 */

import React, { useEffect, useState, useCallback } from "react";
import { useDevUIStore } from "@/stores/devuiStore";
import { apiClient } from "@/services/api";
import { Trash2, Plus, Clock } from "lucide-react";
import type { WorkflowSession } from "@/types";

interface WorkflowSessionManagerProps {
  workflowId: string;
  onSessionChange?: (session: WorkflowSession | undefined) => void;
}

export const WorkflowSessionManager: React.FC<WorkflowSessionManagerProps> = ({
  workflowId,
  onSessionChange,
}) => {
  // Use individual selectors to avoid creating new objects on every render
  const currentSession = useDevUIStore((state) => state.currentSession);
  const availableSessions = useDevUIStore((state) => state.availableSessions);
  const loadingSessions = useDevUIStore((state) => state.loadingSessions);
  const setCurrentSession = useDevUIStore((state) => state.setCurrentSession);
  const setAvailableSessions = useDevUIStore((state) => state.setAvailableSessions);
  const setLoadingSessions = useDevUIStore((state) => state.setLoadingSessions);
  const addSession = useDevUIStore((state) => state.addSession);
  const removeSession = useDevUIStore((state) => state.removeSession);
  const addToast = useDevUIStore((state) => state.addToast);
  const runtime = useDevUIStore((state) => state.runtime);

  const [creatingSession, setCreatingSession] = useState(false);
  const [deletingSession, setDeletingSession] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const response = await apiClient.listWorkflowSessions(workflowId);

      // If no conversations exist, auto-create one (like agent conversations)
      if (response.data.length === 0) {
        console.log("No workflow conversations found, creating default conversation");
        const newSession = await apiClient.createWorkflowSession(workflowId, {
          name: `Conversation ${new Date().toLocaleString()}`,
        });
        setAvailableSessions([newSession]);
        setCurrentSession(newSession);
        onSessionChange?.(newSession);
        addToast({
          message: "Default conversation created",
          type: "success",
        });
      } else {
        // Conversations exist - set available and auto-select the first one
        setAvailableSessions(response.data);

        // Auto-select first conversation if no current selection
        if (!currentSession) {
          const firstSession = response.data[0];
          setCurrentSession(firstSession);
          onSessionChange?.(firstSession);
        }
      }
    } catch (error) {
      console.error("Failed to load workflow conversations:", error);

      // Silently handle for .NET backend (doesn't support conversations yet)
      // Only show error for Python backend where this is unexpected
      if (runtime !== "dotnet") {
        addToast({
          message: "Failed to load workflow conversations",
          type: "error",
        });
      }
    } finally {
      setLoadingSessions(false);
    }
  }, [workflowId, currentSession, runtime, setLoadingSessions, setAvailableSessions, setCurrentSession, onSessionChange, addToast]);

  // Load sessions on mount
  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const handleCreateSession = async () => {
    setCreatingSession(true);
    try {
      const newSession = await apiClient.createWorkflowSession(workflowId, {
        name: `Conversation ${new Date().toLocaleString()}`,
      });
      addSession(newSession);
      setCurrentSession(newSession);
      onSessionChange?.(newSession);
      addToast({
        message: "New conversation created",
        type: "success",
      });
    } catch (error) {
      console.error("Failed to create conversation:", error);
      addToast({
        message: "Failed to create conversation",
        type: "error",
      });
    } finally {
      setCreatingSession(false);
    }
  };

  const handleSelectSession = (session: WorkflowSession) => {
    setCurrentSession(session);
    onSessionChange?.(session);
  };

  const handleDeleteSession = async (
    sessionId: string,
    event: React.MouseEvent
  ) => {
    event.stopPropagation(); // Prevent session selection when clicking delete

    if (!confirm("Delete this conversation? All checkpoints will be lost.")) {
      return;
    }

    setDeletingSession(sessionId);
    try {
      await apiClient.deleteWorkflowSession(workflowId, sessionId);
      removeSession(sessionId);
      addToast({
        message: "Conversation deleted",
        type: "success",
      });
    } catch (error) {
      console.error("Failed to delete conversation:", error);
      addToast({
        message: "Failed to delete conversation",
        type: "error",
      });
    } finally {
      setDeletingSession(null);
    }
  };

  const formatTimestamp = (timestamp: number) => {
    const date = new Date(timestamp * 1000);
    return date.toLocaleString();
  };

  if (loadingSessions) {
    return (
      <div className="flex items-center justify-center py-4">
        <div className="animate-spin h-5 w-5 border-2 border-blue-500 border-t-transparent rounded-full" />
        <span className="ml-2 text-sm text-gray-600">Loading sessions...</span>
      </div>
    );
  }

  return (
    <div className="workflow-session-manager space-y-3">
      {/* Header with Create Button */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">
          Conversations
        </h3>
        <button
          onClick={handleCreateSession}
          disabled={creatingSession}
          className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          title="Create new conversation"
        >
          <Plus className="h-4 w-4" />
          New Conversation
        </button>
      </div>

      {/* Conversation List */}
      {availableSessions.length === 0 ? (
        <div className="text-center py-6 text-sm text-gray-500 dark:text-gray-400">
          Loading conversations...
        </div>
      ) : (
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {availableSessions.map((session) => (
            <div
              key={session.conversation_id}
              onClick={() => handleSelectSession(session)}
              className={`
                flex items-center justify-between p-3 rounded-lg border cursor-pointer transition-all
                ${
                  currentSession?.conversation_id === session.conversation_id
                    ? "bg-blue-50 dark:bg-blue-900/20 border-blue-300 dark:border-blue-700"
                    : "bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
                }
              `}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4 text-gray-400 flex-shrink-0" />
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                    {session.metadata.name || "Unnamed Conversation"}
                  </span>
                </div>
                <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {formatTimestamp(session.created_at)}
                </div>
              </div>
              <button
                onClick={(e) => handleDeleteSession(session.conversation_id, e)}
                disabled={deletingSession === session.conversation_id}
                className="ml-3 p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors disabled:opacity-50"
                title="Delete conversation"
              >
                {deletingSession === session.conversation_id ? (
                  <div className="animate-spin h-4 w-4 border-2 border-red-500 border-t-transparent rounded-full" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
