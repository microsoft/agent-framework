// Copyright (c) Microsoft. All rights reserved.

// Foundry Responses Client REPL
//
// Connects to a Foundry Responses agent running on a given endpoint
// and provides an interactive multi-turn chat REPL.
//
// Usage:
//   dotnet run                                    (connects to http://localhost:8088)
//   dotnet run -- --endpoint http://localhost:9090
//   dotnet run -- --endpoint https://my-foundry-project.services.ai.azure.com
//
// The endpoint should be running a Foundry Responses server (POST /responses).

using System.ClientModel;
using Microsoft.Agents.AI;
using OpenAI;
using OpenAI.Responses;

// ── Parse args ────────────────────────────────────────────────────────────────

string endpointUrl = "http://localhost:8088";
for (int i = 0; i < args.Length - 1; i++)
{
    if (args[i] is "--endpoint" or "-e")
    {
        endpointUrl = args[i + 1];
    }
}

// ── Create an agent-framework agent backed by the remote Responses endpoint ──

// The OpenAI SDK's ResponsesClient can target any OpenAI-compatible endpoint.
// We use a dummy API key since our local server doesn't require auth.
var credential = new ApiKeyCredential(
    Environment.GetEnvironmentVariable("RESPONSES_API_KEY") ?? "no-key-needed");

var openAiClient = new OpenAIClient(
    credential,
    new OpenAIClientOptions { Endpoint = new Uri(endpointUrl) });

ResponsesClient responsesClient = openAiClient.GetResponsesClient();

// Wrap as an agent-framework AIAgent via the OpenAI extensions.
// We pass an empty model since hosted agents use their own model configuration.
AIAgent agent = responsesClient.AsAIAgent(
    model: "",
    name: "remote-agent");

// Create a session so multi-turn context is preserved via previous_response_id
AgentSession session = await agent.CreateSessionAsync();

// ── REPL ──────────────────────────────────────────────────────────────────────

Console.ForegroundColor = ConsoleColor.Cyan;
Console.WriteLine("╔══════════════════════════════════════════════════════════╗");
Console.WriteLine("║  Foundry Responses Client REPL                          ║");
Console.WriteLine($"║  Connected to: {endpointUrl,-41}║");
Console.WriteLine("║  Type a message or 'quit' to exit                       ║");
Console.WriteLine("╚══════════════════════════════════════════════════════════╝");
Console.ResetColor();
Console.WriteLine();

while (true)
{
    Console.ForegroundColor = ConsoleColor.Green;
    Console.Write("You> ");
    Console.ResetColor();

    string? input = Console.ReadLine();
    if (string.IsNullOrWhiteSpace(input))
    {
        continue;
    }

    if (input.Equals("quit", StringComparison.OrdinalIgnoreCase) ||
        input.Equals("exit", StringComparison.OrdinalIgnoreCase))
    {
        break;
    }

    try
    {
        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.Write("Agent> ");
        Console.ResetColor();

        // Stream the response token-by-token
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
