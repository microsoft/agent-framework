// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates a hosted agent with two layers of MCP (Model Context Protocol) tools:
//
// 1. CLIENT-SIDE MCP: The agent connects to the Microsoft Learn MCP server directly via
//    McpClient, discovers tools, and handles tool invocations locally within the agent process.
//
// 2. SERVER-SIDE MCP: The agent declares a HostedMcpServerTool for the same MCP server which
//    delegates tool discovery and invocation to the LLM provider (Azure OpenAI Responses API).
//    The provider calls the MCP server on behalf of the agent — no local connection needed.
//
// Both patterns use the Microsoft Learn MCP server to illustrate the architectural difference:
// client-side tools are resolved and invoked by the agent, while server-side tools are resolved
// and invoked by the LLM provider.

#pragma warning disable MEAI001 // HostedMcpServerTool is experimental

using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;

// Load .env file if present (for local development)
Env.TraversePath().Load();

var projectEndpoint = new Uri(Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set."));
var deployment = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o";

// Use a chained credential: try a temporary dev token first (for local Docker debugging),
// then fall back to DefaultAzureCredential (for local dev via dotnet run / managed identity in production).
TokenCredential credential = new ChainedTokenCredential(
    new DevTemporaryTokenCredential(),
    new DefaultAzureCredential());

// ── Client-side MCP: Microsoft Learn (local resolution) ──────────────────────
// Connect directly to the MCP server. The agent discovers and invokes tools locally.
Console.WriteLine("Connecting to Microsoft Learn MCP server (client-side)...");

await using var learnMcp = await McpClient.CreateAsync(new HttpClientTransport(new()
{
    Endpoint = new Uri("https://learn.microsoft.com/api/mcp"),
    Name = "Microsoft Learn (client)",
}));

var clientTools = await learnMcp.ListToolsAsync();
Console.WriteLine($"Client-side MCP tools: {string.Join(", ", clientTools.Select(t => t.Name))}");

// ── Server-side MCP: Microsoft Learn (provider resolution) ───────────────────
// Declare a HostedMcpServerTool — the LLM provider (Responses API) handles tool
// invocations directly. No local MCP connection needed for this pattern.
AITool serverTool = new HostedMcpServerTool(
    serverName: "microsoft_learn_hosted",
    serverAddress: "https://learn.microsoft.com/api/mcp")
{
    AllowedTools = ["microsoft_docs_search"],
    ApprovalMode = HostedMcpServerToolApprovalMode.NeverRequire
};
Console.WriteLine("Server-side MCP tool: microsoft_docs_search (via HostedMcpServerTool)");

// ── Combine both tool types into a single agent ──────────────────────────────
// The agent has access to tools from both MCP patterns simultaneously.
List<AITool> allTools = [.. clientTools.Cast<AITool>(), serverTool];

AIAgent agent = new AIProjectClient(projectEndpoint, credential)
    .AsAIAgent(
        model: deployment,
        instructions: """
            You are a helpful developer assistant with access to Microsoft Learn documentation.
            Use the available tools to search and retrieve documentation.
            Be concise and provide direct answers with relevant links.
            """,
        name: "mcp-tools",
        description: "Developer assistant with dual-layer MCP tools (client-side and server-side)",
        tools: allTools);

// Host the agent as a Foundry Hosted Agent using the Responses API.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();

// In Development, also map the OpenAI-compatible route that AIProjectClient uses.
if (app.Environment.IsDevelopment())
{
    app.MapFoundryResponses("openai/v1");
}

app.Run();

/// <summary>
/// A <see cref="TokenCredential"/> for local Docker debugging only.
/// Reads a pre-fetched bearer token from the <c>AZURE_BEARER_TOKEN</c> environment variable
/// once at startup. This should NOT be used in production.
///
/// Generate a token on your host and pass it to the container:
///   export AZURE_BEARER_TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
///   docker run -e AZURE_BEARER_TOKEN=$AZURE_BEARER_TOKEN ...
/// </summary>
internal sealed class DevTemporaryTokenCredential : TokenCredential
{
    private const string EnvironmentVariable = "AZURE_BEARER_TOKEN";
    private readonly string? _token;

    public DevTemporaryTokenCredential()
    {
        this._token = Environment.GetEnvironmentVariable(EnvironmentVariable);
    }

    public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken)
        => this.GetAccessToken();

    public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken)
        => new(this.GetAccessToken());

    private AccessToken GetAccessToken()
    {
        if (string.IsNullOrEmpty(this._token) || this._token == "DefaultAzureCredential")
        {
            throw new CredentialUnavailableException($"{EnvironmentVariable} environment variable is not set.");
        }

        return new AccessToken(this._token, DateTimeOffset.UtcNow.AddHours(1));
    }
}
