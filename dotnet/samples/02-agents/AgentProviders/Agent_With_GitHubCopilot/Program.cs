// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create a GitHub Copilot agent with shell command permissions.

using GitHub.Copilot.SDK;
using Microsoft.Agents.AI;

// Permission handler that prompts the user for approval
static Task<PermissionRequestResult> PromptPermission(PermissionRequest request, PermissionInvocation invocation)
{
    Console.WriteLine($"\n[Permission Request: {request.Kind}]");
    Console.Write("Approve? (y/n): ");

    string? input = Console.ReadLine()?.Trim().ToUpperInvariant();
    string kind = input is "Y" or "YES" ? "approved" : "denied-interactively-by-user";

    return Task.FromResult(new PermissionRequestResult { Kind = kind });
}

// Create and start a Copilot client
await using CopilotClient copilotClient = new();
await copilotClient.StartAsync();

// Create an agent with a session config that enables permission handling
SessionConfig sessionConfig = new()
{
    OnPermissionRequest = PromptPermission,
};

AIAgent agent = copilotClient.AsAIAgent(sessionConfig, ownsClient: true);

// Toggle between streaming and non-streaming modes
bool useStreaming = true;

string prompt = "List all files in the current directory";
Console.WriteLine($"User: {prompt}\n");

if (useStreaming)
{
    await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(prompt))
    {
        Console.Write(update);
    }

    Console.WriteLine();
}
else
{
    AgentResponse response = await agent.RunAsync(prompt);
    Console.WriteLine(response);
}
