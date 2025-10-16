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

// Get backend URL from localStorage or default
function getBackendUrl(): string {
  return localStorage.getItem("devui_backend_url") || DEFAULT_API_BASE_URL;
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

  // Stream agent execution using OpenAI format with simplified routing
  async *streamAgentExecutionOpenAI(
    agentId: string,
    request: RunAgentRequest
  ): AsyncGenerator<ExtendedResponseStreamEvent, void, unknown> {
    const openAIRequest: AgentFrameworkRequest = {
      model: agentId, // Model IS the entity_id (simplified routing!)
      input: request.input, // Direct OpenAI ResponseInputParam
      stream: true,
      conversation: request.conversation_id, // OpenAI standard conversation param
    };

    return yield* this.streamAgentExecutionOpenAIDirect(agentId, openAIRequest);
  }

  // Stream agent execution using direct OpenAI format
  async *streamAgentExecutionOpenAIDirect(
    _agentId: string,
    openAIRequest: AgentFrameworkRequest
  ): AsyncGenerator<ExtendedResponseStreamEvent, void, unknown> {

    const response = await fetch(`${this.baseUrl}/v1/responses`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(openAIRequest),
    });

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
          break;
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
              return;
            }

            try {
              const openAIEvent: ExtendedResponseStreamEvent =
                JSON.parse(dataStr);
              yield openAIEvent; // Direct pass-through - no conversion!
            } catch (e) {
              console.error("Failed to parse OpenAI SSE event:", e);
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }

  // Stream workflow execution using OpenAI format - direct event pass-through
  async *streamWorkflowExecutionOpenAI(
    workflowId: string,
    request: RunWorkflowRequest
  ): AsyncGenerator<ExtendedResponseStreamEvent, void, unknown> {
    // Convert to OpenAI format - use model field for entity_id (same as agents)
    const openAIRequest: AgentFrameworkRequest = {
      model: workflowId, // Use workflow ID in model field (matches agent pattern)
      input: typeof request.input_data === 'string'
        ? request.input_data
        : JSON.stringify(request.input_data || ""), // Convert input_data to string
      stream: true,
      conversation: request.conversation_id, // Include conversation if present
    };

    const response = await fetch(`${this.baseUrl}/v1/responses`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(openAIRequest),
    });

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
          break;
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
              return;
            }

            try {
              const openAIEvent: ExtendedResponseStreamEvent =
                JSON.parse(dataStr);
              yield openAIEvent; // Direct pass-through - no conversion!
            } catch (e) {
              console.error("Failed to parse OpenAI SSE event:", e);
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
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
}

// Export singleton instance
export const apiClient = new ApiClient();
export { ApiClient };
