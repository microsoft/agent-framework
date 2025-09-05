/**
 * ChatPanel - Clean conversation interface with streaming support
 * Features: Real-time message updates, typing indicators, auto-scroll
 */

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Send, User, Bot, Workflow, Loader2 } from "lucide-react";
import type { AgentInfo, ChatMessage } from "@/types";

interface ChatPanelProps {
  selectedItem?: AgentInfo;
  messages: ChatMessage[];
  onSendMessage: (message: string) => void;
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
          <div className="whitespace-pre-wrap break-words">
            {message.content}
            {message.streaming && (
              <span className="ml-1 inline-block h-2 w-2 animate-pulse rounded-full bg-current" />
            )}
          </div>
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
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!inputValue.trim() || isSubmitting || !selectedItem) return;

    setIsSubmitting(true);
    const message = inputValue.trim();
    setInputValue("");

    try {
      onSendMessage(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const canSendMessage =
    selectedItem && !isSubmitting && !isStreaming && inputValue.trim();

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Header */}
      <div className="border-b p-4 flex-shrink-0">
        <h2 className="font-semibold">
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
            "Select an agent to start chatting"
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
      <div className="border-t p-4 flex-shrink-0">
        {selectedItem ? (
          <form onSubmit={handleSubmit} className="flex gap-2">
            <Input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={`Message ${selectedItem.name || selectedItem.id}...`}
              disabled={isSubmitting || isStreaming}
              className="flex-1"
            />
            <Button
              type="submit"
              size="icon"
              disabled={!canSendMessage}
              className="shrink-0"
            >
              {isSubmitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </form>
        ) : (
          <div className="text-center text-muted-foreground text-sm py-2">
            Select an agent from the dropdown to start chatting
          </div>
        )}
      </div>
    </div>
  );
}
