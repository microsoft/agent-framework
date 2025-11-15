/**
 * API client for DevUI backend
 * Handles agents, workflows, streaming, and session management
 */

import type {
  AgentInfo,
  AgentSource,
  Conversation,
  HealthResponse,
  MetaResponse,
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
  required_env_vars?: import("@/types").EnvVarRequirement[];
  // Deployment support
  deployment_supported?: boolean;
  deployment_reason?: string;
  // Agent-specific fields (present when type === "agent")
  instructions?: string;
  model_id?: string;
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
    : ""; // Default to relative URLs (same host as frontend)

// Retry configuration for streaming
const RETRY_INTERVAL_MS = 1000; // Base retry interval (will use exponential backoff)
const MAX_RETRY_ATTEMPTS = 10; // Max 10 retries (~30 seconds with exponential backoff)

// Get backend URL from localStorage or default
function getBackendUrl(): string {
  const stored = localStorage.getItem("devui_backend_url");
  if (stored) return stored;
  
  return DEFAULT_API_BASE_URL;
}

// Helper to sleep for a given duration
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

class ApiClient {
  private baseUrl: string;
  private authToken: string | null = null;

  constructor(baseUrl?: string) {
    this.baseUrl = baseUrl || getBackendUrl();
    // Load auth token from localStorage on initialization
    this.authToken = localStorage.getItem("devui_auth_token");
  }

  // Allow updating the base URL at runtime
  setBaseUrl(url: string) {
    this.baseUrl = url;
  }

  getBaseUrl(): string {
    return this.baseUrl;
  }

  // Set auth token and persist to localStorage
  setAuthToken(token: string | null): void {
    this.authToken = token;
    if (token) {
      localStorage.setItem("devui_auth_token", token);
    } else {
      localStorage.removeItem("devui_auth_token");
    }
  }

  // Get current auth token
  getAuthToken(): string | null {
    return this.authToken;
  }

  // Clear auth token
  clearAuthToken(): void {
    this.setAuthToken(null);
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    // Build headers with auth token if available
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    };

    if (this.authToken) {
      headers["Authorization"] = `Bearer ${this.authToken}`;
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      // Handle 401 Unauthorized - clear invalid token
      if (response.status === 401) {
        this.clearAuthToken();
        throw new Error("UNAUTHORIZED");
      }

      // Try to extract error message from response body
      let errorMessage = `API request failed: ${response.status} ${response.statusText}`;
      try {
        const errorData = await response.json();
        // Handle detail as string or object
        if (errorData.detail) {
          if (typeof errorData.detail === "string") {
            errorMessage = errorData.detail;
          } else if (typeof errorData.detail === "object" && errorData.detail.error?.message) {
            // Backend returns detail: { error: { message: "...", type: "...", code: "..." } }
            errorMessage = errorData.detail.error.message;
          }
        } else if (errorData.error?.message) {
          errorMessage = errorData.error.message;
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

  // Server metadata
  async getMeta(): Promise<MetaResponse> {
    return this.request<MetaResponse>("/meta");
  }

  // Entity discovery using new unified endpoint
  async getEntities(): Promise<{
    entities: (AgentInfo | WorkflowInfo)[];
    agents: AgentInfo[];
    workflows: WorkflowInfo[];
  }> {
    const response = await this.request<DiscoveryResponse>("/v1/entities");

    // Transform entities while preserving backend order
    const entities: (AgentInfo | WorkflowInfo)[] = response.entities.map((entity) => {
      if (entity.type === "agent") {
        return {
          id: entity.id,
          name: entity.name,
          description: entity.description,
          type: "agent" as const,
          source: (entity.source as AgentSource) || "directory",
          tools: (entity.tools || []).map((tool) =>
            typeof tool === "string" ? tool : JSON.stringify(tool)
          ),
          has_env: !!(entity.required_env_vars && entity.required_env_vars.length > 0),
          module_path:
            typeof entity.metadata?.module_path === "string"
              ? entity.metadata.module_path
              : undefined,
          required_env_vars: entity.required_env_vars,
          metadata: entity.metadata, // Preserve metadata including lazy_loaded flag
          // Deployment support
          deployment_supported: entity.deployment_supported,
          deployment_reason: entity.deployment_reason,
          // Agent-specific fields
          instructions: entity.instructions,
          model_id: entity.model_id,
          chat_client_type: entity.chat_client_type,
          context_providers: entity.context_providers,
          middleware: entity.middleware,
        };
      } else {
        // Workflow - prefer executors field, fall back to tools for backward compatibility
        const executorList = entity.executors || entity.tools || [];
        
        // Determine start_executor_id: use entity value, or first executor if it's a string
        let startExecutorId = entity.start_executor_id || "";
        if (!startExecutorId && executorList.length > 0) {
          const firstExecutor = executorList[0];
          if (typeof firstExecutor === "string") {
            startExecutorId = firstExecutor;
          }
        }
        
        return {
          id: entity.id,
          name: entity.name,
          description: entity.description,
          type: "workflow" as const,
          source: (entity.source as AgentSource) || "directory",
          executors: executorList.map((executor) =>
            typeof executor === "string" ? executor : JSON.stringify(executor)
          ),
          has_env: !!(entity.required_env_vars && entity.required_env_vars.length > 0),
          module_path:
            typeof entity.metadata?.module_path === "string"
              ? entity.metadata.module_path
              : undefined,
          required_env_vars: entity.required_env_vars,
          metadata: entity.metadata, // Preserve metadata including lazy_loaded flag
          // Deployment support
          deployment_supported: entity.deployment_supported,
          deployment_reason: entity.deployment_reason,
          input_schema:
            (entity.input_schema as unknown as import("@/types").JSONSchema) || {
              type: "string",
            }, // Default schema
          input_type_name: entity.input_type_name || "Input",
          start_executor_id: startExecutorId,
          tools: [],
        };
      }
    });

    // Create filtered arrays for backward compatibility
    const agents = entities.filter((e): e is AgentInfo => e.type === "agent");
    const workflows = entities.filter((e): e is WorkflowInfo => e.type === "workflow");

    return { entities, agents, workflows };
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
    return this.request<AgentInfo>(`/v1/entities/${agentId}/info?type=agent`);
  }

  async getWorkflowInfo(
    workflowId: string
  ): Promise<import("@/types").WorkflowInfo> {
    // Get detailed entity info from unified endpoint
    return this.request<import("@/types").WorkflowInfo>(
      `/v1/entities/${workflowId}/info?type=workflow`
    );
  }

  async reloadEntity(entityId: string): Promise<{ success: boolean; message: string }> {
    // Hot reload entity - clears cache and forces reimport on next access
    return this.request<{ success: boolean; message: string }>(
      `/v1/entities/${entityId}/reload`,
      {
        method: "POST",
      }
    );
  }

  // ========================================
  // Conversation Management (OpenAI Standard)
  // ========================================

  async createConversation(
    metadata?: Record<string, string>
  ): Promise<Conversation> {
    // Check if OAI proxy mode is enabled
    const { oaiMode } = await import("@/stores").then((m) => ({
      oaiMode: m.useDevUIStore.getState().oaiMode,
    }));

    const headers: Record<string, string> = {};

    // Add proxy mode header if enabled
    if (oaiMode.enabled) {
      headers["X-Proxy-Backend"] = "openai";
    }

    const response = await this.request<ConversationApiResponse>(
      "/v1/conversations",
      {
        method: "POST",
        headers,
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

  async deleteConversationItem(
    conversationId: string,
    itemId: string
  ): Promise<void> {
    const response = await fetch(
      `${this.baseUrl}/v1/conversations/${conversationId}/items/${itemId}`,
      { method: "DELETE" }
    );
    if (!response.ok) {
      throw new Error(`Failed to delete item: ${response.statusText}`);
    }
  }

  // OpenAI-compatible streaming methods using /v1/responses endpoint

  // Private helper method that handles the actual streaming with retry logic
  private async *streamOpenAIResponse(
    openAIRequest: AgentFrameworkRequest,
    conversationId?: string,
    resumeResponseId?: string
  ): AsyncGenerator<ExtendedResponseStreamEvent, void, unknown> {
    // Check if OpenAI proxy mode is enabled
    const { oaiMode } = await import("@/stores").then((m) => ({
      oaiMode: m.useDevUIStore.getState().oaiMode,
    }));

    // Modify request if OAI mode is enabled
    if (oaiMode.enabled) {
      // Override model with OAI model
      openAIRequest.model = oaiMode.model;

      // Merge optional OpenAI parameters
      if (oaiMode.temperature !== undefined) {
        openAIRequest.temperature = oaiMode.temperature;
      }
      if (oaiMode.max_output_tokens !== undefined) {
        openAIRequest.max_output_tokens = oaiMode.max_output_tokens;
      }
      if (oaiMode.top_p !== undefined) {
        openAIRequest.top_p = oaiMode.top_p;
      }
      if (oaiMode.instructions !== undefined) {
        openAIRequest.instructions = oaiMode.instructions;
      }
      // Reasoning parameters (for o-series models)
      if (oaiMode.reasoning_effort !== undefined) {
        openAIRequest.reasoning = { effort: oaiMode.reasoning_effort };
      }
    }

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

          const headers: Record<string, string> = {
            Accept: "text/event-stream",
          };

          // Add auth token if available
          if (this.authToken) {
            headers["Authorization"] = `Bearer ${this.authToken}`;
          }

          response = await fetch(url, {
            method: "GET",
            headers,
          });
        } else {
          const url = `${this.baseUrl}/v1/responses`;
          const headers: Record<string, string> = {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          };

          // Add proxy header if OAI mode is enabled
          if (oaiMode.enabled) {
            headers["X-Proxy-Backend"] = "openai";
          }

          // Add auth token if available
          if (this.authToken) {
            headers["Authorization"] = `Bearer ${this.authToken}`;
          }

          response = await fetch(url, {
            method: "POST",
            headers,
            body: JSON.stringify(openAIRequest),
          });
        }

        if (!response.ok) {
          // Handle authentication errors - don't retry these
          if (response.status === 401) {
            this.clearAuthToken(); // Clear invalid token
            throw new Error("UNAUTHORIZED"); // Special error that won't be retried
          }

          // Handle other client errors (400-499) - don't retry these either
          if (response.status >= 400 && response.status < 500) {
            let errorMessage = `Client error ${response.status}`;
            try {
              const errorBody = await response.json();
              if (errorBody.error && errorBody.error.message) {
                errorMessage = errorBody.error.message;
              } else if (errorBody.detail) {
                errorMessage = errorBody.detail;
              }
            } catch {
              // Fallback to generic message
            }
            throw new Error(`CLIENT_ERROR: ${errorMessage}`);
          }

          // Server errors (500-599) - these can be retried
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
        const errorMessage = error instanceof Error ? error.message : String(error);

        // Don't retry on auth errors or client errors
        if (errorMessage === "UNAUTHORIZED" || errorMessage.startsWith("CLIENT_ERROR:")) {
          throw error; // Re-throw without retrying
        }

        // Network error or server error occurred - prepare to retry
        retryCount++;

        if (retryCount > MAX_RETRY_ATTEMPTS) {
          // Max retries exceeded - give up
          throw new Error(
            `Connection failed after ${MAX_RETRY_ATTEMPTS} retry attempts: ${errorMessage}`
          );
        }

        // Exponential backoff: 1s, 2s, 4s, 8s, 16s, max 30s
        const retryDelay = Math.min(RETRY_INTERVAL_MS * Math.pow(2, retryCount - 1), 30000);
        await sleep(retryDelay);
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
      metadata: { entity_id: agentId }, // Entity ID in metadata for routing
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
    // Proxy mode handling is now inside streamOpenAIResponse
    yield* this.streamOpenAIResponse(openAIRequest, conversationId, resumeResponseId);
  }

  // Stream workflow execution using OpenAI format
  async *streamWorkflowExecutionOpenAI(
    workflowId: string,
    request: RunWorkflowRequest
  ): AsyncGenerator<ExtendedResponseStreamEvent, void, unknown> {
    // Convert to OpenAI format - use metadata.entity_id for routing
    const openAIRequest: AgentFrameworkRequest = {
      metadata: { entity_id: workflowId }, // Entity ID in metadata for routing
      input: JSON.stringify(request.input_data || {}), // Serialize workflow input as JSON string
      stream: true,
      conversation: request.conversation_id, // Include conversation if present
      extra_body: request.checkpoint_id
        ? { entity_id: workflowId, checkpoint_id: request.checkpoint_id }
        : undefined, // Pass checkpoint_id if provided
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

  // Deployment methods
  async* streamDeployment(config: {
    entity_id: string;
    resource_group: string;
    app_name: string;
    region?: string;
    ui_mode?: string;
  }): AsyncGenerator<{
    type: string;
    message: string;
    url?: string;
    auth_token?: string;
  }> {
    const response = await fetch(`${this.baseUrl}/v1/deployments`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ...config, stream: true }),
    });

    if (!response.ok) {
      throw new Error(`Deployment failed: ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error("No response body");

    const decoder = new TextDecoder();
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6);
            if (data === "[DONE]") return;
            try {
              yield JSON.parse(data);
            } catch (e) {
              // Emit error event for parsing failures
              yield {
                type: "deploy.error",
                message: `Failed to parse deployment event: ${e instanceof Error ? e.message : "Unknown error"}`,
              };
            }
          }
        }
      }
    } catch (error) {
      // Emit error event before throwing
      yield {
        type: "deploy.failed",
        message: `Stream interrupted: ${error instanceof Error ? error.message : "Unknown error"}`,
      };
      throw error;
    } finally {
      reader.releaseLock();
    }
  }

  // ============================================================================
  // Workflow Session Management (uses /conversations API)
  // ============================================================================

  async listWorkflowSessions(entityId: string): Promise<{ data: import("@/types").WorkflowSession[] }> {
    // Workflow sessions are conversations with entity_id and type metadata
    const url = `/v1/conversations?entity_id=${encodeURIComponent(entityId)}&type=workflow_session`;
    const response = await this.request<{
      object: "list";
      data: ConversationApiResponse[];
      has_more: boolean;
    }>(url);

    // Transform conversations to WorkflowSession format (no checkpoint counting)
    const sessions = response.data.map((conv) => ({
      conversation_id: conv.id,
      entity_id: conv.metadata?.entity_id || entityId,
      created_at: conv.created_at,
      metadata: {
        name: conv.metadata?.name || `Session ${new Date(conv.created_at * 1000).toLocaleString()}`,
        description: conv.metadata?.description,
        type: "workflow_session" as const,
      },
    }));

    return { data: sessions };
  }

  async createWorkflowSession(
    entityId: string,
    params?: { name?: string; description?: string }
  ): Promise<import("@/types").WorkflowSession> {
    // Create conversation with workflow session metadata
    const metadata = {
      entity_id: entityId,
      type: "workflow_session" as const,
      name: params?.name || `Session ${new Date().toLocaleString()}`,
      ...(params?.description && { description: params.description }),
    };

    const conversation = await this.createConversation(metadata);

    return {
      conversation_id: conversation.id,
      entity_id: entityId,
      created_at: conversation.created_at,
      metadata: {
        name: metadata.name,
        description: metadata.description,
        type: "workflow_session" as const,
      },
    };
  }

  async deleteWorkflowSession(_entityId: string, conversationId: string): Promise<void> {
    // Delete conversation (this also deletes all associated items/checkpoints)
    const success = await this.deleteConversation(conversationId);
    if (!success) {
      throw new Error("Failed to delete workflow session");
    }
  }

  // Checkpoint operations now handled through standard conversation items API
  // Checkpoints are conversation items with type="checkpoint"
}

// Export singleton instance
export const apiClient = new ApiClient();
export { ApiClient };

// Export streaming state init function
export { initStreamingState } from "./streaming-state";
