# Aspire.Hosting.AgentFramework library

Provides extension methods and resource definitions for an Aspire AppHost to configure a DevUI resource for testing and debugging AI agents built with [Microsoft Agent Framework](https://github.com/microsoft/agent-framework).

## Getting started

### Prerequisites

Agent services must expose the OpenAI Responses and Conversations API endpoints. This is compatible with services using [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) with `MapOpenAIResponses()` and `MapOpenAIConversations()` mapped.

### Install the package

In your AppHost project, install the Aspire Agent Framework Hosting library with [NuGet](https://www.nuget.org):

```dotnetcli
dotnet add package Aspire.Hosting.AgentFramework
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

The aggregator publishes its URL to the Aspire dashboard, where it appears as a clickable link.

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
