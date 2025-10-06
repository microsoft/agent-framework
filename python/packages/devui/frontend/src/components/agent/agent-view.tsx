/**
 * AgentView - Complete agent interaction interface
 * Features: Chat interface, message streaming, thread management
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { FileUpload } from "@/components/ui/file-upload";
import {
  AttachmentGallery,
  type AttachmentItem,
} from "@/components/ui/attachment-gallery";
import { MessageRenderer } from "@/components/message_renderer";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AgentDetailsModal } from "@/components/shared/agent-details-modal";
import {
  SendHorizontal,
  User,
  Bot,
  Plus,
  AlertCircle,
  Paperclip,
  Info,
  Trash2,
  FileText,
} from "lucide-react";
import { apiClient } from "@/services/api";
import type {
  AgentInfo,
  ChatMessage,
  RunAgentRequest,
  ThreadInfo,
  ExtendedResponseStreamEvent,
} from "@/types";

interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
}

type DebugEventHandler = (event: ExtendedResponseStreamEvent | "clear") => void;

interface AgentViewProps {
  selectedAgent: AgentInfo;
  onDebugEvent: DebugEventHandler;
}

interface MessageBubbleProps {
  message: ChatMessage;
}

function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isError = message.error;
  const Icon = isUser ? User : isError ? AlertCircle : Bot;

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-md border ${
          isUser
            ? "bg-primary text-primary-foreground"
            : isError
            ? "bg-orange-100 dark:bg-orange-900 text-orange-600 dark:text-orange-400 border-orange-200 dark:border-orange-800"
            : "bg-muted"
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
          className={`rounded px-3 py-2 text-sm break-all ${
            isUser
              ? "bg-primary text-primary-foreground"
              : isError
              ? "bg-orange-50 dark:bg-orange-950/50 text-orange-800 dark:text-orange-200 border border-orange-200 dark:border-orange-800"
              : "bg-muted"
          }`}
        >
          {isError && (
            <div className="flex items-start gap-2 mb-2">
              <AlertCircle className="h-4 w-4 text-orange-500 mt-0.5 flex-shrink-0" />
              <span className="font-medium text-sm">
                Unable to process request
              </span>
            </div>
          )}
          <div className={isError ? "text-xs leading-relaxed break-all" : ""}>
            <MessageRenderer
              contents={message.contents}
              isStreaming={message.streaming}
            />
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
          <span>{new Date(message.timestamp).toLocaleTimeString()}</span>
          {!isUser && message.usage && (
            <>
              <span>•</span>
              <span className="text-[11px]">
                {message.usage.total_tokens >= 1000
                  ? `${(message.usage.total_tokens / 1000).toFixed(2)}k`
                  : message.usage.total_tokens}{" "}
                tokens
                {message.usage.prompt_tokens > 0 && (
                  <span className="opacity-70">
                    {" "}
                    (
                    {message.usage.prompt_tokens >= 1000
                      ? `${(message.usage.prompt_tokens / 1000).toFixed(1)}k`
                      : message.usage.prompt_tokens}{" "}
                    in,{" "}
                    {message.usage.completion_tokens >= 1000
                      ? `${(message.usage.completion_tokens / 1000).toFixed(1)}k`
                      : message.usage.completion_tokens}{" "}
                    out)
                  </span>
                )}
              </span>
            </>
          )}
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
  });
  const [currentThread, setCurrentThread] = useState<ThreadInfo | undefined>(
    undefined
  );
  const [availableThreads, setAvailableThreads] = useState<ThreadInfo[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [attachments, setAttachments] = useState<AttachmentItem[]>([]);
  const [loadingThreads, setLoadingThreads] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [dragCounter, setDragCounter] = useState(0);
  const [pasteNotification, setPasteNotification] = useState<string | null>(
    null
  );
  const [detailsModalOpen, setDetailsModalOpen] = useState(false);
  const [threadUsage, setThreadUsage] = useState<{
    total_tokens: number;
    message_count: number;
  }>({ total_tokens: 0, message_count: 0 });

  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const accumulatedText = useRef<string>("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const currentMessageUsage = useRef<{
    total_tokens: number;
    prompt_tokens: number;
    completion_tokens: number;
  } | null>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatState.messages, chatState.isStreaming]);

  // Load threads when agent changes
  useEffect(() => {
    const loadThreads = async () => {
      if (!selectedAgent) return;

      setLoadingThreads(true);
      try {
        const threads = await apiClient.getThreads(selectedAgent.id);
        setAvailableThreads(threads);

        // Auto-select the most recent thread if available
        if (threads.length > 0) {
          const mostRecentThread = threads[0]; // Assuming threads are sorted by creation date (newest first)
          setCurrentThread(mostRecentThread);

          // Load messages for the selected thread
          try {
            const threadMessages = await apiClient.getThreadMessages(
              mostRecentThread.id
            );
            setChatState({
              messages: threadMessages,
              isStreaming: false,
            });
          } catch (error) {
            console.error("Failed to load thread messages:", error);
            setChatState({
              messages: [],
              isStreaming: false,
            });
          }
        }
      } catch (error) {
        console.error("Failed to load threads:", error);
        setAvailableThreads([]);
      } finally {
        setLoadingThreads(false);
      }
    };

    // Clear chat when agent changes
    setChatState({
      messages: [],
      isStreaming: false,
    });
    setCurrentThread(undefined);
    accumulatedText.current = "";

    loadThreads();
  }, [selectedAgent]);

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

  // Drag and drop handlers
  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragCounter((prev) => prev + 1);
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragOver(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const newCounter = dragCounter - 1;
    setDragCounter(newCounter);
    if (newCounter === 0) {
      setIsDragOver(false);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    setDragCounter(0);

    if (isSubmitting || chatState.isStreaming) return;

    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      await handleFilesSelected(files);
    }
  };

  // Paste handler
  const handlePaste = async (e: React.ClipboardEvent) => {
    const items = Array.from(e.clipboardData.items);
    const files: File[] = [];
    let hasProcessedText = false;
    const TEXT_THRESHOLD = 8000; // Convert to file if text is larger than this

    for (const item of items) {
      // Handle pasted images (screenshots)
      if (item.type.startsWith("image/")) {
        e.preventDefault();
        const blob = item.getAsFile();
        if (blob) {
          const timestamp = Date.now();
          files.push(
            new File([blob], `screenshot-${timestamp}.png`, { type: blob.type })
          );
        }
      }
      // Handle text - only process first text item (browsers often duplicate)
      else if (item.type === "text/plain" && !hasProcessedText) {
        hasProcessedText = true;

        // We need to check the text synchronously to decide whether to prevent default
        // Unfortunately, getAsString is async, so we'll prevent default for all text
        // and then decide whether to actually create a file or manually insert the text
        e.preventDefault();

        await new Promise<void>((resolve) => {
          item.getAsString((text) => {
            // Check if text should be converted to file
            const lineCount = (text.match(/\n/g) || []).length;
            const shouldConvert =
              text.length > TEXT_THRESHOLD ||
              lineCount > 50 || // Many lines suggests logs/data
              /^\s*[{[][\s\S]*[}\]]\s*$/.test(text) || // JSON-like
              /^<\?xml|^<html|^<!DOCTYPE/i.test(text); // XML/HTML

            if (shouldConvert) {
              // Create file for large/complex text
              const extension = detectFileExtension(text);
              const timestamp = Date.now();
              const blob = new Blob([text], { type: "text/plain" });
              files.push(
                new File([blob], `pasted-text-${timestamp}${extension}`, {
                  type: "text/plain",
                })
              );
            } else {
              // For small text, manually insert into textarea since we prevented default
              const textarea = textareaRef.current;
              if (textarea) {
                const start = textarea.selectionStart;
                const end = textarea.selectionEnd;
                const currentValue = textarea.value;
                const newValue = currentValue.slice(0, start) + text + currentValue.slice(end);
                setInputValue(newValue);

                // Restore cursor position after the inserted text
                setTimeout(() => {
                  textarea.selectionStart = textarea.selectionEnd = start + text.length;
                  textarea.focus();
                }, 0);
              }
            }
            resolve();
          });
        });
      }
    }

    // Process collected files
    if (files.length > 0) {
      await handleFilesSelected(files);

      // Show notification with appropriate icon
      const message =
        files.length === 1
          ? files[0].name.includes("screenshot")
            ? "Screenshot added as attachment"
            : "Large text converted to file"
          : `${files.length} files added`;

      setPasteNotification(message);
      setTimeout(() => setPasteNotification(null), 3000);
    }
  };

  // Detect file extension from content
  const detectFileExtension = (text: string): string => {
    const trimmed = text.trim();
    const lines = trimmed.split('\n');

    // JSON detection
    if (/^{[\s\S]*}$|^\[[\s\S]*\]$/.test(trimmed)) return ".json";

    // XML/HTML detection
    if (/^<\?xml|^<html|^<!DOCTYPE/i.test(trimmed)) return ".html";

    // Markdown detection (code blocks)
    if (/^```/.test(trimmed)) return ".md";

    // TSV detection (tabs with multiple lines)
    if (/\t/.test(text) && lines.length > 1) return ".tsv";

    // CSV detection (more strict) - need multiple lines with consistent comma patterns
    if (lines.length > 2) {
      const commaLines = lines.filter(line => line.includes(','));
      const semicolonLines = lines.filter(line => line.includes(';'));

      // If >50% of lines have commas and it looks tabular
      if (commaLines.length > lines.length * 0.5) {
        const avgCommas = commaLines.reduce((sum, line) => sum + (line.match(/,/g) || []).length, 0) / commaLines.length;
        if (avgCommas >= 2) return ".csv";
      }

      // If >50% of lines have semicolons and it looks tabular
      if (semicolonLines.length > lines.length * 0.5) {
        const avgSemicolons = semicolonLines.reduce((sum, line) => sum + (line.match(/;/g) || []).length, 0) / semicolonLines.length;
        if (avgSemicolons >= 2) return ".csv";
      }
    }

    return ".txt";
  };

  // Helper functions
  const getFileType = (file: File): AttachmentItem["type"] => {
    if (file.type.startsWith("image/")) return "image";
    if (file.type === "application/pdf") return "pdf";
    if (file.type.startsWith("audio/")) return "audio";
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
  const handleNewThread = useCallback(async () => {
    if (!selectedAgent) return;

    try {
      const newThread = await apiClient.createThread(selectedAgent.id);
      setCurrentThread(newThread);
      setAvailableThreads((prev) => [newThread, ...prev]);
      setChatState({
        messages: [],
        isStreaming: false,
      });
      setThreadUsage({ total_tokens: 0, message_count: 0 });
      accumulatedText.current = "";
    } catch (error) {
      console.error("Failed to create thread:", error);
    }
  }, [selectedAgent]);

  // Handle thread deletion
  const handleDeleteThread = useCallback(
    async (threadId: string, e?: React.MouseEvent) => {
      // Prevent event from bubbling to SelectItem
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }

      // Confirm deletion
      if (!confirm("Delete this thread? This cannot be undone.")) {
        return;
      }

      try {
        const success = await apiClient.deleteThread(threadId);
        if (success) {
          // Remove thread from available threads
          const updatedThreads = availableThreads.filter((t) => t.id !== threadId);
          setAvailableThreads(updatedThreads);

          // If deleted thread was selected, switch to another thread or clear chat
          if (currentThread?.id === threadId) {
            if (updatedThreads.length > 0) {
              // Select the most recent remaining thread
              const nextThread = updatedThreads[0];
              setCurrentThread(nextThread);

              // Load messages for the next thread
              try {
                const threadMessages = await apiClient.getThreadMessages(nextThread.id);
                setChatState({
                  messages: threadMessages,
                  isStreaming: false,
                });
              } catch (error) {
                console.error("Failed to load thread messages:", error);
                setChatState({
                  messages: [],
                  isStreaming: false,
                });
              }
            } else {
              // No threads left, clear everything
              setCurrentThread(undefined);
              setChatState({
                messages: [],
                isStreaming: false,
              });
              setThreadUsage({ total_tokens: 0, message_count: 0 });
              accumulatedText.current = "";
            }
          }

          // Clear debug panel
          onDebugEvent("clear");
        }
      } catch (error) {
        console.error("Failed to delete thread:", error);
        alert("Failed to delete thread. Please try again.");
      }
    },
    [availableThreads, currentThread, onDebugEvent]
  );

  // Handle thread selection
  const handleThreadSelect = useCallback(
    async (threadId: string) => {
      const thread = availableThreads.find((t) => t.id === threadId);
      if (!thread) return;

      setCurrentThread(thread);

      // Clear debug panel when switching threads
      onDebugEvent("clear");

      try {
        // Load thread messages from backend
        const threadMessages = await apiClient.getThreadMessages(threadId);

        setChatState({
          messages: threadMessages,
          isStreaming: false,
        });

        // Calculate cumulative usage for this thread
        const totalTokens = threadMessages.reduce(
          (sum, msg) => sum + (msg.usage?.total_tokens || 0),
          0
        );
        const messageCount = threadMessages.filter(
          (msg) => msg.role === "assistant" && msg.usage
        ).length;
        setThreadUsage({ total_tokens: totalTokens, message_count: messageCount });

        console.log(
          `Restored ${threadMessages.length} messages for thread ${threadId}`
        );
      } catch (error) {
        console.error("Failed to load thread messages:", error);
        // Fallback to clearing messages
        setChatState({
          messages: [],
          isStreaming: false,
        });
      }

      accumulatedText.current = "";
    },
    [availableThreads]
  );

  // Handle message sending
  const handleSendMessage = useCallback(
    async (request: RunAgentRequest) => {
      if (!selectedAgent) return;

      // Extract text and attachments from OpenAI format for UI display
      let displayText = "";
      const attachmentContents: import("@/types/agent-framework").Contents[] =
        [];

      // Parse OpenAI ResponseInputParam to extract display content
      for (const inputItem of request.input) {
        if (inputItem.type === "message" && Array.isArray(inputItem.content)) {
          for (const contentItem of inputItem.content) {
            if (contentItem.type === "input_text") {
              displayText += contentItem.text + " ";
            } else if (contentItem.type === "input_image") {
              attachmentContents.push({
                type: "data",
                uri: contentItem.image_url || "",
                media_type: "image/png", // Default, should extract from data URI
              } as import("@/types/agent-framework").DataContent);
            } else if (contentItem.type === "input_file") {
              const dataUri = `data:application/octet-stream;base64,${contentItem.file_data}`;
              // Determine media type from filename
              const filename = (contentItem as import("@/types/agent-framework").ResponseInputFileParam).filename || "";
              let mediaType = "application/octet-stream";

              if (filename.endsWith(".pdf")) mediaType = "application/pdf";
              else if (filename.endsWith(".txt")) mediaType = "text/plain";
              else if (filename.endsWith(".json")) mediaType = "application/json";
              else if (filename.endsWith(".csv")) mediaType = "text/csv";
              else if (filename.endsWith(".html")) mediaType = "text/html";
              else if (filename.endsWith(".md")) mediaType = "text/markdown";

              attachmentContents.push({
                type: "data",
                uri: dataUri,
                media_type: mediaType,
              } as import("@/types/agent-framework").DataContent);
            }
          }
        }
      }

      const userMessageContents: import("@/types/agent-framework").Contents[] =
        [
          ...(displayText.trim()
            ? [
                {
                  type: "text",
                  text: displayText.trim(),
                } as import("@/types/agent-framework").TextContent,
              ]
            : []),
          ...attachmentContents,
        ];

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
        // If no thread selected, create one automatically
        let threadToUse = currentThread;
        if (!threadToUse) {
          try {
            threadToUse = await apiClient.createThread(selectedAgent.id);
            setCurrentThread(threadToUse);
            setAvailableThreads((prev) => [threadToUse!, ...prev]);
          } catch (error) {
            console.error("Failed to create thread:", error);
          }
        }

        const apiRequest = {
          input: request.input,
          thread_id: threadToUse?.id,
        };

        // Clear text accumulator for new response
        accumulatedText.current = "";

        // Clear debug panel events for new agent run
        onDebugEvent("clear");

        // Use OpenAI-compatible API streaming - direct event handling
        const streamGenerator = apiClient.streamAgentExecutionOpenAI(
          selectedAgent.id,
          apiRequest
        );

        for await (const openAIEvent of streamGenerator) {
          // Pass all events to debug panel
          onDebugEvent(openAIEvent);

          // Handle usage events
          if (openAIEvent.type === "response.usage.complete") {
            const usageEvent = openAIEvent as import("@/types").ResponseUsageEventComplete;
            console.log("📊 Usage event received:", usageEvent.data);
            if (usageEvent.data) {
              currentMessageUsage.current = {
                total_tokens: usageEvent.data.total_tokens || 0,
                prompt_tokens: usageEvent.data.prompt_tokens || 0,
                completion_tokens: usageEvent.data.completion_tokens || 0,
              };
              console.log("📊 Set usage:", currentMessageUsage.current);
            }
          }

          // Handle error events from the stream
          if (openAIEvent.type === "error") {
            const errorEvent = openAIEvent as ExtendedResponseStreamEvent & {
              message?: string;
            };
            const errorMessage = errorEvent.message || "An error occurred";

            // Update assistant message with error and stop streaming
            setChatState((prev) => ({
              ...prev,
              isStreaming: false,
              messages: prev.messages.map((msg) =>
                msg.id === assistantMessage.id
                  ? {
                      ...msg,
                      contents: [
                        {
                          type: "text",
                          text: errorMessage,
                        },
                      ],
                      streaming: false,
                      error: true, // Add error flag for styling
                    }
                  : msg
              ),
            }));
            return; // Exit stream processing early on error
          }

          // Handle text delta events for chat
          if (
            openAIEvent.type === "response.output_text.delta" &&
            "delta" in openAIEvent &&
            openAIEvent.delta
          ) {
            accumulatedText.current += openAIEvent.delta;

            // Update assistant message with accumulated content
            setChatState((prev) => ({
              ...prev,
              messages: prev.messages.map((msg) =>
                msg.id === assistantMessage.id
                  ? {
                      ...msg,
                      contents: [
                        {
                          type: "text",
                          text: accumulatedText.current,
                        },
                      ],
                    }
                  : msg
              ),
            }));
          }

          // Handle completion/error by detecting when streaming stops
          // (Server will close the stream when done, so we'll exit the loop naturally)
        }

        // Stream ended - mark as complete and attach usage
        const finalUsage = currentMessageUsage.current;
        console.log("📊 Stream ended, attaching usage to message:", finalUsage);

        setChatState((prev) => ({
          ...prev,
          isStreaming: false,
          messages: prev.messages.map((msg) =>
            msg.id === assistantMessage.id
              ? {
                  ...msg,
                  streaming: false,
                  usage: finalUsage || undefined,
                }
              : msg
          ),
        }));

        // Update thread-level usage stats
        if (finalUsage) {
          setThreadUsage((prev) => ({
            total_tokens: prev.total_tokens + finalUsage.total_tokens,
            message_count: prev.message_count + 1,
          }));
          console.log("📊 Updated thread usage");
        }

        // Reset usage for next message
        currentMessageUsage.current = null;
      } catch (error) {
        console.error("Streaming error:", error);
        setChatState((prev) => ({
          ...prev,
          isStreaming: false,
          messages: prev.messages.map((msg) =>
            msg.id === assistantMessage.id
              ? {
                  ...msg,
                  contents: [
                    {
                      type: "text",
                      text: `Error: ${
                        error instanceof Error
                          ? error.message
                          : "Failed to get response"
                      }`,
                    },
                  ],
                  streaming: false,
                }
              : msg
          ),
        }));
      }
    },
    [selectedAgent, currentThread, onDebugEvent]
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
      // Create OpenAI Responses API format
      if (attachments.length > 0 || messageText) {
        const content: import("@/types/agent-framework").ResponseInputContent[] =
          [];

        // Add text content if present - EXACT OpenAI ResponseInputTextParam
        if (messageText) {
          content.push({
            text: messageText,
            type: "input_text",
          } as import("@/types/agent-framework").ResponseInputTextParam);
        }

        // Add attachments using EXACT OpenAI types
        for (const attachment of attachments) {
          const dataUri = await readFileAsDataURL(attachment.file);

          if (attachment.file.type.startsWith("image/")) {
            // EXACT OpenAI ResponseInputImageParam
            content.push({
              detail: "auto",
              type: "input_image",
              image_url: dataUri,
            } as import("@/types/agent-framework").ResponseInputImageParam);
          } else if (
            attachment.file.type === "text/plain" &&
            (attachment.file.name.includes("pasted-text-") ||
             attachment.file.name.endsWith(".txt") ||
             attachment.file.name.endsWith(".csv") ||
             attachment.file.name.endsWith(".json") ||
             attachment.file.name.endsWith(".html") ||
             attachment.file.name.endsWith(".md") ||
             attachment.file.name.endsWith(".tsv"))
          ) {
            // Convert all text files (from pasted large text) back to input_text
            const text = await attachment.file.text();
            content.push({
              text: text,
              type: "input_text",
            } as import("@/types/agent-framework").ResponseInputTextParam);
          } else {
            // EXACT OpenAI ResponseInputFileParam for other files
            const base64Data = dataUri.split(",")[1]; // Extract base64 part
            content.push({
              type: "input_file",
              file_data: base64Data,
              file_url: dataUri, // Use data URI as the URL
              filename: attachment.file.name,
            } as import("@/types/agent-framework").ResponseInputFileParam);
          }
        }

        const openaiInput: import("@/types/agent-framework").ResponseInputParam =
          [
            {
              type: "message",
              role: "user",
              content,
            },
          ];

        // Use pure OpenAI format
        await handleSendMessage({
          input: openaiInput,
          thread_id: currentThread?.id,
        });
      } else {
        // Simple text message using OpenAI format
        const openaiInput: import("@/types/agent-framework").ResponseInputParam =
          [
            {
              type: "message",
              role: "user",
              content: [
                {
                  text: messageText,
                  type: "input_text",
                } as import("@/types/agent-framework").ResponseInputTextParam,
              ],
            },
          ];

        await handleSendMessage({
          input: openaiInput,
          thread_id: currentThread?.id,
        });
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
      <div className="border-b pb-2  p-4 flex-shrink-0">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3 mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <h2 className="font-semibold text-sm truncate">
              <div className="flex items-center gap-2">
                <Bot className="h-4 w-4 flex-shrink-0" />
                <span className="truncate">Chat with {selectedAgent.name || selectedAgent.id}</span>
              </div>
            </h2>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setDetailsModalOpen(true)}
              className="h-6 w-6 p-0 flex-shrink-0"
              title="View agent details"
            >
              <Info className="h-4 w-4" />
            </Button>
          </div>

          {/* Thread Controls */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 flex-shrink-0">
            <Select
              value={currentThread?.id || ""}
              onValueChange={handleThreadSelect}
              disabled={loadingThreads || isSubmitting}
            >
              <SelectTrigger className="w-full sm:w-64">
                <SelectValue
                  placeholder={
                    loadingThreads
                      ? "Loading..."
                      : availableThreads.length === 0
                      ? "No threads"
                      : currentThread
                      ? `Thread ${currentThread.id.slice(-8)}`
                      : "Select thread"
                  }
                >
                  {currentThread && (
                    <div className="flex items-center gap-2 text-xs">
                      <span>Thread {currentThread.id.slice(-8)}</span>
                      {threadUsage.total_tokens > 0 && (
                        <>
                          <span className="text-muted-foreground">•</span>
                          <span className="text-muted-foreground">
                            {threadUsage.total_tokens >= 1000
                              ? `${(threadUsage.total_tokens / 1000).toFixed(1)}k`
                              : threadUsage.total_tokens}{" "}
                            tokens
                          </span>
                        </>
                      )}
                    </div>
                  )}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {availableThreads.map((thread) => (
                  <SelectItem key={thread.id} value={thread.id}>
                    <div className="flex items-center justify-between w-full">
                      <span>Thread {thread.id.slice(-8)}</span>
                      {thread.created_at && (
                        <span className="text-xs text-muted-foreground ml-3">
                          {new Date(thread.created_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Button
              variant="outline"
              size="icon"
              onClick={() => currentThread && handleDeleteThread(currentThread.id)}
              disabled={!currentThread || isSubmitting}
              title={currentThread ? `Delete Thread ${currentThread.id.slice(-8)}` : "No thread selected"}
            >
              <Trash2 className="h-4 w-4" />
            </Button>

            <Button
              variant="outline"
              size="lg"
              onClick={handleNewThread}
              disabled={!selectedAgent || isSubmitting}
              className="whitespace-nowrap"
            >
              <Plus className="h-4 w-4 mr-2" />
              New Thread
            </Button>
          </div>
        </div>

        {selectedAgent.description && (
          <p className="text-sm text-muted-foreground">
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

          {chatState.isStreaming && !isSubmitting && <TypingIndicator />}

          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="border-t flex-shrink-0">
        <div
          className={`p-4 relative transition-all duration-300 ease-in-out ${
            isDragOver ? "bg-blue-50 dark:bg-blue-950/20" : ""
          }`}
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
        >
          {/* Drag overlay */}
          {isDragOver && (
            <div className="absolute inset-2 border-2 border-dashed border-blue-400 dark:border-blue-500 rounded-lg bg-blue-50/80 dark:bg-blue-950/40 backdrop-blur-sm flex items-center justify-center transition-all duration-200 ease-in-out z-10">
              <div className="text-center">
                <div className="text-blue-600 dark:text-blue-400 text-sm font-medium mb-1">
                  Drop files here
                </div>
                <div className="text-blue-500 dark:text-blue-500 text-xs">
                  Images, PDFs, and other files
                </div>
              </div>
            </div>
          )}

          {/* Attachment gallery */}
          {attachments.length > 0 && (
            <div className="mb-3">
              <AttachmentGallery
                attachments={attachments}
                onRemoveAttachment={handleRemoveAttachment}
              />
            </div>
          )}

          {/* Paste notification */}
          {pasteNotification && (
            <div
              className="absolute bottom-24 left-1/2 -translate-x-1/2 z-20
                          bg-blue-500 text-white px-4 py-2 rounded-full text-sm
                          animate-in slide-in-from-bottom-2 fade-in duration-200
                          flex items-center gap-2 shadow-lg"
            >
              {pasteNotification.includes("screenshot") ? (
                <Paperclip className="h-3 w-3" />
              ) : (
                <FileText className="h-3 w-3" />
              )}
              {pasteNotification}
            </div>
          )}

          {/* Input form */}
          <form onSubmit={handleSubmit} className="flex gap-2 items-end">
            <Textarea
              ref={textareaRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onPaste={handlePaste}
              onKeyDown={(e) => {
                // Submit on Enter (without shift)
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
              placeholder={`Message ${
                selectedAgent.name || selectedAgent.id
              }... (Shift+Enter for new line)`}
              disabled={isSubmitting || chatState.isStreaming}
              className="flex-1 min-h-[40px] max-h-[200px] resize-none"
              style={{ fieldSizing: "content" } as React.CSSProperties}
            />
            <FileUpload
              onFilesSelected={handleFilesSelected}
              disabled={isSubmitting || chatState.isStreaming}
            />
            <Button
              type="submit"
              size="icon"
              disabled={!canSendMessage}
              className="shrink-0 h-10"
            >
              {isSubmitting ? (
                <LoadingSpinner size="sm" />
              ) : (
                <SendHorizontal className="h-4 w-4" />
              )}
            </Button>
          </form>
        </div>
      </div>

      {/* Agent Details Modal */}
      <AgentDetailsModal
        agent={selectedAgent}
        open={detailsModalOpen}
        onOpenChange={setDetailsModalOpen}
      />
    </div>
  );
}
