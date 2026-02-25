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

// Create and start a Copilot client
await using CopilotClient copilotClient = new();
await copilotClient.StartAsync();

// Create session configuration with specific model
SessionConfig sessionConfig = new()
{
    Model = "claude-opus-4.5",
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

// Use the agent - ask it to write code for us
AgentResponse response = await agent.RunAsync("Write a small .NET 10 C# hello world single file application");
Console.WriteLine(response);
```

## Streaming Responses

To get streaming responses:

```csharp
await foreach (AgentResponseUpdate update in agent.RunStreamingAsync("Write a C# function to calculate Fibonacci numbers"))
{
    Console.Write(update.Text);
}
```
