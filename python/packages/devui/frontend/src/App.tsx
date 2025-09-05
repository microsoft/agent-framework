/**
 * DevUI App - Split-panel chat interface for agent debugging
 * Features: Agent switching, real-time chat, debug panel with events/traces/tools
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { AgentSwitcher } from "@/components/main/agent-switcher";
import { ChatRouter } from "@/components/main/chat-router";
import { DebugPanel } from "@/components/main/debug-panel";
import { apiClient } from "@/services/api";
import { Plus, Settings, ChevronLeft, GripVertical } from "lucide-react";
import type { AgentInfo, WorkflowInfo, ChatMessage, AppState, ChatState } from "@/types";
import type { AgentRunResponseUpdate } from "@/types/agent-framework";
import {
  isTextContent,
  isFunctionCallContent,
  isFunctionResultContent,
} from "@/types/agent-framework";

// Function call accumulator to handle streaming function arguments
interface FunctionCallAccumulator {
  [callId: string]: {
    name: string;
    arguments: string;
    isComplete: boolean;
  };
}

// Helper to extract text content from AgentRunResponseUpdate with proper function call accumulation
function extractMessageContent(
  update: AgentRunResponseUpdate,
  functionCallAccumulator: React.MutableRefObject<FunctionCallAccumulator>
): string {
  if (!update) return "";

  console.log("📦 Extracting from update:", update);

  // Use the text property if available (concatenated text from all TextContent)
  if (update.text && typeof update.text === "string") {
    console.log("✅ Found text property:", update.text);
    return update.text;
  }

  // Fallback to manual extraction
  if (!update.contents || !Array.isArray(update.contents)) {
    console.log("❌ No contents array found");
    return "";
  }

  console.log(`📝 Processing ${update.contents.length} content items`);

  const textParts: string[] = [];

  for (const content of update.contents) {
    console.log("📄 Content:", content);
    if (isTextContent(content)) {
      textParts.push(content.text);
    } else if (isFunctionCallContent(content)) {
      // Accumulate function call arguments by call_id
      const callId = content.call_id;
      const name = content.name || "";
      const args = content.arguments || "";

      if (!functionCallAccumulator.current[callId]) {
        functionCallAccumulator.current[callId] = {
          name,
          arguments: "",
          isComplete: false,
        };
      }

      // Accumulate arguments
      if (typeof args === "string") {
        functionCallAccumulator.current[callId].arguments += args;
      } else if (args !== null && args !== undefined) {
        // If we get a complete object, stringify it
        functionCallAccumulator.current[callId].arguments =
          JSON.stringify(args);
        functionCallAccumulator.current[callId].isComplete = true;
      }

      // Update name if provided (sometimes name comes later)
      if (name) {
        functionCallAccumulator.current[callId].name = name;
      }

      // Try to parse arguments to see if they're complete JSON
      const accumulated = functionCallAccumulator.current[callId];
      let isValidJson = false;
      try {
        if (accumulated.arguments.trim()) {
          JSON.parse(accumulated.arguments);
          isValidJson = true;
          accumulated.isComplete = true;
        }
      } catch {
        // Not complete JSON yet, continue accumulating
      }

      // Only show function call if we have complete arguments or it's marked complete
      if (accumulated.isComplete && accumulated.name) {
        textParts.push(`Calling ${accumulated.name}(${accumulated.arguments})`);
        console.log("✅ Complete function call:", accumulated);
      } else if (isValidJson && accumulated.name) {
        textParts.push(`Calling ${accumulated.name}(${accumulated.arguments})`);
        console.log("✅ Valid JSON function call:", accumulated);
      }
      // If incomplete, don't add anything to textParts yet
    } else if (isFunctionResultContent(content)) {
      textParts.push(`Tool result: ${content.result}`);
    }
  }

  const result = textParts.join("\n");
  console.log("🎯 Extracted content:", result);
  return result;
}

export default function App() {
  const [appState, setAppState] = useState<AppState>({
    agents: [],
    workflows: [],
    isLoading: true,
  });

  const [chatState, setChatState] = useState<ChatState>({
    messages: [],
    isStreaming: false,
    streamEvents: [],
  });

  const [workflowInfo, setWorkflowInfo] = useState<WorkflowInfo | null>(null);

  const [debugPanelOpen, setDebugPanelOpen] = useState(true);
  const [debugPanelWidth, setDebugPanelWidth] = useState(320); // Default 320px (w-80)
  const [isResizing, setIsResizing] = useState(false);

  // Function call accumulator for streaming function arguments
  const functionCallAccumulator = useRef<FunctionCallAccumulator>({});

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
          selectedAgent: agents[0] || workflows[0], // Select first item by default
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

  // Load debug panel width from localStorage
  useEffect(() => {
    const savedWidth = localStorage.getItem("debugPanelWidth");
    if (savedWidth) {
      setDebugPanelWidth(parseInt(savedWidth, 10));
    }
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

  // Handle agent/workflow selection
  const handleAgentSelect = useCallback(async (item: AgentInfo) => {
    setAppState((prev) => ({
      ...prev,
      selectedAgent: item,
      currentThread: undefined,
    }));

    // Clear chat when switching agents
    setChatState({
      messages: [],
      isStreaming: false,
      streamEvents: [],
    });

    // Clear function call accumulator
    functionCallAccumulator.current = {};

    // Load workflow info if it's a workflow
    if (item.type === "workflow") {
      try {
        const info = await apiClient.getWorkflowInfo(item.id);
        setWorkflowInfo(info);
      } catch (error) {
        console.error("Failed to load workflow info:", error);
        setWorkflowInfo(null);
      }
    } else {
      setWorkflowInfo(null);
    }
  }, []);

  // Handle new thread creation
  const handleNewThread = useCallback(() => {
    setAppState((prev) => ({ ...prev, currentThread: undefined }));
    setChatState({
      messages: [],
      isStreaming: false,
      streamEvents: [],
    });

    // Clear function call accumulator
    functionCallAccumulator.current = {};
  }, []);

  // Handle message sending
  const handleSendMessage = useCallback(
    async (message: string) => {
      if (!appState.selectedAgent) return;

      // Add user message
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        content: message,
        timestamp: new Date().toISOString(),
      };

      setChatState((prev) => ({
        ...prev,
        messages: [...prev.messages, userMessage],
        isStreaming: true,
        streamEvents: [], // Clear previous events for new conversation
      }));

      // Create assistant message placeholder
      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: "",
        timestamp: new Date().toISOString(),
        streaming: true,
      };

      setChatState((prev) => ({
        ...prev,
        messages: [...prev.messages, assistantMessage],
      }));

      try {
        const request = {
          message,
          thread_id:
            chatState.messages.length > 0
              ? appState.currentThread?.id
              : undefined,
          options: { capture_traces: true },
        };

        const isWorkflow = appState.selectedAgent.type === "workflow";

        // Use real API streaming
        const streamGenerator = apiClient.streamAgentExecution(
          appState.selectedAgent.id,
          request,
          isWorkflow
        );

        for await (const event of streamGenerator) {
          // Add event to debug stream
          setChatState((prev) => ({
            ...prev,
            streamEvents: [...prev.streamEvents, event],
          }));

          // Store thread_id when first received
          if (event.thread_id && !appState.currentThread) {
            setAppState((prev) => ({
              ...prev,
              currentThread: {
                id: event.thread_id!,
                agent_id: appState.selectedAgent!.id,
                created_at: new Date().toISOString(),
                message_count: 0,
              },
            }));
          }

          // Update chat message if it's a content update
          if (event.type === "agent_run_update" && event.update) {
            const newChunk = extractMessageContent(
              event.update,
              functionCallAccumulator
            );
            if (newChunk) {
              setChatState((prev) => ({
                ...prev,
                messages: prev.messages.map((msg) =>
                  msg.id === assistantMessage.id
                    ? {
                        ...msg,
                        content: msg.content + newChunk, // Accumulate chunks
                      }
                    : msg
                ),
              }));
            }
          }

          // Handle completion
          if (event.type === "completion") {
            setChatState((prev) => ({
              ...prev,
              isStreaming: false,
              messages: prev.messages.map((msg) =>
                msg.id === assistantMessage.id
                  ? { ...msg, streaming: false }
                  : msg
              ),
            }));
            break;
          }

          // Handle errors
          if (event.type === "error") {
            setChatState((prev) => ({
              ...prev,
              isStreaming: false,
              messages: prev.messages.map((msg) =>
                msg.id === assistantMessage.id
                  ? {
                      ...msg,
                      content: `Error: ${event.error}`,
                      streaming: false,
                    }
                  : msg
              ),
            }));
            break;
          }
        }
      } catch (error) {
        console.error("Streaming error:", error);
        setChatState((prev) => ({
          ...prev,
          isStreaming: false,
          streamEvents: [
            ...prev.streamEvents,
            {
              type: "error",
              error: error instanceof Error ? error.message : "Unknown error",
              timestamp: new Date().toISOString(),
            },
          ],
          messages: prev.messages.map((msg) =>
            msg.id === assistantMessage.id
              ? {
                  ...msg,
                  content: `Error: ${
                    error instanceof Error
                      ? error.message
                      : "Failed to get response"
                  }`,
                  streaming: false,
                }
              : msg
          ),
        }));
      }
    },
    [appState.selectedAgent, appState.currentThread, chatState.messages]
  );

  return (
    <div className="h-screen flex flex-col bg-background max-h-screen">
      {/* Top Bar */}
      <header className="flex h-14 items-center gap-4 border-b px-4">
        <AgentSwitcher
          agents={appState.agents}
          workflows={appState.workflows}
          selectedItem={appState.selectedAgent}
          onSelect={handleAgentSelect}
          isLoading={appState.isLoading}
        />

        <div className="flex items-center gap-2 ml-auto">
          <Button
            variant="outline"
            size="sm"
            onClick={handleNewThread}
            disabled={!appState.selectedAgent}
          >
            <Plus className="h-4 w-4 mr-2" />
            New Thread
          </Button>

          <Separator orientation="vertical" className="h-6" />

          <Button variant="ghost" size="sm">
            <Settings className="h-4 w-4" />
          </Button>
        </div>
      </header>

      {/* Main Content - Split Panel */}
      <div className="flex flex-1 overflow-hidden ">
        {/* Left Panel - Chat */}
        <div className="flex-1 min-w-0">
          <ChatRouter
            selectedItem={appState.selectedAgent}
            workflowInfo={workflowInfo}
            messages={chatState.messages}
            debugEvents={chatState.streamEvents}
            onSendMessage={handleSendMessage}
            isStreaming={chatState.isStreaming}
          />
        </div>

        {/* Resize Handle */}
        {debugPanelOpen && (
          <div
            className={`w-1 bg-border hover:bg-accent cursor-col-resize flex-shrink-0 relative group ${
              isResizing ? "bg-accent" : ""
            }`}
            onMouseDown={handleMouseDown}
            onDoubleClick={handleDoubleClick}
          >
            <div className="absolute inset-y-0 -left-1 -right-1 flex items-center justify-center">
              <GripVertical className="h-4 w-4 text-muted-foreground group-hover:text-foreground" />
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
              events={chatState.streamEvents}
              isStreaming={chatState.isStreaming}
            />
          </div>
        )}
      </div>
    </div>
  );
}
