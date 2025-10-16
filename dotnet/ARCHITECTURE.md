# Microsoft Agent Framework - .NET Architecture

## High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │   Blazor     │  │  Console     │  │   ASP.NET    │  │   Aspire     │   │
│  │   Web Apps   │  │     Apps     │  │    Core      │  │   Projects   │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│                          HOSTING LAYER                                       │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │          Microsoft.Agents.AI.Hosting                               │    │
│  │  - AgentCatalog                                                    │    │
│  │  - LocalAgentRegistry                                              │    │
│  │  - Dependency Injection                                            │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────┐  ┌──────────────────────────────────────────┐    │
│  │  Hosting.A2A        │  │  Hosting.OpenAI                          │    │
│  │  AspNetCore         │  │  - Endpoint builders                     │    │
│  │  - A2A endpoints    │  │  - OpenAI-compatible API hosting         │    │
│  └─────────────────────┘  └──────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│                        WORKFLOW LAYER (Optional)                             │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │       Microsoft.Agents.AI.Workflows.Declarative                    │    │
│  │  - YAML workflow definitions                                       │    │
│  │  - PowerFx expression evaluation                                   │    │
│  │  - Schema validation                                               │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                             │                                                │
│                             ▼                                                │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │          Microsoft.Agents.AI.Workflows                             │    │
│  │  - Graph-based orchestration                                       │    │
│  │  - Executors & Edges                                               │    │
│  │  - Checkpoint/Resume                                               │    │
│  │  - State management                                                │    │
│  │  - Observability (OpenTelemetry)                                   │    │
│  └────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CORE AGENT LAYER                                    │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │             Microsoft.Agents.AI                                    │    │
│  │  - AIAgentBuilder (fluent API)                                     │    │
│  │  - OpenTelemetry integration                                       │    │
│  │  - Function invocation handling                                    │    │
│  │  - Chat client abstraction                                         │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                             │                                                │
│                             ▼                                                │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │          Microsoft.Agents.AI.Abstractions                          │    │
│  │  - AIAgent interface                                               │    │
│  │  - AgentThread                                                     │    │
│  │  - AgentRunOptions / AgentRunResponse                              │    │
│  │  - ChatMessageStore                                                │    │
│  │  - AIContext                                                       │    │
│  └────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│                       PROVIDER LAYER                                         │
│                                                                              │
│  ┌───────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐   │
│  │  AI.OpenAI    │  │  AI.AzureAI  │  │ AI.Copilot   │  │   AI.A2A    │   │
│  │               │  │              │  │   Studio     │  │             │   │
│  │ - ChatClient  │  │ - Persistent │  │ - Activity   │  │ - A2AAgent  │   │
│  │ - Response    │  │   Agents     │  │   Processor  │  │ - A2AHost   │   │
│  │   API         │  │              │  │              │  │   Agent     │   │
│  └───────────────┘  └──────────────┘  └──────────────┘  └─────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│                     EXTERNAL SDK LAYER                                       │
│                                                                              │
│  ┌───────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐   │
│  │ Azure.AI.     │  │   OpenAI     │  │   Copilot    │  │    A2A      │   │
│  │  OpenAI       │  │     SDK      │  │   Studio     │  │  Protocol   │   │
│  │               │  │              │  │   Client     │  │             │   │
│  └───────────────┘  └──────────────┘  └──────────────┘  └─────────────┘   │
│                                                                              │
│  ┌───────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐   │
│  │  Microsoft.   │  │  OllamaSharp │  │ ONNX Runtime │  │    MCP      │   │
│  │ Extensions.AI │  │              │  │    GenAI     │  │  Protocol   │   │
│  └───────────────┘  └──────────────┘  └──────────────┘  └─────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Dependency Graph

### Core Dependencies

```
Microsoft.Agents.AI.Abstractions
    ├── Microsoft.Extensions.AI.Abstractions
    └── Microsoft.Extensions.Logging.Abstractions
    
Microsoft.Agents.AI
    ├── Microsoft.Agents.AI.Abstractions
    ├── Microsoft.Extensions.AI
    ├── Microsoft.Extensions.DependencyInjection.Abstractions
    └── System.Diagnostics.DiagnosticSource
```

### Provider Dependencies

```
Microsoft.Agents.AI.OpenAI
    ├── Microsoft.Agents.AI.Abstractions
    ├── Microsoft.Agents.AI
    └── OpenAI SDK (via Microsoft.Extensions.AI)

Microsoft.Agents.AI.AzureAI
    ├── Microsoft.Agents.AI.Abstractions
    ├── Microsoft.Agents.AI
    └── Azure.AI.Agents.Persistent

Microsoft.Agents.AI.CopilotStudio
    ├── Microsoft.Agents.AI.Abstractions
    ├── Microsoft.Agents.AI
    └── Microsoft.Agents.CopilotStudio.Client

Microsoft.Agents.AI.A2A
    ├── Microsoft.Agents.AI.Abstractions
    ├── Microsoft.Agents.AI
    └── A2A Protocol Library
```

### Workflow Dependencies

```
Microsoft.Agents.AI.Workflows
    ├── Microsoft.Agents.AI.Abstractions
    ├── Microsoft.Agents.AI
    └── OpenTelemetry.Api

Microsoft.Agents.AI.Workflows.Declarative
    ├── Microsoft.Agents.AI.Workflows
    ├── Microsoft.Bot.ObjectModel
    ├── Microsoft.Bot.ObjectModel.Json
    ├── Microsoft.Bot.ObjectModel.PowerFx
    └── Microsoft.PowerFx.Interpreter
```

### Hosting Dependencies

```
Microsoft.Agents.AI.Hosting
    ├── Microsoft.Agents.AI.Abstractions
    ├── Microsoft.Agents.AI
    └── Microsoft.Extensions.DependencyInjection

Microsoft.Agents.AI.Hosting.A2A
    ├── Microsoft.Agents.AI.Hosting
    ├── Microsoft.Agents.AI.A2A
    └── A2A Protocol

Microsoft.Agents.AI.Hosting.A2A.AspNetCore
    ├── Microsoft.Agents.AI.Hosting.A2A
    ├── ASP.NET Core
    └── A2A.AspNetCore

Microsoft.Agents.AI.Hosting.OpenAI
    ├── Microsoft.Agents.AI.Hosting
    └── ASP.NET Core
```

---

## Data Flow Diagrams

### Basic Agent Execution Flow

```
┌──────────────┐
│   Client     │
│  Application │
└──────┬───────┘
       │
       │ 1. Create agent using builder
       ▼
┌────────────────────────┐
│   AIAgentBuilder       │
│  - Configure provider  │
│  - Set instructions    │
│  - Add tools           │
└──────┬─────────────────┘
       │
       │ 2. Build agent
       ▼
┌────────────────────────┐
│    AIAgent instance    │
│   (OpenTelemetry-      │
│    wrapped)            │
└──────┬─────────────────┘
       │
       │ 3. RunAsync(message)
       ▼
┌────────────────────────┐
│  Provider-specific     │
│  Agent Implementation  │
│  (e.g., OpenAI)        │
└──────┬─────────────────┘
       │
       │ 4. Call LLM API
       ▼
┌────────────────────────┐
│   External LLM API     │
│  (OpenAI, Azure, etc)  │
└──────┬─────────────────┘
       │
       │ 5. Response
       ▼
┌────────────────────────┐
│   AgentRunResponse     │
│  - Messages            │
│  - Tool calls          │
│  - Metadata            │
└──────┬─────────────────┘
       │
       │ 6. Return to client
       ▼
┌──────────────┐
│   Client     │
│  Application │
└──────────────┘
```

### Workflow Execution Flow

```
┌──────────────┐
│   Client     │
└──────┬───────┘
       │ 1. Define workflow using builder
       ▼
┌────────────────────────┐
│  WorkflowBuilder       │
│  - Add executors       │
│  - Define edges        │
│  - Configure routing   │
└──────┬─────────────────┘
       │ 2. Build
       ▼
┌────────────────────────┐
│    Workflow            │
│  - Graph structure     │
│  - Executors           │
│  - Routing logic       │
└──────┬─────────────────┘
       │ 3. RunAsync(input)
       ▼
┌────────────────────────┐
│   InProcessRunner      │
│  - Execution engine    │
└──────┬─────────────────┘
       │ 4. Execute executors in graph order
       ▼
┌────────────────────────────────────────────┐
│         Executor Execution                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐│
│  │Executor 1│→ │Executor 2│→ │Executor 3││
│  └──────────┘  └──────────┘  └──────────┘│
│       │             │             │       │
│       ├─────────────┴─────────────┤       │
│       │  Message routing          │       │
│       │  State management         │       │
│       │  Conditional edges        │       │
└───────┴───────────────────────────────────┘
       │
       │ 5. Collect outputs
       ▼
┌────────────────────────┐
│   StreamingRun         │
│  - Output stream       │
│  - Events              │
│  - State snapshots     │
└──────┬─────────────────┘
       │ 6. Stream to client
       ▼
┌──────────────┐
│   Client     │
│  (processes  │
│   events)    │
└──────────────┘
```

### Declarative Workflow Flow

```
┌──────────────┐
│  YAML file   │
│  (workflow   │
│  definition) │
└──────┬───────┘
       │ 1. Load YAML
       ▼
┌────────────────────────┐
│ DeclarativeWorkflow    │
│   Language             │
│  - Parse YAML          │
│  - Validate schema     │
└──────┬─────────────────┘
       │ 2. Create object model
       ▼
┌────────────────────────┐
│  Workflow ObjectModel  │
│  - Agents              │
│  - Executors           │
│  - Edges               │
│  - PowerFx expressions │
└──────┬─────────────────┘
       │ 3. Build workflow
       ▼
┌────────────────────────┐
│ DeclarativeWorkflow    │
│   Builder              │
│  - Create executors    │
│  - Resolve agents      │
│  - Set up routing      │
└──────┬─────────────────┘
       │ 4. Generate
       ▼
┌────────────────────────┐
│   Workflow             │
│   (executable)         │
└──────┬─────────────────┘
       │ 5. Execute (same as programmatic)
       ▼
    (see above)
```

### A2A Communication Flow

```
┌──────────────┐                    ┌──────────────┐
│  Client      │                    │  A2A Server  │
│  Agent       │                    │  Agent       │
└──────┬───────┘                    └──────┬───────┘
       │                                   │
       │ 1. Create A2A connection          │
       │───────────────────────────────────>
       │                                   │
       │ 2. Send message (A2A protocol)    │
       │───────────────────────────────────>
       │                                   │
       │                                   │ 3. Process with
       │                                   │    A2AHostAgent
       │                                   ▼
       │                            ┌──────────────┐
       │                            │  Actual      │
       │                            │  Agent       │
       │                            │  Logic       │
       │                            └──────┬───────┘
       │                                   │
       │                                   │ 4. Execute
       │                                   │
       │                                   ▼
       │                            ┌──────────────┐
       │                            │  Response    │
       │                            └──────┬───────┘
       │                                   │
       │ 5. Return via A2A protocol        │
       │<───────────────────────────────────
       │                                   │
       ▼                                   ▼
┌──────────────┐                    ┌──────────────┐
│  Client      │                    │  A2A Server  │
│  receives    │                    │              │
│  response    │                    │              │
└──────────────┘                    └──────────────┘
```

---

## Key Design Patterns

### 1. Builder Pattern
**Used in:** `AIAgentBuilder`, `WorkflowBuilder`, `DeclarativeWorkflowBuilder`

Provides fluent API for constructing complex agents and workflows:
```csharp
var agent = chatClient
    .CreateAIAgent(name: "MyAgent")
    .WithInstructions("You are helpful")
    .WithTools([myTool])
    .Build();
```

### 2. Decorator Pattern
**Used in:** `OpenTelemetryAgent`, `DelegatingAIAgent`, `FunctionInvocationDelegatingAgent`

Wraps agents to add cross-cutting concerns:
- Observability
- Function invocation handling
- Middleware processing

### 3. Provider Pattern
**Used in:** Multiple provider implementations (`OpenAI`, `AzureAI`, `CopilotStudio`, `A2A`)

Abstracts different AI service providers behind common interfaces.

### 4. Repository Pattern
**Used in:** `ChatMessageStore`, `ICheckpointStore`

Abstracts data storage for threads, messages, and checkpoints.

### 5. Graph Pattern
**Used in:** Workflows

Represents execution flow as a directed graph with executors as nodes and edges defining transitions.

### 6. Observer Pattern
**Used in:** Streaming responses, workflow events

Streams events and updates to subscribers:
```csharp
await foreach (var update in streamingRun)
{
    // Process updates
}
```

### 7. Strategy Pattern
**Used in:** Executors, routing logic

Different execution strategies for workflow nodes.

### 8. Chain of Responsibility
**Used in:** Middleware pipeline, edge routing

Sequential processing with conditional forwarding.

---

## Cross-Cutting Concerns

### Observability (OpenTelemetry)

**Instrumentation Points:**
- Agent execution (traces)
- Function calls (spans)
- Workflow steps (activities)
- Message routing (events)

**Configured via:**
- `OpenTelemetryAgent` wrapper
- Workflow observability extensions
- ASP.NET Core instrumentation

### Dependency Injection

**Registration:**
```csharp
builder.Services.AddAgent<MyAgent>();
builder.Services.AddAgentCatalog();
```

**Resolution:**
- Agents resolved from DI container
- Tools and dependencies injected
- Scoped services for threads

### Error Handling

**Strategies:**
- Exception propagation in agents
- Workflow error events
- Retry policies (via resilience extensions)
- Validation at multiple layers

### Serialization

**JSON handling:**
- `System.Text.Json` throughout
- Custom converters for workflow types
- PowerFx expression serialization
- Checkpoint serialization

---

## Extension Points

### Custom Agents
Implement `AIAgent` from `Microsoft.Agents.AI.Abstractions`:
```csharp
public class MyCustomAgent : AIAgent
{
    public override async Task<AgentRunResponse> RunAsync(...)
    {
        // Custom implementation
    }
}
```

### Custom Executors
Implement executor interface for workflows:
```csharp
public class MyExecutor : Executor<TInput, TOutput>
{
    public override async Task ExecuteAsync(...)
    {
        // Custom workflow step
    }
}
```

### Custom Storage
Implement `ICheckpointStore` or `ChatMessageStore`:
```csharp
public class MyCheckpointStore : ICheckpointStore
{
    // Custom storage implementation
}
```

### Custom Middleware
Add delegating agents:
```csharp
public class MyMiddleware : DelegatingAIAgent
{
    public override async Task<AgentRunResponse> RunAsync(...)
    {
        // Pre-processing
        var response = await InnerAgent.RunAsync(...);
        // Post-processing
        return response;
    }
}
```

---

## Technology Stack

### .NET Platform
- **.NET 9.0** (primary)
- **.NET 8.0** (LTS support)
- **.NET Framework 4.8** (legacy)

### Key Libraries
- **Microsoft.Extensions.AI** - AI abstraction layer
- **System.Text.Json** - JSON serialization
- **OpenTelemetry** - Observability
- **System.Threading.Channels** - Async streaming
- **Microsoft.PowerFx** - Expression evaluation

### Test Stack
- **xUnit** - Test framework
- **FluentAssertions** - Assertion library
- **Moq** - Mocking framework
- **xretry** - Retry policies for flaky tests

---

## Performance Considerations

### Streaming
- Uses `IAsyncEnumerable<T>` for efficient streaming
- `System.Threading.Channels` for backpressure
- Incremental response processing

### Memory Management
- Async/await throughout
- Proper disposal of resources
- Pooling where applicable

### Concurrency
- Thread-safe collections
- Async coordination primitives
- Workflow parallel execution support

---

## Security Considerations

### Authentication
- Azure Identity integration
- API key management
- OAuth2 support (via providers)

### Authorization
- Human approval gates
- Tool execution policies
- Agent access control

### Data Protection
- Secure credential storage
- Encryption in transit (HTTPS)
- PII handling guidelines

---

**Last Updated:** October 14, 2025  
**Version:** 1.0

