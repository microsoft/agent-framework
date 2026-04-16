// Copyright (c) Microsoft. All rights reserved.

using DotNetEnv;
using Microsoft.Agents.AI;

// Load .env file if present (for local development)
Env.TraversePath().Load();

Uri agentEndpoint = new(Environment.GetEnvironmentVariable("AGENT_ENDPOINT")
    ?? "http://localhost:8088");

// Create an agent that calls the remote Invocations endpoint.
InvocationsAIAgent agent = new(agentEndpoint);

// REPL
Console.ForegroundColor = ConsoleColor.Cyan;
Console.WriteLine($"""
    ══════════════════════════════════════════════════════════
    Simple Invocations Agent Sample
    Connected to: {agentEndpoint}
    Type a message or 'quit' to exit
    ══════════════════════════════════════════════════════════
    """);
Console.ResetColor();
Console.WriteLine();

while (true)
{
    Console.ForegroundColor = ConsoleColor.Green;
    Console.Write("You> ");
    Console.ResetColor();

    string? input = Console.ReadLine();

    if (string.IsNullOrWhiteSpace(input)) { continue; }
    if (input.Equals("quit", StringComparison.OrdinalIgnoreCase)) { break; }

    try
    {
        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.Write("Agent> ");
        Console.ResetColor();

        await foreach (var update in agent.RunStreamingAsync(input))
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
