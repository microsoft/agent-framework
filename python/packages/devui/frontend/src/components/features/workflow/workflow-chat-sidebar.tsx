import { useState, useEffect, useRef, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { WorkflowChatMessage, type ChatMessage } from "./workflow-chat-message";
import { WorkflowChatInput } from "./workflow-chat-input";
import type { ExtendedResponseStreamEvent, JSONSchemaProperty } from "@/types";
import { MessageSquare, ChevronRight } from "lucide-react";
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
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const currentExecutorRef = useRef<string | null>(null);
  const lastExecutorRef = useRef<string | null>(null);
  const processedEventCount = useRef<number>(0);
  const currentToolCallRef = useRef<string | null>(null);

  // Auto-scroll
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

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

            const newMessage: ChatMessage = {
              id: `${executorId}-${Date.now()}`,
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
            prev.map((m) =>
              m.executorId === executorId && m.role === "assistant"
                ? { ...m, state: "completed" as const }
                : m
            )
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

  // Auto-scroll during streaming
  useEffect(() => {
    if (isStreaming || messages.length > 0) {
      scrollToBottom();
    }
  }, [messages, isStreaming, scrollToBottom]);

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
      <div className="shrink-0 border-l border-border bg-muted/30">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setIsCollapsed(false)}
          className="h-full rounded-none px-2"
          title="Expand chat"
        >
          <MessageSquare className="w-4 h-4" />
        </Button>
      </div>
    );
  }

  // Expanded view
  return (
    <div
      className="shrink-0 border-l border-border bg-background flex flex-col relative h-full"
      style={{ width: `${width}px` }}
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
      <div className="shrink-0 border-b border-border p-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-muted-foreground" />
          <h3 className="font-semibold text-sm">Workflow Chat</h3>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setIsCollapsed(true)}
          className="h-6 w-6 p-0"
          title="Collapse chat"
        >
          <ChevronRight className="w-4 h-4" />
        </Button>
      </div>

      {/* Messages area */}
      <ScrollArea className="flex-1 min-h-0">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm py-12">
            <div className="text-center">
              <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p>No messages yet</p>
              <p className="text-xs mt-1">Submit input below to start execution</p>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4 py-6 px-4">
            {messages.map((message) => (
              <WorkflowChatMessage key={message.id} message={message} />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </ScrollArea>

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
