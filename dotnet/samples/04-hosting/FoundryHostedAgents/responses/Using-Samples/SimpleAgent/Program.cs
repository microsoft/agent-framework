// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.ClientModel.Primitives;
using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using OpenAI;
using OpenAI.Responses;

// Load .env file if present (for local development)
Env.TraversePath().Load();

// Port the Hosted-* samples listen on when run locally with `dotnet run`.
const int LocalAgentPort = 8088;

// AZURE_AI_AGENT_NAME is the registered server-side agent name.
string agentName = Environment.GetEnvironmentVariable("AZURE_AI_AGENT_NAME")
    ?? throw new InvalidOperationException("AZURE_AI_AGENT_NAME is not set.");

// Pick the server to talk to. `--local` and `--remote` mirror the flag `azd ai agent invoke`
// exposes; with neither, ask at startup.
bool useLocalAgent = ResolveTarget(args);

AIAgent agent = useLocalAgent ? CreateLocalAgent() : CreateHostedAgent(agentName);
string target = useLocalAgent ? $"http://localhost:{LocalAgentPort}" : agentName;

AgentSession session = await agent.CreateSessionAsync();

// ── REPL ──────────────────────────────────────────────────────────────────────

Console.ForegroundColor = ConsoleColor.Cyan;
Console.WriteLine($"""
    ══════════════════════════════════════════════════════════
    Simple Agent Sample
    Connected to: {target}
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

// Returns true when the client should target a locally running agent. `--local` and `--remote`
// answer the question up front, which is what non-interactive runs need; with neither, ask.
static bool ResolveTarget(string[] args)
{
    if (args.Contains("--local", StringComparer.OrdinalIgnoreCase)) { return true; }
    if (args.Contains("--remote", StringComparer.OrdinalIgnoreCase)) { return false; }

    return PromptForLocalTarget();
}

// Asks whether to target a locally running agent or the one deployed to Foundry, and returns
// true for local. Defaults to remote on an empty answer, matching `azd ai agent invoke`, which
// targets Foundry unless --local is passed.
static bool PromptForLocalTarget()
{
    Console.ForegroundColor = ConsoleColor.Cyan;
    Console.WriteLine("Which agent do you want to chat with?");
    Console.ResetColor();
    Console.WriteLine("  [1] Foundry (deployed agent)   [default]");
    Console.WriteLine($"  [2] Local    (dotnet run, http://localhost:{LocalAgentPort})");
    Console.Write("Choice: ");

    string? choice = Console.ReadLine()?.Trim();
    Console.WriteLine();

    return choice is "2";
}

// Builds an agent against a Hosted-* sample running locally. The sample serves the standard
// Responses route (POST /responses), so an OpenAI responses client pointed at the server reaches
// it directly. The server hosts its own agent and ignores both the model id and the api key, but
// the SDK requires them to shape the request.
static AIAgent CreateLocalAgent()
{
    var options = new OpenAIClientOptions { Endpoint = new Uri($"http://localhost:{LocalAgentPort}") };

    return new OpenAIClient(new ApiKeyCredential("not-needed"), options)
        .GetResponsesClient()
        .AsAIAgent(model: "hosted-agent", name: "LocalHostedAgent");
}

// Builds an agent against an agent deployed to Foundry. Hosted agents are reached through their
// per-agent endpoint, which the platform routes to the container's /responses route.
static AIAgent CreateHostedAgent(string agentName)
{
    Uri projectEndpoint = new(Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
        ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set."));

    Uri agentEndpoint = new($"{projectEndpoint}/agents/{agentName}/endpoint/protocols/openai");

    var options = new AIProjectClientOptions();

    if (projectEndpoint.Scheme == Uri.UriSchemeHttp)
    {
        // For local HTTP dev: the client pipeline refuses to attach a bearer token to a plain
        // HTTP endpoint, so point the client at an https:// URI to satisfy that check, then swap
        // the scheme back to http:// right before the request hits the wire.
        projectEndpoint = new UriBuilder(projectEndpoint) { Scheme = Uri.UriSchemeHttps }.Uri;
        agentEndpoint = new UriBuilder(agentEndpoint) { Scheme = Uri.UriSchemeHttps }.Uri;
        options.AddPolicy(new HttpSchemeRewritePolicy(), PipelinePosition.BeforeTransport);
    }

    return new AIProjectClient(projectEndpoint, new AzureCliCredential(), options).AsAIAgent(agentEndpoint);
}

/// <summary>
/// For Local Development Only.
/// Rewrites HTTPS URIs to HTTP right before transport, allowing <see cref="AIProjectClient"/> to
/// target a local HTTP dev server while satisfying the pipeline's TLS check: bearer tokens are
/// only attached to TLS-protected endpoints, so a plain http:// endpoint is rejected outright.
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
            message.Request.Uri = new UriBuilder(uri) { Scheme = Uri.UriSchemeHttp }.Uri;
        }
    }
}
