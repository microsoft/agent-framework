// Copyright (c) Microsoft. All rights reserved.

// Creates a Foundry hosted session explicitly, pins an Agent Framework session to it,
// reuses the hosted sandbox across turns, and deletes the hosted session on exit.

#pragma warning disable MEAI001 // Foundry hosted session helpers are experimental.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;

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

Console.WriteLine("Creating a Foundry hosted session...");
ProjectsAgentRecord agentRecord = await adminClient.GetAgentAsync(agentName);
string agentVersion = agentRecord.GetLatestVersion().Version;
ProjectAgentSession hostedSession = await adminClient.CreateSessionAsync(
    agentName,
    new VersionRefIndicator(agentVersion));
string hostedSessionId = hostedSession.AgentSessionId;

try
{
    await WaitForSessionActiveAsync(adminClient, agentName, hostedSessionId);

    ChatClientAgentSession session = await agent.CreateFoundryHostedAgentSessionAsync(
        hostedSessionId: hostedSessionId);

    Console.ForegroundColor = ConsoleColor.Cyan;
    Console.WriteLine($"""
        ============================================================
        Foundry Hosted Session Sample
        Agent: {agentName}
        Hosted session: {session.FoundryHostedAgentSessionId}

        Every turn uses the same Foundry sandbox. Conversation history
        remains a separate concern and is carried by this AgentSession.
        Type a message or 'quit' to exit.
        ============================================================
        """);
    Console.ResetColor();

    while (true)
    {
        Console.ForegroundColor = ConsoleColor.Green;
        Console.Write("You> ");
        Console.ResetColor();

        string? input = Console.ReadLine();
        if (input is null)
        {
            break;
        }

        if (string.IsNullOrWhiteSpace(input))
        {
            continue;
        }

        if (input.Equals("quit", StringComparison.OrdinalIgnoreCase))
        {
            break;
        }

        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.Write("Agent> ");
        Console.ResetColor();

        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(input, session))
        {
            Console.Write(update);
        }

        Console.WriteLine();
        Console.WriteLine();
    }
}
finally
{
    Console.WriteLine($"Deleting hosted session {hostedSessionId}...");
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
