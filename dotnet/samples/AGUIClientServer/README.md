# AG-UI Client and Server Sample

This sample demonstrates how to use the AG-UI (Agent UI) protocol to enable communication between a client application and a remote agent server. The AG-UI protocol provides a standardized way for clients to interact with AI agents.

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
$env:AZURE_OPENAI_ENDPOINT="https://ag-ui-agent-framework.openai.azure.com/"
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4.1-mini"
```

> **Note:** This sample uses `DefaultAzureCredential` for authentication. Make sure you're authenticated with Azure (e.g., via `az login`, Visual Studio, or environment variables).

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

The `AGUIServer` uses the `MapAGUIAgent` extension method to expose an agent through the AG-UI protocol:

```csharp
app.MapAGUIAgent("/", (messages, tools, context, forwardedProps) =>
{
    AIAgent agent = new OpenAIClient(apiKey)
        .GetChatClient(model)
        .CreateAIAgent(
            instructions: "You are a helpful assistant.",
            name: "AGUIAssistant");
    return agent;
});
```

This automatically handles:
- HTTP POST requests with message payloads
- Converting agent responses to AG-UI event streams
- Server-sent events (SSE) formatting
- Thread and run management

### Client Side

The `AGUIClient` uses the `AGUIAgent` class to connect to the remote server:

```csharp
AGUIAgent agent = new(
    id: "agui-client",
    description: "AG-UI Client Agent",
    messages: [],
    httpClient: httpClient,
    endpoint: serverUrl);

await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(messages, thread))
{
    foreach (AIContent content in update.Contents)
    {
        switch (content)
        {
            case RunStartedContent runStarted:
                // Display run started notification
                break;
            case TextContent textContent:
                // Display streaming text
                break;
            case RunFinishedContent runFinished:
                // Display run finished notification
                break;
        }
    }
}
```

The `RunStreamingAsync` method:
1. Sends messages to the server via HTTP POST
2. Receives server-sent events (SSE) stream
3. Parses events into `AgentRunResponseUpdate` objects
4. Yields updates as they arrive for real-time display

## Key Concepts

- **Thread**: Represents a conversation context that persists across multiple runs
- **Run**: A single execution of the agent for a given set of messages
- **RunStartedContent**: Signals that the agent has begun processing
- **TextContent**: Incremental text content streamed from the agent
- **RunFinishedContent**: Signals successful completion of the agent run
- **RunErrorContent**: Signals an error occurred during processing

## Next Steps

- Explore adding tools/functions to the agent
- Implement conversation history management
- Add authentication and authorization
- Deploy to production environments
- Integrate with web applications using the AG-UI protocol
