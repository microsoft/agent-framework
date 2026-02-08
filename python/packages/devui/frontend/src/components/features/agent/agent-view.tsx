/**
 * AgentView - Complete agent interaction interface
 * Features: Chat interface, message streaming, conversation management
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { useCancellableRequest, isAbortError, useDragDrop } from "@/hooks";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatMessageInput } from "@/components/ui/chat-message-input";
import { OpenAIMessageRenderer } from "./message-renderers/OpenAIMessageRenderer";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AgentDetailsModal } from "./agent-details-modal";
import {
  User,
  Bot,
  Plus,
  AlertCircle,
  Info,
  Trash2,
  Check,
  X,
  Copy,
  CheckCheck,
  RefreshCw,
  Wrench,
  Square,
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
  toolCalls?: import("@/types/openai").ConversationFunctionCall[];
  toolResults?: import("@/types/openai").ConversationFunctionCallOutput[];
}

function ConversationItemBubble({ item, toolCalls = [], toolResults = [] }: ConversationItemBubbleProps) {
  // All hooks must be at the top - cannot be conditional
  const [isHovered, setIsHovered] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showToolDetails, setShowToolDetails] = useState(false); // For tool call expansion
  const showToolCalls = useDevUIStore((state) => state.showToolCalls);

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
            {/* Tool calls badge */}
            {!isUser && showToolCalls && toolCalls.length > 0 && (
              <>
                <span>•</span>
                <button
                  onClick={() => setShowToolDetails(!showToolDetails)}
                  className="flex items-center gap-1 hover:text-foreground transition-colors"
                  title={`${toolCalls.length} tool call${toolCalls.length > 1 ? 's' : ''} - click to ${showToolDetails ? 'hide' : 'show'} details`}
                >
                  <Wrench className="h-3 w-3" />
                  <span>{toolCalls.length}</span>
                </button>
              </>
            )}
          </div>

          {/* Expandable tool call details */}
          {!isUser && showToolDetails && toolCalls.length > 0 && (
            <div className="mt-2 ml-0 p-3 bg-muted/30 rounded-md border border-muted">
              <div className="space-y-2">
                {toolCalls.map((call) => {
                  // Find the matching result for this call
                  const result = toolResults.find(r => r.call_id === call.call_id);

                  return (
                    <div key={call.id} className="text-xs">
                      <div className="flex items-start gap-2">
                        <Wrench className="h-3 w-3 text-muted-foreground mt-0.5 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="font-mono text-muted-foreground">
                            <span className="text-blue-600 dark:text-blue-400">{call.name}</span>
                            <span className="text-muted-foreground/60 ml-1">
                              {call.arguments && (
                                <span className="break-all">({call.arguments})</span>
                              )}
                            </span>
                          </div>
                          {result && result.output && (
                            <div className="mt-1 pl-5 border-l-2 border-green-600/20">
                              <div className="flex items-start gap-1">
                                <Check className="h-3 w-3 text-green-600 dark:text-green-400 mt-0.5 flex-shrink-0" />
                                <pre className="font-mono text-muted-foreground whitespace-pre-wrap break-all">
                                  {result.output.substring(0, 200) + (result.output.length > 200 ? '...' : '')}
                                </pre>
                              </div>
                            </div>
                          )}
                          {call.status === "incomplete" && (
                            <div className="mt-1 pl-5 border-l-2 border-orange-600/20">
                              <div className="flex items-start gap-1">
                                <X className="h-3 w-3 text-orange-600 dark:text-orange-400 mt-0.5 flex-shrink-0" />
                                <span className="font-mono text-orange-600 dark:text-orange-400">Failed</span>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Function calls and results are now handled within message items
  // Don't render them as separate items anymore
  if (item.type === "function_call" || item.type === "function_call_output") {
    return null;
  }

  return null;
}

export function AgentView({ selectedAgent, onDebugEvent }: AgentViewProps) {
  // Get conversation state from Zustand
  const currentConversation = useDevUIStore((state) => state.currentConversation);
  const availableConversations = useDevUIStore((state) => state.availableConversations);
  const chatItems = useDevUIStore((state) => state.chatItems);
  const isStreaming = useDevUIStore((state) => state.isStreaming);
  const isSubmitting = useDevUIStore((state) => state.isSubmitting);
  const loadingConversations = useDevUIStore((state) => state.loadingConversations);
  const uiMode = useDevUIStore((state) => state.uiMode);
  const conversationUsage = useDevUIStore((state) => state.conversationUsage);
  const pendingApprovals = useDevUIStore((state) => state.pendingApprovals);
  const oaiMode = useDevUIStore((state) => state.oaiMode);
  const streamingEnabled = useDevUIStore((state) => state.streamingEnabled);

  // Get conversation actions from Zustand (only the ones we actually use)
  const setCurrentConversation = useDevUIStore((state) => state.setCurrentConversation);
  const setAvailableConversations = useDevUIStore((state) => state.setAvailableConversations);
  const setChatItems = useDevUIStore((state) => state.setChatItems);
  const setIsStreaming = useDevUIStore((state) => state.setIsStreaming);
  const setIsSubmitting = useDevUIStore((state) => state.setIsSubmitting);
  const setLoadingConversations = useDevUIStore((state) => state.setLoadingConversations);
  const updateConversationUsage = useDevUIStore((state) => state.updateConversationUsage);
  const setPendingApprovals = useDevUIStore((state) => state.setPendingApprovals);

  // Local UI state (not in Zustand - component-specific)
  const [detailsModalOpen, setDetailsModalOpen] = useState(false);
  const [conversationError, setConversationError] = useState<{
    message: string;
    code?: string;
    type?: string;
  } | null>(null);
  const [isReloading, setIsReloading] = useState(false);
  const [wasCancelled, setWasCancelled] = useState(false);

  // Use the cancellation hook
  const { isCancelling, createAbortSignal, handleCancel, resetCancelling } = useCancellableRequest();

  // Use the drag/drop hook for parent-level file dropping
  const { isDragOver, droppedFiles, clearDroppedFiles, dragHandlers } = useDragDrop({
    disabled: isSubmitting || isStreaming,
  });

  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
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
  // Note: Focus handling is now managed by ChatMessageInput component
  useEffect(() => {
    // ChatMessageInput will handle its own focus
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
          undefined,  // No abort signal for resume
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
                ? (error as { message: string }).message
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
              let storedTraces: unknown[] = [];

              while (hasMore) {
                const result = await apiClient.listConversationItems(
                  mostRecent.id,
                  { order: "asc", after } // Load in chronological order (oldest first)
                );
                allItems = allItems.concat(result.data);
                hasMore = result.has_more;

                // Capture traces from metadata (only need from one response, they accumulate)
                if (result.metadata?.traces && result.metadata.traces.length > 0) {
                  storedTraces = result.metadata.traces;
                }

                // Get the last item's ID for pagination
                if (hasMore && result.data.length > 0) {
                  const lastItem = result.data[result.data.length - 1] as { id?: string };
                  after = lastItem.id;
                }
              }

              // Use OpenAI ConversationItems directly (no conversion!)
              setChatItems(allItems as import("@/types/openai").ConversationItem[]);
              setIsStreaming(false);

              // Restore stored traces as debug events for context inspection
              if (storedTraces.length > 0) {
                // Clear any previous debug events first
                onDebugEvent("clear");
                for (const trace of storedTraces) {
                  // Convert stored trace back to ResponseTraceComplete event format
                  const traceEvent: ExtendedResponseStreamEvent = {
                    type: "response.trace.completed",
                    data: trace as Record<string, unknown>,
                    sequence_number: 0, // Not used for display
                  };
                  onDebugEvent(traceEvent);
                }
              }

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

  // Removed old input handling functions - now handled by ChatMessageInput component

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

      // Clear debug panel for fresh conversation
      onDebugEvent("clear");

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
  }, [selectedAgent, onDebugEvent, setCurrentConversation, setAvailableConversations, setChatItems, setIsStreaming]);

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
        let storedTraces: unknown[] = [];

        while (hasMore) {
          const result = await apiClient.listConversationItems(conversationId, {
            order: "asc", // Load in chronological order (oldest first)
            after,
          });
          allItems = allItems.concat(result.data);
          hasMore = result.has_more;

          // Capture traces from metadata (only need from one response, they accumulate)
          if (result.metadata?.traces && result.metadata.traces.length > 0) {
            storedTraces = result.metadata.traces;
          }

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

        // Restore stored traces as debug events for context inspection
        if (storedTraces.length > 0) {
          for (const trace of storedTraces) {
            // Convert stored trace back to ResponseTraceComplete event format
            const traceEvent: ExtendedResponseStreamEvent = {
              type: "response.trace.completed",
              data: trace as Record<string, unknown>,
              sequence_number: 0, // Not used for display
            };
            onDebugEvent(traceEvent);
          }
        }

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

        // Create new AbortController for this request
        const signal = createAbortSignal();

        // Use OpenAI-compatible API streaming - direct event handling
        const streamGenerator = apiClient.streamAgentExecutionOpenAI(
          selectedAgent.id,
          apiRequest,
          signal
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

          // Handle function call arguments delta (streaming arguments)
          if (openAIEvent.type === "response.function_call_arguments.delta") {
            const argsEvent = openAIEvent as import("@/types/openai").ResponseFunctionCallArgumentsDelta;

            // Update the function call item with accumulated arguments
            const currentItems = useDevUIStore.getState().chatItems;
            setChatItems(currentItems.map((item) => {
              if (item.type === "function_call" && item.call_id === argsEvent.item_id) {
                return {
                  ...item,
                  arguments: (item.arguments || "") + (argsEvent.delta || ""),
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

          // Handle output item added events (images, files, data, function calls)
          if (openAIEvent.type === "response.output_item.added") {
            const outputItemEvent = openAIEvent as import("@/types/openai").ResponseOutputItemAddedEvent;
            const item = outputItemEvent.item;

            // Handle function calls as separate conversation items
            if (item.type === "function_call") {
              // Type assertion for function call - narrows from union type
              const funcCall = item as import("@/types/openai").ResponseFunctionToolCall;
              const functionCallItem: import("@/types/openai").ConversationFunctionCall = {
                id: funcCall.id || `call-${Date.now()}`,
                type: "function_call",
                name: funcCall.name,
                arguments: funcCall.arguments || "",
                call_id: funcCall.call_id,
                status: funcCall.status || "in_progress",
                created_at: Math.floor(Date.now() / 1000),
              };

              const currentItems = useDevUIStore.getState().chatItems;
              setChatItems([...currentItems, functionCallItem]);
              continue;
            }

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
        // Handle abort separately - don't show error message
        if (isAbortError(error)) {
          // User cancelled - mark as cancelled for UI feedback
          setWasCancelled(true);
          // Mark the message as completed with what we have
          const currentItems = useDevUIStore.getState().chatItems;
          setChatItems(currentItems.map((item) =>
            item.id === assistantMessage.id && item.type === "message"
              ? {
                  ...item,
                  status: accumulatedTextRef.current ? "completed" as const : "incomplete" as const,
                  // Keep whatever text we have accumulated
                  content: item.content,
                }
              : item
          ));
        } else {
          // Other errors - show error message
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
        }
        setIsStreaming(false);
        resetCancelling();
      }
    },
    [selectedAgent, currentConversation, onDebugEvent, setChatItems, setIsStreaming, setCurrentConversation, setAvailableConversations, setPendingApprovals, updateConversationUsage, createAbortSignal, resetCancelling]
  );

  // Handle non-streaming message sending
  const handleSendMessageSync = useCallback(
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

      // Show loading state (but not streaming indicator)
      setIsSubmitting(true);

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
            setConversationError(null);
          } catch (error) {
            const errorMessage = error instanceof Error ? error.message : "Failed to create conversation";
            setConversationError({
              message: errorMessage,
              type: "conversation_creation_error",
            });
            setIsSubmitting(false);
            return;
          }
        }

        // Call non-streaming API
        const response = await apiClient.runAgentSync(selectedAgent.id, {
          input: request.input,
          conversation_id: conversationToUse?.id,
        });

        // Extract content from response output
        const assistantContent: import("@/types/openai").MessageContent[] = [];
        const toolCalls: import("@/types/openai").ConversationFunctionCall[] = [];
        const toolResults: import("@/types/openai").ConversationFunctionCallOutput[] = [];

        if (response.output) {
          for (const outputItem of response.output) {
            if (outputItem.type === "message") {
              // Extract message content
              const msgItem = outputItem as import("@/types/openai").ResponseOutputMessage;
              if (msgItem.content) {
                for (const content of msgItem.content) {
                  if (content.type === "output_text") {
                    assistantContent.push({
                      type: "text",
                      text: (content as { text: string }).text,
                    } as import("@/types/openai").MessageTextContent);
                  } else if (content.type === "output_image") {
                    assistantContent.push(content as unknown as import("@/types/openai").MessageOutputImage);
                  } else if (content.type === "output_file") {
                    assistantContent.push(content as unknown as import("@/types/openai").MessageOutputFile);
                  } else if (content.type === "output_data") {
                    assistantContent.push(content as unknown as import("@/types/openai").MessageOutputData);
                  }
                }
              }
            } else if (outputItem.type === "function_call") {
              const funcCall = outputItem as unknown as import("@/types/openai").ResponseFunctionToolCall;
              toolCalls.push({
                id: funcCall.id || `call-${Date.now()}`,
                type: "function_call",
                name: funcCall.name,
                arguments: funcCall.arguments || "",
                call_id: funcCall.call_id,
                status: funcCall.status || "completed",
                created_at: messageTimestamp,
              });
            } else if (outputItem.type === "function_call_output") {
              const resultItem = outputItem as unknown as { call_id: string; output: string };
              toolResults.push({
                id: `result-${Date.now()}`,
                type: "function_call_output",
                call_id: resultItem.call_id,
                output: resultItem.output,
                status: "completed",
                created_at: messageTimestamp,
              });
            }
          }
        }

        // Create assistant message with all content
        const assistantMessage: import("@/types/openai").ConversationMessage = {
          id: `assistant-${Date.now()}`,
          type: "message",
          role: "assistant",
          content: assistantContent,
          status: "completed",
          created_at: messageTimestamp,
          usage: response.usage ? {
            input_tokens: response.usage.input_tokens,
            output_tokens: response.usage.output_tokens,
            total_tokens: response.usage.total_tokens,
          } : undefined,
        };

        // Add all items to chat
        const currentItems = useDevUIStore.getState().chatItems;
        const newItems: import("@/types/openai").ConversationItem[] = [
          ...currentItems,
          assistantMessage,
          ...toolCalls,
          ...toolResults,
        ];
        setChatItems(newItems);

        // Update conversation-level usage stats
        if (response.usage) {
          updateConversationUsage(response.usage.total_tokens);
        }

        // Send debug event with response completed
        onDebugEvent({
          type: "response.completed",
          response: response,
          sequence_number: 0,
        } as ExtendedResponseStreamEvent);

      } catch (error) {
        // Show error message
        const errorMessage = error instanceof Error ? error.message : "Failed to get response";
        const assistantMessage: import("@/types/openai").ConversationMessage = {
          id: `assistant-${Date.now()}`,
          type: "message",
          role: "assistant",
          content: [{
            type: "text",
            text: `Error: ${errorMessage}`,
          } as import("@/types/openai").MessageTextContent],
          status: "incomplete",
          created_at: messageTimestamp,
        };

        const currentItems = useDevUIStore.getState().chatItems;
        setChatItems([...currentItems, assistantMessage]);
      } finally {
        setIsSubmitting(false);
      }
    },
    [selectedAgent, currentConversation, onDebugEvent, setChatItems, setCurrentConversation, setAvailableConversations, updateConversationUsage, setIsSubmitting]
  );


  // Handle message submission from ChatMessageInput
  const handleChatInputSubmit = async (content: import("@/types/agent-framework").ResponseInputContent[]) => {
    if (!selectedAgent || content.length === 0) return;

    // Set flag to force scroll when user sends message
    userJustSentMessage.current = true;
    setWasCancelled(false); // Reset cancelled state for new message

    setIsSubmitting(true);

    try {
      // Create OpenAI Responses API format
      const openaiInput: import("@/types/agent-framework").ResponseInputParam = [
        {
          type: "message",
          role: "user",
          content,
        },
      ];

      const request = {
        input: openaiInput,
        conversation_id: currentConversation?.id,
      };

      // Use streaming or non-streaming based on setting
      if (streamingEnabled) {
        await handleSendMessage(request);
      } else {
        await handleSendMessageSync(request);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Old handleSubmit and canSendMessage removed - replaced by handleChatInputSubmit

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col relative" {...dragHandlers}>
      {/* Full-area drop overlay */}
      {isDragOver && (
        <div className="absolute inset-0 z-50 bg-blue-50/95 dark:bg-blue-950/95 backdrop-blur-sm flex items-center justify-center border-2 border-dashed border-blue-400 dark:border-blue-500 rounded-lg m-2">
          <div className="text-center p-8">
            <div className="text-blue-600 dark:text-blue-400 text-lg font-medium mb-2">
              Drop files here
            </div>
            <div className="text-blue-500/80 dark:text-blue-400/70 text-sm">
              Images, PDFs, audio, and other files
            </div>
          </div>
        </div>
      )}

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
                {/* Only show reload button for directory-based entities */}
                {selectedAgent.source !== "in_memory" && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleReloadEntity}
                    disabled={isReloading}
                    className="h-6 w-6 p-0 flex-shrink-0"
                    title={
                      isReloading
                        ? "Reloading..."
                        : "Reload entity code (hot reload)"
                    }
                  >
                    <RefreshCw className={`h-4 w-4 ${isReloading ? "animate-spin" : ""}`} />
                  </Button>
                )}
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
            (() => {
              // Group tool calls and results with their assistant messages
              // Bidirectional association:
              // - Loading mode: tools come BEFORE assistant message (associate forward)
              // - Streaming mode: tools come AFTER assistant message placeholder (associate backward)
              const processedItems: React.ReactElement[] = [];
              const toolCallsByMessage = new Map<string, import("@/types/openai").ConversationFunctionCall[]>();
              const toolResultsByMessage = new Map<string, import("@/types/openai").ConversationFunctionCallOutput[]>();

              // Track the last assistant message for backward association (streaming)
              let lastAssistantMessageId: string | null = null;
              // Track orphaned tools for forward association (loading)
              const orphanedToolCalls: import("@/types/openai").ConversationFunctionCall[] = [];
              const orphanedToolResults: import("@/types/openai").ConversationFunctionCallOutput[] = [];

              for (let i = 0; i < chatItems.length; i++) {
                const item = chatItems[i];

                if (item.type === "message" && item.role === "assistant") {
                  // Initialize arrays for this message
                  if (!toolCallsByMessage.has(item.id)) {
                    toolCallsByMessage.set(item.id, []);
                    toolResultsByMessage.set(item.id, []);
                  }

                  // Forward association: if we have orphaned tools, associate with this message
                  if (orphanedToolCalls.length > 0) {
                    const calls = toolCallsByMessage.get(item.id) || [];
                    calls.push(...orphanedToolCalls);
                    toolCallsByMessage.set(item.id, calls);
                    orphanedToolCalls.length = 0;
                  }

                  if (orphanedToolResults.length > 0) {
                    const results = toolResultsByMessage.get(item.id) || [];
                    results.push(...orphanedToolResults);
                    toolResultsByMessage.set(item.id, results);
                    orphanedToolResults.length = 0;
                  }

                  // Track this as the last assistant message for backward association
                  lastAssistantMessageId = item.id;
                } else if (item.type === "function_call") {
                  // Try backward association first (streaming mode)
                  if (lastAssistantMessageId) {
                    const calls = toolCallsByMessage.get(lastAssistantMessageId) || [];
                    calls.push(item);
                    toolCallsByMessage.set(lastAssistantMessageId, calls);
                  } else {
                    // No previous assistant message, store for forward association
                    orphanedToolCalls.push(item);
                  }
                } else if (item.type === "function_call_output") {
                  // Try backward association first (streaming mode)
                  if (lastAssistantMessageId) {
                    const results = toolResultsByMessage.get(lastAssistantMessageId) || [];
                    results.push(item);
                    toolResultsByMessage.set(lastAssistantMessageId, results);
                  } else {
                    // No previous assistant message, store for forward association
                    orphanedToolResults.push(item);
                  }
                } else if (item.type === "message" && item.role === "user") {
                  // User message resets the backward association context
                  // Tools after a user message belong to the next assistant response
                  lastAssistantMessageId = null;
                }
              }

              // Second pass: render items, passing tool calls/results to assistant messages
              for (const item of chatItems) {
                if (item.type === "message") {
                  const toolCalls = toolCallsByMessage.get(item.id) || [];
                  const toolResults = toolResultsByMessage.get(item.id) || [];
                  processedItems.push(
                    <ConversationItemBubble
                      key={item.id}
                      item={item}
                      toolCalls={toolCalls}
                      toolResults={toolResults}
                    />
                  );
                }
                // Tool calls and results are rendered within messages, skip standalone
              }

              return processedItems;
            })()
          )}

          {/* Response cancelled card */}
          {wasCancelled && !isStreaming && (
            <div className="px-4 py-2">
              <div className="border rounded-lg border-orange-500/40 bg-orange-500/5 dark:bg-orange-500/10">
                <div className="px-4 py-3 flex items-center gap-2">
                  <Square className="w-4 h-4 text-orange-500 dark:text-orange-400 fill-current" />
                  <span className="font-medium text-sm text-orange-700 dark:text-orange-300">Response stopped by user</span>
                </div>
              </div>
            </div>
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
        <div className="p-4">
          <ChatMessageInput
            onSubmit={handleChatInputSubmit}
            isSubmitting={isSubmitting}
            isStreaming={isStreaming}
            onCancel={handleCancel}
            isCancelling={isCancelling}
            placeholder={`Message ${selectedAgent.name || selectedAgent.id}... (Shift+Enter for new line)`}
            showFileUpload={true}
            entityName={selectedAgent.name || selectedAgent.id}
            disabled={!selectedAgent}
            externalFiles={droppedFiles}
            onExternalFilesProcessed={clearDroppedFiles}
          />
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
