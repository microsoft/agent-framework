/**
 * API client for DevUI backend
 * Handles agents, workflows, streaming, and session management
 */

import type {
  AgentInfo,
  HealthResponse,
  RunAgentRequest,
  RunWorkflowRequest,
  ThreadInfo,
} from "@/types";
import type {
  AgentFrameworkRequest,
  ExtendedResponseStreamEvent,
} from "@/types/openai";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL !== undefined
    ? import.meta.env.VITE_API_BASE_URL
    : "http://localhost:8080";

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
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
      throw new Error(
        `API request failed: ${response.status} ${response.statusText}`
      );
    }

    return response.json();
  }

  // Health check
  async getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>("/health");
  }

  // Entity discovery using new unified endpoint
  async getEntities(): Promise<{
    entities: (AgentInfo | import("@/types").WorkflowInfo)[];
    agents: AgentInfo[];
    workflows: import("@/types").WorkflowInfo[];
  }> {
    const response = await this.request<{ entities: any[] }>("/v1/entities");

    // Separate agents and workflows
    const agents: AgentInfo[] = [];
    const workflows: import("@/types").WorkflowInfo[] = [];

    response.entities.forEach((entity) => {
      if (entity.type === "agent") {
        agents.push({
          id: entity.id,
          name: entity.name,
          description: entity.description,
          type: "agent",
          source: "directory", // Default source
          tools: entity.tools || [],
          has_env: false, // Default value
          module_path: entity.metadata?.module_path,
        });
      } else if (entity.type === "workflow") {
        workflows.push({
          id: entity.id,
          name: entity.name,
          description: entity.description,
          type: "workflow",
          source: "directory",
          executors: entity.tools || [], // Tools are executors for workflows
          has_env: false,
          module_path: entity.metadata?.module_path,
          input_schema: { type: "string" }, // Default schema
          input_type_name: "Input",
          start_executor_id: entity.tools?.[0] || "",
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

  async getWorkflows(): Promise<import("@/types").WorkflowInfo[]> {
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

  // Thread management (simplified for OpenAI compatibility)
  async createThread(agentId: string): Promise<ThreadInfo> {
    // For now, return a mock thread since OpenAI API doesn't use explicit threads
    return {
      id: `thread_${Date.now()}`,
      agent_id: agentId,
      created_at: new Date().toISOString(),
      message_count: 0,
    };
  }

  async getThreads(_agentId: string): Promise<ThreadInfo[]> {
    // Return empty array since we're not tracking threads in OpenAI format
    return [];
  }

  // OpenAI-compatible streaming methods using /v1/responses endpoint

  // Stream agent execution using OpenAI format - direct event pass-through
  async *streamAgentExecutionOpenAI(
    agentId: string,
    request: RunAgentRequest
  ): AsyncGenerator<ExtendedResponseStreamEvent, void, unknown> {
    // Convert to OpenAI format
    const openAIRequest: AgentFrameworkRequest = {
      model: "agent-framework", // Placeholder model name
      input: Array.isArray(request.messages)
        ? request.messages
            .map((m) => (typeof m === "string" ? m : JSON.stringify(m)))
            .join("\n")
        : request.messages,
      stream: true,
      extra_body: {
        entity_id: agentId,
      },
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
      throw new Error(`OpenAI streaming request failed: ${response.status}`);
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
    // Convert to OpenAI format
    const openAIRequest: AgentFrameworkRequest = {
      model: "agent-framework", // Placeholder model name
      input: "", // Empty string for workflows - actual data is in extra_body.input_data
      stream: true,
      extra_body: {
        entity_id: workflowId,
        input_data: request.input_data, // Preserve structured data
      },
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
      throw new Error(`OpenAI streaming request failed: ${response.status}`);
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
    thread_id: string;
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
