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
using GitHub.Copilot;
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

## Approving or denying tool execution

The GitHub Copilot SDK owns the tool-calling loop for this provider, so approval is enforced through the SDK's
native pre-execution hook rather than the Agent Framework chat-client approval round-trip.

When you register a tool wrapped in `ApprovalRequiredAIFunction`, `GitHubCopilotAgent` installs a default
`SessionConfig.Hooks.OnPreToolUse` hook that returns `"ask"` for that tool and defers (`null`) for all other tools.
The `"ask"` decision routes to your `SessionConfig.OnPermissionRequest` handler, where you approve or deny the call
(this also fires even for tools configured with `SkipPermission = true`):

```csharp
using GitHub.Copilot;

AIFunction deleteFile = AIFunctionFactory.Create(DeleteFile, "DeleteFile", "Deletes a file.");

SessionConfig sessionConfig = new()
{
    // Wrapping the tool marks it approval-required; the agent turns this into an "ask" at OnPreToolUse.
    Tools = [new ApprovalRequiredAIFunction(deleteFile)],

    // OnPermissionRequest decides the "asked" tools (and Copilot's built-in shell/file/URL prompts).
    OnPermissionRequest = (request, invocation) =>
    {
        // Surface to a human, check policy, etc.
        bool approved = AskHuman(request);
        return Task.FromResult(approved
            ? PermissionDecision.ApproveOnce()
            : PermissionDecision.Reject("Denied by user."));
    },
};
```

> **⚠️ If you provide your own `OnPreToolUse` hook**, it takes precedence and the agent does **not** install its
> default approval hook. In that case **you are fully responsible** for enforcing approval — including for any
> `ApprovalRequiredAIFunction` you register (e.g. by returning a `"deny"` or `"ask"` `PreToolUseHookOutput`). The
> agent logs a warning when it detects an approval-required tool that your hook must handle.

## Streaming Responses

To get streaming responses:

```csharp
await foreach (AgentResponseUpdate update in agent.RunStreamingAsync("Write a C# function to calculate Fibonacci numbers"))
{
    Console.Write(update.Text);
}
```
