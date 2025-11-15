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

For the client sample, you can optionally set:

```bash
export AGUI_SERVER_URL="http://localhost:8888"
```

## Samples

### AGUI_Step01_ServerBasic

A basic AG-UI server that hosts an AI agent accessible via HTTP. Demonstrates:

- Creating an ASP.NET Core web application
- Setting up an AG-UI server endpoint with `MapAGUI`
- Creating an AI agent from an Azure OpenAI chat client
- Streaming responses via Server-Sent Events (SSE)

**Run the sample:**

```bash
cd AGUI_Step01_ServerBasic
dotnet run --urls http://localhost:8888
```

### AGUI_Step02_ClientBasic

An interactive console client that connects to an AG-UI server. Demonstrates:

- Creating an AG-UI client with `AGUIAgent`
- Managing conversation threads
- Streaming responses with `RunStreamingAsync`
- Displaying colored console output for different content types
- Using System.CommandLine for interactive input

**Prerequisites:** AGUI_Step01_ServerBasic (or any AG-UI server) must be running.

**Run the sample:**

```bash
cd AGUI_Step02_ClientBasic
dotnet run
```

Type messages and press Enter to interact with the agent. Type `:q` or `quit` to exit.

### AGUI_Step03_ServerWithTools

An AG-UI server with function tools that execute on the backend. Demonstrates:

- Creating function tools using `AIFunctionFactory.Create`
- Using `[Description]` attributes for tool documentation
- Defining explicit request/response types for type safety
- Setting up JSON serialization contexts for source generation
- Handling both simple (string) and complex (object) return types

**Run the sample:**

```bash
cd AGUI_Step03_ServerWithTools
dotnet run --urls http://localhost:8888
```

This server can be used with the AGUI_Step02_ClientBasic client. Try asking about weather or searching for restaurants.

### AGUI_Step04_ServerWithState

An AG-UI server that demonstrates state management with predictive updates. Demonstrates:

- Defining state schemas using C# records
- Streaming predictive state updates as tools execute
- Managing shared state between client and server
- Using JSON serialization contexts for state types

**Run the sample:**

```bash
cd AGUI_Step04_ServerWithState
dotnet run --urls http://localhost:8888
```

### AGUI_Step05_Approvals

Demonstrates human-in-the-loop approval workflows for sensitive operations. This sample includes both a server and client component.

#### Server (`AGUI_Step05_Approvals/Server`)

An AG-UI server that implements approval workflows. Demonstrates:

- Wrapping tools with `ApprovalRequiredAIFunction`
- Converting `FunctionApprovalRequestContent` to client tool calls
- Middleware pattern for approval request/response handling
- Complete function call capture and restoration

**Run the server:**

```bash
cd AGUI_Step05_Approvals/Server
dotnet run --urls http://localhost:8888
```

#### Client (`AGUI_Step05_Approvals/Client`)

An interactive client that handles approval requests from the server. Demonstrates:

- Detecting and parsing `"request_approval"` tool calls
- Displaying approval details to users
- Prompting for approval/rejection
- Sending approval responses as tool results
- Resuming conversation after approval

**Prerequisites:** The approval server must be running.

**Run the client:**

```bash
cd AGUI_Step05_Approvals/Client
dotnet run
```

Try asking the agent to perform sensitive operations like "Send an email to user@example.com" or "Transfer $500 from account 1234 to account 5678".

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

- [AG-UI Overview](https://learn.microsoft.com/azure/agent-framework/integrations/ag-ui/) - Complete AG-UI documentation
- [Getting Started Tutorial](https://learn.microsoft.com/azure/agent-framework/integrations/ag-ui/getting-started) - Step-by-step walkthrough
- [Backend Tool Rendering](https://learn.microsoft.com/azure/agent-framework/integrations/ag-ui/backend-tool-rendering) - Function tools tutorial
- [Human-in-the-Loop](https://learn.microsoft.com/azure/agent-framework/integrations/ag-ui/human-in-the-loop) - Approval workflows tutorial
- [State Management](https://learn.microsoft.com/azure/agent-framework/integrations/ag-ui/state-management) - State management tutorial
- [Agent Framework Overview](https://learn.microsoft.com/azure/agent-framework/overview/agent-framework-overview) - Core framework concepts
