// Copyright (c) Microsoft. All rights reserved.

// Shares one Foundry hosted session across application users while preserving an
// independent Agent Framework session and delegated identity for each user.

#pragma warning disable MEAI001 // Foundry hosted session and user identity helpers are experimental.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Extensions.AI;

Env.TraversePath().Load();

Uri projectEndpoint = new(Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set."));
string agentName = Environment.GetEnvironmentVariable("AZURE_AI_AGENT_NAME")
    ?? throw new InvalidOperationException("AZURE_AI_AGENT_NAME is not set.");
Uri agentEndpoint = new($"{projectEndpoint.ToString().TrimEnd('/')}/agents/{agentName}/endpoint/protocols/openai");

var credential = new AzureCliCredential();
var projectClient = new AIProjectClient(projectEndpoint, credential);
FoundryAgent agent = projectClient.AsAIAgent(agentEndpoint);
AgentAdministrationClient adminClient = projectClient.AgentAdministrationClient;

Console.WriteLine("Creating one shared Foundry hosted session...");
ProjectsAgentRecord agentRecord = await adminClient.GetAgentAsync(agentName);
string agentVersion = agentRecord.GetLatestVersion().Version;
ProjectAgentSession hostedSession = await adminClient.CreateSessionAsync(
    agentName,
    new VersionRefIndicator(agentVersion));
string hostedSessionId = hostedSession.AgentSessionId;

// Demonstration only: this console accepts arbitrary user IDs to make isolation visible.
// Production code must derive the user ID from authenticated request context, authorize the
// operation, and use a managed session pool instead of trusting caller-provided identity text.
var userSessions = new Dictionary<string, ChatClientAgentSession>(StringComparer.Ordinal);

try
{
    await WaitForSessionActiveAsync(adminClient, agentName, hostedSessionId);

    Console.ForegroundColor = ConsoleColor.Cyan;
    Console.WriteLine($"""
        ============================================================
        User Isolation Agent Sample
        Agent: {agentName}
        Shared hosted session: {hostedSessionId}

        Enter a stable application user id for each message.
        Each user gets an independent AgentSession and conversation,
        while every user shares the same Foundry hosted sandbox.
        Enter 'quit' as the user id to exit.
        ============================================================
        """);
    Console.ResetColor();

    while (true)
    {
        Console.ForegroundColor = ConsoleColor.Green;
        Console.Write("User id> ");
        Console.ResetColor();

        string? userId = Console.ReadLine();
        if (userId is null)
        {
            break;
        }

        userId = userId.Trim();
        if (string.IsNullOrWhiteSpace(userId))
        {
            continue;
        }

        if (userId.Equals("quit", StringComparison.OrdinalIgnoreCase))
        {
            break;
        }

        Console.Write("Message> ");
        string? input = Console.ReadLine();
        if (input is null)
        {
            break;
        }

        if (string.IsNullOrWhiteSpace(input))
        {
            continue;
        }

        if (!userSessions.TryGetValue(userId, out ChatClientAgentSession? userSession))
        {
            userSession = await agent.CreateFoundryHostedAgentSessionAsync(
                hostedSessionId: hostedSessionId);
            userSessions.Add(userId, userSession);
            Console.WriteLine($"Created an independent conversation for '{userId}'.");
        }

        var runOptions = new ChatClientAgentRunOptions(
            new ChatOptions().WithFoundryHostedAgentUserIdentity(userId));

        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.Write($"Agent for {userId}> ");
        Console.ResetColor();

        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(
            input,
            userSession,
            runOptions))
        {
            Console.Write(update);
        }

        Console.WriteLine();
        Console.WriteLine();
    }
}
finally
{
    Console.WriteLine($"Deleting shared hosted session {hostedSessionId}...");
    await adminClient.DeleteSessionAsync(agentName, hostedSessionId);
}

static async Task WaitForSessionActiveAsync(
    AgentAdministrationClient adminClient,
    string agentName,
    string sessionId,
    CancellationToken cancellationToken = default)
{
    TimeSpan timeout = TimeSpan.FromMinutes(3);
    DateTimeOffset deadline = DateTimeOffset.UtcNow + timeout;
    ProjectAgentSession session = await adminClient.GetSessionAsync(agentName, sessionId, cancellationToken);

    while (session.Status != AgentSessionStatus.Active)
    {
        if (session.Status == AgentSessionStatus.Failed
            || session.Status == AgentSessionStatus.Deleted
            || session.Status == AgentSessionStatus.Expired)
        {
            throw new InvalidOperationException(
                $"Hosted session '{sessionId}' entered terminal status '{session.Status}'.");
        }

        if (DateTimeOffset.UtcNow >= deadline)
        {
            throw new TimeoutException(
                $"Hosted session '{sessionId}' did not become active within {timeout.TotalSeconds:F0} seconds. Last status: {session.Status}.");
        }

        await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken);
        session = await adminClient.GetSessionAsync(agentName, sessionId, cancellationToken);
    }
}
