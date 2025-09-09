/**
 * ChatPanel - Rich conversation interface with attachment support
 * Features: File uploads, rich message rendering, streaming support
 */

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { FileUpload } from "@/components/ui/file-upload";
import { AttachmentGallery, type AttachmentItem } from "@/components/ui/attachment-gallery";
import { MessageRenderer } from "@/components/message_renderer";
import { Send, User, Bot, Workflow } from "lucide-react";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import type { AgentInfo, WorkflowInfo, ChatMessage, RunAgentRequest } from "@/types";

interface ChatPanelProps {
  selectedItem?: AgentInfo | WorkflowInfo;
  messages: ChatMessage[];
  onSendMessage: (request: RunAgentRequest["messages"]) => void;
  isStreaming?: boolean;
}

interface MessageBubbleProps {
  message: ChatMessage;
  agentType?: "agent" | "workflow";
}

function MessageBubble({ message, agentType }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const Icon = isUser ? User : agentType === "workflow" ? Workflow : Bot;

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
          className={`rounded-lg px-3 py-2 text-sm ${
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

function TypingIndicator({ agentType }: { agentType?: "agent" | "workflow" }) {
  const Icon = agentType === "workflow" ? Workflow : Bot;

  return (
    <div className="flex gap-3">
      <div className="flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-md border bg-muted">
        <Icon className="h-4 w-4" />
      </div>
      <div className="flex items-center space-x-1 rounded-lg bg-muted px-3 py-2">
        <div className="flex space-x-1">
          <div className="h-2 w-2 animate-bounce rounded-full bg-current [animation-delay:-0.3s]" />
          <div className="h-2 w-2 animate-bounce rounded-full bg-current [animation-delay:-0.15s]" />
          <div className="h-2 w-2 animate-bounce rounded-full bg-current" />
        </div>
      </div>
    </div>
  );
}

export function ChatPanel({
  selectedItem,
  messages,
  onSendMessage,
  isStreaming = false,
}: ChatPanelProps) {
  const [inputValue, setInputValue] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [attachments, setAttachments] = useState<AttachmentItem[]>([]);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if ((!inputValue.trim() && attachments.length === 0) || isSubmitting || !selectedItem) return;

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

        const richMessage = [{
          role: "user" as const,
          contents,
        }];

        onSendMessage(richMessage);
      } else {
        // Simple string message for backward compatibility
        onSendMessage(messageText);
      }

      // Clear attachments after sending
      setAttachments([]);
    } finally {
      setIsSubmitting(false);
    }
  };

  const canSendMessage =
    selectedItem && !isSubmitting && !isStreaming && (inputValue.trim() || attachments.length > 0);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Header */}
      <div className="border-b p-4 flex-shrink-0">
        <h2 className="font-semiboldd text-sm">
          {selectedItem ? (
            <div className="flex items-center gap-2">
              {selectedItem.type === "workflow" ? (
                <Workflow className="h-4 w-4" />
              ) : (
                <Bot className="h-4 w-4" />
              )}
              Chat with {selectedItem.name || selectedItem.id}
            </div>
          ) : (
            "Select an agent or workflow from the dropdown to begin"
          )}
        </h2>
        {selectedItem?.description && (
          <p className="text-sm text-muted-foreground mt-1">
            {selectedItem.description}
          </p>
        )}
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 p-4 h-0" ref={scrollAreaRef}>
        <div className="space-y-4">
          {messages.length === 0 && selectedItem ? (
            <div className="flex flex-col items-center justify-center h-32 text-center">
              <div className="text-muted-foreground text-sm">
                Start a conversation with {selectedItem.name || selectedItem.id}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                Type a message below to begin
              </div>
            </div>
          ) : (
            messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                agentType={selectedItem?.type}
              />
            ))
          )}

          {isStreaming && <TypingIndicator agentType={selectedItem?.type} />}

          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="border-t flex-shrink-0">
        {selectedItem ? (
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
                placeholder={`Message ${selectedItem.name || selectedItem.id}...`}
                disabled={isSubmitting || isStreaming}
                className="flex-1"
              />
              <FileUpload
                onFilesSelected={handleFilesSelected}
                disabled={isSubmitting || isStreaming}
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
        ) : (
          <div className="text-center text-muted-foreground text-sm py-2">
            Select an agent or workflow from the dropdown to begin
          </div>
        )}
      </div>
    </div>
  );
}
