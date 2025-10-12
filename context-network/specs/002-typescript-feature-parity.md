# Specification 002: TypeScript Implementation Feature Parity

## Summary

This specification defines the feature set, architecture, and implementation approach for a TypeScript/JavaScript implementation of the Microsoft Agent Framework, achieving feature parity with the existing Python and .NET implementations while leveraging TypeScript-specific idioms and patterns.

## Metadata
- **Status**: Proposed
- **Created**: 2025-10-11
- **Authors**: Analysis Team
- **Target Release**: TBD

## Motivation

### Why TypeScript?

1. **Ecosystem Reach**: JavaScript/TypeScript is the most widely deployed language ecosystem, running in browsers, Node.js, edge runtimes (Cloudflare Workers, Deno, Bun), and mobile environments
2. **Developer Base**: Largest developer community with strong AI/ML tooling momentum
3. **Type Safety**: TypeScript provides excellent static typing while maintaining JavaScript compatibility
4. **Async Patterns**: Native Promise/async-await support aligns well with agent framework patterns
5. **Tooling**: Exceptional IDE support, testing frameworks, and build tools
6. **Edge Computing**: Perfect fit for serverless and edge deployment scenarios

### Use Cases

- **Web Applications**: Browser-based agent interfaces and interactive experiences
- **Serverless Functions**: AWS Lambda, Azure Functions, Cloudflare Workers
- **Edge Computing**: Deploy agents close to users with minimal latency
- **Cross-Platform**: Electron, React Native, mobile web applications
- **API Services**: Node.js backends for agent orchestration
- **Developer Tools**: VS Code extensions, CLI tools, development aids

## Requirements

### Functional Requirements

#### FR-1: Core Agent Abstraction
- Implement `AgentProtocol` interface for structural typing
- Provide `BaseAgent` abstract class with common functionality
- Implement `ChatAgent` for LLM-based agents
- Support agent metadata (id, name, description, displayName)
- Thread management and conversation state

#### FR-2: Tool System
- `AIFunction` class for wrapping functions as tools
- Decorator pattern (`@aiFunction`) for function-to-tool conversion
- Tool protocol for custom tool implementations
- Automatic JSON schema generation from TypeScript types
- Tool invocation with validation and error handling
- Support for both sync and async functions

#### FR-3: Chat Client Protocol
- Abstract `ChatClientProtocol` interface
- Support for multiple LLM providers:
  - OpenAI
  - Azure OpenAI
  - Anthropic (Claude)
  - Google (Gemini)
  - Local models (Ollama, LM Studio)
- Streaming and non-streaming responses
- Function/tool calling support
- Automatic function invocation via decorator pattern

#### FR-4: Types System
- `ChatMessage` with role and content
- `ChatOptions` for request configuration
- `AgentRunResponse` and `AgentRunResponseUpdate`
- Content types:
  - Text, Function Call, Function Result
  - Function Approval Request, Function Approval Response
  - Image, Audio, File content types
- Type-safe enums for roles, tool modes, finish reasons
- Serialization support for all major types

#### FR-5: Thread Management
- `AgentThread` for conversation state
- Service-managed threads (server-side history via `serviceThreadId`)
- Local-managed threads (client-side history via `messageStore`)
- Message storage protocols (`ChatMessageStore`)
- Context provider integration
- Thread serialization and deserialization
- Support for both conversation ID and message store patterns

#### FR-6: Middleware System
- Middleware protocol for intercepting agent/function calls
- Pipeline-based execution
- Support for logging, telemetry, filtering, approval flows
- Compose multiple middleware

#### FR-7: Model Context Protocol (MCP)
- MCP client for connecting to MCP servers
- MCP server creation from agents
- Tool discovery and invocation
- Authentication support
- `MCPTool` class for hosted MCP services

#### FR-8: Workflows
- Graph-based multi-agent orchestration (Pregel-like model)
- Node types:
  - `AgentExecutor`: Agent-based nodes
  - `FunctionExecutor`: Function-based nodes
  - `WorkflowExecutor`: Nested workflows
  - `RequestInfoExecutor`: Human-in-the-loop interaction
- Edge types:
  - Direct edges
  - Conditional edges
  - Fan-out/fan-in patterns
  - Switch-case routing
- Workflow execution:
  - Synchronous execution (`run()`)
  - Streaming with real-time events (`runStream()`)
  - Checkpointing for state persistence (`CheckpointStorage`)
  - Resumption from checkpoints (`runFromCheckpoint()`)
- Workflow events:
  - `WorkflowStartedEvent`, `WorkflowStatusEvent`
  - `WorkflowOutputEvent`, `WorkflowFailedEvent`
  - `RequestInfoEvent`, `AgentRunEvent`, `AgentRunUpdateEvent`
- Workflow states:
  - `IN_PROGRESS`, `IN_PROGRESS_PENDING_REQUESTS`
  - `IDLE`, `IDLE_WITH_PENDING_REQUESTS`, `FAILED`
- Human-in-the-loop via `RequestInfoExecutor`
- Shared state between executors
- Graph signature validation for checkpoint compatibility

#### FR-9: Memory & Context
- `ContextProvider` abstract class with lifecycle hooks:
  - `invoking()`: Called before agent invocation to provide context
  - `invoked()`: Called after invocation to update state
  - `threadCreated()`: Called when new thread is created
- `AggregateContextProvider` for combining multiple providers
- `AIContext` interface for context data:
  - Additional instructions
  - Contextual messages
  - Dynamic tools
- Memory integration (Redis, in-memory, custom)
- RAG patterns with vector stores
- Conversation history management

#### FR-10: Observability
- OpenTelemetry integration
- Centralized logging via `getLogger()` function
- Structured logging with context
- Telemetry for:
  - Agent invocations (spans, duration, token usage)
  - Tool calls (function execution, arguments, results)
  - Workflow execution (workflow spans, executor spans)
  - Token usage tracking
- Metrics and traces
- Configurable log levels and sensitive data filtering
- `@traced` decorator for automatic span creation

#### FR-11: Provider-Specific Features
- **OpenAI**:
  - Chat completions
  - Assistant API
  - Responses API (reasoning models)
  - Vision, audio, structured outputs
  - Moderation API
- **Azure OpenAI**:
  - Endpoint configuration
  - API key and Azure AD (Entra ID) authentication
  - Model deployment names (vs model IDs)
  - API version selection
  - Regional endpoint support
- **Anthropic**:
  - Claude models (Opus, Sonnet, Haiku)
  - Extended thinking and thinking tokens
  - Tool use patterns
  - Vision capabilities
  - Prompt caching
- **Google**:
  - Gemini models
  - Function calling
  - Multimodal inputs

#### FR-12: Hosted Tools
- `HostedCodeInterpreterTool`:
  - Execute code in sandboxed environment
  - Support for file inputs
  - Session management
- `HostedFileSearchTool`:
  - Vector store-based file search
  - Configurable max results
  - Multiple vector store inputs
- `HostedWebSearchTool`:
  - Web search capabilities
  - Location context support
  - Result filtering
- `HostedMCPTool`:
  - Connect to hosted MCP services
  - Approval modes: `always_require`, `never_require`, or specific per-tool
  - Authentication headers
  - Tool filtering via `allowedTools`

#### FR-13: Agent-to-Agent Communication
- A2A protocol support
- Agent discovery and registration
- Inter-agent message passing
- Authentication and authorization
- Service mesh integration patterns

### Non-Functional Requirements

#### NFR-1: Package Structure
Follow tier-based organization similar to Python:

**Tier 0 (Core)**: Import from `@microsoft/agent-framework`
- Agents
- Tools
- Types
- Threads
- Logging
- Middleware
- Telemetry

**Tier 1 (Components)**: Import from `@microsoft/agent-framework/<component>`
- `workflows`
- `vector-data`
- `guardrails`
- `observability`

**Tier 2 (Connectors)**: Import from `@microsoft/agent-framework-<vendor>`
- `@microsoft/agent-framework-openai`
- `@microsoft/agent-framework-azure`
- `@microsoft/agent-framework-anthropic`
- `@microsoft/agent-framework-google`
- `@microsoft/agent-framework-a2a`
- `@microsoft/agent-framework-redis`

#### NFR-2: Type Safety
- Strict TypeScript compilation
- Generic types for workflows and agents
- Discriminated unions for content types
- Zod for runtime validation where needed

#### NFR-3: Runtime Compatibility
Support multiple JavaScript runtimes:
- Node.js (18+)
- Deno
- Bun
- Browser (via bundlers)
- Edge runtimes (Cloudflare Workers, Vercel Edge)

#### NFR-4: Bundle Size
- Core package < 100KB (minified + gzipped)
- Tree-shakeable exports
- Lazy loading for optional features
- No unnecessary dependencies

#### NFR-5: Performance
- Async I/O throughout
- Streaming support for large responses
- Efficient message batching
- Memory-conscious implementations

#### NFR-6: Developer Experience
- IntelliSense support via TypeScript
- Comprehensive JSDoc comments
- Example code for all major features
- Clear error messages
- Minimal configuration required

## Architecture

### Core Abstractions

#### Agent Protocol (Structural Typing)

```typescript
/**
 * Protocol for AI agents that can be invoked with messages.
 * Uses structural typing - any object with these properties/methods is compatible.
 */
export interface AgentProtocol {
  readonly id: string;
  readonly name?: string;
  readonly displayName: string;
  readonly description?: string;

  run(
    messages?: string | ChatMessage | (string | ChatMessage)[],
    options?: { thread?: AgentThread; [key: string]: any }
  ): Promise<AgentRunResponse>;

  runStream(
    messages?: string | ChatMessage | (string | ChatMessage)[],
    options?: { thread?: AgentThread; [key: string]: any }
  ): AsyncIterable<AgentRunResponseUpdate>;

  getNewThread(options?: Record<string, any>): AgentThread;
}
```

#### BaseAgent

```typescript
export abstract class BaseAgent implements AgentProtocol {
  public readonly id: string;
  public readonly name?: string;
  public readonly description?: string;
  protected contextProvider?: AggregateContextProvider;
  protected middleware?: Middleware[];

  constructor(options: BaseAgentOptions) {
    this.id = options.id ?? randomUUID();
    this.name = options.name;
    this.description = options.description;
    this.contextProvider = this.prepareContextProviders(options.contextProviders);
    this.middleware = Array.isArray(options.middleware)
      ? options.middleware
      : options.middleware ? [options.middleware] : undefined;
  }

  get displayName(): string {
    return this.name ?? this.id;
  }

  abstract run(
    messages?: string | ChatMessage | (string | ChatMessage)[],
    options?: AgentRunOptions
  ): Promise<AgentRunResponse>;

  abstract runStream(
    messages?: string | ChatMessage | (string | ChatMessage)[],
    options?: AgentRunOptions
  ): AsyncIterable<AgentRunResponseUpdate>;

  getNewThread(options?: ThreadOptions): AgentThread {
    return new AgentThread({
      ...options,
      contextProvider: this.contextProvider
    });
  }

  async deserializeThread(
    serializedThread: unknown,
    options?: Record<string, any>
  ): Promise<AgentThread> {
    const thread = this.getNewThread();
    await thread.updateFromThreadState(serializedThread, options);
    return thread;
  }

  /**
   * Convert this agent to an AIFunction tool for use by other agents
   */
  asTool(options?: AgentAsToolOptions): AIFunction<{ task: string }, string> {
    // Implementation
  }

  protected normalizeMessages(
    messages?: string | ChatMessage | (string | ChatMessage)[]
  ): ChatMessage[] {
    if (!messages) return [];
    if (typeof messages === 'string') {
      return [new ChatMessage({ role: 'user', content: messages })];
    }
    if (!Array.isArray(messages)) {
      return [messages];
    }
    return messages.map(msg =>
      typeof msg === 'string'
        ? new ChatMessage({ role: 'user', content: msg })
        : msg
    );
  }
}
```

#### ChatAgent

```typescript
export class ChatAgent extends BaseAgent {
  private chatClient: ChatClientProtocol;
  private chatOptions: ChatOptions;

  constructor(options: ChatAgentOptions) {
    super(options);
    this.chatClient = options.chatClient;
    this.chatOptions = new ChatOptions({
      modelId: options.modelId,
      instructions: options.instructions,
      temperature: options.temperature,
      maxTokens: options.maxTokens,
      tools: options.tools,
      toolChoice: options.toolChoice ?? 'auto',
      // ... other options
    });
  }

  async run(
    messages?: string | ChatMessage | (string | ChatMessage)[],
    options?: AgentRunOptions
  ): Promise<AgentRunResponse> {
    const inputMessages = this.normalizeMessages(messages);
    const [thread, chatOptions, threadMessages] = await this.prepareThreadAndMessages(
      options?.thread,
      inputMessages
    );

    // Merge runtime options with agent options
    const finalOptions = chatOptions.merge({
      modelId: options?.modelId,
      temperature: options?.temperature,
      // ... other overrides
    });

    // Call chat client
    const response = await this.chatClient.getResponse(threadMessages, finalOptions);

    // Update thread
    await this.notifyThreadOfNewMessages(thread, inputMessages, response.messages);

    return new AgentRunResponse({
      messages: response.messages,
      responseId: response.responseId,
      createdAt: response.createdAt,
      usageDetails: response.usageDetails,
      rawRepresentation: response
    });
  }

  async *runStream(
    messages?: string | ChatMessage | (string | ChatMessage)[],
    options?: AgentRunOptions
  ): AsyncIterable<AgentRunResponseUpdate> {
    const inputMessages = this.normalizeMessages(messages);
    const [thread, chatOptions, threadMessages] = await this.prepareThreadAndMessages(
      options?.thread,
      inputMessages
    );

    const finalOptions = chatOptions.merge({
      modelId: options?.modelId,
      // ... other overrides
    });

    const responseUpdates: ChatResponseUpdate[] = [];

    for await (const update of this.chatClient.getStreamingResponse(threadMessages, finalOptions)) {
      responseUpdates.push(update);

      yield new AgentRunResponseUpdate({
        contents: update.contents,
        role: update.role,
        authorName: update.authorName ?? this.name,
        responseId: update.responseId,
        messageId: update.messageId,
        rawRepresentation: update
      });
    }

    // Reconstruct final response and notify thread
    const response = ChatResponse.fromChatResponseUpdates(responseUpdates);
    await this.notifyThreadOfNewMessages(thread, inputMessages, response.messages);
  }
}
```

### Tool System

#### AIFunction

```typescript
export class AIFunction<TArgs extends z.ZodType, TReturn> implements ToolProtocol {
  public readonly name: string;
  public readonly description: string;
  public readonly approvalMode: 'always_require' | 'never_require';
  private func: (args: z.infer<TArgs>) => Promise<TReturn> | TReturn;
  private inputSchema: TArgs;

  constructor(options: AIFunctionOptions<TArgs, TReturn>) {
    this.name = options.name;
    this.description = options.description ?? '';
    this.approvalMode = options.approvalMode ?? 'never_require';
    this.func = options.func;
    this.inputSchema = options.inputSchema;
  }

  async invoke(args: z.infer<TArgs>, context?: Record<string, any>): Promise<TReturn> {
    // Validate arguments
    const validatedArgs = this.inputSchema.parse(args);

    // Execute with observability
    return await withFunctionSpan(
      { name: this.name, arguments: validatedArgs },
      async () => {
        const result = this.func(validatedArgs);
        return result instanceof Promise ? await result : result;
      }
    );
  }

  toJsonSchema(): FunctionSchema {
    return {
      type: 'function',
      function: {
        name: this.name,
        description: this.description,
        parameters: zodToJsonSchema(this.inputSchema)
      }
    };
  }
}
```

#### Decorator Pattern

```typescript
/**
 * Decorator to convert a function into an AIFunction tool
 */
export function aiFunction(options?: Partial<AIFunctionOptions<any, any>>) {
  return function <TArgs extends z.ZodType, TReturn>(
    target: any,
    propertyKey: string,
    descriptor: PropertyDescriptor
  ) {
    const originalMethod = descriptor.value;

    // Generate schema from parameter decorators or infer from TypeScript types
    const inputSchema = getSchemaFromReflection(target, propertyKey, options?.inputSchema);

    const aiFunc = new AIFunction({
      name: options?.name ?? propertyKey,
      description: options?.description ?? '',
      approvalMode: options?.approvalMode ?? 'never_require',
      func: originalMethod,
      inputSchema
    });

    descriptor.value = aiFunc;
    return descriptor;
  };
}

// Alternative functional API
export function createAIFunction<TArgs extends z.ZodType, TReturn>(
  func: (args: z.infer<TArgs>) => Promise<TReturn> | TReturn,
  schema: TArgs,
  options?: Partial<AIFunctionOptions<TArgs, TReturn>>
): AIFunction<TArgs, TReturn> {
  return new AIFunction({
    name: options?.name ?? func.name,
    description: options?.description ?? '',
    approvalMode: options?.approvalMode ?? 'never_require',
    func,
    inputSchema: schema
  });
}
```

### Workflow System

#### Workflow Builder

```typescript
export class WorkflowBuilder<TContext = any> {
  private executors = new Map<string, Executor<any, any>>();
  private edges: Edge[] = [];
  private entryExecutorId?: string;

  addExecutor<TInput, TOutput>(
    id: string,
    executor: Executor<TInput, TOutput>
  ): this {
    this.executors.set(id, executor);
    return this;
  }

  addEdge(from: string, to: string, condition?: EdgeCondition): this {
    this.edges.push({ from, to, condition });
    return this;
  }

  addConditionalEdge(
    from: string,
    condition: (output: any) => string | Promise<string>
  ): this {
    this.edges.push({ from, condition, type: 'conditional' });
    return this;
  }

  addFanOutEdge(from: string, to: string[]): this {
    this.edges.push({ from, to, type: 'fan-out' });
    return this;
  }

  addFanInEdge(from: string[], to: string): this {
    this.edges.push({ from, to, type: 'fan-in' });
    return this;
  }

  setEntry(executorId: string): this {
    this.entryExecutorId = executorId;
    return this;
  }

  build(): Workflow<TContext> {
    if (!this.entryExecutorId) {
      throw new Error('Entry executor must be set');
    }

    // Validate graph connectivity
    validateWorkflowGraph(this.executors, this.edges, this.entryExecutorId);

    return new Workflow({
      executors: this.executors,
      edges: this.edges,
      entryExecutorId: this.entryExecutorId
    });
  }
}
```

#### Workflow Execution

```typescript
export class Workflow<TContext = any> {
  private executors: Map<string, Executor<any, any>>;
  private edges: Edge[];
  private entryExecutorId: string;

  async run(
    input: any,
    options?: WorkflowRunOptions
  ): Promise<WorkflowRunResult> {
    const context = this.createRunnerContext(input, options);
    const runner = new Runner(this.executors, this.edges, this.entryExecutorId);

    // Load from checkpoint if provided
    if (options?.checkpoint) {
      await runner.loadCheckpoint(options.checkpoint);
    }

    const result = await runner.run(context);

    return {
      output: result.output,
      checkpoints: result.checkpoints,
      events: result.events
    };
  }

  async *runStream(
    input: any,
    options?: WorkflowRunOptions
  ): AsyncIterable<WorkflowEvent> {
    const context = this.createRunnerContext(input, options);
    const runner = new Runner(this.executors, this.edges, this.entryExecutorId);

    if (options?.checkpoint) {
      await runner.loadCheckpoint(options.checkpoint);
    }

    for await (const event of runner.runStream(context)) {
      yield event;
    }
  }
}
```

### Chat Client Protocol

```typescript
export interface ChatClientProtocol {
  getResponse(
    messages: ChatMessage[],
    options?: ChatOptions
  ): Promise<ChatResponse>;

  getStreamingResponse(
    messages: ChatMessage[],
    options?: ChatOptions
  ): AsyncIterable<ChatResponseUpdate>;
}

// Decorator for automatic function invocation
export function useFunctionInvocation<T extends ChatClientProtocol>(
  client: new (...args: any[]) => T
): new (...args: any[]) => T {
  return class extends client {
    async getResponse(
      messages: ChatMessage[],
      options?: ChatOptions
    ): Promise<ChatResponse> {
      // Wrap with automatic function invocation logic
      return await functionInvocationWrapper(
        super.getResponse.bind(this),
        messages,
        options
      );
    }

    async *getStreamingResponse(
      messages: ChatMessage[],
      options?: ChatOptions
    ): AsyncIterable<ChatResponseUpdate> {
      // Wrap with streaming function invocation logic
      yield* streamingFunctionInvocationWrapper(
        super.getStreamingResponse.bind(this),
        messages,
        options
      );
    }
  };
}
```

### OpenTelemetry Integration

```typescript
export const telemetry = {
  /**
   * Configure OpenTelemetry for the agent framework
   */
  configure(options: TelemetryOptions): void {
    // Setup tracer provider
    // Setup meter provider
    // Register instrumentation
  },

  /**
   * Get tracer for agent framework
   */
  getTracer(name?: string): Tracer {
    return trace.getTracer(name ?? '@microsoft/agent-framework');
  },

  /**
   * Get meter for metrics
   */
  getMeter(name?: string): Meter {
    return metrics.getMeter(name ?? '@microsoft/agent-framework');
  }
};

/**
 * Decorator for automatic tracing
 */
export function traced(spanName?: string) {
  return function (
    target: any,
    propertyKey: string,
    descriptor: PropertyDescriptor
  ) {
    const originalMethod = descriptor.value;

    descriptor.value = async function (...args: any[]) {
      const tracer = telemetry.getTracer();
      return await tracer.startActiveSpan(
        spanName ?? `${target.constructor.name}.${propertyKey}`,
        async (span) => {
          try {
            const result = await originalMethod.apply(this, args);
            span.setStatus({ code: SpanStatusCode.OK });
            return result;
          } catch (error) {
            span.recordException(error as Error);
            span.setStatus({ code: SpanStatusCode.ERROR });
            throw error;
          } finally {
            span.end();
          }
        }
      );
    };

    return descriptor;
  };
}
```

## TypeScript-Specific Patterns

### 1. Type Safety with Generics

```typescript
// Strongly typed workflow inputs/outputs
interface ResearchWorkflowInput {
  topic: string;
  depth: 'basic' | 'detailed' | 'comprehensive';
}

interface ResearchWorkflowOutput {
  summary: string;
  sources: string[];
  confidence: number;
}

const workflow = new WorkflowBuilder<ResearchWorkflowInput>()
  .addExecutor('research', new AgentExecutor<ResearchWorkflowInput, IntermediateResult>(...))
  .addExecutor('summarize', new AgentExecutor<IntermediateResult, ResearchWorkflowOutput>(...))
  .addEdge('research', 'summarize')
  .setEntry('research')
  .build();

const result = await workflow.run({
  topic: 'AI agents',
  depth: 'detailed'
}); // result is typed as WorkflowRunResult<ResearchWorkflowOutput>
```

### 2. Discriminated Unions for Content

```typescript
// Type-safe content types
type Content =
  | { type: 'text'; text: string }
  | { type: 'function_call'; callId: string; name: string; arguments: string }
  | { type: 'function_result'; callId: string; result: unknown; error?: Error }
  | { type: 'function_approval_request'; id: string; functionCall: FunctionCallContent }
  | { type: 'function_approval_response'; id: string; approved: boolean; functionCall: FunctionCallContent }
  | { type: 'image'; url: string; detail?: 'low' | 'high' | 'auto' }
  | { type: 'audio'; data: Buffer; format: 'wav' | 'mp3' }
  | { type: 'file'; fileId: string; purpose?: string }
  | { type: 'vector_store'; vectorStoreId: string };

// Type guards
export function isTextContent(content: Content): content is Extract<Content, { type: 'text' }> {
  return content.type === 'text';
}

export function isFunctionCallContent(content: Content): content is Extract<Content, { type: 'function_call' }> {
  return content.type === 'function_call';
}

export function isFunctionApprovalRequest(content: Content): content is Extract<Content, { type: 'function_approval_request' }> {
  return content.type === 'function_approval_request';
}
```

### 3. Zod for Runtime Validation

```typescript
import { z } from 'zod';

// Define schema
const WeatherArgsSchema = z.object({
  location: z.string().describe('The city name'),
  unit: z.enum(['celsius', 'fahrenheit']).default('celsius').describe('Temperature unit')
});

// Create typed function
const getWeather = createAIFunction(
  async (args) => {
    // args is typed as { location: string; unit: 'celsius' | 'fahrenheit' }
    return `Weather in ${args.location}: 22°${args.unit === 'celsius' ? 'C' : 'F'}`;
  },
  WeatherArgsSchema,
  {
    name: 'get_weather',
    description: 'Get current weather for a location'
  }
);
```

### 4. Async Iterators for Streaming

```typescript
// Clean streaming APIs
async function demonstrateStreaming() {
  const agent = new ChatAgent({ chatClient, name: 'assistant' });

  // Stream with for-await-of
  for await (const update of agent.runStream('Tell me a story')) {
    process.stdout.write(update.text ?? '');
  }

  // Or collect all updates
  const updates = [];
  for await (const update of agent.runStream('Tell me a story')) {
    updates.push(update);
  }

  // Transform streams
  async function* addTimestamps() {
    for await (const update of agent.runStream('Hello')) {
      yield { ...update, timestamp: Date.now() };
    }
  }
}
```

### 5. Builder Pattern with Method Chaining

```typescript
const agent = new ChatAgentBuilder()
  .withChatClient(client)
  .withName('assistant')
  .withInstructions('You are a helpful assistant')
  .withTools([weatherTool, calculatorTool])
  .withTemperature(0.7)
  .withMaxTokens(500)
  .withMiddleware([loggingMiddleware, telemetryMiddleware])
  .build();
```

### 6. Dependency Injection

```typescript
// Interface-based DI
interface IChatClient {
  getResponse(messages: ChatMessage[], options?: ChatOptions): Promise<ChatResponse>;
}

class ChatAgent {
  constructor(
    private readonly chatClient: IChatClient,
    private readonly logger: ILogger,
    private readonly telemetry: ITelemetry
  ) {}
}

// With DI container (e.g., TSyringe)
@injectable()
class ChatAgent {
  constructor(
    @inject('ChatClient') private chatClient: IChatClient,
    @inject('Logger') private logger: ILogger
  ) {}
}
```

## Memory & Context System

### Context Provider Architecture

```typescript
/**
 * Abstract base class for context providers
 */
export abstract class ContextProvider {
  /**
   * Called when a new thread is created
   */
  async threadCreated(threadId?: string): Promise<void> {
    // Override in subclass
  }

  /**
   * Called before agent invocation to provide additional context
   */
  abstract invoking(messages: ChatMessage[], options?: any): Promise<AIContext>;

  /**
   * Called after agent invocation to update state
   */
  async invoked(
    requestMessages: ChatMessage[],
    responseMessages: ChatMessage[],
    error?: Error
  ): Promise<void> {
    // Override in subclass
  }
}

/**
 * Context data returned by context providers
 */
export interface AIContext {
  instructions?: string;
  messages?: ChatMessage[];
  tools?: AITool[];
}

/**
 * Combines multiple context providers into one
 */
export class AggregateContextProvider extends ContextProvider {
  private providers: ContextProvider[];

  constructor(providers: ContextProvider | ContextProvider[]) {
    super();
    this.providers = Array.isArray(providers) ? providers : [providers];
  }

  add(provider: ContextProvider): void {
    this.providers.push(provider);
  }

  async threadCreated(threadId?: string): Promise<void> {
    await Promise.all(this.providers.map(p => p.threadCreated(threadId)));
  }

  async invoking(messages: ChatMessage[], options?: any): Promise<AIContext> {
    const contexts = await Promise.all(
      this.providers.map(p => p.invoking(messages, options))
    );

    // Merge all contexts
    return {
      instructions: contexts.map(c => c.instructions).filter(Boolean).join('\n\n'),
      messages: contexts.flatMap(c => c.messages ?? []),
      tools: contexts.flatMap(c => c.tools ?? [])
    };
  }

  async invoked(
    requestMessages: ChatMessage[],
    responseMessages: ChatMessage[],
    error?: Error
  ): Promise<void> {
    await Promise.all(
      this.providers.map(p => p.invoked(requestMessages, responseMessages, error))
    );
  }
}
```

### Example: Memory Context Provider

```typescript
class MemoryContextProvider extends ContextProvider {
  private memories = new Map<string, string[]>();

  async invoking(messages: ChatMessage[]): Promise<AIContext> {
    const threadId = this.getCurrentThreadId();
    const memories = this.memories.get(threadId) ?? [];

    if (memories.length === 0) {
      return { instructions: undefined, messages: [], tools: [] };
    }

    const instructions = [
      '## Memories',
      'Consider the following memories when answering:',
      ...memories.map((m, i) => `${i + 1}. ${m}`)
    ].join('\n');

    return { instructions, messages: [], tools: [] };
  }

  async invoked(
    requestMessages: ChatMessage[],
    responseMessages: ChatMessage[]
  ): Promise<void> {
    // Extract and store important information from the conversation
    const threadId = this.getCurrentThreadId();
    // ... memory extraction logic
  }
}
```

## Thread Management & Serialization

### Thread Architecture

```typescript
export interface ChatMessageStore {
  addMessage(message: ChatMessage): Promise<void>;
  getMessages(): Promise<ChatMessage[]>;
  clear(): Promise<void>;
  serialize(): Promise<ThreadState>;
  deserialize(state: ThreadState): Promise<void>;
}

export class AgentThread {
  // Service-managed thread (server-side history)
  public serviceThreadId?: string;

  // Local-managed thread (client-side history)
  public messageStore?: ChatMessageStore;

  // Context provider for memory
  public contextProvider?: ContextProvider;

  constructor(options?: {
    serviceThreadId?: string;
    messageStore?: ChatMessageStore;
    contextProvider?: ContextProvider;
  }) {
    this.serviceThreadId = options?.serviceThreadId;
    this.messageStore = options?.messageStore;
    this.contextProvider = options?.contextProvider;
  }

  async onNewMessages(messages: ChatMessage | ChatMessage[]): Promise<void> {
    const messageArray = Array.isArray(messages) ? messages : [messages];

    if (this.messageStore) {
      for (const message of messageArray) {
        await this.messageStore.addMessage(message);
      }
    }
  }

  serialize(): ThreadState {
    return {
      serviceThreadId: this.serviceThreadId,
      messages: this.messageStore ? await this.messageStore.getMessages() : [],
      contextProviderState: this.contextProvider?.serialize()
    };
  }

  async updateFromThreadState(state: ThreadState): Promise<void> {
    this.serviceThreadId = state.serviceThreadId;

    if (this.messageStore && state.messages) {
      await this.messageStore.clear();
      for (const message of state.messages) {
        await this.messageStore.addMessage(message);
      }
    }

    if (this.contextProvider && state.contextProviderState) {
      await this.contextProvider.deserialize(state.contextProviderState);
    }
  }
}

interface ThreadState {
  serviceThreadId?: string;
  messages?: ChatMessage[];
  contextProviderState?: any;
}
```

## Workflow System Details

### Workflow Events

```typescript
// Base workflow event
export interface WorkflowEvent {
  type: string;
  timestamp: Date;
  workflowId: string;
}

// Specific event types
export interface WorkflowStartedEvent extends WorkflowEvent {
  type: 'workflow_started';
}

export enum WorkflowRunState {
  IN_PROGRESS = 'IN_PROGRESS',
  IN_PROGRESS_PENDING_REQUESTS = 'IN_PROGRESS_PENDING_REQUESTS',
  IDLE = 'IDLE',
  IDLE_WITH_PENDING_REQUESTS = 'IDLE_WITH_PENDING_REQUESTS',
  FAILED = 'FAILED'
}

export interface WorkflowStatusEvent extends WorkflowEvent {
  type: 'workflow_status';
  state: WorkflowRunState;
}

export interface WorkflowOutputEvent extends WorkflowEvent {
  type: 'workflow_output';
  data: any;
}

export interface WorkflowFailedEvent extends WorkflowEvent {
  type: 'workflow_failed';
  error: Error;
  errorType: string;
  errorMessage: string;
}

export interface RequestInfoEvent extends WorkflowEvent {
  type: 'request_info';
  requestId: string;
  data: any;
}

export interface AgentRunEvent extends WorkflowEvent {
  type: 'agent_run';
  executorId: string;
  agentId: string;
  response: AgentRunResponse;
}

export interface AgentRunUpdateEvent extends WorkflowEvent {
  type: 'agent_run_update';
  executorId: string;
  agentId: string;
  update: AgentRunResponseUpdate;
}

type WorkflowEventUnion =
  | WorkflowStartedEvent
  | WorkflowStatusEvent
  | WorkflowOutputEvent
  | WorkflowFailedEvent
  | RequestInfoEvent
  | AgentRunEvent
  | AgentRunUpdateEvent;
```

### Checkpoint System

```typescript
export interface CheckpointStorage {
  saveCheckpoint(checkpointId: string, data: WorkflowCheckpoint): Promise<void>;
  loadCheckpoint(checkpointId: string): Promise<WorkflowCheckpoint | null>;
  listCheckpoints(workflowId: string): Promise<string[]>;
  deleteCheckpoint(checkpointId: string): Promise<void>;
}

export interface WorkflowCheckpoint {
  checkpointId: string;
  workflowId: string;
  timestamp: Date;
  graphSignatureHash: string;
  executorStates: Record<string, any>;
  pendingMessages: any[];
  sharedState: any;
}

// In-memory checkpoint storage
export class InMemoryCheckpointStorage implements CheckpointStorage {
  private checkpoints = new Map<string, WorkflowCheckpoint>();

  async saveCheckpoint(checkpointId: string, data: WorkflowCheckpoint): Promise<void> {
    this.checkpoints.set(checkpointId, data);
  }

  async loadCheckpoint(checkpointId: string): Promise<WorkflowCheckpoint | null> {
    return this.checkpoints.get(checkpointId) ?? null;
  }

  async listCheckpoints(workflowId: string): Promise<string[]> {
    return Array.from(this.checkpoints.values())
      .filter(cp => cp.workflowId === workflowId)
      .map(cp => cp.checkpointId);
  }

  async deleteCheckpoint(checkpointId: string): Promise<void> {
    this.checkpoints.delete(checkpointId);
  }
}

// Usage in workflow
const workflow = new WorkflowBuilder()
  .withCheckpointing(new InMemoryCheckpointStorage())
  .addAgent(researchAgent)
  .addAgent(summaryAgent)
  .addEdge(researchAgent, summaryAgent)
  .setEntry(researchAgent)
  .build();

// Resume from checkpoint
const events = await workflow.runFromCheckpoint(
  'checkpoint-123',
  { 'request-1': 'user provided data' }
);
```

### Human-in-the-Loop (RequestInfoExecutor)

```typescript
export class RequestInfoExecutor extends Executor {
  async execute(message: any, context: WorkflowContext): Promise<void> {
    // Extract request information from message
    const requestId = generateRequestId();

    // Emit request event
    context.addEvent({
      type: 'request_info',
      requestId,
      data: message,
      timestamp: new Date(),
      workflowId: context.workflowId
    });

    // Store pending request
    this.pendingRequests.set(requestId, message);
  }

  async handleResponse(response: any, requestId: string, context: WorkflowContext): Promise<void> {
    if (!this.pendingRequests.has(requestId)) {
      throw new Error(`No pending request found with ID: ${requestId}`);
    }

    this.pendingRequests.delete(requestId);

    // Send response back to the workflow
    context.sendMessage(response, this.targetExecutorId);
  }
}

// Usage
const workflow = new WorkflowBuilder()
  .addAgent(researchAgent, 'research')
  .addExecutor('request_info', new RequestInfoExecutor())
  .addAgent(processAgent, 'process')
  .addEdge('research', 'request_info')
  .addEdge('request_info', 'process')
  .setEntry('research')
  .build();

// Run and wait for request
const events: WorkflowEvent[] = [];
for await (const event of workflow.runStream(input)) {
  events.push(event);

  if (event.type === 'request_info') {
    // Pause and handle request
    const response = await getUserInput(event.data);

    // Continue workflow with response
    for await (const continueEvent of workflow.sendResponsesStreaming({
      [event.requestId]: response
    })) {
      events.push(continueEvent);
    }
  }
}
```

## Error Handling & Exception Hierarchy

```typescript
/**
 * Base error class for all agent framework errors
 */
export class AgentFrameworkError extends Error {
  public readonly cause?: Error;

  constructor(message: string, cause?: Error) {
    super(message);
    this.name = this.constructor.name;
    this.cause = cause;
    Error.captureStackTrace?.(this, this.constructor);
  }
}

/**
 * Thrown when agent execution fails
 */
export class AgentExecutionError extends AgentFrameworkError {}

/**
 * Thrown when agent initialization fails
 */
export class AgentInitializationError extends AgentFrameworkError {}

/**
 * Thrown when tool execution fails
 */
export class ToolExecutionError extends AgentFrameworkError {
  constructor(
    message: string,
    public readonly toolName: string,
    cause?: Error
  ) {
    super(message, cause);
  }
}

/**
 * Thrown when chat client operations fail
 */
export class ChatClientError extends AgentFrameworkError {}

/**
 * Thrown when workflow validation fails
 */
export class WorkflowValidationError extends AgentFrameworkError {}

/**
 * Thrown when workflow graph is invalid
 */
export class GraphConnectivityError extends WorkflowValidationError {}

/**
 * Thrown when workflow type compatibility fails
 */
export class TypeCompatibilityError extends WorkflowValidationError {}
```

## Logging System

```typescript
export enum LogLevel {
  DEBUG = 'debug',
  INFO = 'info',
  WARN = 'warn',
  ERROR = 'error'
}

export interface Logger {
  debug(message: string, context?: Record<string, any>): void;
  info(message: string, context?: Record<string, any>): void;
  warn(message: string, context?: Record<string, any>): void;
  error(message: string, error?: Error, context?: Record<string, any>): void;
  setLevel(level: LogLevel): void;
}

// Centralized logger configuration
const loggers = new Map<string, Logger>();

export function getLogger(name: string = 'agent_framework'): Logger {
  if (!loggers.has(name)) {
    loggers.set(name, createLogger(name));
  }
  return loggers.get(name)!;
}

export function configureLogging(options: {
  level?: LogLevel;
  format?: 'json' | 'text';
  destination?: (message: string) => void;
}): void {
  // Configure global logging settings
}

// Usage in agent code
const logger = getLogger('agent_framework.agents');

logger.info('Agent invoked', { agentId: this.id, modelId: options.modelId });
logger.debug('Function arguments', { functionName, args });
logger.error('Agent execution failed', error, { agentId: this.id });
```

## Hosted Tools Implementation

```typescript
export class HostedCodeInterpreterTool extends BaseTool {
  constructor(options?: {
    inputs?: Content[];
    description?: string;
  }) {
    super({
      name: 'code_interpreter',
      description: options?.description ?? 'Execute code in a sandboxed environment'
    });
    this.inputs = options?.inputs ?? [];
  }
}

export class HostedFileSearchTool extends BaseTool {
  constructor(options?: {
    inputs?: Content[];
    maxResults?: number;
    description?: string;
  }) {
    super({
      name: 'file_search',
      description: options?.description ?? 'Search through uploaded files'
    });
    this.inputs = options?.inputs ?? [];
    this.maxResults = options?.maxResults;
  }
}

export class HostedWebSearchTool extends BaseTool {
  constructor(options?: {
    userLocation?: { city: string; country: string };
    description?: string;
  }) {
    super({
      name: 'web_search',
      description: options?.description ?? 'Search the web for information'
    });
    this.userLocation = options?.userLocation;
  }
}

export interface HostedMCPSpecificApproval {
  alwaysRequireApproval?: string[];
  neverRequireApproval?: string[];
}

export class HostedMCPTool extends BaseTool {
  public readonly url: string;
  public readonly approvalMode?: 'always_require' | 'never_require' | HostedMCPSpecificApproval;
  public readonly allowedTools?: Set<string>;
  public readonly headers?: Record<string, string>;

  constructor(options: {
    name: string;
    url: string;
    description?: string;
    approvalMode?: 'always_require' | 'never_require' | HostedMCPSpecificApproval;
    allowedTools?: string[];
    headers?: Record<string, string>;
  }) {
    super({
      name: options.name,
      description: options.description ?? `MCP tool: ${options.name}`
    });
    this.url = options.url;
    this.approvalMode = options.approvalMode;
    this.allowedTools = options.allowedTools ? new Set(options.allowedTools) : undefined;
    this.headers = options.headers;
  }
}

// Usage
const agent = new ChatAgent({
  chatClient,
  name: 'assistant',
  tools: [
    new HostedCodeInterpreterTool(),
    new HostedFileSearchTool({ maxResults: 10 }),
    new HostedWebSearchTool(),
    new HostedMCPTool({
      name: 'my_mcp_service',
      url: 'https://api.example.com/mcp',
      approvalMode: 'always_require',
      headers: { 'Authorization': 'Bearer token' }
    })
  ]
});
```

## Package Structure

```
packages/
├── core/                          # @microsoft/agent-framework
│   ├── src/
│   │   ├── agents/
│   │   │   ├── base-agent.ts
│   │   │   ├── chat-agent.ts
│   │   │   ├── protocol.ts
│   │   │   └── index.ts
│   │   ├── tools/
│   │   │   ├── ai-function.ts
│   │   │   ├── decorators.ts
│   │   │   ├── hosted-tools.ts
│   │   │   ├── protocol.ts
│   │   │   └── index.ts
│   │   ├── types/
│   │   │   ├── messages.ts
│   │   │   ├── responses.ts
│   │   │   ├── options.ts
│   │   │   ├── content.ts
│   │   │   └── index.ts
│   │   ├── threads/
│   │   │   ├── agent-thread.ts
│   │   │   ├── message-store.ts
│   │   │   └── index.ts
│   │   ├── clients/
│   │   │   ├── protocol.ts
│   │   │   ├── base-client.ts
│   │   │   └── index.ts
│   │   ├── middleware/
│   │   │   ├── protocol.ts
│   │   │   ├── pipeline.ts
│   │   │   └── index.ts
│   │   ├── mcp/
│   │   │   ├── client.ts
│   │   │   ├── server.ts
│   │   │   ├── tool.ts
│   │   │   └── index.ts
│   │   ├── memory/
│   │   │   ├── context-provider.ts
│   │   │   └── index.ts
│   │   ├── telemetry/
│   │   │   ├── configure.ts
│   │   │   ├── decorators.ts
│   │   │   └── index.ts
│   │   ├── logging/
│   │   │   └── index.ts
│   │   └── index.ts              # Main exports
│   ├── tests/
│   ├── package.json
│   └── tsconfig.json
│
├── workflows/                     # @microsoft/agent-framework/workflows
│   ├── src/
│   │   ├── workflow.ts
│   │   ├── builder.ts
│   │   ├── executors/
│   │   ├── edges/
│   │   ├── events.ts
│   │   ├── checkpoint.ts
│   │   ├── runner.ts
│   │   └── index.ts
│   └── package.json
│
├── openai/                        # @microsoft/agent-framework-openai
│   ├── src/
│   │   ├── chat-client.ts
│   │   ├── assistant-client.ts
│   │   ├── responses-client.ts
│   │   ├── extensions.ts
│   │   └── index.ts
│   └── package.json
│
├── azure/                         # @microsoft/agent-framework-azure
│   ├── src/
│   │   ├── openai-client.ts
│   │   ├── ai-client.ts
│   │   ├── auth.ts
│   │   └── index.ts
│   └── package.json
│
├── anthropic/                     # @microsoft/agent-framework-anthropic
│   ├── src/
│   │   ├── claude-client.ts
│   │   └── index.ts
│   └── package.json
│
└── examples/                      # Example applications
    ├── basic-chat/
    ├── workflows/
    ├── streaming/
    └── multi-agent/
```

## Implementation Roadmap

### Phase 1: Core Foundation (MVP)
**Goal**: Minimal viable implementation for basic agent scenarios

**Features**:
- Core types (ChatMessage, ChatOptions, AgentRunResponse)
- AgentProtocol interface and BaseAgent class
- ChatAgent implementation
- Basic tool system (AIFunction, ToolProtocol)
- Chat client protocol
- OpenAI chat client implementation
- In-memory thread management
- Function calling support (manual invocation)

**Deliverables**:
- `@microsoft/agent-framework` core package
- `@microsoft/agent-framework-openai` connector
- Basic examples
- Unit tests

**Timeline**: 4-6 weeks

### Phase 2: Enhanced Features
**Goal**: Add middleware, automatic function invocation, and streaming

**Features**:
- Middleware system and pipeline
- Automatic function invocation via decorator
- Streaming support for agents and chat clients
- Context providers
- OpenTelemetry integration (basic)
- Logging system
- Azure OpenAI client
- Anthropic client

**Deliverables**:
- Enhanced core package
- `@microsoft/agent-framework-azure` connector
- `@microsoft/agent-framework-anthropic` connector
- Middleware examples
- Integration tests

**Timeline**: 4-6 weeks

### Phase 3: Workflows
**Goal**: Multi-agent orchestration

**Features**:
- Workflow graph system
- Executors (Agent, Function, Workflow)
- Edges (direct, conditional, fan-out/in, switch-case)
- Workflow builder
- Execution engine
- Event streaming
- Checkpointing system
- Human-in-the-loop (request ports)
- Shared state

**Deliverables**:
- `@microsoft/agent-framework/workflows` package
- Workflow examples
- Declarative workflow support (YAML)

**Timeline**: 6-8 weeks

### Phase 4: Advanced Features
**Goal**: Production-ready feature complete implementation

**Features**:
- MCP client and server
- Vector stores and memory
- Guardrails
- Additional providers (Google, etc.)
- A2A support
- Enhanced observability
- Performance optimizations
- Edge runtime support

**Deliverables**:
- Full provider coverage
- MCP support
- Memory packages
- Production examples
- Performance benchmarks

**Timeline**: 6-8 weeks

### Phase 5: Polish and Ecosystem
**Goal**: Production hardening and ecosystem growth

**Features**:
- Comprehensive documentation
- Video tutorials
- Advanced examples (RAG, multi-agent systems, etc.)
- Framework integrations (Next.js, Express, Fastify)
- CLI tools
- VS Code extension
- Performance optimization
- Security hardening

**Deliverables**:
- Complete documentation site
- Migration guides
- Integration packages
- Developer tools

**Timeline**: 8-12 weeks

## Testing Strategy

### Unit Tests
- Jest or Vitest for test runner
- Mock all external dependencies
- Test coverage > 80%
- Test all public APIs
- Type safety tests

### Integration Tests
- Real LLM provider calls (with VCR for CI)
- Workflow execution scenarios
- MCP client/server interactions
- End-to-end agent scenarios

### Type Tests
- Use `@ts-expect-error` for negative type tests
- Verify generic type inference
- Discriminated union exhaustiveness
- Schema validation

### Performance Tests
- Benchmark critical paths
- Memory leak detection
- Bundle size monitoring
- Streaming performance

## Alternative Considerations

### Alternative 1: Port Exact Python API
**Pros**: Easier migration from Python
**Cons**: Not idiomatic TypeScript, misses TypeScript advantages
**Decision**: Rejected - prefer idiomatic TypeScript

### Alternative 2: Minimal Core + Plugins
**Pros**: Smaller core bundle
**Cons**: More complex for users, discovery issues
**Decision**: Partial adoption - core features included, extensions as plugins

### Alternative 3: Class-Based vs Functional
**Pros (Classes)**: Familiar OOP patterns, matches Python/.NET
**Pros (Functional)**: Better tree-shaking, simpler
**Decision**: Hybrid - classes for agents/workflows, functional utilities

### Alternative 4: Zod vs JSON Schema
**Pros (Zod)**: Better TypeScript integration, runtime validation
**Pros (JSON Schema)**: Standard format, wider compatibility
**Decision**: Zod primary, JSON Schema for interop

## Open Questions

1. **Runtime Support Priority**: Which runtimes to prioritize? (Node.js first, then edge?)
2. **Bundle Size vs Features**: Where to draw the line on core package size?
3. **Naming Conventions**: Match Python (snake_case methods) or use TypeScript conventions (camelCase)?
4. **Versioning Strategy**: Independent package versions or monolithic versioning?
5. **CLI Tools**: Should we include CLI tools in core or separate package?

## Dependencies

### Core Dependencies
- `zod` - Schema validation
- `@opentelemetry/api` - Telemetry (peer dependency)
- `@modelcontextprotocol/sdk` - MCP support

### Development Dependencies
- TypeScript 5.3+
- Jest or Vitest
- ESLint + Prettier
- Rollup or tsup for bundling

## Success Metrics

- **Adoption**: 1000+ npm downloads/week within 6 months
- **Performance**: < 50ms overhead for agent invocation
- **Bundle Size**: Core < 100KB minified + gzipped
- **Type Safety**: 100% TypeScript strict mode
- **Test Coverage**: > 80% code coverage
- **Documentation**: 100% of public APIs documented
- **Examples**: 20+ runnable examples covering major scenarios

## References

- [Python Implementation](../../python/)
- [.NET Implementation](../../dotnet/)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)
- [Zod Documentation](https://zod.dev/)
- [OpenTelemetry JS](https://opentelemetry.io/docs/languages/js/)
- [Model Context Protocol](https://modelcontextprotocol.io/)

## Change History
- 2025-10-11: Initial specification created based on Python and .NET analysis
- 2025-10-11: Comprehensive updates based on gap analysis:
  - Added FR-13 for Agent-to-Agent (A2A) communication
  - Expanded FR-4 with approval flow content types
  - Expanded FR-5 with service vs local thread management details
  - Expanded FR-8 with comprehensive workflow events and states
  - Expanded FR-9 with detailed ContextProvider architecture
  - Expanded FR-10 with centralized logging approach
  - Expanded FR-11 with provider-specific nuances
  - Expanded FR-12 with complete hosted tool signatures
  - Added comprehensive Memory & Context System section
  - Added Thread Management & Serialization section
  - Added Workflow System Details with events and checkpointing
  - Added Error Handling & Exception Hierarchy
  - Added Logging System specification
  - Added complete Hosted Tools Implementation examples
