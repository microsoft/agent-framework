// Copyright (c) Microsoft. All rights reserved.

// Provider: GitHub Copilot
// Create an agent using GitHub Copilot with shell command permissions.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/providers

using GitHub.Copilot.SDK;
using Microsoft.Agents.AI;

// <github_copilot>
static Task<PermissionRequestResult> PromptPermission(PermissionRequest request, PermissionInvocation invocation)
{
    Console.WriteLine($"\n[Permission Request: {request.Kind}]");
    Console.Write("Approve? (y/n): ");

    string? input = Console.ReadLine()?.Trim().ToUpperInvariant();
    string kind = input is "Y" or "YES" ? "approved" : "denied-interactively-by-user";

    return Task.FromResult(new PermissionRequestResult { Kind = kind });
}

await using CopilotClient copilotClient = new();
await copilotClient.StartAsync();

SessionConfig sessionConfig = new()
{
    OnPermissionRequest = PromptPermission,
};

AIAgent agent = copilotClient.AsAIAgent(sessionConfig, ownsClient: true);
// </github_copilot>

Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
