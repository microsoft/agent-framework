/**
 * API client for DevUI backend
 * Handles agents, workflows, streaming, and session management
 */

import type {
  AgentInfo,
  AgentSource,
  Conversation,
  HealthResponse,
  RunAgentRequest,
  RunWorkflowRequest,
  WorkflowInfo,
} from "@/types";
import type { AgentFrameworkRequest } from "@/types/agent-framework";
import type { ExtendedResponseStreamEvent } from "@/types/openai";
import {
  loadStreamingState,
  updateStreamingState,
  markStreamingCompleted,
  clearStreamingState,
} from "./streaming-state";

// Backend API response type - polymorphic entity that can be agent or workflow
// This matches the Python Pydantic EntityInfo model which has all fields optional
interface BackendEntityInfo {
  id: string;
  type: "agent" | "workflow";
  name: string;
  description?: string;
  framework: string;
  tools?: (string | Record<string, unknown>)[];
  metadata: Record<string, unknown>;
  source?: string;
  // Agent-specific fields (present when type === "agent")
  instructions?: string;
  model?: string;
  chat_client_type?: string;
  context_providers?: string[];
  middleware?: string[];
  // Workflow-specific fields (present when type === "workflow")
  executors?: string[];
  workflow_dump?: Record<string, unknown>;
  input_schema?: Record<string, unknown>;
  input_type_name?: string;
  start_executor_id?: string;
}

interface DiscoveryResponse {
  entities: BackendEntityInfo[];
}

// Conversation API types (OpenAI standard)
interface ConversationApiResponse {
  id: string;
  object: "conversation";
  created_at: number;
  metadata?: Record<string, string>;
}

const DEFAULT_API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL !== undefined
    ? import.meta.env.VITE_API_BASE_URL
    : "http://localhost:8080";

// Retry configuration for streaming
const RETRY_INTERVAL_MS = 1000; // Retry every second
const MAX_RETRY_ATTEMPTS = 600; // Max 600 retries (10 minutes total)

// Get backend URL from localStorage or default
function getBackendUrl(): string {
  const stored = localStorage.getItem("devui_backend_url");
  if (stored) return stored;
  
  // If VITE_API_BASE_URL is explicitly set to empty string, use relative path
  // This allows the frontend to call the same host it's served from
  if (import.meta.env.VITE_API_BASE_URL === "") {
    return "";
  }
  
  return DEFAULT_API_BASE_URL;
}

// Helper to sleep for a given duration
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl?: string) {
    this.baseUrl = baseUrl || getBackendUrl();
  }

  // Allow updating the base URL at runtime
  setBaseUrl(url: string) {
    this.baseUrl = url;
  }

  getBaseUrl(): string {
    return this.baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    const response = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
      ...options,
    });

    if (!response.ok) {
      // Try to extract error message from response body
      let errorMessage = `API request failed: ${response.status} ${response.statusText}`;
      try {
        const errorData = await response.json();
        if (errorData.detail) {
          errorMessage = errorData.detail;
        }
      } catch {
        // If parsing fails, use default message
      }
      throw new Error(errorMessage);
    }

    return response.json();
  }

  // Health check
  async getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>("/health");
  }

  // Entity discovery using new unified endpoint
  async getEntities(): Promise<{
    entities: (AgentInfo | WorkflowInfo)[];
    agents: AgentInfo[];
    workflows: WorkflowInfo[];
  }> {
    const response = await this.request<DiscoveryResponse>("/v1/entities");

    // Separate agents and workflows
    const agents: AgentInfo[] = [];
    const workflows: WorkflowInfo[] = [];

    response.entities.forEach((entity) => {
      if (entity.type === "agent") {
        agents.push({
          id: entity.id,
          name: entity.name,
          description: entity.description,
          type: "agent",
          source: (entity.source as AgentSource) || "directory",
          tools: (entity.tools || []).map((tool) =>
            typeof tool === "string" ? tool : JSON.stringify(tool)
          ),
          has_env: false, // Default value
          module_path:
            typeof entity.metadata?.module_path === "string"
              ? entity.metadata.module_path
              : undefined,
          metadata: entity.metadata, // Preserve metadata including lazy_loaded flag
          // Agent-specific fields
          instructions: entity.instructions,
          model: entity.model,
          chat_client_type: entity.chat_client_type,
          context_providers: entity.context_providers,
          middleware: entity.middleware,
        });
      } else if (entity.type === "workflow") {
        const firstTool = entity.tools?.[0];
        const startExecutorId = typeof firstTool === "string" ? firstTool : "";

        workflows.push({
          id: entity.id,
          name: entity.name,
          description: entity.description,
          type: "workflow",
          source: (entity.source as AgentSource) || "directory",
          executors: (entity.tools || []).map((tool) =>
            typeof tool === "string" ? tool : JSON.stringify(tool)
          ),
          has_env: false,
          module_path:
            typeof entity.metadata?.module_path === "string"
              ? entity.metadata.module_path
              : undefined,
          metadata: entity.metadata, // Preserve metadata including lazy_loaded flag
          input_schema:
            (entity.input_schema as unknown as import("@/types").JSONSchema) || {
              type: "string",
            }, // Default schema
          input_type_name: entity.input_type_name || "Input",
          start_executor_id: startExecutorId,
        });
      }
    });

    return { entities: [...agents, ...workflows], agents, workflows };
  }

  // Legacy methods for compatibility
  async getAgents(): Promise<AgentInfo[]> {
    const { agents } = await this.getEntities();
    return agents;
  }

  async getWorkflows(): Promise<WorkflowInfo[]> {
    const { workflows } = await this.getEntities();
    return workflows;
  }

  async getAgentInfo(agentId: string): Promise<AgentInfo> {
    // Get detailed entity info from unified endpoint
    return this.request<AgentInfo>(`/v1/entities/${agentId}/info`);
  }

  async getWorkflowInfo(
    workflowId: string
  ): Promise<import("@/types").WorkflowInfo> {
    // Get detailed entity info from unified endpoint
    return this.request<import("@/types").WorkflowInfo>(
      `/v1/entities/${workflowId}/info`
    );
  }

  // ========================================
  // Conversation Management (OpenAI Standard)
  // ========================================

  async createConversation(
    metadata?: Record<string, string>
  ): Promise<Conversation> {
    const response = await this.request<ConversationApiResponse>(
      "/v1/conversations",
      {
        method: "POST",
        body: JSON.stringify({ metadata }),
      }
    );

    return {
      id: response.id,
      object: "conversation",
      created_at: response.created_at,
      metadata: response.metadata,
    };
  }

  async listConversations(
    agentId?: string
  ): Promise<{ data: Conversation[]; has_more: boolean }> {
    const url = agentId
      ? `/v1/conversations?agent_id=${encodeURIComponent(agentId)}`
      : "/v1/conversations";

    const response = await this.request<{
      object: "list";
      data: ConversationApiResponse[];
      has_more: boolean;
    }>(url);

    return {
      data: response.data.map((conv) => ({
        id: conv.id,
        object: "conversation",
        created_at: conv.created_at,
        metadata: conv.metadata,
      })),
      has_more: response.has_more,
    };
  }

  async getConversation(conversationId: string): Promise<Conversation> {
    const response = await this.request<ConversationApiResponse>(
      `/v1/conversations/${conversationId}`
    );

    return {
      id: response.id,
      object: "conversation",
      created_at: response.created_at,
      metadata: response.metadata,
    };
  }

  async deleteConversation(conversationId: string): Promise<boolean> {
    try {
      await this.request(`/v1/conversations/${conversationId}`, {
        method: "DELETE",
      });
      // Clear streaming state when conversation is deleted
      clearStreamingState(conversationId);
      return true;
    } catch {
      return false;
    }
  }

  async listConversationItems(
    conversationId: string,
    options?: { limit?: number; after?: string; order?: "asc" | "desc" }
  ): Promise<{ data: unknown[]; has_more: boolean }> {
    const params = new URLSearchParams();
    if (options?.limit) params.set("limit", options.limit.toString());
    if (options?.after) params.set("after", options.after);
    if (options?.order) params.set("order", options.order);

    const queryString = params.toString();
    const url = `/v1/conversations/${conversationId}/items${
      queryString ? `?${queryString}` : ""
    }`;

    return this.request<{ data: unknown[]; has_more: boolean }>(url);
  }

  // OpenAI-compatible streaming methods using /v1/responses endpoint

  // Private helper method that handles the actual streaming with retry logic
  private async *streamOpenAIResponse(
    openAIRequest: AgentFrameworkRequest,
    conversationId?: string,
    resumeResponseId?: string
  ): AsyncGenerator<ExtendedResponseStreamEvent, void, unknown> {
    let lastSequenceNumber = -1;
    let retryCount = 0;
    let hasYieldedAnyEvent = false;
    let currentResponseId: string | undefined = resumeResponseId;
    let lastMessageId: string | undefined = undefined;

    // Try to resume from stored state if conversation ID is provided
    if (conversationId) {
      const storedState = loadStreamingState(conversationId);
      if (storedState) {
        // Use stored response ID if no explicit one provided
        if (!resumeResponseId) {
          currentResponseId = storedState.responseId;
        }
        
        lastSequenceNumber = storedState.lastSequenceNumber;
        lastMessageId = storedState.lastMessageId;
        
        // Replay stored events only if we're not explicitly resuming
        // (explicit resume means the caller already has the events)
        if (!resumeResponseId) {
          for (const event of storedState.events) {
            hasYieldedAnyEvent = true;
            yield event;
          }
        } else {
          // Mark that we've already seen events up to this sequence number
          hasYieldedAnyEvent = storedState.events.length > 0;
        }
      }
    }

    while (retryCount <= MAX_RETRY_ATTEMPTS) {
      try {
        // If we have a response_id from a previous attempt, use GET endpoint to resume
        // Otherwise, use POST to create a new response
        let response: Response;
        if (currentResponseId) {
          const params = new URLSearchParams();
          params.set("stream", "true");
          if (lastSequenceNumber >= 0) {
            params.set("starting_after", lastSequenceNumber.toString());
          }
          const url = `${this.baseUrl}/v1/responses/${currentResponseId}?${params.toString()}`;
          response = await fetch(url, {
            method: "GET",
            headers: {
              Accept: "text/event-stream",
            },
          });
        } else {
          const url = `${this.baseUrl}/v1/responses`;
          response = await fetch(url, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Accept: "text/event-stream",
            },
            body: JSON.stringify(openAIRequest),
          });
        }

        if (!response.ok) {
          // Try to extract detailed error message from response body
          let errorMessage = `Request failed with status ${response.status}`;
          try {
            const errorBody = await response.json();
            if (errorBody.error && errorBody.error.message) {
              errorMessage = errorBody.error.message;
            } else if (errorBody.detail) {
              errorMessage = errorBody.detail;
            }
          } catch {
            // Fallback to generic message if parsing fails
          }
          throw new Error(errorMessage);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error("Response body is not readable");
        }

        const decoder = new TextDecoder();
        let buffer = "";

        try {
          while (true) {
            const { done, value } = await reader.read();

            if (done) {
              // Stream completed successfully
              if (conversationId) {
                markStreamingCompleted(conversationId);
              }
              return;
            }

            buffer += decoder.decode(value, { stream: true });

            // Parse SSE events
            const lines = buffer.split("\n");
            buffer = lines.pop() || ""; // Keep incomplete line in buffer

            for (const line of lines) {
              if (line.startsWith("data: ")) {
                const dataStr = line.slice(6);

                // Handle [DONE] signal
                if (dataStr === "[DONE]") {
                  if (conversationId) {
                    markStreamingCompleted(conversationId);
                  }
                  return;
                }

                try {
                  const openAIEvent: ExtendedResponseStreamEvent =
                    JSON.parse(dataStr);

                  // Capture response_id if present in the event for use in retries
                  if ("response" in openAIEvent && openAIEvent.response && typeof openAIEvent.response === "object" && "id" in openAIEvent.response) {
                    const newResponseId = openAIEvent.response.id as string;
                    if (!currentResponseId || currentResponseId !== newResponseId) {
                      currentResponseId = newResponseId;
                    }
                  } else if ("id" in openAIEvent && typeof openAIEvent.id === "string" && openAIEvent.id.startsWith("resp_")) {
                    const newResponseId = openAIEvent.id;
                    if (!currentResponseId || currentResponseId !== newResponseId) {
                      currentResponseId = newResponseId;
                    }
                  }

                  // Track last message ID if present (for user/assistant messages)
                  if ("item_id" in openAIEvent && openAIEvent.item_id) {
                    lastMessageId = openAIEvent.item_id;
                  }

                  // Check for sequence number restart (server restarted response)
                  const eventSeq = "sequence_number" in openAIEvent ? openAIEvent.sequence_number : undefined;
                  if (eventSeq !== undefined) {
                    // If we've received events before and sequence restarted from 0/1
                    if (hasYieldedAnyEvent && eventSeq <= 1 && lastSequenceNumber > 1) {
                      // Server restarted the response - clear old state and start fresh
                      if (conversationId) {
                        clearStreamingState(conversationId);
                      }
                      yield {
                        type: "error",
                        message: "Connection lost - previous response failed. Starting new response.",
                      } as ExtendedResponseStreamEvent;
                      lastSequenceNumber = eventSeq;
                      hasYieldedAnyEvent = true;
                      
                      // Save new event to storage
                      if (conversationId && currentResponseId) {
                        updateStreamingState(conversationId, openAIEvent, currentResponseId, lastMessageId);
                      }
                      
                      yield openAIEvent;
                    }
                    // Skip events we've already seen (resume from last position)
                    else if (eventSeq <= lastSequenceNumber) {
                      continue; // Skip duplicate event
                    } else {
                      lastSequenceNumber = eventSeq;
                      hasYieldedAnyEvent = true;
                      
                      // Save event to storage before yielding
                      if (conversationId && currentResponseId) {
                        updateStreamingState(conversationId, openAIEvent, currentResponseId, lastMessageId);
                      }
                      
                      yield openAIEvent;
                    }
                  } else {
                    // No sequence number - just yield the event
                    hasYieldedAnyEvent = true;
                    
                    // Still save to storage if we have conversation context
                    if (conversationId && currentResponseId) {
                      updateStreamingState(conversationId, openAIEvent, currentResponseId, lastMessageId);
                    }
                    
                    yield openAIEvent;
                  }
                } catch (e) {
                  console.error("Failed to parse OpenAI SSE event:", e);
                }
              }
            }
          }
        } finally {
          reader.releaseLock();
        }
      } catch (error) {
        // Network error occurred - prepare to retry
        retryCount++;

        if (retryCount > MAX_RETRY_ATTEMPTS) {
          // Max retries exceeded - give up
          throw new Error(
            `Connection failed after ${MAX_RETRY_ATTEMPTS} retry attempts: ${error instanceof Error ? error.message : String(error)}`
          );
        }

        // Wait before retrying
        await sleep(RETRY_INTERVAL_MS);
        // Loop will retry with GET if we have response_id, otherwise POST
      }
    }
  }

  // Stream agent execution using OpenAI format with simplified routing
  async *streamAgentExecutionOpenAI(
    agentId: string,
    request: RunAgentRequest,
    resumeResponseId?: string
  ): AsyncGenerator<ExtendedResponseStreamEvent, void, unknown> {
    const openAIRequest: AgentFrameworkRequest = {
      model: agentId, // Model IS the entity_id (simplified routing!)
      input: request.input, // Direct OpenAI ResponseInputParam
      stream: true,
      conversation: request.conversation_id, // OpenAI standard conversation param
    };

    return yield* this.streamAgentExecutionOpenAIDirect(agentId, openAIRequest, request.conversation_id, resumeResponseId);
  }

  // Stream agent execution using direct OpenAI format
  async *streamAgentExecutionOpenAIDirect(
    _agentId: string,
    openAIRequest: AgentFrameworkRequest,
    conversationId?: string,
    resumeResponseId?: string
  ): AsyncGenerator<ExtendedResponseStreamEvent, void, unknown> {
    yield* this.streamOpenAIResponse(openAIRequest, conversationId, resumeResponseId);
  }

  // Stream workflow execution using OpenAI format
  async *streamWorkflowExecutionOpenAI(
    workflowId: string,
    request: RunWorkflowRequest
  ): AsyncGenerator<ExtendedResponseStreamEvent, void, unknown> {
    // Convert to OpenAI format - use model field for entity_id (same as agents)
    const openAIRequest: AgentFrameworkRequest = {
      model: workflowId, // Use workflow ID in model field (matches agent pattern)
      input: request.input_data || "", // Send dict directly, no stringification needed
      stream: true,
      conversation: request.conversation_id, // Include conversation if present
    };

    yield* this.streamOpenAIResponse(openAIRequest, request.conversation_id);
  }

  // REMOVED: Legacy streaming methods - use streamAgentExecutionOpenAI and streamWorkflowExecutionOpenAI instead

  // Non-streaming execution (for testing)
  async runAgent(
    agentId: string,
    request: RunAgentRequest
  ): Promise<{
    conversation_id: string;
    result: unknown[];
    message_count: number;
  }> {
    return this.request(`/agents/${agentId}/run`, {
      method: "POST",
      body: JSON.stringify(request),
    });
  }

  async runWorkflow(
    workflowId: string,
    request: RunWorkflowRequest
  ): Promise<{
    result: string;
    events: number;
    message_count: number;
  }> {
    return this.request(`/workflows/${workflowId}/run`, {
      method: "POST",
      body: JSON.stringify(request),
    });
  }

  // Clear streaming state for a conversation (e.g., when starting a new message)
  clearStreamingState(conversationId: string): void {
    clearStreamingState(conversationId);
  }
}

// Export singleton instance
export const apiClient = new ApiClient();
export { ApiClient };

// Export streaming state init function
export { initStreamingState } from "./streaming-state";
