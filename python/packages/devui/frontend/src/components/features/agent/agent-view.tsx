/**
 * AgentView - Complete agent interaction interface
 * Features: Chat interface, message streaming, conversation management
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
import { OpenAIMessageRenderer } from "./message-renderers/OpenAIMessageRenderer";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AgentDetailsModal } from "./agent-details-modal";
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
  Check,
  X,
  Copy,
  CheckCheck,
  RefreshCw,
} from "lucide-react";
import { apiClient } from "@/services/api";
import type {
  AgentInfo,
  RunAgentRequest,
  Conversation,
  ExtendedResponseStreamEvent,
} from "@/types";
import { useDevUIStore } from "@/stores";
import { loadStreamingState } from "@/services/streaming-state";

type DebugEventHandler = (event: ExtendedResponseStreamEvent | "clear") => void;

interface AgentViewProps {
  selectedAgent: AgentInfo;
  onDebugEvent: DebugEventHandler;
}

interface ConversationItemBubbleProps {
  item: import("@/types/openai").ConversationItem;
}

function ConversationItemBubble({ item }: ConversationItemBubbleProps) {
  const [isHovered, setIsHovered] = useState(false);
  const [copied, setCopied] = useState(false);

  // Extract text content from message for copying
  const getMessageText = () => {
    if (item.type === "message") {
      return item.content
        .filter((c) => c.type === "text")
        .map((c) => (c as import("@/types/openai").MessageTextContent).text)
        .join("\n");
    }
    return "";
  };

  const handleCopy = async () => {
    const text = getMessageText();
    if (!text) return;

    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  // Handle different item types
  if (item.type === "message") {
    const isUser = item.role === "user";
    const isError = item.status === "incomplete";
    const Icon = isUser ? User : isError ? AlertCircle : Bot;
    const messageText = getMessageText();

    return (
      <div
        className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
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
          <div className="relative group">
            <div
              className={`rounded px-3 py-2 text-sm ${
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
                <OpenAIMessageRenderer item={item} />
              </div>
            </div>

            {/* Copy button - appears on hover, always top-right inside */}
            {messageText && isHovered && (
              <button
                onClick={handleCopy}
                className="absolute top-1 right-1
                           p-1.5 rounded-md border shadow-sm
                           bg-background hover:bg-accent
                           text-muted-foreground hover:text-foreground
                           transition-all duration-200 ease-in-out
                           opacity-0 group-hover:opacity-100"
                title={copied ? "Copied!" : "Copy message"}
              >
                {copied ? (
                  <CheckCheck className="h-3.5 w-3.5 text-green-600 dark:text-green-400" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </button>
            )}
          </div>

          <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
            <span>
              {item.created_at
                ? new Date(item.created_at * 1000).toLocaleTimeString()
                : new Date().toLocaleTimeString() // Fallback for legacy items without timestamp
              }
            </span>
            {!isUser && item.usage && (
              <>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <span className="text-blue-600 dark:text-blue-400">
                    ↑{item.usage.input_tokens}
                  </span>
                  <span className="text-green-600 dark:text-green-400">
                    ↓{item.usage.output_tokens}
                  </span>
                  <span>({item.usage.total_tokens} tokens)</span>
                </span>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Function calls and results - render with neutral styling
  return (
    <div className="flex gap-3">
      <div className="flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-md border bg-muted">
        <Bot className="h-4 w-4" />
      </div>
      <div className="flex flex-col space-y-1 items-start max-w-[80%]">
        <div className="rounded px-3 py-2 text-sm bg-muted">
          <OpenAIMessageRenderer item={item} />
        </div>
      </div>
    </div>
  );
}

export function AgentView({ selectedAgent, onDebugEvent }: AgentViewProps) {
  // Get conversation state from Zustand
  const currentConversation = useDevUIStore((state) => state.currentConversation);
  const availableConversations = useDevUIStore((state) => state.availableConversations);
  const chatItems = useDevUIStore((state) => state.chatItems);
  const isStreaming = useDevUIStore((state) => state.isStreaming);
  const isSubmitting = useDevUIStore((state) => state.isSubmitting);
  const loadingConversations = useDevUIStore((state) => state.loadingConversations);
  const inputValue = useDevUIStore((state) => state.inputValue);
  const attachments = useDevUIStore((state) => state.attachments);
  const uiMode = useDevUIStore((state) => state.uiMode);
  const conversationUsage = useDevUIStore((state) => state.conversationUsage);
  const pendingApprovals = useDevUIStore((state) => state.pendingApprovals);
  const oaiMode = useDevUIStore((state) => state.oaiMode);

  // Get conversation actions from Zustand (only the ones we actually use)
  const setCurrentConversation = useDevUIStore((state) => state.setCurrentConversation);
  const setAvailableConversations = useDevUIStore((state) => state.setAvailableConversations);
  const setChatItems = useDevUIStore((state) => state.setChatItems);
  const setIsStreaming = useDevUIStore((state) => state.setIsStreaming);
  const setIsSubmitting = useDevUIStore((state) => state.setIsSubmitting);
  const setLoadingConversations = useDevUIStore((state) => state.setLoadingConversations);
  const setInputValue = useDevUIStore((state) => state.setInputValue);
  const setAttachments = useDevUIStore((state) => state.setAttachments);
  const updateConversationUsage = useDevUIStore((state) => state.updateConversationUsage);
  const setPendingApprovals = useDevUIStore((state) => state.setPendingApprovals);

  // Local UI state (not in Zustand - component-specific)
  const [isDragOver, setIsDragOver] = useState(false);
  const [dragCounter, setDragCounter] = useState(0);
  const [pasteNotification, setPasteNotification] = useState<string | null>(null);
  const [detailsModalOpen, setDetailsModalOpen] = useState(false);
  const [conversationError, setConversationError] = useState<{
    message: string;
    code?: string;
    type?: string;
  } | null>(null);
  const [isReloading, setIsReloading] = useState(false);

  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const currentMessageUsage = useRef<{
    total_tokens: number;
    input_tokens: number;
    output_tokens: number;
  } | null>(null);
  const userJustSentMessage = useRef<boolean>(false);
  const accumulatedTextRef = useRef<string>("");

  // Auto-scroll to bottom when new items arrive
  useEffect(() => {
    if (!messagesEndRef.current) return;

    // Check if user is near bottom (within 100px)
    const scrollContainer = scrollAreaRef.current?.querySelector('[data-radix-scroll-area-viewport]');

    let shouldScroll = false;

    if (scrollContainer) {
      const { scrollTop, scrollHeight, clientHeight } = scrollContainer;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;

      // Always scroll if user just sent a message, otherwise only if near bottom
      shouldScroll = userJustSentMessage.current || isNearBottom;
    } else {
      // Fallback if scroll container not found - always scroll
      shouldScroll = true;
    }

    if (shouldScroll) {
      // Use instant scroll during streaming for smooth chunk additions
      // Use smooth scroll when not streaming (new messages)
      messagesEndRef.current.scrollIntoView({
        behavior: isStreaming ? "instant" : "smooth"
      });
    }

    // Reset the flag after first scroll
    if (userJustSentMessage.current && !isStreaming) {
      userJustSentMessage.current = false;
    }
  }, [chatItems, isStreaming]);

  // Return focus to input after streaming completes
  useEffect(() => {
    if (!isStreaming && !isSubmitting) {
      textareaRef.current?.focus();
    }
  }, [isStreaming, isSubmitting]);

  // Load conversations when agent changes
  useEffect(() => {
    // Resume streaming after page refresh
    const resumeStreaming = async (
      assistantMessage: import("@/types/openai").ConversationMessage,
      conversation: Conversation,
      agent: AgentInfo
    ) => {
      // Load the stored state to get the response ID
      const storedState = loadStreamingState(conversation.id);
      if (!storedState || !storedState.responseId) {
        setIsStreaming(false);
        return;
      }

      try {
        // Use the stored responseId to resume the stream via GET /v1/responses/{responseId}
        const openAIRequest: import("@/types/agent-framework").AgentFrameworkRequest = {
          model: agent.id,
          input: [], // Not needed for resume (using GET)
          stream: true,
          conversation: conversation.id,
        };

        // Pass the response ID explicitly to trigger GET request
        const streamGenerator = apiClient.streamAgentExecutionOpenAIDirect(
          agent.id,
          openAIRequest,
          conversation.id,
          storedState.responseId  // Pass response ID for resume
        );

        for await (const openAIEvent of streamGenerator) {
          // Pass all events to debug panel
          onDebugEvent(openAIEvent);

          // Handle response.completed event
          if (openAIEvent.type === "response.completed") {
            const completedEvent = openAIEvent as import("@/types/openai").ResponseCompletedEvent;
            const usage = completedEvent.response?.usage;

            if (usage) {
              currentMessageUsage.current = {
                input_tokens: usage.input_tokens,
                output_tokens: usage.output_tokens,
                total_tokens: usage.total_tokens,
              };
            }
            continue;
          }

          // Handle response.failed event
          if (openAIEvent.type === "response.failed") {
            const failedEvent = openAIEvent as import("@/types/openai").ResponseFailedEvent;
            const error = failedEvent.response?.error;
            const errorMessage = error
              ? typeof error === "object" && "message" in error
                ? (error as any).message
                : JSON.stringify(error)
              : "Request failed";

            const currentItems = useDevUIStore.getState().chatItems;
            setChatItems(currentItems.map((item) =>
              item.id === assistantMessage.id && item.type === "message"
                ? {
                    ...item,
                    content: [
                      {
                        type: "text",
                        text: accumulatedTextRef.current || errorMessage,
                      } as import("@/types/openai").MessageTextContent,
                    ],
                    status: "incomplete" as const,
                  }
                : item
            ));
            setIsStreaming(false);
            return;
          }

          // Handle function approval request events
          if (openAIEvent.type === "response.function_approval.requested") {
            const approvalEvent = openAIEvent as import("@/types/openai").ResponseFunctionApprovalRequestedEvent;
            setPendingApprovals([
              ...useDevUIStore.getState().pendingApprovals,
              {
                request_id: approvalEvent.request_id,
                function_call: approvalEvent.function_call,
              },
            ]);
            continue;
          }

          // Handle function approval response events
          if (openAIEvent.type === "response.function_approval.responded") {
            const responseEvent = openAIEvent as import("@/types/openai").ResponseFunctionApprovalRespondedEvent;
            setPendingApprovals(
              useDevUIStore.getState().pendingApprovals.filter((a) => a.request_id !== responseEvent.request_id)
            );
            continue;
          }

          // Handle error events
          if (openAIEvent.type === "error") {
            const errorEvent = openAIEvent as ExtendedResponseStreamEvent & { message?: string };
            const errorMessage = errorEvent.message || "An error occurred";

            const currentItems = useDevUIStore.getState().chatItems;
            setChatItems(currentItems.map((item) =>
              item.id === assistantMessage.id && item.type === "message"
                ? {
                    ...item,
                    content: [
                      {
                        type: "text",
                        text: accumulatedTextRef.current || errorMessage,
                      } as import("@/types/openai").MessageTextContent,
                    ],
                    status: "incomplete" as const,
                  }
                : item
            ));
            setIsStreaming(false);
            return;
          }

          // Handle text delta events
          if (
            openAIEvent.type === "response.output_text.delta" &&
            "delta" in openAIEvent &&
            openAIEvent.delta
          ) {
            accumulatedTextRef.current += openAIEvent.delta;

            const currentItems = useDevUIStore.getState().chatItems;
            setChatItems(currentItems.map((item) =>
              item.id === assistantMessage.id && item.type === "message"
                ? {
                    ...item,
                    content: [
                      {
                        type: "text",
                        text: accumulatedTextRef.current,
                      } as import("@/types/openai").MessageTextContent,
                    ],
                    status: "in_progress" as const,
                  }
                : item
            ));
          }
        }

        // Stream ended - mark as complete
        const finalUsage = currentMessageUsage.current;

        const currentItems = useDevUIStore.getState().chatItems;
        setChatItems(currentItems.map((item) =>
          item.id === assistantMessage.id && item.type === "message"
            ? {
                ...item,
                status: "completed" as const,
                usage: finalUsage || undefined,
              }
            : item
        ));
        setIsStreaming(false);

        if (finalUsage) {
          updateConversationUsage(finalUsage.total_tokens);
        }

        currentMessageUsage.current = null;
      } catch (error) {
        const currentItems = useDevUIStore.getState().chatItems;
        setChatItems(currentItems.map((item) =>
          item.id === assistantMessage.id && item.type === "message"
            ? {
                ...item,
                content: [
                  {
                    type: "text",
                    text: `Error resuming stream: ${
                      error instanceof Error ? error.message : "Unknown error"
                    }`,
                  } as import("@/types/openai").MessageTextContent,
                ],
                status: "incomplete" as const,
              }
            : item
        ));
        setIsStreaming(false);
      }
    };

    const loadConversations = async () => {
      if (!selectedAgent) return;

      setLoadingConversations(true);
      try {
        // Step 1: Always try to list conversations from backend first
        // This ensures we get the latest data from the server
        try {
          const { data: conversations } = await apiClient.listConversations(
            selectedAgent.id
          );

          // Backend successfully returned conversations list
          setAvailableConversations(conversations);
          
          if (conversations.length > 0) {
            // Found conversations on backend - use most recent
            const mostRecent = conversations[0];
            setCurrentConversation(mostRecent);

            // Load conversation items from backend
            try {
              // Load all conversation items with pagination
              let allItems: unknown[] = [];
              let hasMore = true;
              let after: string | undefined = undefined;

              while (hasMore) {
                const result = await apiClient.listConversationItems(
                  mostRecent.id,
                  { order: "asc", after } // Load in chronological order (oldest first)
                );
                allItems = allItems.concat(result.data);
                hasMore = result.has_more;
                
                // Get the last item's ID for pagination
                if (hasMore && result.data.length > 0) {
                  const lastItem = result.data[result.data.length - 1] as { id?: string };
                  after = lastItem.id;
                }
              }

              // Use OpenAI ConversationItems directly (no conversion!)
              setChatItems(allItems as import("@/types/openai").ConversationItem[]);
              setIsStreaming(false);

              // Check for incomplete stream and resume if needed
              const state = loadStreamingState(mostRecent.id);
              
              if (state && !state.completed) {
                accumulatedTextRef.current = state.accumulatedText || "";
                // Add assistant message with resumed text
                const assistantMsg: import("@/types/openai").ConversationMessage = {
                  id: state.lastMessageId || `assistant-${Date.now()}`,
                  type: "message",
                  role: "assistant",
                  content: state.accumulatedText ? [{ type: "text", text: state.accumulatedText }] : [],
                  status: "in_progress",
                };
                setChatItems([...allItems as import("@/types/openai").ConversationItem[], assistantMsg]);
                setIsStreaming(true);

                // Resume streaming from where we left off
                setTimeout(() => {
                  resumeStreaming(assistantMsg, mostRecent, selectedAgent);
                }, 100);
              }

              // Scroll to bottom after loading conversation
              setTimeout(() => {
                messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
              }, 100);
            } catch {
              // 404 means conversation exists but has no items yet (newly created)
              // This is normal - just start with empty chat
              console.debug(`No items found for conversation ${mostRecent.id}, starting fresh`);
              setChatItems([]);
              setIsStreaming(false);
            }

            return;
          }
        } catch {
          // Backend doesn't support list endpoint (OpenAI, Azure, etc.)
          // This is expected - fall through to localStorage
        }

        // Step 2: Try localStorage (works with all backends)
        const cachedKey = `devui_convs_${selectedAgent.id}`;
        const cached = localStorage.getItem(cachedKey);

        if (cached) {
          try {
            const convs = JSON.parse(cached) as Conversation[];

            if (convs.length > 0) {
              // Validate that cached conversations still exist in backend
              // Try to load items for the most recent one to verify it exists
              try {
                await apiClient.listConversationItems(convs[0].id);

                // Success! Conversation exists in backend
                setAvailableConversations(convs);
                setCurrentConversation(convs[0]);
                setChatItems([]);
                setIsStreaming(false);
                return;
              } catch {
                // Cached conversation doesn't exist anymore (server restarted)
                // Clear stale cache and create new conversation
                console.debug(`Cached conversation ${convs[0].id} no longer exists, clearing cache`);
                localStorage.removeItem(cachedKey);
                // Fall through to Step 3
              }
            }
          } catch {
            // Invalid cache - clear it
            localStorage.removeItem(cachedKey);
          }
        }

        // Step 3: No conversations found - create new
        const newConversation = await apiClient.createConversation({
          agent_id: selectedAgent.id,
        });

        setCurrentConversation(newConversation);
        setAvailableConversations([newConversation]);
        setChatItems([]);
        setIsStreaming(false);
        setConversationError(null); // Clear any previous errors

        // Save to localStorage
        localStorage.setItem(cachedKey, JSON.stringify([newConversation]));
      } catch (error) {
        setAvailableConversations([]);
        setChatItems([]);
        setIsStreaming(false);

        // Extract error details for display
        const errorMessage = error instanceof Error ? error.message : "Failed to create conversation";
        setConversationError({
          message: errorMessage,
          type: "conversation_creation_error",
        });
      } finally {
        setLoadingConversations(false);
      }
    };

    // Clear chat when agent changes
    setChatItems([]);
    setIsStreaming(false);
    setCurrentConversation(undefined);
    accumulatedTextRef.current = "";

    loadConversations();
    // currentConversation is intentionally excluded - this effect should only run when agent changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAgent, onDebugEvent, setChatItems, setIsStreaming, setLoadingConversations, setAvailableConversations, setCurrentConversation, setPendingApprovals, updateConversationUsage]);

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

    setAttachments([...useDevUIStore.getState().attachments, ...newAttachments]);
  };

  const handleRemoveAttachment = (id: string) => {
    setAttachments(useDevUIStore.getState().attachments.filter((att) => att.id !== id));
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

    if (isSubmitting || isStreaming) return;

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
                const newValue =
                  currentValue.slice(0, start) + text + currentValue.slice(end);
                setInputValue(newValue);

                // Restore cursor position after the inserted text
                setTimeout(() => {
                  textarea.selectionStart = textarea.selectionEnd =
                    start + text.length;
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
    const lines = trimmed.split("\n");

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
      const commaLines = lines.filter((line) => line.includes(","));
      const semicolonLines = lines.filter((line) => line.includes(";"));

      // If >50% of lines have commas and it looks tabular
      if (commaLines.length > lines.length * 0.5) {
        const avgCommas =
          commaLines.reduce(
            (sum, line) => sum + (line.match(/,/g) || []).length,
            0
          ) / commaLines.length;
        if (avgCommas >= 2) return ".csv";
      }

      // If >50% of lines have semicolons and it looks tabular
      if (semicolonLines.length > lines.length * 0.5) {
        const avgSemicolons =
          semicolonLines.reduce(
            (sum, line) => sum + (line.match(/;/g) || []).length,
            0
          ) / semicolonLines.length;
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

  // Handle new conversation creation
  const handleNewConversation = useCallback(async () => {
    if (!selectedAgent) return;

    try {
      const newConversation = await apiClient.createConversation({
        agent_id: selectedAgent.id,
      });
      setCurrentConversation(newConversation);
      setAvailableConversations([newConversation, ...useDevUIStore.getState().availableConversations]);
      setChatItems([]);
      setIsStreaming(false);
      setConversationError(null); // Clear any previous errors
      // Reset conversation usage by setting it to initial state
      useDevUIStore.setState({ conversationUsage: { total_tokens: 0, message_count: 0 } });
      accumulatedTextRef.current = "";

      // Update localStorage cache with new conversation
      const cachedKey = `devui_convs_${selectedAgent.id}`;
      const updated = [newConversation, ...availableConversations];
      localStorage.setItem(cachedKey, JSON.stringify(updated));
    } catch (error) {
      // Failed to create conversation - show error to user
      const errorMessage = error instanceof Error ? error.message : "Failed to create conversation";
      setConversationError({
        message: errorMessage,
        type: "conversation_creation_error",
      });
    }
  }, [selectedAgent, setCurrentConversation, setAvailableConversations, setChatItems, setIsStreaming]);

  // Handle conversation deletion
  const handleDeleteConversation = useCallback(
    async (conversationId: string, e?: React.MouseEvent) => {
      // Prevent event from bubbling to SelectItem
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }

      // Confirm deletion
      if (!confirm("Delete this conversation? This cannot be undone.")) {
        return;
      }

      try {
        const success = await apiClient.deleteConversation(conversationId);
        if (success) {
          // Remove conversation from available conversations
          const updatedConversations = availableConversations.filter(
            (c) => c.id !== conversationId
          );
          setAvailableConversations(updatedConversations);

          // If deleted conversation was selected, switch to another conversation or clear chat
          if (currentConversation?.id === conversationId) {
            if (updatedConversations.length > 0) {
              // Select the most recent remaining conversation
              const nextConversation = updatedConversations[0];
              setCurrentConversation(nextConversation);
              setChatItems([]);
              setIsStreaming(false);
            } else {
              // No conversations left, clear everything
              setCurrentConversation(undefined);
              setChatItems([]);
              setIsStreaming(false);
              useDevUIStore.setState({ conversationUsage: { total_tokens: 0, message_count: 0 } });
              accumulatedTextRef.current = "";
            }
          }

          // Clear debug panel
          onDebugEvent("clear");
        }
      } catch {
        alert("Failed to delete conversation. Please try again.");
      }
    },
    [availableConversations, currentConversation, onDebugEvent, setAvailableConversations, setCurrentConversation, setChatItems, setIsStreaming]
  );

  // Handle entity reload (hot reload)
  const handleReloadEntity = useCallback(async () => {
    if (isReloading || !selectedAgent) return;

    setIsReloading(true);
    const addToast = useDevUIStore.getState().addToast;
    const updateAgent = useDevUIStore.getState().updateAgent;

    try {
      // Call backend reload endpoint
      await apiClient.reloadEntity(selectedAgent.id);

      // Fetch updated entity info
      const updatedAgent = await apiClient.getAgentInfo(selectedAgent.id);

      // Update store with fresh metadata
      updateAgent(updatedAgent);

      // Show success toast
      addToast({
        message: `${selectedAgent.name} has been reloaded successfully`,
        type: "success",
      });
    } catch (error) {
      // Show error toast
      const errorMessage = error instanceof Error ? error.message : "Failed to reload entity";
      addToast({
        message: `Failed to reload: ${errorMessage}`,
        type: "error",
        duration: 6000,
      });
    } finally {
      setIsReloading(false);
    }
  }, [isReloading, selectedAgent]);

  // Handle conversation selection
  const handleConversationSelect = useCallback(
    async (conversationId: string) => {
      const conversation = availableConversations.find(
        (c) => c.id === conversationId
      );
      if (!conversation) return;

      setCurrentConversation(conversation);

      // Clear debug panel when switching conversations
      onDebugEvent("clear");

      try {
        // Load conversation history from backend with pagination
        let allItems: unknown[] = [];
        let hasMore = true;
        let after: string | undefined = undefined;

        while (hasMore) {
          const result = await apiClient.listConversationItems(conversationId, {
            order: "asc", // Load in chronological order (oldest first)
            after,
          });
          allItems = allItems.concat(result.data);
          hasMore = result.has_more;
          
          // Get the last item's ID for pagination
          if (hasMore && result.data.length > 0) {
            const lastItem = result.data[result.data.length - 1] as { id?: string };
            after = lastItem.id;
          }
        }

        // Use OpenAI ConversationItems directly (no conversion!)
        const items = allItems as import("@/types/openai").ConversationItem[];

        setChatItems(items);
        setIsStreaming(false);

        // Calculate usage from loaded items
        useDevUIStore.setState({
          conversationUsage: {
            total_tokens: 0, // We don't have usage info in stored items
            message_count: items.length,
          }
        });

        // Check for incomplete stream and restore accumulated text
        const state = loadStreamingState(conversationId);
        if (state?.accumulatedText) {
          accumulatedTextRef.current = state.accumulatedText;
          // Add assistant message with resumed text - streaming will continue automatically
          const assistantMsg: import("@/types/openai").ConversationMessage = {
            id: `assistant-${Date.now()}`,
            type: "message",
            role: "assistant",
            content: [{ type: "output_text", text: state.accumulatedText }],
            status: "in_progress",
          };
          setChatItems([...items, assistantMsg]);
          setIsStreaming(true);
        }

        // Scroll to bottom after loading conversation
        setTimeout(() => {
          messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
        }, 100);
      } catch {
        // 404 means conversation doesn't exist or has no items yet
        // This can happen if server restarted (in-memory store cleared)
        console.debug(`No items found for conversation ${conversationId}, starting with empty chat`);
        setChatItems([]);
        setIsStreaming(false);
        useDevUIStore.setState({ conversationUsage: { total_tokens: 0, message_count: 0 } });
      }

      accumulatedTextRef.current = "";
    },
    [availableConversations, onDebugEvent, setCurrentConversation, setChatItems, setIsStreaming]
  );

  // Handle function approval responses
  const handleApproval = async (request_id: string, approved: boolean) => {
    const approval = pendingApprovals.find((a) => a.request_id === request_id);
    if (!approval) return;

    // Add user's decision as a visible message in the chat
    const messageTimestamp = Math.floor(Date.now() / 1000);
    const userDecisionMessage: import("@/types/openai").ConversationMessage = {
      id: `user-approval-${Date.now()}`,
      type: "message",
      role: "user",
      content: [
        {
          type: "function_approval_request",
          request_id: request_id,
          status: approved ? "approved" : "rejected",
          function_call: approval.function_call,
        } as import("@/types/openai").MessageFunctionApprovalRequestContent,
      ],
      status: "completed",
      created_at: messageTimestamp,
    };

    const currentItems = useDevUIStore.getState().chatItems;
    setChatItems([...currentItems, userDecisionMessage]);

    // Create approval response in OpenAI-compatible format
    const approvalInput: import("@/types/agent-framework").ResponseInputParam = [
      {
        type: "message",  // CRITICAL: Must set type for backend to recognize it
        role: "user",
        content: [
          {
            type: "function_approval_response",
            request_id: request_id,
            approved: approved,
            function_call: approval.function_call,
          } as import("@/types/openai").MessageFunctionApprovalResponseContent,
        ],
      },
    ];

    // Send approval response through the conversation
    const request: RunAgentRequest = {
      input: approvalInput,
      conversation_id: currentConversation?.id,
    };

    // Remove from pending immediately
    setPendingApprovals(
      useDevUIStore.getState().pendingApprovals.filter((a) => a.request_id !== request_id)
    );

    // Trigger send (we'll call this from the UI button handler)
    return request;
  };

  // Handle message sending
  const handleSendMessage = useCallback(
    async (request: RunAgentRequest) => {
      if (!selectedAgent) return;

      // Check if this is a function approval response (internal, don't show in chat)
      const isApprovalResponse = request.input.some(
        (inputItem) =>
          inputItem.type === "message" &&
          Array.isArray(inputItem.content) &&
          inputItem.content.some((c) => c.type === "function_approval_response")
      );

      // Extract content from OpenAI format to create ConversationMessage
      const messageContent: import("@/types/openai").MessageContent[] = [];

      // Parse OpenAI ResponseInputParam to extract content
      for (const inputItem of request.input) {
        if (inputItem.type === "message" && Array.isArray(inputItem.content)) {
          for (const contentItem of inputItem.content) {
            if (contentItem.type === "input_text") {
              messageContent.push({
                type: "text",
                text: contentItem.text,
              });
            } else if (contentItem.type === "input_image") {
              messageContent.push({
                type: "input_image",
                image_url: contentItem.image_url || "",
                detail: "auto",
              });
            } else if (contentItem.type === "input_file") {
              const fileItem = contentItem as import("@/types/agent-framework").ResponseInputFileParam;
              messageContent.push({
                type: "input_file",
                file_data: fileItem.file_data,
                filename: fileItem.filename,
              });
            }
          }
        }
      }

      // Capture timestamp once for both user and assistant messages
      const messageTimestamp = Math.floor(Date.now() / 1000); // Unix seconds

      // Only add user message to UI if it's not an approval response (internal messages)
      if (!isApprovalResponse && messageContent.length > 0) {
        const userMessage: import("@/types/openai").ConversationMessage = {
          id: `user-${Date.now()}`,
          type: "message",
          role: "user",
          content: messageContent,
          status: "completed",
          created_at: messageTimestamp,
        };

        setChatItems([...useDevUIStore.getState().chatItems, userMessage]);
      }

      setIsStreaming(true);

      // Create assistant message placeholder
      const assistantMessage: import("@/types/openai").ConversationMessage = {
        id: `assistant-${Date.now()}`,
        type: "message",
        role: "assistant",
        content: [], // Will be filled during streaming
        status: "in_progress",
        created_at: messageTimestamp,
      };

      setChatItems([...useDevUIStore.getState().chatItems, assistantMessage]);

      try {
        // If no conversation selected, create one automatically
        let conversationToUse = currentConversation;
        if (!conversationToUse) {
          try {
            conversationToUse = await apiClient.createConversation({
              agent_id: selectedAgent.id,
            });
            setCurrentConversation(conversationToUse);
            setAvailableConversations([conversationToUse, ...useDevUIStore.getState().availableConversations]);
            setConversationError(null); // Clear any previous errors
          } catch (error) {
            // Failed to create conversation - show error and stop execution
            const errorMessage = error instanceof Error ? error.message : "Failed to create conversation";
            setConversationError({
              message: errorMessage,
              type: "conversation_creation_error",
            });
            setIsSubmitting(false);
            setIsStreaming(false);
            return; // Stop execution - can't send message without conversation
          }
        }

        // Clear any previous streaming state for this conversation before starting new message
        if (conversationToUse?.id) {
          apiClient.clearStreamingState(conversationToUse.id);
        }

        const apiRequest = {
          input: request.input,
          conversation_id: conversationToUse?.id,
        };

        // Clear text accumulator for new response
        accumulatedTextRef.current = "";

        // Use OpenAI-compatible API streaming - direct event handling
        const streamGenerator = apiClient.streamAgentExecutionOpenAI(
          selectedAgent.id,
          apiRequest
        );

        for await (const openAIEvent of streamGenerator) {
          // Pass all events to debug panel
          onDebugEvent(openAIEvent);

          // Handle response.completed event (OpenAI standard)
          if (openAIEvent.type === "response.completed") {
            const completedEvent = openAIEvent as import("@/types/openai").ResponseCompletedEvent;
            const usage = completedEvent.response?.usage;

            if (usage) {
              currentMessageUsage.current = {
                input_tokens: usage.input_tokens,
                output_tokens: usage.output_tokens,
                total_tokens: usage.total_tokens,
              };
            }
            continue; // Continue processing other events
          }

          // Handle response.failed event (OpenAI standard)
          if (openAIEvent.type === "response.failed") {
            const failedEvent = openAIEvent as import("@/types/openai").ResponseFailedEvent;
            const error = failedEvent.response?.error;

            // Format error message with details
            let errorMessage = "Request failed";
            if (error) {
              if (typeof error === "object" && "message" in error) {
                errorMessage = error.message as string;
                if ("code" in error && error.code) {
                  errorMessage += ` (Code: ${error.code})`;
                }
              } else if (typeof error === "string") {
                errorMessage = error;
              }
            }

            // Update assistant message with error
            const currentItems = useDevUIStore.getState().chatItems;
            setChatItems(currentItems.map((item) =>
              item.id === assistantMessage.id && item.type === "message"
                ? {
                    ...item,
                    content: [
                      {
                        type: "text",
                        text: accumulatedTextRef.current || errorMessage,
                      } as import("@/types/openai").MessageTextContent,
                    ],
                    status: "incomplete" as const,
                  }
                : item
            ));
            setIsStreaming(false);
            return; // Exit stream processing on failure
          }

          // Handle function approval request events
          if (openAIEvent.type === "response.function_approval.requested") {
            const approvalEvent = openAIEvent as import("@/types/openai").ResponseFunctionApprovalRequestedEvent;

            // Add to pending approvals (for popup)
            setPendingApprovals([
              ...useDevUIStore.getState().pendingApprovals,
              {
                request_id: approvalEvent.request_id,
                function_call: approvalEvent.function_call,
              },
            ]);

            // Also add to chat UI to show function call progress
            const currentItems = useDevUIStore.getState().chatItems;
            setChatItems(currentItems.map((item) => {
              if (item.id === assistantMessage.id && item.type === "message") {
                return {
                  ...item,
                  content: [
                    ...item.content,
                    {
                      type: "function_approval_request",
                      request_id: approvalEvent.request_id,
                      status: "pending",
                      function_call: approvalEvent.function_call,
                    } as import("@/types/openai").MessageFunctionApprovalRequestContent,
                  ],
                  status: "in_progress" as const,
                };
              }
              return item;
            }));
            continue;
          }

          // Handle function result events (after function execution)
          if (openAIEvent.type === "response.function_result.complete") {
            const resultEvent = openAIEvent as import("@/types/openai").ResponseFunctionResultComplete;

            // Add function result as a separate conversation item for clear visibility
            const functionResultItem: import("@/types/openai").ConversationFunctionCallOutput = {
              id: `result-${Date.now()}`,
              type: "function_call_output",
              call_id: resultEvent.call_id,
              output: resultEvent.output,
              status: resultEvent.status === "completed" ? "completed" : "incomplete",
              created_at: Math.floor(Date.now() / 1000),
            };

            const currentItems = useDevUIStore.getState().chatItems;
            setChatItems([...currentItems, functionResultItem]);
            continue;
          }

          // Handle error events from the stream
          if (openAIEvent.type === "error") {
            const errorEvent = openAIEvent as ExtendedResponseStreamEvent & {
              message?: string;
            };
            const errorMessage = errorEvent.message || "An error occurred";

            // Update assistant message with error and stop streaming
            const currentItems = useDevUIStore.getState().chatItems;
            setChatItems(currentItems.map((item) =>
              item.id === assistantMessage.id && item.type === "message"
                ? {
                    ...item,
                    content: [
                      {
                        type: "text",
                        text: errorMessage,
                      } as import("@/types/openai").MessageTextContent,
                    ],
                    status: "incomplete" as const,
                  }
                : item
            ));
            setIsStreaming(false);
            return; // Exit stream processing early on error
          }

          // Handle output item added events (images, files, data)
          if (openAIEvent.type === "response.output_item.added") {
            const outputItemEvent = openAIEvent as import("@/types/openai").ResponseOutputItemAddedEvent;
            const item = outputItemEvent.item;

            // Add output items to assistant message content
            const currentItems = useDevUIStore.getState().chatItems;
            setChatItems(currentItems.map((chatItem) => {
              if (chatItem.id === assistantMessage.id && chatItem.type === "message") {
                const existingContent = chatItem.content;
                let newContent: import("@/types/openai").MessageContent | null = null;

                // Map output items to message content
                if (item.type === "output_image") {
                  newContent = {
                    type: "output_image",
                    image_url: item.image_url,
                    alt_text: item.alt_text,
                    mime_type: item.mime_type,
                  } as import("@/types/openai").MessageOutputImage;
                } else if (item.type === "output_file") {
                  newContent = {
                    type: "output_file",
                    filename: item.filename,
                    file_url: item.file_url,
                    file_data: item.file_data,
                    mime_type: item.mime_type,
                  } as import("@/types/openai").MessageOutputFile;
                } else if (item.type === "output_data") {
                  newContent = {
                    type: "output_data",
                    data: item.data,
                    mime_type: item.mime_type,
                    description: item.description,
                  } as import("@/types/openai").MessageOutputData;
                }

                // If we created new content, append it
                if (newContent) {
                  return {
                    ...chatItem,
                    content: [...existingContent, newContent],
                    status: "in_progress" as const,
                  };
                }
              }
              return chatItem;
            }));
            continue; // Continue to next event
          }

          // Handle text delta events for chat
          if (
            openAIEvent.type === "response.output_text.delta" &&
            "delta" in openAIEvent &&
            openAIEvent.delta
          ) {
            accumulatedTextRef.current += openAIEvent.delta;

            // Update assistant message with accumulated content
            // Preserve any existing non-text content (images, files, data)
            const currentItems = useDevUIStore.getState().chatItems;
            setChatItems(currentItems.map((item) => {
              if (item.id === assistantMessage.id && item.type === "message") {
                // Keep existing non-text content, update text content
                const existingNonTextContent = item.content.filter(c => c.type !== "text");
                return {
                  ...item,
                  content: [
                    ...existingNonTextContent,
                    {
                      type: "text",
                      text: accumulatedTextRef.current,
                    } as import("@/types/openai").MessageTextContent,
                  ],
                  status: "in_progress" as const,
                };
              }
              return item;
            }));
          }

          // Handle completion/error by detecting when streaming stops
          // (Server will close the stream when done, so we'll exit the loop naturally)
        }

        // Stream ended - mark as complete
        // Usage is provided via response.completed event (OpenAI standard)
        const finalUsage = currentMessageUsage.current;

        const currentItems = useDevUIStore.getState().chatItems;
        setChatItems(currentItems.map((item) =>
          item.id === assistantMessage.id && item.type === "message"
            ? {
                ...item,
                status: "completed" as const,
                usage: finalUsage || undefined,
              }
            : item
        ));
        setIsStreaming(false);

        // Update conversation-level usage stats
        if (finalUsage) {
          updateConversationUsage(finalUsage.total_tokens);
        }

        // Reset usage for next message
        currentMessageUsage.current = null;
      } catch (error) {
        const currentItems = useDevUIStore.getState().chatItems;
        setChatItems(currentItems.map((item) =>
          item.id === assistantMessage.id && item.type === "message"
            ? {
                ...item,
                content: [
                  {
                    type: "text",
                    text: `Error: ${
                      error instanceof Error
                        ? error.message
                        : "Failed to get response"
                    }`,
                  } as import("@/types/openai").MessageTextContent,
                ],
                status: "incomplete" as const,
              }
            : item
        ));
        setIsStreaming(false);
      }
    },
    [selectedAgent, currentConversation, onDebugEvent, setChatItems, setIsStreaming, setCurrentConversation, setAvailableConversations, setPendingApprovals, updateConversationUsage]
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (
      (!inputValue.trim() && attachments.length === 0) ||
      isSubmitting ||
      !selectedAgent
    )
      return;

    // Set flag to force scroll when user sends message
    userJustSentMessage.current = true;

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
          conversation_id: currentConversation?.id,
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
          conversation_id: currentConversation?.id,
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
    !isStreaming &&
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
                <span className="truncate">
                  {oaiMode.enabled
                    ? `Chat with ${oaiMode.model}`
                    : `Chat with ${selectedAgent.name || selectedAgent.id}`
                  }
                </span>
              </div>
            </h2>
            {!oaiMode.enabled && uiMode === "developer" && (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setDetailsModalOpen(true)}
                  className="h-6 w-6 p-0 flex-shrink-0"
                  title="View agent details"
                >
                  <Info className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleReloadEntity}
                  disabled={isReloading || selectedAgent.metadata?.source === "in_memory"}
                  className="h-6 w-6 p-0 flex-shrink-0"
                  title={
                    selectedAgent.metadata?.source === "in_memory"
                      ? "In-memory entities cannot be reloaded"
                      : isReloading
                      ? "Reloading..."
                      : "Reload entity code (hot reload)"
                  }
                >
                  <RefreshCw className={`h-4 w-4 ${isReloading ? "animate-spin" : ""}`} />
                </Button>
              </>
            )}
          </div>

          {/* Conversation Controls */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 flex-shrink-0">
            <Select
              value={currentConversation?.id || ""}
              onValueChange={handleConversationSelect}
              disabled={loadingConversations || isSubmitting}
            >
              <SelectTrigger className="w-full sm:w-64">
                <SelectValue
                  placeholder={
                    loadingConversations
                      ? "Loading..."
                      : availableConversations.length === 0
                      ? "No conversations"
                      : currentConversation
                      ? `Conversation ${currentConversation.id.slice(-8)}`
                      : "Select conversation"
                  }
                >
                  {currentConversation && (
                    <div className="flex items-center gap-2 text-xs">
                      <span>
                        Conversation {currentConversation.id.slice(-8)}
                      </span>
                      {conversationUsage.total_tokens > 0 && (
                        <>
                          <span className="text-muted-foreground">•</span>
                          <span className="text-muted-foreground">
                            {conversationUsage.total_tokens >= 1000
                              ? `${(
                                  conversationUsage.total_tokens / 1000
                                ).toFixed(1)}k`
                              : conversationUsage.total_tokens}{" "}
                            tokens
                          </span>
                        </>
                      )}
                    </div>
                  )}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {availableConversations.map((conversation) => (
                  <SelectItem key={conversation.id} value={conversation.id}>
                    <div className="flex items-center justify-between w-full">
                      <span>Conversation {conversation.id.slice(-8)}</span>
                      {conversation.created_at && (
                        <span className="text-xs text-muted-foreground ml-3">
                          {new Date(
                            conversation.created_at * 1000
                          ).toLocaleDateString()}
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
              onClick={() =>
                currentConversation &&
                handleDeleteConversation(currentConversation.id)
              }
              disabled={!currentConversation || isSubmitting}
              title={
                currentConversation
                  ? `Delete Conversation ${currentConversation.id.slice(-8)}`
                  : "No conversation selected"
              }
            >
              <Trash2 className="h-4 w-4" />
            </Button>

            <Button
              variant="outline"
              size="lg"
              onClick={handleNewConversation}
              disabled={!selectedAgent || isSubmitting}
              className="whitespace-nowrap "
            >
              <Plus className="h-4 w-4 mr-2" />
              <span className="hidden md:inline"> New Conversation</span>
            </Button>
          </div>
        </div>

        {oaiMode.enabled ? (
          <p className="text-sm text-muted-foreground">
            Using OpenAI model directly. Local agent tools and instructions are not applied.
          </p>
        ) : (
          selectedAgent.description && (
            <p className="text-sm text-muted-foreground">
              {selectedAgent.description}
            </p>
          )
        )}
      </div>

      {/* Error Banner */}
      {conversationError && (
        <div className="mx-4 mt-2 p-3 bg-destructive/10 border border-destructive/30 rounded-md flex items-start gap-2">
          <AlertCircle className="h-4 w-4 text-destructive mt-0.5 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-destructive">
              Failed to Create Conversation
            </div>
            <div className="text-xs text-destructive/90 mt-1 break-words">
              {conversationError.message}
            </div>
            {conversationError.code && (
              <div className="text-xs text-destructive/70 mt-1">
                Error Code: {conversationError.code}
              </div>
            )}
          </div>
          <button
            onClick={() => setConversationError(null)}
            className="text-destructive hover:text-destructive/80 flex-shrink-0"
            title="Dismiss error"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Messages */}
      <ScrollArea className="flex-1 p-4 h-0" ref={scrollAreaRef}>
        <div className="space-y-4">
          {chatItems.length === 0 ? (
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
            chatItems.map((item) => (
              <ConversationItemBubble key={item.id} item={item} />
            ))
          )}

          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Function Approval Prompt */}
      {pendingApprovals.length > 0 && (
        <div className="border-t bg-amber-50 dark:bg-amber-950/20 p-4 flex-shrink-0">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-amber-600 dark:text-amber-500 mt-0.5 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <h4 className="font-medium text-sm mb-2">Approval Required</h4>
              <div className="space-y-2">
                {pendingApprovals.map((approval) => (
                  <div
                    key={approval.request_id}
                    className="bg-white dark:bg-gray-900 rounded-lg p-3 border border-amber-200 dark:border-amber-900"
                  >
                    <div className="font-mono text-xs mb-3 break-all">
                      <span className="text-blue-600 dark:text-blue-400 font-semibold">
                        {approval.function_call.name}
                      </span>
                      <span className="text-gray-500">(</span>
                      <span className="text-gray-700 dark:text-gray-300">
                        {JSON.stringify(approval.function_call.arguments)}
                      </span>
                      <span className="text-gray-500">)</span>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={async () => {
                          const request = await handleApproval(
                            approval.request_id,
                            true
                          );
                          if (request) {
                            await handleSendMessage(request);
                          }
                        }}
                        variant="default"
                        className="flex-1 sm:flex-none"
                      >
                        <Check className="h-4 w-4 mr-1" />
                        Approve
                      </Button>
                      <Button
                        size="sm"
                        onClick={async () => {
                          const request = await handleApproval(
                            approval.request_id,
                            false
                          );
                          if (request) {
                            await handleSendMessage(request);
                          }
                        }}
                        variant="outline"
                        className="flex-1 sm:flex-none"
                      >
                        <X className="h-4 w-4 mr-1" />
                        Reject
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

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
              disabled={isSubmitting || isStreaming}
              className="flex-1 min-h-[40px] max-h-[200px] resize-none"
              style={{ fieldSizing: "content" } as React.CSSProperties}
            />
            <FileUpload
              onFilesSelected={handleFilesSelected}
              disabled={isSubmitting || isStreaming}
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
