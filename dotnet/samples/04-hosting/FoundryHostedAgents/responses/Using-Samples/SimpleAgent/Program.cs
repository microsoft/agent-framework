// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;

// Load .env file if present (for local development)
Env.TraversePath().Load();

Uri agentEndpoint = new(Environment.GetEnvironmentVariable("AGENT_ENDPOINT")
    ?? "http://localhost:8088");

var agentName = Environment.GetEnvironmentVariable("AGENT_NAME")
    ?? throw new InvalidOperationException("AGENT_NAME is not set.");

// ── Create an agent-framework agent backed by the remote agent endpoint ──────

var options = new AIProjectClientOptions();

if (agentEndpoint.Scheme == "http")
{
    // For local HTTP dev: tell AIProjectClient the endpoint is HTTPS (to satisfy
    // BearerTokenPolicy's TLS check), then swap the scheme back to HTTP right
    // before the request hits the wire.

    agentEndpoint = new UriBuilder(agentEndpoint) { Scheme = "https" }.Uri;
    options.AddPolicy(new HttpSchemeRewritePolicy(), PipelinePosition.BeforeTransport);
}

var aiProjectClient = new AIProjectClient(agentEndpoint, new AzureCliCredential(), options);
FoundryAgent agent = aiProjectClient.AsAIAgent(new AgentReference(agentName));

AgentSession session = await agent.CreateSessionAsync();

// ── REPL ──────────────────────────────────────────────────────────────────────

Console.ForegroundColor = ConsoleColor.Cyan;
Console.WriteLine($"""
    ══════════════════════════════════════════════════════════
    Simple Agent Sample                                     
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

/// <summary>
/// For Local Development Only
/// Rewrites HTTPS URIs to HTTP right before transport, allowing AIProjectClient
/// to target a local HTTP dev server while satisfying BearerTokenPolicy's TLS check.
/// </summary>
internal sealed class HttpSchemeRewritePolicy : PipelinePolicy
{
    public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
    {
        RewriteScheme(message);
        ProcessNext(message, pipeline, currentIndex);
    }

    public override async ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
    {
        RewriteScheme(message);
        await ProcessNextAsync(message, pipeline, currentIndex).ConfigureAwait(false);
    }

    private static void RewriteScheme(PipelineMessage message)
    {
        var uri = message.Request.Uri!;
        if (uri.Scheme == Uri.UriSchemeHttps)
        {
            message.Request.Uri = new UriBuilder(uri) { Scheme = "http" }.Uri;
        }
    }
}
