# AG-UI Getting Started Samples

This directory contains samples that demonstrate how to build AG-UI (Agent UI Protocol) servers and clients using the Microsoft Agent Framework.

> [!WARNING]
> These samples do not authenticate AG-UI callers and are intended for local development. Before exposing an endpoint to other users, configure endpoint authorization and caller-scoped session isolation as described in [Security considerations](#security-considerations). Signing in with `az login` authenticates the server to Azure OpenAI, not users to the AG-UI endpoint.

## Prerequisites

- .NET 9.0 or later
- Azure OpenAI service endpoint and deployment configured
- Azure CLI installed and authenticated (`az login`)
- User has the `Cognitive Services OpenAI Contributor` role for the Azure OpenAI resource

## Environment Variables

All samples require the following environment variables:

```bash
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5.4-mini"
```

For the client samples, you can optionally set:

```bash
export AGUI_SERVER_URL="http://localhost:8888"
```

## Samples

### Step01_GettingStarted

A basic AG-UI server and client that demonstrate the foundational concepts.

#### Server (`Step01_GettingStarted/Server`)

A basic AG-UI server that hosts an AI agent accessible via HTTP. Demonstrates:

- Creating an ASP.NET Core web application
- Setting up an AG-UI server endpoint with `MapAGUIServer`
- Creating an AI agent from an Azure OpenAI chat client
- Streaming responses via Server-Sent Events (SSE)

**Run the server:**

```bash
cd Step01_GettingStarted/Server
dotnet run --urls http://localhost:8888
```

#### Client (`Step01_GettingStarted/Client`)

An interactive console client that connects to an AG-UI server. Demonstrates:

- Creating an AG-UI client with `AGUIChatClient`
- Managing multi-turn conversations with an `AgentSession`
- Streaming responses with `RunStreamingAsync`
- Displaying colored console output for different content types
- Supporting both interactive and automated modes

**Prerequisites:** The Step01_GettingStarted server (or any AG-UI server) must be running.

**Run the client:**

```bash
cd Step01_GettingStarted/Client
dotnet run
```

Type messages and press Enter to interact with the agent. Type `:q` or `quit` to exit.

### Step02_BackendTools

An AG-UI server with function tools that execute on the backend.

#### Server (`Step02_BackendTools/Server`)

Demonstrates:

- Creating function tools using `AIFunctionFactory.Create`
- Using `[Description]` attributes for tool documentation
- Defining explicit request/response types for type safety
- Setting up JSON serialization contexts for source generation
- Backend tool rendering (tools execute on the server)

**Run the server:**

```bash
cd Step02_BackendTools/Server
dotnet run --urls http://localhost:8888
```

#### Client (`Step02_BackendTools/Client`)

A client that works with the backend tools server. Try asking: "Find Italian restaurants in Seattle" or "Search for Mexican food in Portland".

**Run the client:**

```bash
cd Step02_BackendTools/Client
dotnet run
```

### Step03_FrontendTools

Demonstrates frontend tool rendering (tools defined on client, executed on server).

#### Server (`Step03_FrontendTools/Server`)

A basic AG-UI server that accepts tool definitions from the client.

**Run the server:**

```bash
cd Step03_FrontendTools/Server
dotnet run --urls http://localhost:8888
```

#### Client (`Step03_FrontendTools/Client`)

A client that defines and sends tools to the server for execution.

**Run the client:**

```bash
cd Step03_FrontendTools/Client
dotnet run
```

### Step04_HumanInLoop

Demonstrates human-in-the-loop approval workflows for sensitive operations. This sample includes both a server and client component.

#### Server (`Step04_HumanInLoop/Server`)

An AG-UI server that implements approval workflows. Demonstrates:

- Wrapping a tool with `ApprovalRequiredAIFunction` so it requires approval before running
- Mapping a plain agent with `MapAGUIServer`, which natively emits an approval interrupt when the model calls the approval-required tool and resumes the run once the client sends the decision back
- Registering a keyed `AgentSessionStore`, which is **required** for approvals: the framework only honors an approval decision it can match against an approval request it recorded itself when it interrupted the run. Approval requests replayed in the inbound message history are deliberately not trusted as the pairing authority, so without a server-side session the decision is rejected

**Run the server:**

```bash
cd Step04_HumanInLoop/Server
dotnet run --urls http://localhost:5100
```

#### Client (`Step04_HumanInLoop/Client`)

An interactive client that handles approval requests from the server. Demonstrates:

- Detecting `ToolApprovalRequestContent` in the streamed response
- Displaying approval details to the user and prompting for approval or rejection
- Sending the decision back as a `ToolApprovalResponseContent` created with `approvalRequest.CreateResponse(approved)`
- Resuming the run so the server continues after the decision is received

**Run the client:**

```bash
cd Step04_HumanInLoop/Client
dotnet run
```

Try asking the agent to perform sensitive operations like "Approve expense report EXP-12345".

### Step05_StateManagement

An AG-UI server and client that demonstrate shared state management.

#### Server (`Step05_StateManagement/Server`)

Demonstrates:

- Exposing a `generate_recipe` tool that returns the complete recipe
- Mapping the tool result to a `STATE_SNAPSHOT` event with `AGUIStreamOptions.MapResultAsStateSnapshot`
- Reading the client's current recipe from `RunAgentInput.State`
- Managing shared state between client and server
- Using JSON serialization contexts for state types

**Run the server:**

```bash
cd Step05_StateManagement/Server
dotnet run
```

The server runs on port 8888 by default.

#### Client (`Step05_StateManagement/Client`)

A client that displays and updates shared state from the server. Try asking: "Create a recipe for chocolate chip cookies" or "Suggest a pasta dish".

**Run the client:**

```bash
cd Step05_StateManagement/Client
dotnet run
```

## How AG-UI Works

### Server-Side

1. Client sends HTTP POST request with messages
2. ASP.NET Core endpoint receives the request via `MapAGUIServer`
3. Agent processes messages using Agent Framework
4. Responses are streamed back as Server-Sent Events (SSE)

### Client-Side

1. `AGUIChatClient` sends HTTP POST request to server
2. Server responds with SSE stream
3. Client parses events into `AgentResponseUpdate` objects
4. Updates are displayed based on content type
5. The client sends the full message history each turn (the stateless AG-UI client does not rely on a server-assigned `ConversationId`)

### Protocol Features

- **HTTP POST** for requests
- **Server-Sent Events (SSE)** for streaming responses
- **JSON** for event serialization
- **Thread IDs** (read from the `RUN_STARTED` event's raw representation) for conversation context. `AGUIChatClient` is stateless and intentionally does not surface a `ConversationId`.
- **Run IDs** (as `ResponseId`) for tracking individual executions

## Security considerations

See the [shared hosting guide](../../04-hosting/README.md) for the common authentication, authorization, and isolation model, including differences between AG-UI, A2A, and OpenAI hosting.

### Endpoint access and session isolation are separate controls

The AG-UI `threadId` identifies a conversation to resume; it does not prove that the caller owns it. `AGUIChatClient` does not expose an `IChatClient` `ConversationId`, so do not rely on that property to authorize AG-UI requests.

Multi-user hosts need both controls:

- **Authentication and authorization:** Validate the caller's credentials and require authorization on the AG-UI endpoint. `AddAGUIServer()` and `MapAGUIServer()` do not configure these controls. Protect endpoints even without session persistence, because callers can consume model resources and invoke the agent's exposed tools.
- **Session isolation:** Register an `AgentIsolationKeyProvider` so persisted sessions are partitioned by a trusted caller identity. Authentication alone does not prevent one authenticated caller from supplying another caller's `threadId`.

`MapAGUIServer` automatically wraps a keyed `AgentSessionStore` in `IsolationKeyScopedAgentSessionStore` unless the decorator is already present. Both session lookups and saves use the isolation partition. Two users presenting the same `threadId` therefore access different sessions when their isolation keys differ. This applies to directly registered stores, including the Step04 sample; using `WithSessionStore(...)` or `WithInMemorySessionStore(...)` is not required for the endpoint to add the wrapper.

Without a provider, the endpoint-added wrapper leaves storage keys unchanged. Any caller who knows a persisted thread's ID can then resume that session. With a provider, that wrapper rejects missing or blank isolation keys instead of falling back to shared storage. A preconfigured isolation decorator retains its own options; the `WithSessionStore(...)` and `WithInMemorySessionStore(...)` helpers use strict isolation by default, requiring a key even if no provider was registered.

If no session store is registered, sessions are not persisted across requests. Step04 explicitly enables persistence because approval continuations require server-recorded state. Approval matching does not replace caller isolation or endpoint authorization.

### Configure a multi-user host

Reference `Microsoft.Agents.AI.Hosting.AspNetCore` for the claims-based provider and import `Microsoft.Agents.AI.Hosting`. Configure a real [ASP.NET Core authentication scheme](https://learn.microsoft.com/aspnet/core/security/authentication/) for your application first, using `AddAuthentication(...).Add...(...)` to validate the credentials your clients send. The following additions are **not** a replacement for that scheme.

Before `builder.Build()`:

```csharp
using Microsoft.Agents.AI.Hosting;

// Keep the application's authentication scheme registration here.
builder.Services.AddAuthorization();
builder.Services.AddHttpContextAccessor();
builder.Services.UseClaimsBasedAgentIsolation();
```

After `builder.Build()`, use the sample's existing agent when mapping the endpoint:

```csharp
app.UseAuthentication();
app.UseAuthorization();

app.MapAGUIServer("/", agent).RequireAuthorization();
```

Use the sample's actual route and agent variable (`baseAgent` in Step04), or apply `RequireAuthorization()` to the named-agent overload. For a host with multiple AG-UI endpoints, protect each one or their route group. Use an application-specific authorization policy when only some authenticated callers may access an agent; tools must also enforce any resource-specific permissions they require.

`UseClaimsBasedAgentIsolation()` defaults to `ClaimTypes.NameIdentifier`. Your authentication scheme must populate that claim with a stable identifier unique across all callers served by the host. If it exposes the subject as an unmapped `sub` claim, configure the provider explicitly:

```csharp
builder.Services.UseClaimsBasedAgentIsolation(new() { ClaimType = "sub" });
```

Use this instead of the default registration, not in addition to it. A subject or object ID may only be unique within one issuer or tenant. Hosts accepting multiple issuers or tenants may need a custom `AgentIsolationKeyProvider` that combines validated issuer/tenant and subject values. Do not use display names, client-submitted user IDs, or `threadId` as caller identity. A tenant-only key intentionally shares sessions within that tenant; use a per-user key when users within a tenant must be isolated.

### Authenticate every client request

Clients must send the authenticated caller's credentials on every AG-UI request, including tool continuations and approval responses. Configure the `HttpClient` used by `AGUIChatClient` for your authentication scheme, and handle challenges or authorization failures. The sample clients do not acquire or send these credentials as shipped.

For a web application that forwards requests to a separate AG-UI server, signing a user into the web application does not automatically authenticate the outbound AG-UI call. Propagate an appropriate validated per-user credential; a single shared service identity would place all users in the same isolation partition.

## Troubleshooting

### Connection Refused

Ensure the server is running before starting the client:

```bash
# Terminal 1
cd AGUI_Step01_ServerBasic
dotnet run --urls http://localhost:8888

# Terminal 2 (after server starts)
cd AGUI_Step02_ClientBasic
dotnet run
```

### Port Already in Use

If port 8888 is already in use, choose a different port:

```bash
# Server
dotnet run --urls http://localhost:8889

# Client (set environment variable)
export AGUI_SERVER_URL="http://localhost:8889"
dotnet run
```

### Authentication Errors

Make sure you're authenticated with Azure:

```bash
az login
```

Verify you have the `Cognitive Services OpenAI Contributor` role on the Azure OpenAI resource.

### Missing Environment Variables

If you see "AZURE_OPENAI_ENDPOINT is not set" errors, ensure environment variables are set in your current shell session before running the samples.

### Streaming Not Working

Check that the client timeout is sufficient (default is 60 seconds). For long-running operations, you may need to increase the timeout in the client code.

## Next Steps

After completing these samples, explore more AG-UI capabilities:

### Currently Available in C#

The samples above demonstrate the AG-UI features currently available in C#:

- ✅ **Basic Server and Client**: Setting up AG-UI communication
- ✅ **Backend Tool Rendering**: Function tools that execute on the server
- ✅ **Streaming Responses**: Real-time Server-Sent Events
- ✅ **State Management**: State schemas with predictive updates
- ✅ **Human-in-the-Loop**: Approval workflows for sensitive operations

### Coming Soon to C#

The following advanced AG-UI features are available in the Python implementation and are planned for future C# releases:

- ⏳ **Generative UI**: Custom UI component generation
- ⏳ **Advanced State Patterns**: Complex state synchronization scenarios

For the most up-to-date AG-UI features, see the [Python samples](../../../../python/samples/) for working examples.

### Related Documentation

- [AG-UI Overview](https://learn.microsoft.com/agent-framework/integrations/ag-ui/) - Complete AG-UI documentation
- [Getting Started Tutorial](https://learn.microsoft.com/agent-framework/integrations/ag-ui/getting-started) - Step-by-step walkthrough
- [Backend Tool Rendering](https://learn.microsoft.com/agent-framework/integrations/ag-ui/backend-tool-rendering) - Function tools tutorial
- [Human-in-the-Loop](https://learn.microsoft.com/agent-framework/integrations/ag-ui/human-in-the-loop) - Approval workflows tutorial
- [State Management](https://learn.microsoft.com/agent-framework/integrations/ag-ui/state-management) - State management tutorial
- [Agent Framework Overview](https://learn.microsoft.com/agent-framework/overview/agent-framework-overview) - Core framework concepts
