// Copyright (c) Microsoft. All rights reserved.

// Hosted Toolbox MCP Skills Agent
//
// Demonstrates how to host an agent that discovers MCP-based skills from a
// Foundry Toolbox MCP endpoint and injects them as AIContextProviders using
// AgentSkillsProviderBuilder.UseMcpSkills().
//
// Required environment variables:
//   AZURE_AI_PROJECT_ENDPOINT         - Azure AI Foundry project endpoint
//   FOUNDRY_TOOLBOX_NAME              - Name of the Foundry Toolbox to connect to
//   AZURE_AI_MODEL_DEPLOYMENT_NAME    - Model deployment name (default: gpt-5)

using System.Net.Http.Headers;
using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using Hosted_Shared_Contributor_Setup;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using ModelContextProtocol.Client;

// Load .env file if present (for local development)
Env.TraversePath().Load();

var projectEndpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
var deployment = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5";
var toolboxName = Environment.GetEnvironmentVariable("FOUNDRY_TOOLBOX_NAME")
    ?? throw new InvalidOperationException("FOUNDRY_TOOLBOX_NAME is not set.");

// Build the Toolbox MCP URL from the project endpoint and toolbox name.
var toolboxMcpServerUrl = $"{projectEndpoint.TrimEnd('/')}/toolboxes/{toolboxName}/mcp?api-version=v1";

// Use a chained credential: try a temporary dev token first (for local Docker debugging),
// then fall back to DefaultAzureCredential (for local dev via dotnet run / managed identity in production).
TokenCredential credential = new ChainedTokenCredential(
    new DevTemporaryTokenCredential(),
    new DefaultAzureCredential());

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
        Name = Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-toolbox-mcp-skills",
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
builder.Services.AddDevTemporaryLocalContributorSetup(); // Local Docker debugging only - must not be used in production.

var app = builder.Build();
app.MapFoundryResponses();

// Contributor-only: in Development, also map the per-agent OpenAI route shape that live Foundry uses
// so a local REPL client can target this server via AIProjectClient.AsAIAgent(Uri agentEndpoint).
// Do not use this in production. Hosted Foundry agents only support the agent-endpoint path.
app.MapDevTemporaryLocalAgentEndpoint();

app.Run();

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
