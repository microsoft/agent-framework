# Aspire.Hosting.AgentFramework.DevUI library

Provides extension methods and resource definitions for an Aspire AppHost to configure a DevUI resource for testing and debugging AI agents built with [Microsoft Agent Framework](https://github.com/microsoft/agent-framework).

## Getting started

### Prerequisites

Agent services must expose the OpenAI Responses and Conversations API endpoints. This is compatible with services using [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) with `MapOpenAIResponses()` and `MapOpenAIConversations()` mapped.

### Install the package

In your AppHost project, install the Aspire Agent Framework DevUI Hosting library with [NuGet](https://www.nuget.org):

```dotnetcli
dotnet add package Aspire.Hosting.AgentFramework.DevUI
```

## Usage example

Then, in the _AppHost.cs_ file of `AppHost`, add a DevUI resource and connect it to your agent services using the following methods:

```csharp
var writerAgent = builder.AddProject<Projects.WriterAgent>("writer-agent")
    .WithHttpHealthCheck("/health");

var editorAgent = builder.AddProject<Projects.EditorAgent>("editor-agent")
    .WithHttpHealthCheck("/health");

var devui = builder.AddDevUI("devui")
    .WithAgentService(writerAgent)
    .WithAgentService(editorAgent)
    .WaitFor(writerAgent)
    .WaitFor(editorAgent);
```

Each agent service only needs to map the standard OpenAI API endpoints — no custom discovery endpoints are required:

```csharp
// In the agent service's Program.cs
builder.AddAIAgent("writer", "You write short stories.");
builder.Services.AddOpenAIResponses();
builder.Services.AddOpenAIConversations();

var app = builder.Build();

app.MapOpenAIResponses();
app.MapOpenAIConversations();
```

## How it works

`AddDevUI` starts an **in-process aggregator** inside the AppHost — no external container image is needed. The aggregator is a lightweight Kestrel server that:

1. **Serves the DevUI frontend** from the `Microsoft.Agents.AI.DevUI` assembly's embedded resources (loaded at runtime). If the assembly is not available, it falls back to proxying the frontend from the first backend.
2. **Aggregates entities** from all configured agent service backends into a single `/v1/entities` listing. Each entity ID is prefixed with the backend name to ensure uniqueness across services (e.g., `writer-agent/writer`, `editor-agent/editor`).
3. **Routes requests** to the correct backend based on the entity ID prefix. When DevUI sends a `POST /v1/responses` or `/v1/conversations` request, the aggregator strips the prefix and forwards it to the appropriate service.
4. **Streams SSE responses** for the `/v1/responses` endpoint, so agent responses stream back to the DevUI frontend in real time.
5. **Correlates OpenTelemetry traces** with each response when the Aspire Dashboard telemetry API is available. The aggregator propagates a unique W3C trace context to the selected agent service, retrieves matching spans from the dashboard after the response completes, and displays them in DevUI's Traces tab.

The aggregator publishes its URL to the Aspire dashboard, where it appears as a clickable link.

## Tracing

Tracing is enabled automatically when the running Aspire Dashboard exposes its telemetry API, available in Aspire 13.2 and later. DevUI checks this capability at startup, so older or unavailable dashboards do not delay agent responses or produce trace errors in the UI. The current Agent Framework dependency is Aspire 13.5.2.

Agent services must still be configured to emit and export OpenTelemetry spans to Aspire. This normally means using Aspire service defaults and registering the Agent Framework activity sources used by the service. The aggregator keeps the dashboard API key server-side; it is never returned to the browser.

Aspire commonly exports spans in batches, so trace events may appear shortly after an answer completes. Trace retrieval works for streaming and non-streaming responses, happens in the background, and does not keep the chat response in a streaming state.

OpenTelemetry attributes can contain sensitive prompts, responses, tool arguments, or results when sensitive-data capture is enabled. Only enable sensitive telemetry in an appropriately secured development environment.

## Agent discovery

By default, `WithAgentService` declares a single agent named after the Aspire resource. You can provide explicit agent metadata when the agent name differs from the resource name, or when a service hosts multiple agents:

```csharp
builder.AddDevUI("devui")
    .WithAgentService(writerAgent, agents: [new("writer", "Writes short stories")])
    .WithAgentService(editorAgent, agents: [new("editor", "Edits and formats stories")]);
```

Agent metadata is declared at the AppHost level so the aggregator builds the entity listing directly — agent services don't need a `/v1/entities` endpoint.

## Configuration

### Custom entity ID prefix

By default, entity IDs are prefixed with the Aspire resource name. You can specify a custom prefix:

```csharp
builder.AddDevUI("devui")
    .WithAgentService(myService, entityIdPrefix: "custom-prefix");
```

### Custom port

You can specify a fixed host port for the DevUI web interface:

```csharp
builder.AddDevUI("devui", port: 8090);
```

### DevUI frontend assembly

To serve the DevUI frontend directly from the aggregator (instead of proxying from a backend), add the `Microsoft.Agents.AI.DevUI` NuGet package to your AppHost project. The aggregator loads its embedded resources at runtime via `Assembly.Load`.

## Additional documentation

* https://github.com/microsoft/agent-framework
* https://github.com/microsoft/agent-framework/tree/main/dotnet/src/Microsoft.Agents.AI.DevUI

## Feedback & contributing

https://github.com/dotnet/aspire
