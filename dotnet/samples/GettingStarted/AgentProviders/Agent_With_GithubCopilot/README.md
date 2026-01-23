# Prerequisites

> **⚠️ WARNING: Container Recommendation**
> 
> GitHub Copilot can execute tools and commands that may interact with your system. For safety, it is strongly recommended to run this sample in a containerized environment (e.g., Docker, Dev Container) to avoid unintended consequences to your machine.

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- GitHub Copilot CLI installed and available in your PATH (or provide a custom path)

## Setting up GitHub Copilot CLI

To use this sample, you need to have the GitHub Copilot CLI installed. You can install it by following the instructions at:
https://github.com/github/copilot-sdk

Once installed, ensure the `copilot` command is available in your PATH, or configure a custom path using `CopilotClientOptions`.

## Running the Sample

No additional environment variables are required if using default configuration. The sample will:

1. Create a GitHub Copilot client with default options
2. Create an AI agent using the Copilot SDK
3. Send a message to the agent
4. Display the response

Run the sample:

```powershell
dotnet run
```

## Advanced Usage

You can customize the agent by providing additional configuration:

```csharp
using GitHub.Copilot.SDK;
using Microsoft.Agents.AI;

// Create a Copilot client with custom options
await using CopilotClient copilotClient = new(new CopilotClientOptions
{
    CliPath = "/custom/path/to/copilot",  // Custom CLI path
    LogLevel = "debug",                    // Enable debug logging
    AutoStart = true
});

await copilotClient.StartAsync();

// Create session configuration with specific model
var sessionConfig = new SessionConfig
{
    Model = "gpt-4",
    Streaming = false
};

// Create an agent with custom configuration using the extension method
AIAgent agent = copilotClient.AsAIAgent(
    sessionConfig,
    ownsClient: true,
    id: "my-copilot-agent",
    name: "My Copilot Assistant",
    description: "A helpful AI assistant powered by GitHub Copilot"
);

// Use the agent
AgentResponse response = await agent.RunAsync("What is the weather like today?");
Console.WriteLine(response);
```

## Streaming Responses

To get streaming responses:

```csharp
await foreach (var update in agent.RunStreamingAsync("Tell me a story"))
{
    Console.Write(update.Text);
}
```
