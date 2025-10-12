# Task: TASK-401 A2A Protocol Core

**Phase**: 5
**Priority**: High
**Estimated Effort**: 8 hours
**Dependencies**: TASK-007 (BaseAgent), TASK-101 (ChatAgent)

### Objective
Implement the Agent-to-Agent (A2A) communication protocol core, enabling agents to discover and communicate with each other across processes and networks.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-13 (Agent-to-Agent Communication)
- **Python Reference**: `/python/packages/a2a/agent_framework_a2a/` - A2A protocol implementation
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI.A2A/` - A2A communication
- **Standards**: CLAUDE.md § Python Architecture → Async-First Design

### Files to Create/Modify
- `src/a2a/protocol.ts` - A2A protocol types and interfaces
- `src/a2a/client.ts` - A2A client for agent communication
- `src/a2a/server.ts` - A2A server for exposing agents
- `src/a2a/__tests__/protocol.test.ts` - Unit tests
- `src/index.ts` - Export A2A types

### Implementation Requirements

**Core Functionality**:
1. Define `A2AMessage` type for agent-to-agent messages
2. Define `A2ARequest` and `A2AResponse` types
3. Implement `A2AClient` for calling remote agents
4. Implement `A2AServer` for exposing local agents
5. Support HTTP/HTTPS transport protocol
6. Support WebSocket transport for streaming
7. Implement agent discovery mechanism
8. Handle authentication and authorization
9. Support request/response pattern
10. Support streaming responses

**Message Format**:
11. Message ID for request tracking
12. Source agent ID and name
13. Target agent ID and name
14. Message content (text, messages array)
15. Metadata (timestamp, trace ID, etc.)
16. Authentication tokens

**TypeScript Patterns**:
- Use interface-based protocol definition
- Implement transport abstraction
- Use async/await for all I/O
- Export all types with comprehensive JSDoc
- Strict null checking

**Code Standards**:
- 120 character line length
- JSDoc documentation for all public APIs with `@example` tags
- Strict TypeScript mode enabled
- No `any` types without explicit justification comment

### Test Requirements
- [ ] Test A2AMessage structure
- [ ] Test A2ARequest/Response types
- [ ] Test A2AClient creation
- [ ] Test A2AServer creation
- [ ] Test agent discovery
- [ ] Test remote agent invocation
- [ ] Test HTTP transport
- [ ] Test WebSocket transport
- [ ] Test authentication handling
- [ ] Test error handling (network errors, timeouts)
- [ ] Test streaming responses
- [ ] Test request tracking
- [ ] Test metadata propagation
- [ ] Test concurrent requests
- [ ] Test connection management

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] A2A protocol types defined
- [ ] A2AClient for calling remote agents
- [ ] A2AServer for exposing agents
- [ ] HTTP and WebSocket transports supported
- [ ] Agent discovery implemented
- [ ] Authentication and authorization supported
- [ ] Tests pass with >85% coverage
- [ ] TypeScript compiles with no errors (strict mode)
- [ ] ESLint passes with no warnings
- [ ] JSDoc complete for all public APIs with examples
- [ ] Exports added to index.ts files

### Example Code Pattern
```typescript
/**
 * A2A message format
 */
export interface A2AMessage {
  messageId: string;
  sourceAgentId: string;
  sourceAgentName?: string;
  targetAgentId: string;
  targetAgentName?: string;
  content: string | ChatMessage[];
  metadata?: {
    timestamp?: Date;
    traceId?: string;
    spanId?: string;
    [key: string]: any;
  };
  authentication?: {
    token?: string;
    type?: 'bearer' | 'api_key';
  };
}

/**
 * A2A request
 */
export interface A2ARequest {
  message: A2AMessage;
  timeout?: number;
  streaming?: boolean;
}

/**
 * A2A response
 */
export interface A2AResponse {
  messageId: string;
  requestId: string;
  response: AgentRunResponse;
  metadata?: {
    duration?: number;
    timestamp?: Date;
    [key: string]: any;
  };
}

/**
 * A2A client for communicating with remote agents
 *
 * @example
 * ```typescript
 * const client = new A2AClient({
 *   baseUrl: 'https://agent-service.example.com',
 *   authentication: {
 *     type: 'bearer',
 *     token: 'abc123'
 *   }
 * });
 *
 * const response = await client.callAgent({
 *   targetAgentId: 'research-agent',
 *   content: 'Research AI agents',
 *   sourceAgentId: 'coordinator'
 * });
 * ```
 */
export class A2AClient {
  private readonly baseUrl: string;
  private readonly authentication?: {
    type: 'bearer' | 'api_key';
    token: string;
  };
  private readonly httpClient: HttpClient;

  constructor(options: {
    baseUrl: string;
    authentication?: {
      type: 'bearer' | 'api_key';
      token: string;
    };
    timeout?: number;
  }) {
    this.baseUrl = options.baseUrl;
    this.authentication = options.authentication;
    this.httpClient = new HttpClient({
      baseURL: this.baseUrl,
      timeout: options.timeout ?? 30000
    });
  }

  /**
   * Call a remote agent
   */
  async callAgent(request: {
    targetAgentId: string;
    targetAgentName?: string;
    content: string | ChatMessage[];
    sourceAgentId: string;
    sourceAgentName?: string;
    metadata?: Record<string, any>;
  }): Promise<A2AResponse> {
    const message: A2AMessage = {
      messageId: this.generateMessageId(),
      sourceAgentId: request.sourceAgentId,
      sourceAgentName: request.sourceAgentName,
      targetAgentId: request.targetAgentId,
      targetAgentName: request.targetAgentName,
      content: request.content,
      metadata: {
        ...request.metadata,
        timestamp: new Date()
      },
      authentication: this.authentication
    };

    const response = await this.httpClient.post<A2AResponse>(
      `/agents/${request.targetAgentId}/invoke`,
      message
    );

    return response.data;
  }

  /**
   * Call a remote agent with streaming
   */
  async *callAgentStream(request: {
    targetAgentId: string;
    content: string | ChatMessage[];
    sourceAgentId: string;
  }): AsyncIterable<AgentRunResponseUpdate> {
    const message: A2AMessage = {
      messageId: this.generateMessageId(),
      sourceAgentId: request.sourceAgentId,
      targetAgentId: request.targetAgentId,
      content: request.content,
      authentication: this.authentication
    };

    // Implementation would use SSE or WebSocket
    const stream = await this.httpClient.stream(
      `/agents/${request.targetAgentId}/invoke-stream`,
      message
    );

    for await (const chunk of stream) {
      yield chunk as AgentRunResponseUpdate;
    }
  }

  /**
   * Discover available agents
   */
  async discoverAgents(): Promise<AgentInfo[]> {
    const response = await this.httpClient.get<{ agents: AgentInfo[] }>('/agents');
    return response.data.agents;
  }

  private generateMessageId(): string {
    return `a2a_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }
}

/**
 * A2A server for exposing local agents
 *
 * @example
 * ```typescript
 * const server = new A2AServer({
 *   port: 3000,
 *   authentication: {
 *     validateToken: async (token) => {
 *       return validateJWT(token);
 *     }
 *   }
 * });
 *
 * server.registerAgent(myAgent);
 * await server.start();
 * ```
 */
export class A2AServer {
  private readonly port: number;
  private readonly agents = new Map<string, AgentProtocol>();
  private readonly authentication?: {
    validateToken: (token: string) => Promise<boolean>;
  };
  private httpServer?: any;

  constructor(options: {
    port: number;
    authentication?: {
      validateToken: (token: string) => Promise<boolean>;
    };
  }) {
    this.port = options.port;
    this.authentication = options.authentication;
  }

  /**
   * Register an agent for A2A communication
   */
  registerAgent(agent: AgentProtocol): void {
    this.agents.set(agent.id, agent);
  }

  /**
   * Unregister an agent
   */
  unregisterAgent(agentId: string): void {
    this.agents.delete(agentId);
  }

  /**
   * Start the A2A server
   */
  async start(): Promise<void> {
    // Implementation would use Express, Fastify, or similar
    this.httpServer = createHttpServer({
      port: this.port,
      routes: this.createRoutes()
    });

    await this.httpServer.listen();
  }

  /**
   * Stop the A2A server
   */
  async stop(): Promise<void> {
    await this.httpServer?.close();
  }

  /**
   * Handle agent invocation request
   */
  private async handleInvokeRequest(
    message: A2AMessage
  ): Promise<A2AResponse> {
    // Validate authentication
    if (this.authentication && message.authentication?.token) {
      const valid = await this.authentication.validateToken(
        message.authentication.token
      );
      if (!valid) {
        throw new Error('Authentication failed');
      }
    }

    // Get target agent
    const agent = this.agents.get(message.targetAgentId);
    if (!agent) {
      throw new Error(`Agent not found: ${message.targetAgentId}`);
    }

    // Invoke agent
    const response = await agent.run(message.content);

    return {
      messageId: this.generateMessageId(),
      requestId: message.messageId,
      response,
      metadata: {
        timestamp: new Date()
      }
    };
  }

  private createRoutes(): any {
    return {
      'POST /agents/:agentId/invoke': this.handleInvokeRequest.bind(this),
      'GET /agents': () => ({
        agents: Array.from(this.agents.values()).map(agent => ({
          id: agent.id,
          name: agent.name,
          displayName: agent.displayName,
          description: agent.description
        }))
      })
    };
  }

  private generateMessageId(): string {
    return `a2a_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }
}
```

### Related Tasks
- **Blocked by**: TASK-007 (BaseAgent protocol)
- **Blocked by**: TASK-101 (ChatAgent implementation)
- **Blocks**: TASK-402 (Agent discovery service)
- **Blocks**: TASK-403 (Inter-agent messaging)
- **Related**: TASK-408 (OpenTelemetry for distributed tracing)

---

## Implementation Notes

### Key Architectural Decisions

**HTTP-Based Protocol**:
Use HTTP/HTTPS for transport:
```typescript
POST /agents/{agentId}/invoke
{
  messageId: "...",
  content: "...",
  sourceAgentId: "..."
}
```

**Authentication**:
Support bearer tokens and API keys:
```typescript
headers: {
  'Authorization': 'Bearer abc123'
}
```

**Discovery**:
Agents advertise themselves via discovery endpoint:
```typescript
GET /agents → [{ id, name, description }]
```

### Common Pitfalls

- Always validate authentication before agent invocation
- Handle network timeouts gracefully
- Propagate trace context for observability
- Don't expose internal agent implementation details
- Remember to handle streaming responses differently
