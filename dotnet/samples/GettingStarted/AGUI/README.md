# AG-UI Getting Started Samples

This directory contains samples that demonstrate how to build AG-UI (Agent UI Protocol) servers and clients using the Microsoft Agent Framework.

## Prerequisites

- .NET 9.0 or later
- Azure OpenAI service endpoint and deployment configured
- Azure CLI installed and authenticated (`az login`)
- User has the `Cognitive Services OpenAI Contributor` role for the Azure OpenAI resource

## Environment Variables

All samples require the following environment variables:

```bash
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"
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
- Setting up an AG-UI server endpoint with `MapAGUI`
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
- Managing conversation threads
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

- Wrapping tools with `ApprovalRequiredAIFunction`
- Converting `FunctionApprovalRequestContent` to approval requests
- Middleware pattern with `ServerFunctionApprovalServerAgent`
- Complete function call capture and restoration

**Run the server:**

```bash
cd Step04_HumanInLoop/Server
dotnet run --urls http://localhost:8888
```

#### Client (`Step04_HumanInLoop/Client`)

An interactive client that handles approval requests from the server. Demonstrates:

- Using `ServerFunctionApprovalClientAgent` middleware
- Detecting `FunctionApprovalRequestContent`
- Displaying approval details to users
- Prompting for approval/rejection
- Sending approval responses with `FunctionApprovalResponseContent`
- Resuming conversation after approval

**Run the client:**

```bash
cd Step04_HumanInLoop/Client
dotnet run
```

Try asking the agent to perform sensitive operations like "Approve expense report EXP-12345".

### Step05_StateManagement

An AG-UI server and client that demonstrate state management with predictive updates.

#### Server (`Step05_StateManagement/Server`)

Demonstrates:

- Defining state schemas using C# records
- Using `SharedStateAgent` middleware for state management
- Streaming predictive state updates with `AgentState` content
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
2. ASP.NET Core endpoint receives the request via `MapAGUI`
3. Agent processes messages using Agent Framework
4. Responses are streamed back as Server-Sent Events (SSE)

### Client-Side

1. `AGUIAgent` sends HTTP POST request to server
2. Server responds with SSE stream
3. Client parses events into `AgentRunResponseUpdate` objects
4. Updates are displayed based on content type
5. `ConversationId` maintains conversation context

### Protocol Features

- **HTTP POST** for requests
- **Server-Sent Events (SSE)** for streaming responses
- **JSON** for event serialization
- **Thread IDs** (as `ConversationId`) for conversation context
- **Run IDs** (as `ResponseId`) for tracking individual executions

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
