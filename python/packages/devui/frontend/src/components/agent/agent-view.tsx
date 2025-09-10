/**
 * AgentView - Complete agent interaction interface
 * Features: Chat interface, message streaming, thread management
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { FileUpload } from "@/components/ui/file-upload";
import {
  AttachmentGallery,
  type AttachmentItem,
} from "@/components/ui/attachment-gallery";
import { MessageRenderer } from "@/components/message_renderer";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { Send, User, Bot, Plus } from "lucide-react";
import { apiClient } from "@/services/api";
import {
  extractMessageContent,
  updateRichMessageContents,
  useFunctionCallAccumulator,
  type DebugEventHandler,
} from "@/components/shared/chat-base";
import type {
  AgentInfo,
  ChatMessage,
  ChatState,
  RunAgentRequest,
  ThreadInfo,
} from "@/types";

interface AgentViewProps {
  selectedAgent: AgentInfo;
  onDebugEvent: DebugEventHandler;
}

interface MessageBubbleProps {
  message: ChatMessage;
}

function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const Icon = isUser ? User : Bot;

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-md border ${
          isUser ? "bg-primary text-primary-foreground" : "bg-muted"
        }`}
      >
        <Icon className="h-4 w-4" />
      </div>

      <div
        className={`flex flex-col space-y-1 ${
          isUser ? "items-end" : "items-start"
        } max-w-[80%]`}
      >
        <div
          className={`rounded px-3 py-2 text-sm ${
            isUser ? "bg-primary text-primary-foreground" : "bg-muted"
          }`}
        >
          <MessageRenderer
            contents={message.contents}
            isStreaming={message.streaming}
          />
        </div>

        <div className="text-xs text-muted-foreground font-mono">
          {new Date(message.timestamp).toLocaleTimeString()}
        </div>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex gap-3">
      <div className="flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-md border bg-muted">
        <Bot className="h-4 w-4" />
      </div>
      <div className="flex items-center space-x-1 rounded bg-muted px-3 py-2">
        <div className="flex space-x-1">
          <div className="h-2 w-2 animate-bounce rounded-full bg-current [animation-delay:-0.3s]" />
          <div className="h-2 w-2 animate-bounce rounded-full bg-current [animation-delay:-0.15s]" />
          <div className="h-2 w-2 animate-bounce rounded-full bg-current" />
        </div>
      </div>
    </div>
  );
}

export function AgentView({ selectedAgent, onDebugEvent }: AgentViewProps) {
  const [chatState, setChatState] = useState<ChatState>({
    messages: [],
    isStreaming: false,
    streamEvents: [],
  });
  const [currentThread, setCurrentThread] = useState<ThreadInfo | undefined>(
    undefined
  );
  const [inputValue, setInputValue] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [attachments, setAttachments] = useState<AttachmentItem[]>([]);

  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { functionCallAccumulator, clearAccumulator } =
    useFunctionCallAccumulator();

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatState.messages, chatState.isStreaming]);

  // Clear chat when agent changes
  useEffect(() => {
    setChatState({
      messages: [],
      isStreaming: false,
      streamEvents: [],
    });
    setCurrentThread(undefined);
    clearAccumulator();
  }, [selectedAgent.id, clearAccumulator]);

  // Handle file uploads
  const handleFilesSelected = async (files: File[]) => {
    const newAttachments: AttachmentItem[] = [];

    for (const file of files) {
      const id = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      const type = getFileType(file);

      let preview: string | undefined;
      if (type === "image") {
        preview = await readFileAsDataURL(file);
      }

      newAttachments.push({
        id,
        file,
        preview,
        type,
      });
    }

    setAttachments((prev) => [...prev, ...newAttachments]);
  };

  const handleRemoveAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((att) => att.id !== id));
  };

  // Helper functions
  const getFileType = (file: File): AttachmentItem["type"] => {
    if (file.type.startsWith("image/")) return "image";
    if (file.type === "application/pdf") return "pdf";
    return "other";
  };

  const readFileAsDataURL = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  };

  // Handle new thread creation
  const handleNewThread = useCallback(() => {
    setCurrentThread(undefined);
    setChatState({
      messages: [],
      isStreaming: false,
      streamEvents: [],
    });
    clearAccumulator();
  }, [clearAccumulator]);

  // Handle message sending
  const handleSendMessage = useCallback(
    async (messages: RunAgentRequest["messages"]) => {
      if (!selectedAgent) return;

      // Convert to ChatMessage format for UI state
      let userMessageContents: import("@/types/agent-framework").Contents[];
      if (typeof messages === "string") {
        userMessageContents = [
          {
            type: "text",
            text: messages,
          } as import("@/types/agent-framework").TextContent,
        ];
      } else {
        // Cast the contents to the proper Contents type
        userMessageContents = messages.flatMap(
          (msg) => msg.contents
        ) as import("@/types/agent-framework").Contents[];
      }

      // Add user message to UI state
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        contents: userMessageContents,
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
        contents: [],
        timestamp: new Date().toISOString(),
        streaming: true,
      };

      setChatState((prev) => ({
        ...prev,
        messages: [...prev.messages, assistantMessage],
      }));

      try {
        const request = {
          messages, // Use the correct field name!
          thread_id:
            chatState.messages.length > 0 ? currentThread?.id : undefined,
          options: { capture_traces: true },
        };

        // Use agent-specific API streaming
        const streamGenerator = apiClient.streamAgentExecution(
          selectedAgent.id,
          request
        );

        for await (const event of streamGenerator) {
          // Add event to debug stream
          setChatState((prev) => ({
            ...prev,
            streamEvents: [...prev.streamEvents, event],
          }));

          // Emit debug event to parent
          onDebugEvent(event);

          // Store thread_id when first received
          if (event.thread_id && !currentThread) {
            setCurrentThread({
              id: event.thread_id,
              agent_id: selectedAgent.id,
              created_at: new Date().toISOString(),
              message_count: 0,
            });
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
                        contents: updateRichMessageContents(
                          msg.contents,
                          newChunk
                        ),
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
    [
      selectedAgent,
      currentThread,
      chatState.messages,
      functionCallAccumulator,
      onDebugEvent,
    ]
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (
      (!inputValue.trim() && attachments.length === 0) ||
      isSubmitting ||
      !selectedAgent
    )
      return;

    setIsSubmitting(true);
    const messageText = inputValue.trim();
    setInputValue("");

    try {
      // Create rich message format
      if (attachments.length > 0 || messageText) {
        const contents: import("@/types/agent-framework").Contents[] = [];

        // Add text content if present
        if (messageText) {
          contents.push({
            type: "text",
            text: messageText,
          } as import("@/types/agent-framework").TextContent);
        }

        // Add attachments as data content
        for (const attachment of attachments) {
          const dataUri = await readFileAsDataURL(attachment.file);
          contents.push({
            type: "data",
            data: dataUri,
            mime_type: attachment.file.type,
          } as import("@/types/agent-framework").DataContent);
        }

        const richMessage = [
          {
            role: "user" as const,
            contents,
          },
        ];

        await handleSendMessage(richMessage);
      } else {
        // Simple string message for backward compatibility
        await handleSendMessage(messageText);
      }

      // Clear attachments after sending
      setAttachments([]);
    } finally {
      setIsSubmitting(false);
    }
  };

  const canSendMessage =
    selectedAgent &&
    !isSubmitting &&
    !chatState.isStreaming &&
    (inputValue.trim() || attachments.length > 0);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Header */}
      <div className="border-b pb-6 p-4 flex-shrink-0">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-sm">
            <div className="flex items-center gap-2">
              <Bot className="h-4 w-4" />
              Chat with {selectedAgent.name || selectedAgent.id}
            </div>
          </h2>
          <Button
            variant="outline"
            size="sm"
            onClick={handleNewThread}
            disabled={!selectedAgent}
          >
            <Plus className="h-4 w-4 mr-2" />
            New Thread
          </Button>
        </div>
        {selectedAgent.description && (
          <p className="text-sm text-muted-foreground mt-1">
            {selectedAgent.description}
          </p>
        )}
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 p-4 h-0" ref={scrollAreaRef}>
        <div className="space-y-4">
          {chatState.messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 text-center">
              <div className="text-muted-foreground text-sm">
                Start a conversation with{" "}
                {selectedAgent.name || selectedAgent.id}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                Type a message below to begin
              </div>
            </div>
          ) : (
            chatState.messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))
          )}

          {chatState.isStreaming && <TypingIndicator />}

          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="border-t flex-shrink-0">
        <div className="p-4">
          {/* Attachment gallery */}
          {attachments.length > 0 && (
            <div className="mb-3">
              <AttachmentGallery
                attachments={attachments}
                onRemoveAttachment={handleRemoveAttachment}
              />
            </div>
          )}

          {/* Input form */}
          <form onSubmit={handleSubmit} className="flex gap-2">
            <Input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={`Message ${
                selectedAgent.name || selectedAgent.id
              }...`}
              disabled={isSubmitting || chatState.isStreaming}
              className="flex-1"
            />
            <FileUpload
              onFilesSelected={handleFilesSelected}
              disabled={isSubmitting || chatState.isStreaming}
            />
            <Button
              type="submit"
              size="icon"
              disabled={!canSendMessage}
              className="shrink-0"
            >
              {isSubmitting ? (
                <LoadingSpinner size="sm" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
