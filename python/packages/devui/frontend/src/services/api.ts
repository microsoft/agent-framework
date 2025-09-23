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
import type { AgentFrameworkRequest } from "@/types/agent-framework";
import type { ExtendedResponseStreamEvent } from "@/types/openai";

// Backend API response types to match Python Pydantic models
interface EntityInfo {
  id: string;
  type: "agent" | "workflow";
  name: string;
  description?: string;
  framework: string;
  tools?: (string | Record<string, unknown>)[];
  metadata: Record<string, unknown>;
  executors?: string[];
  workflow_dump?: Record<string, unknown>;
  input_schema?: Record<string, unknown>;
  input_type_name?: string;
  start_executor_id?: string;
}

interface DiscoveryResponse {
  entities: EntityInfo[];
}

interface ThreadApiResponse {
  id: string;
  object: "thread";
  created_at: number;
  metadata: { agent_id: string };
}

interface ThreadListResponse {
  object: "list";
  data: ThreadApiObject[];
}

interface ThreadApiObject {
  id: string;
  object: "thread";
  agent_id: string;
  created_at?: string;
}

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
    const response = await this.request<DiscoveryResponse>("/v1/entities");

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
          tools: (entity.tools || []).map((tool) =>
            typeof tool === "string" ? tool : JSON.stringify(tool)
          ),
          has_env: false, // Default value
          module_path:
            typeof entity.metadata?.module_path === "string"
              ? entity.metadata.module_path
              : undefined,
        });
      } else if (entity.type === "workflow") {
        const firstTool = entity.tools?.[0];
        const startExecutorId = typeof firstTool === "string" ? firstTool : "";

        workflows.push({
          id: entity.id,
          name: entity.name,
          description: entity.description,
          type: "workflow",
          source: "directory",
          executors: (entity.tools || []).map((tool) =>
            typeof tool === "string" ? tool : JSON.stringify(tool)
          ),
          has_env: false,
          module_path:
            typeof entity.metadata?.module_path === "string"
              ? entity.metadata.module_path
              : undefined,
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

  // Thread management using real /v1/threads endpoints
  async createThread(agentId: string): Promise<ThreadInfo> {
    const response = await this.request<ThreadApiResponse>("/v1/threads", {
      method: "POST",
      body: JSON.stringify({ agent_id: agentId }),
    });

    return {
      id: response.id,
      agent_id: agentId,
      created_at: new Date(response.created_at * 1000).toISOString(),
      message_count: 0,
    };
  }

  async getThreads(agentId: string): Promise<ThreadInfo[]> {
    const response = await this.request<ThreadListResponse>(
      `/v1/threads?agent_id=${agentId}`
    );
    return response.data.map((thread: ThreadApiObject) => ({
      id: thread.id,
      agent_id: thread.agent_id,
      created_at: thread.created_at || new Date().toISOString(),
      message_count: 0, // We don't track this yet
    }));
  }

  async deleteThread(threadId: string): Promise<boolean> {
    try {
      await this.request(`/v1/threads/${threadId}`, {
        method: "DELETE",
      });
      return true;
    } catch {
      return false;
    }
  }

  async getThreadMessages(
    threadId: string
  ): Promise<import("@/types").ChatMessage[]> {
    try {
      const response = await this.request<{ data: unknown[] }>(
        `/v1/threads/${threadId}/messages`
      );

      // Convert API messages to ChatMessage format, handling missing fields
      return response.data.map((msg: unknown, index: number) => {
        const msgObj = msg as Record<string, unknown>;
        const role = msgObj.role as string;
        return {
          id: (msgObj.message_id as string) || `restored-${index}`,
          role:
            role === "user" ||
            role === "assistant" ||
            role === "system" ||
            role === "tool"
              ? role
              : "user",
          contents:
            (msgObj.contents as import("@/types/agent-framework").Contents[]) ||
            [],
          timestamp: (msgObj.timestamp as string) || new Date().toISOString(),
          author_name: msgObj.author_name as string | undefined,
          message_id: msgObj.message_id as string | undefined,
        };
      });
    } catch (error) {
      console.error("Failed to get thread messages:", error);
      return [];
    }
  }

  // OpenAI-compatible streaming methods using /v1/responses endpoint

  // Stream agent execution using pure OpenAI format
  async *streamAgentExecutionOpenAI(
    agentId: string,
    request: RunAgentRequest
  ): AsyncGenerator<ExtendedResponseStreamEvent, void, unknown> {
    const openAIRequest: AgentFrameworkRequest = {
      model: "agent-framework",
      input: request.input, // Direct OpenAI ResponseInputParam
      stream: true,
      extra_body: {
        entity_id: agentId,
        thread_id: request.thread_id,
      },
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
