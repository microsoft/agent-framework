/**
 * API client for DevUI backend
 * Handles agents, workflows, streaming, and session management
 */

import type {
  AgentInfo,
  HealthResponse,
  RunAgentRequest,
  ThreadInfo,
} from "@/types";

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

  // Agent discovery
  async getAgents(): Promise<AgentInfo[]> {
    return this.request<AgentInfo[]>("/agents");
  }

  async getWorkflows(): Promise<AgentInfo[]> {
    return this.request<AgentInfo[]>("/workflows");
  }

  async getAgentInfo(agentId: string): Promise<AgentInfo> {
    return this.request<AgentInfo>(`/agents/${agentId}/info`);
  }

  async getWorkflowInfo(
    workflowId: string
  ): Promise<import("@/types").WorkflowInfo> {
    return this.request<import("@/types").WorkflowInfo>(
      `/workflows/${workflowId}/info`
    );
  }

  // Thread management
  async createThread(agentId: string): Promise<ThreadInfo> {
    return this.request<ThreadInfo>(`/agents/${agentId}/threads`, {
      method: "POST",
    });
  }

  async getThreads(agentId: string): Promise<ThreadInfo[]> {
    return this.request<ThreadInfo[]>(`/agents/${agentId}/threads`);
  }

  // Note: EventSource doesn't support POST, so we use fetch streaming instead

  // Custom streaming with fetch
  async *streamAgentExecution(
    agentId: string,
    request: RunAgentRequest,
    isWorkflow: boolean = false
  ): AsyncGenerator<import("@/types").DebugStreamEvent, void, unknown> {
    const endpoint = isWorkflow
      ? `/workflows/${agentId}/run/stream`
      : `/agents/${agentId}/run/stream`;

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`Streaming request failed: ${response.status}`);
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
            try {
              const eventData = JSON.parse(line.slice(6));
              yield eventData;
            } catch (e) {
              console.error("Failed to parse SSE event:", e);
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }

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
    request: RunAgentRequest
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
