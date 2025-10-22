import { useState, useEffect, useRef, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { WorkflowChatMessage, type ChatMessage } from "./workflow-chat-message";
import { WorkflowChatInput } from "./workflow-chat-input";
import { Conversation, ConversationContent, ConversationEmptyState } from "@/components/ai-elements/conversation";
import { Shimmer } from "@/components/ai-elements/shimmer";
import type { ExtendedResponseStreamEvent, JSONSchemaProperty } from "@/types";
import { ChevronRight, Sparkles, Bot } from "lucide-react";
import { cn } from "@/lib/utils";

interface WorkflowChatSidebarProps {
  events: ExtendedResponseStreamEvent[];
  isStreaming: boolean;
  inputSchema: JSONSchemaProperty;
  onSubmit: (data: Record<string, unknown>) => void;
}

const DEFAULT_WIDTH = 600;
const MIN_WIDTH = 400;
const MAX_WIDTH_PERCENT = 0.6;

export function WorkflowChatSidebar({
  events,
  isStreaming,
  inputSchema,
  onSubmit,
}: WorkflowChatSidebarProps) {
  // State
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [width, setWidth] = useState(() => {
    const saved = localStorage.getItem("workflowChatSidebarWidth");
    return saved ? parseInt(saved, 10) : DEFAULT_WIDTH;
  });
  const [isCollapsed, setIsCollapsed] = useState(() => {
    const saved = localStorage.getItem("workflowChatSidebarCollapsed");
    return saved === "true";
  });
  const [isResizing, setIsResizing] = useState(false);

  // Refs
  const currentExecutorRef = useRef<string | null>(null);
  const lastExecutorRef = useRef<string | null>(null);
  const processedEventCount = useRef<number>(0);
  const currentToolCallRef = useRef<string | null>(null);
  const messageStartTimesRef = useRef<Record<string, number>>({});

  // Save state to localStorage
  useEffect(() => {
    localStorage.setItem("workflowChatSidebarWidth", width.toString());
  }, [width]);

  useEffect(() => {
    localStorage.setItem("workflowChatSidebarCollapsed", isCollapsed.toString());
  }, [isCollapsed]);

  // Clear messages when events are cleared (new execution)
  useEffect(() => {
    if (events.length === 0) {
      setMessages([]);
      currentExecutorRef.current = null;
      lastExecutorRef.current = null;
      processedEventCount.current = 0;
      currentToolCallRef.current = null;
      messageStartTimesRef.current = {};
    }
  }, [events.length]);

  // Process workflow events into chat messages
  useEffect(() => {
    // Only process new events that haven't been processed yet
    const newEvents = events.slice(processedEventCount.current);
    processedEventCount.current = events.length;

    newEvents.forEach((event) => {
      // Workflow events
      if (event.type === "response.workflow_event.complete" && "data" in event && event.data) {
        const data = event.data as {
          event_type?: string;
          executor_id?: string;
          data?: unknown;
        };

        const executorId = data.executor_id;
        if (!executorId) return;

        // ExecutorInvokedEvent - create new message for this executor
        if (data.event_type === "ExecutorInvokedEvent") {
          currentExecutorRef.current = executorId;

          setMessages((prev) => {
            // Check if message already exists
            if (prev.some((m) => m.executorId === executorId && m.role === "assistant")) {
              return prev;
            }

            const messageId = `${executorId}-${Date.now()}`;
            // Start timing for this message
            messageStartTimesRef.current[messageId] = Date.now();

            const newMessage: ChatMessage = {
              id: messageId,
              executorId,
              executorName: executorId,
              role: "assistant",
              content: "",
              isIntermediate: true,
              toolCalls: [],
              timestamp: new Date().toISOString(),
              state: "streaming",
            };

            return [...prev, newMessage];
          });
        }

        // ExecutorCompletedEvent - mark message as completed
        if (data.event_type === "ExecutorCompletedEvent") {
          lastExecutorRef.current = executorId;

          setMessages((prev) =>
            prev.map((m) => {
              if (m.executorId === executorId && m.role === "assistant") {
                // Calculate duration if timing exists
                let reasoningDuration = undefined;
                if (messageStartTimesRef.current[m.id]) {
                  const elapsed = Date.now() - messageStartTimesRef.current[m.id];
                  reasoningDuration = Math.max(1, Math.ceil(elapsed / 1000));
                  // Clean up the timing ref
                  delete messageStartTimesRef.current[m.id];
                }
                return { ...m, state: "completed" as const, reasoningDuration };
              }
              return m;
            })
          );

          if (currentExecutorRef.current === executorId) {
            currentExecutorRef.current = null;
          }
        }

        // WorkflowCompletedEvent - mark last executor as final output
        if (data.event_type === "WorkflowCompletedEvent") {
          const finalExecutorId = lastExecutorRef.current;
          if (finalExecutorId) {
            setMessages((prev) =>
              prev.map((m) =>
                m.executorId === finalExecutorId && m.role === "assistant"
                  ? { ...m, isIntermediate: false }
                  : m
              )
            );
          }
        }
      }

      // Text deltas - append to current executor's message
      if (event.type === "response.output_text.delta" && "delta" in event && event.delta) {
        const executorId = currentExecutorRef.current;
        if (!executorId) return;

        setMessages((prev) =>
          prev.map((m) =>
            m.executorId === executorId && m.role === "assistant"
              ? { ...m, content: m.content + event.delta }
              : m
          )
        );
      }

      // Function call added
      if (event.type === "response.output_item.added" && "item" in event && event.item) {
        const item = event.item as { type?: string; call_id?: string; name?: string };
        if (item.type === "function" && item.call_id && item.name) {
          const executorId = currentExecutorRef.current;
          if (!executorId) return;

          const callId = item.call_id;
          const callName = item.name;

          currentToolCallRef.current = callId;

          setMessages((prev) =>
            prev.map((m) => {
              if (m.executorId === executorId && m.role === "assistant") {
                const toolCalls = m.toolCalls || [];
                // Don't duplicate
                if (toolCalls.some((t) => t.id === callId)) return m;

                return {
                  ...m,
                  toolCalls: [
                    ...toolCalls,
                    {
                      id: callId,
                      name: callName,
                      input: "",
                      state: "input-streaming" as const,
                    },
                  ],
                };
              }
              return m;
            })
          );
        }
      }

      // Function call arguments delta
      if (event.type === "response.function_call_arguments.delta" && "delta" in event) {
        const toolCallId = currentToolCallRef.current;
        if (!toolCallId) return;

        setMessages((prev) =>
          prev.map((m) => {
            if (m.toolCalls) {
              return {
                ...m,
                toolCalls: m.toolCalls.map((t) => {
                  if (t.id === toolCallId) {
                    const currentInput = typeof t.input === "string" ? t.input : JSON.stringify(t.input || "");
                    const newInput = currentInput + (event.delta || "");

                    try {
                      return {
                        ...t,
                        input: JSON.parse(newInput),
                        state: "input-available" as const,
                      };
                    } catch {
                      return { ...t, input: newInput };
                    }
                  }
                  return t;
                }),
              };
            }
            return m;
          })
        );
      }

      // Function result
      if (event.type === "response.function_result.complete" && "data" in event && event.data) {
        const data = event.data as { call_id?: string; result?: unknown };
        if (!data.call_id) return;

        setMessages((prev) =>
          prev.map((m) => {
            if (m.toolCalls) {
              return {
                ...m,
                toolCalls: m.toolCalls.map((t) =>
                  t.id === data.call_id
                    ? {
                        ...t,
                        output: data.result,
                        state: "output-available" as const,
                      }
                    : t
                ),
              };
            }
            return m;
          })
        );
      }
    });
  }, [events]);


  // Resize handler
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      setIsResizing(true);

      const startX = e.clientX;
      const startWidth = width;

      const handleMouseMove = (e: MouseEvent) => {
        const deltaX = startX - e.clientX;
        const maxWidth = window.innerWidth * MAX_WIDTH_PERCENT;
        const newWidth = Math.max(MIN_WIDTH, Math.min(maxWidth, startWidth + deltaX));
        setWidth(newWidth);
      };

      const handleMouseUp = () => {
        setIsResizing(false);
        document.removeEventListener("mousemove", handleMouseMove);
        document.removeEventListener("mouseup", handleMouseUp);
      };

      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
    },
    [width]
  );

  // Handle input submit
  const handleInputSubmit = (data: Record<string, unknown>) => {
    // Extract display text from data - try common field names
    let displayText = "";
    if (typeof data === "string") {
      displayText = data;
    } else {
      // Try to extract text from common field names
      const textField = data.text || data.message || data.content || data.input;
      displayText = typeof textField === "string" ? textField : JSON.stringify(data, null, 2);
    }

    // Add user message
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      executorId: "user",
      role: "user",
      content: displayText,
      isIntermediate: false,
      timestamp: new Date().toISOString(),
      state: "completed",
    };

    setMessages((prev) => [...prev, userMessage]);

    // Submit to workflow
    onSubmit(data);
  };

  // Collapsed view
  if (isCollapsed) {
    return (
      <div className="shrink-0 border-l border-border bg-gradient-to-b from-background to-muted/30 flex flex-col items-center py-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setIsCollapsed(false)}
          className="rounded-full p-3 hover:bg-primary/10 group transition-all"
          title="Expand chat"
        >
          <div className="relative">
            <Bot className="w-5 h-5 text-primary group-hover:scale-110 transition-transform" />
            {messages.length > 0 && (
              <span className="absolute -top-1 -right-1 w-2 h-2 bg-primary rounded-full animate-pulse" />
            )}
          </div>
        </Button>
      </div>
    );
  }

  // Expanded view
  return (
    <div
      className="shrink-0 border-l border-border bg-background flex flex-col relative h-full w-(--sidebar-width)"
      style={{ "--sidebar-width": `${width}px` } as React.CSSProperties}
    >
      {/* Resize handle */}
      <div
        className={cn(
          "absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-primary/20 transition-colors z-10",
          isResizing && "bg-primary/40"
        )}
        onMouseDown={handleMouseDown}
      >
        <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-12 bg-primary/30 hover:bg-primary rounded-full transition-colors" />
      </div>

      {/* Header */}
      <div className="shrink-0 border-b border-border bg-gradient-to-r from-background to-muted/30 p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-primary/10 rounded-lg">
              <Bot className="w-4 h-4 text-primary" />
            </div>
            <div>
              <h3 className="font-semibold text-sm">Workflow Chat Assistant</h3>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsCollapsed(true)}
            className="h-8 w-8 rounded-full hover:bg-muted"
            title="Collapse chat"
          >
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Messages area */}
      <Conversation className="flex-1 min-h-0 bg-gradient-to-b from-background to-muted/5">
        <ConversationContent className="px-6 py-8">
          {messages.length === 0 ? (
            <ConversationEmptyState
              icon={
                <div className="relative">
                  <div className="absolute inset-0 bg-primary/20 blur-3xl rounded-full animate-pulse" />
                  <div className="relative p-4 bg-gradient-to-br from-primary/10 to-primary/5 rounded-2xl border border-primary/20">
                    <Sparkles className="w-10 h-10 text-primary" />
                  </div>
                </div>
              }
              title="Initiate Workflow"
              description="Input to execute your workflow"
              className="min-h-[400px]"
            />
          ) : (
            <div className="flex flex-col gap-5">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={cn(
                    "animate-in fade-in-0 slide-in-from-bottom-2 duration-300",
                    message.state === "streaming" && "opacity-90"
                  )}
                >
                  <WorkflowChatMessage message={message} />
                </div>
              ))}
              {isStreaming && (
                <div className="flex items-center gap-2 text-muted-foreground text-sm px-2">
                  <Shimmer duration={1.5} className="font-medium">
                    Processing workflow...
                  </Shimmer>
                </div>
              )}
            </div>
          )}
        </ConversationContent>
      </Conversation>

      {/* Chat input */}
      <div className="shrink-0">
        <WorkflowChatInput
          inputSchema={inputSchema}
          onSubmit={handleInputSubmit}
          disabled={isStreaming}
        />
      </div>
    </div>
  );
}
