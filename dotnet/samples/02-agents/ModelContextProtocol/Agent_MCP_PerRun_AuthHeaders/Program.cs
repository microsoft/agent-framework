// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to attach per-run (refreshable) authentication headers to MCP requests.
//
// The agent connects to an MCP server with a custom HttpClient. A DelegatingHandler reads a token
// for the current run from an AsyncLocal scope and stamps it on each outbound MCP request, so a
// short-lived token (for example an OBO or cloud identity token that expires) can be refreshed on
// every run without rebuilding the agent or the MCP connection.
//
// The agent backend is Microsoft Foundry via the Responses API (RAPI). The MCP server is the public
// Microsoft Learn MCP server, which ignores the demonstration token; in production you point the
// handler at your own protected MCP server and mint a real token per run.

using System.Net.Http.Headers;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;

var projectEndpoint = new Uri(Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set."));
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

var serverEndpoint = new Uri("https://learn.microsoft.com/api/mcp");

// Custom HttpClient for the MCP transport. The per-run handler attaches the bearer; the inner
// handler disables cookies (no cross-context state), disables auto-redirect (so a redirect cannot
// carry the bearer past the origin re-check), and checks certificate revocation.
using var httpClient = new HttpClient(new PerRunAuthHeaderHandler(serverEndpoint)
{
    InnerHandler = new HttpClientHandler
    {
        UseCookies = false,
        AllowAutoRedirect = false,
        CheckCertificateRevocationList = true,
    },
});

Console.WriteLine($"Connecting to MCP server at {serverEndpoint} ...");

await using var mcpClient = await McpClient.CreateAsync(new HttpClientTransport(new()
{
    Endpoint = serverEndpoint,
    Name = "Microsoft Learn MCP",
    TransportMode = HttpTransportMode.StreamableHttp,
}, httpClient));

IList<McpClientTool> mcpTools = await mcpClient.ListToolsAsync();
Console.WriteLine($"MCP tools available: {string.Join(", ", mcpTools.Select(t => t.Name))}");

// Build the agent from Microsoft Foundry using the Responses API (RAPI).
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AIProjectClient(projectEndpoint, new DefaultAzureCredential())
    .AsAIAgent(
        model: deploymentName,
        instructions: "You answer Microsoft documentation questions using the available tools.",
        name: "DocsAgent",
        tools: [.. mcpTools.Cast<AITool>()]);

// Run the same agent twice under two different contexts. Each run gets a freshly minted token,
// proving the auth header is per-run rather than bound when the agent or MCP connection was created.
await RunForContextAsync(agent, "tenant-a", "How do I create an Azure storage account with az cli?");
await RunForContextAsync(agent, "tenant-b", "What is Azure Functions?");

static async Task RunForContextAsync(AIAgent agent, string label, string prompt)
{
    // Stand-in for a real per-run token (for example an OBO or cloud identity token).
    // It carries no PII and is regenerated on every run. The label is non-secret and used for logging.
    McpRunContext? previous = McpRunScope.Current;
    McpRunScope.Current = new McpRunContext(label, $"{label}.{Guid.NewGuid():N}");
    try
    {
        Console.WriteLine($"\n=== Run for '{label}' (fresh per-run token) ===");
        Console.WriteLine(await agent.RunAsync(prompt));
    }
    finally
    {
        // Restore the prior scope (stack-like) so this is safe to call from within an outer scope.
        McpRunScope.Current = previous;
    }
}

/// <summary>
/// Carries the context for the current run. <see cref="Label"/> is a non-secret identifier safe to
/// log; <see cref="Token"/> is the secret that must never be logged or persisted.
/// </summary>
internal sealed record McpRunContext(string Label, string Token);

/// <summary>
/// Flows the current <see cref="McpRunContext"/> to the MCP <see cref="DelegatingHandler"/> without
/// threading it through every call. Set it before a run and reset it afterwards.
/// </summary>
internal static class McpRunScope
{
    private static readonly AsyncLocal<McpRunContext?> s_current = new();

    public static McpRunContext? Current
    {
        get => s_current.Value;
        set => s_current.Value = value;
    }
}

/// <summary>
/// Attaches the current run's bearer token to outbound MCP requests. The token is read fresh on
/// every request, so refreshing it between runs needs no agent or connection rebuild.
/// </summary>
/// <remarks>
/// Security: the bearer is attached only over HTTPS and only when the request targets the configured
/// MCP server origin, which prevents the credential from leaking over plaintext or to a redirect
/// target on another origin. Only the non-secret label is logged, never the token.
/// </remarks>
internal sealed class PerRunAuthHeaderHandler(Uri serverEndpoint) : DelegatingHandler
{
    private readonly string _serverOrigin = serverEndpoint.GetLeftPart(UriPartial.Authority);

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        McpRunContext? context = McpRunScope.Current;
        Uri? requestUri = request.RequestUri;

        if (context is not null
            && requestUri is not null
            && requestUri.Scheme == Uri.UriSchemeHttps
            && string.Equals(requestUri.GetLeftPart(UriPartial.Authority), this._serverOrigin, StringComparison.OrdinalIgnoreCase))
        {
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", context.Token);
            Console.WriteLine($"[mcp-auth] attached bearer for '{context.Label}' -> {request.Method} {requestUri.AbsolutePath}");
        }

        return await base.SendAsync(request, cancellationToken).ConfigureAwait(false);
    }
}
