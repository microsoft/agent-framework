// Copyright (c) Microsoft. All rights reserved.

// Hosted Toolbox MCP Skills Agent
//
// Demonstrates how to host an agent that discovers MCP-based skills from a
// Foundry Toolbox MCP endpoint and injects them as AIContextProviders using
// AgentSkillsProviderBuilder.UseMcpSkills().
//
// Required environment variables:
//   FOUNDRY_PROJECT_ENDPOINT         - Foundry project endpoint
//   TOOLBOX_NAME                     - Name of the Foundry Toolbox to connect to
//
// Optional:
//   AZURE_AI_MODEL_DEPLOYMENT_NAME  - Model deployment name (default: gpt-5)
//   FOUNDRY_MODEL                    - Legacy local-development fallback
//
// NOTE: All FOUNDRY_* and AGENT_* env-var prefixes (other than the platform-injected ones
// listed above) are reserved by the Foundry container platform and rejected at agent-create.
// Use TOOLBOX_NAME, not FOUNDRY_TOOLBOX_NAME, for the sample-owned toolbox name so it
// survives deployment.

using System.Net.Http.Headers;
using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using ModelContextProtocol.Client;

// Load .env file if present (for local development)
Env.TraversePath().Load();

var projectEndpoint = System.Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deployment = FirstNonBlank(
    System.Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
    System.Environment.GetEnvironmentVariable("FOUNDRY_MODEL"),
    "gpt-5");
var toolboxName = FirstNonBlank(System.Environment.GetEnvironmentVariable("TOOLBOX_NAME"))
    ?? throw new InvalidOperationException("TOOLBOX_NAME is not set.");

// Build the Toolbox MCP URL from the project endpoint and toolbox name.
var toolboxMcpServerUrl = $"{projectEndpoint.TrimEnd('/')}/toolboxes/{toolboxName}/mcp?api-version=v1";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
// Use a chained credential: try a temporary dev token first (for local Docker debugging),
// then fall back to DefaultAzureCredential (for local dev via dotnet run / managed identity in production).
var credential = new DefaultAzureCredential();

// ── Connect to the Foundry Toolbox MCP endpoint ─────────────────────────────
// Create an HttpClient that attaches a fresh Foundry bearer token to every request.
using var httpClient = new HttpClient(new BearerTokenHandler(credential, "https://ai.azure.com/.default") { CheckCertificateRevocationList = true });

Console.WriteLine($"Connecting to Foundry Toolbox '{toolboxName}' MCP server...");

await using var mcpClient = await McpClient.CreateAsync(
    new HttpClientTransport(
        new HttpClientTransportOptions
        {
            Endpoint = new Uri(toolboxMcpServerUrl),
            Name = toolboxName,
            TransportMode = HttpTransportMode.StreamableHttp,
            AdditionalHeaders = new Dictionary<string, string>
            {
                ["Foundry-Features"] = "Toolboxes=V1Preview",
            },
        },
        httpClient));

// ── Configure MCP-based skills provider ──────────────────────────────────────
var skillsProvider = new AgentSkillsProviderBuilder()
    .UseMcpSkills(mcpClient)
    .Build();

// ── Create the agent ─────────────────────────────────────────────────────────
AIAgent agent = new AIProjectClient(new Uri(projectEndpoint), credential)
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = System.Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-toolbox-mcp-skills",
        Description = "Hosted agent with MCP skills discovered from a Foundry Toolbox",
        ChatOptions = new()
        {
            ModelId = deployment,
            Instructions = "You are a helpful assistant.",
        },
        AIContextProviders = [skillsProvider],
    });

// ── Build the host ───────────────────────────────────────────────────────────
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();


app.Run();

static string? FirstNonBlank(params string?[] candidates) =>
    Array.Find(candidates, candidate => !string.IsNullOrWhiteSpace(candidate));

// ---------------------------------------------------------------------------
// HttpClientHandler: attaches a fresh Foundry bearer token to every request
// ---------------------------------------------------------------------------
internal sealed class BearerTokenHandler(TokenCredential credential, string scope) : HttpClientHandler
{
    private readonly TokenRequestContext _tokenContext = new([scope]);

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        AccessToken token = await credential.GetTokenAsync(this._tokenContext, cancellationToken).ConfigureAwait(false);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);
        return await base.SendAsync(request, cancellationToken).ConfigureAwait(false);
    }
}
