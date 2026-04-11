// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;

// Load .env file if present (for local development)
Env.TraversePath().Load();

string agentEndpoint = Environment.GetEnvironmentVariable("AGENT_ENDPOINT") ?? "http://localhost:8088";

// ── Create an agent-framework agent backed by the remote agent endpoint ──────
// The Foundry Agent SDK's AIProjectClient can target any OpenAI-compatible endpoint.

var aiProjectClient = new AIProjectClient(new Uri(agentEndpoint), new AzureCliCredential());
var agent = aiProjectClient.AsAIAgent();

AgentSession session = await agent.CreateSessionAsync();

// ── REPL ──────────────────────────────────────────────────────────────────────

Console.ForegroundColor = ConsoleColor.Cyan;
Console.WriteLine("╔══════════════════════════════════════════════════════════╗");
Console.WriteLine("║  Simple Agent Client                                     ║");
Console.WriteLine($"║  Connected to: {agentEndpoint,-41}║");
Console.WriteLine("║  Type a message or 'quit' to exit                        ║");
Console.WriteLine("╚══════════════════════════════════════════════════════════╝");
Console.ResetColor();
Console.WriteLine();

while (true)
{
    Console.ForegroundColor = ConsoleColor.Green;
    Console.Write("You> ");
    Console.ResetColor();

    string? input = Console.ReadLine();

    if (string.IsNullOrWhiteSpace(input)) { continue; }
    if (input.Equals("quit", StringComparison.OrdinalIgnoreCase) ||
        input.Equals("exit", StringComparison.OrdinalIgnoreCase))
    { break; }

    try
    {
        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.Write("Agent> ");
        Console.ResetColor();

        await foreach (var update in agent.RunStreamingAsync(input, session))
        {
            Console.Write(update);
        }

        Console.WriteLine();
    }
    catch (Exception ex)
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine($"Error: {ex.Message}");
        Console.ResetColor();
    }

    Console.WriteLine();
}

Console.WriteLine("Goodbye!");
