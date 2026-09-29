# AG-UI Client and Server Sample

This sample demonstrates how to use the AG-UI (Agent UI) protocol to enable communication between a client application and a remote agent server. The AG-UI protocol provides a standardized way for clients to interact with AI agents.

> [!WARNING]
> This sample does not authenticate AG-UI callers. Before exposing either server to other users, configure authentication, require authorization on every AG-UI endpoint, and enable caller-scoped session isolation. Follow the shared [AG-UI security configuration](../../02-agents/AGUI/README.md#security-considerations), including its client credential requirements. Azure OpenAI credentials authenticate the server to the model service, not callers to this server.

## Overview

The demonstration has two components:

1. **AGUIServer** - An ASP.NET Core web server that hosts an AI agent and exposes it via the AG-UI protocol
2. **AGUIClient** - A console application that connects to the AG-UI server and displays streaming updates

> **Warning**
> The AG-UI protocol is still under development and changing.
> We will try to keep these samples updated as the protocol evolves.

## Configuring Environment Variables

Configure the required Azure OpenAI environment variables:

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://<your-resource>.openai.azure.com/openai/v1/"
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5.4-mini"
```

> [!NOTE]
> Include `/openai/v1/` in the endpoint. The OpenAI SDK uses `DefaultAzureCredential` to obtain a bearer token. Make sure you're authenticated with Azure, for example through `az login`, Visual Studio, or environment variables.

> [!NOTE]
> This sample calls Azure OpenAI inference directly through the resource endpoint. It does not require a Microsoft Foundry project. A project-scoped application would instead use a Foundry project endpoint with `Azure.AI.Projects` and the Agent Framework Foundry provider.

> [!NOTE]
> The server uses the Azure OpenAI Responses API because hosted web search is a Responses API tool. It sets `store` to `false` so Agent Framework persists chat history in the configured session store instead of depending on service-retained responses. Web search uses Grounding with Bing and may incur additional charges; review the [web search documentation and data usage terms](https://learn.microsoft.com/azure/foundry/openai/how-to/web-search) before using it.

## Running the Sample

### Step 1: Start the AG-UI Server

```bash
cd AGUIServer
dotnet build
dotnet run --urls "http://localhost:5100"
```

The server will start and listen on `http://localhost:5100`.

### Step 2: Testing with the REST Client (Optional)

Before running the client, you can test the server using the included `.http` file:

1. Open [./AGUIServer/AGUIServer.http](./AGUIServer/AGUIServer.http) in Visual Studio or VS Code with the REST Client extension
2. Send a test request to verify the server is working
3. Observe the server-sent events stream in the response

Sample request:
```http
POST http://localhost:5100/
Content-Type: application/json

{
  "threadId": "thread_123",
  "runId": "run_456",
  "messages": [
    {
      "role": "user",
      "content": "What is the capital of France?"
    }
  ],
  "context": {}
}
```

### Step 3: Run the AG-UI Client

In a new terminal window:

```bash
cd AGUIClient
dotnet run
```

Optionally, configure a different server URL:

```powershell
$env:AGUI_SERVER_URL="http://localhost:5100"
```

### Step 4: Interact with the Agent

1. The client will connect to the AG-UI server
2. Enter your message at the prompt
3. Observe the streaming updates with color-coded output:
   - **Yellow**: Run started notification showing thread and run IDs
   - **Cyan**: Agent's text response (streamed character by character)
   - **Green**: Run finished notification
   - **Red**: Error messages (if any occur)
4. Type `:q` or `quit` to exit

## Sample Output

```
AGUIClient> dotnet run
info: AGUIClient[0]
      Connecting to AG-UI server at: http://localhost:5100

User (:q or quit to exit): What is the capital of France?

[Run Started - Thread: thread_abc123, Run: run_xyz789]
The capital of France is Paris. It is known for its rich history, culture, and iconic landmarks such as the Eiffel Tower and the Louvre Museum.
[Run Finished - Thread: thread_abc123, Run: run_xyz789]

User (:q or quit to exit): Tell me a fun fact about space

[Run Started - Thread: thread_abc123, Run: run_def456]
Here's a fun fact: A day on Venus is longer than its year! Venus takes about 243 Earth days to rotate once on its axis, but only about 225 Earth days to orbit the Sun.
[Run Finished - Thread: thread_abc123, Run: run_def456]

User (:q or quit to exit): :q
```

## How It Works

### Server Side

The `AGUIServer` uses the `MapAGUIServer` extension method to expose an agent through the AG-UI protocol:

```csharp
IChatClient chatClient = new OpenAIClient(
        new BearerTokenPolicy(new DefaultAzureCredential(), "https://ai.azure.com/.default"),
        new OpenAIClientOptions { Endpoint = new Uri(endpoint) })
    .GetResponsesClient()
    .AsIChatClientWithStoredOutputDisabled(model: deploymentName);

builder
    .AddAIAgent("AGUIAssistant", (services, name) => chatClient.AsAIAgent(new ChatClientAgentOptions
    {
        Name = name,
        // Mixed client/server calls otherwise leave both calls unexecuted on the server.
        // Retain server calls in the session and expose only client calls. The client executes them
        // and sends results with matching call IDs on the same thread's continuation request.
        // The server then executes its saved calls and streams their call/result pairs as completed
        // history, not requests for client execution. WithInMemorySessionStore preserves deferred calls
        // between HTTP requests so execution does not rely on client-replayed server calls.
        EnableInvocableFunctionBypassing = true,
        ChatOptions = new ChatOptions
        {
            Instructions = "You are a helpful assistant.",
            Tools = services.GetKeyedServices<AITool>(name).ToList(),
        },
    }, services: services))
    .WithAITool(new HostedWebSearchTool())
    .WithInMemorySessionStore();

app.MapAGUIServer("AGUIAssistant", "/");
```

This automatically handles:
- HTTP POST requests with message payloads
- Converting agent responses to AG-UI event streams
- Server-sent events (SSE) formatting
- Thread and run management

### Mixed Client and Server Tools

`AGUIServer` enables `ChatClientAgentOptions.EnableInvocableFunctionBypassing` and uses an in-memory session store. When a model response requests both a client tool and a non-approval-required server function, the server retains the pending server call in its session and sends only the client call for execution. After the client returns its result, the server resumes the stored call.

The client result carries the original call ID and returns on a continuation request for the same thread. The server executes its saved call, and the server call and its matching result appear in the continuation stream as completed history; the client does not execute that server tool.

Both bypassing and session persistence are required for this flow. `AGUIDojoServer` configures the same behavior for `PredictiveStateUpdatesAgent`, which combines server-side `write_document` with client-side `confirm_changes`. Session stores must be keyed by the agent's name.

In-memory storage is for demonstration: it loses sessions on restart and has no size limit or eviction. Production hosts should use a persistent store and an `AgentIsolationKeyProvider` to isolate sessions by authenticated user. The `WithInMemorySessionStore()` helper uses strict isolation by default, so the main server requires a valid isolation key to use that store. Registering an in-memory store alone does not supply caller identity; see the [configuration example](../../02-agents/AGUI/README.md#configure-a-multi-user-host).

### Client Side

The `AGUIClient` uses the `AGUIChatClient` to connect to the remote server:

```csharp
using HttpClient httpClient = new();
var chatClient = new AGUIChatClient(new(httpClient, serverUrl));

AIAgent agent = chatClient.AsAIAgent(
    instructions: null,
    name: "agui-client",
    description: "AG-UI Client Agent",
    tools: []);

bool isFirstUpdate = true;
AgentResponseUpdate? currentUpdate = null;
string? threadId = null;

await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(messages, thread))
{
    // AGUIChatClient is stateless and never surfaces a ConversationId; the thread id is
    // carried on the AG-UI RUN_STARTED event's raw representation.
    if (update.AsChatResponseUpdate().RawRepresentation is RunStartedEvent runStarted)
    {
        threadId = runStarted.ThreadId;
    }

    // First update indicates run started
    if (isFirstUpdate)
    {
        Console.WriteLine($"[Run Started - Thread: {threadId}, Run: {update.ResponseId}]");
        isFirstUpdate = false;
    }
    
    currentUpdate = update;
    
    foreach (AIContent content in update.Contents)
    {
        switch (content)
        {
            case TextContent textContent:
                // Display streaming text
                Console.Write(textContent.Text);
                break;
            case ErrorContent errorContent:
                // Display error notification
                Console.WriteLine($"[Error: {errorContent.Message}]");
                break;
        }
    }
}

// Last update indicates run finished
if (currentUpdate != null)
{
    Console.WriteLine($"\n[Run Finished - Thread: {threadId}, Run: {currentUpdate.ResponseId}]");
}
```

The `RunStreamingAsync` method:
1. Sends messages to the server via HTTP POST
2. Receives server-sent events (SSE) stream
3. Parses events into `AgentResponseUpdate` objects
4. Yields updates as they arrive for real-time display

## Key Concepts

- **Thread**: Represents a conversation context that persists across multiple runs. `AGUIChatClient` is stateless and does not surface a `ConversationId`; the thread id is read from the `RUN_STARTED`/`RUN_FINISHED` event's raw representation (`RunStartedEvent.ThreadId`). Continuation is driven by resending the full message history (and, to branch from a prior run, setting `RunAgentInput.ThreadId`/`ParentRunId` via `ChatOptions.RawRepresentationFactory`).
- **Run**: A single execution of the agent for a given set of messages (identified by `ResponseId` property)
- **AgentResponseUpdate**: Contains the response data with:
  - `ResponseId`: The unique run identifier
  - `RawRepresentation`: The underlying AG-UI event (e.g. `RunStartedEvent`), which carries wire-level fields such as the thread id
  - `Contents`: Collection of content items (TextContent, ErrorContent, etc.)
- **Run Lifecycle**: 
  - The **first** `AgentResponseUpdate` in a run indicates the run has started
  - Subsequent updates contain streaming content as the agent processes
  - The **last** `AgentResponseUpdate` in a run indicates the run has finished
  - If an error occurs, the update will contain `ErrorContent`