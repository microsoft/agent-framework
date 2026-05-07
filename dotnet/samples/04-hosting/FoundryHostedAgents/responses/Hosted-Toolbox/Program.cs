// Copyright (c) Microsoft. All rights reserved.

// Foundry Toolbox Agent - A hosted agent that uses Foundry Toolset MCP tools.
//
// Demonstrates how to register one or more Foundry toolsets so the agent can
// call tools provided by the Foundry platform's managed MCP proxy.
//
// Required environment variables:
//   AZURE_AI_PROJECT_ENDPOINT         - Azure AI Foundry project endpoint
//   AZURE_AI_MODEL_DEPLOYMENT_NAME    - Model deployment name (default: gpt-4o)
//   FOUNDRY_AGENT_TOOLSET_ENDPOINT    - Foundry Toolsets proxy base URL
//                                       (injected automatically by Foundry platform at runtime)
//
// Optional:
//   FOUNDRY_TOOLBOX_NAME              - Name of the toolset to load (default: my-toolset)
//   FOUNDRY_AGENT_NAME                - Client name reported to MCP server
//   FOUNDRY_AGENT_VERSION             - Client version reported to MCP server
//   FOUNDRY_AGENT_TOOLSET_FEATURES    - Feature flags sent to Foundry proxy via header

using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;

// Load .env file if present (for local development)
Env.TraversePath().Load();

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o";
string toolboxName = Environment.GetEnvironmentVariable("FOUNDRY_TOOLBOX_NAME") ?? "my-toolset";

// Use a chained credential: try a temporary dev token first (for local Docker debugging),
// then fall back to DefaultAzureCredential (for local dev via dotnet run / managed identity in production).
TokenCredential credential = new ChainedTokenCredential(
    new DevTemporaryTokenCredential(),
    new DefaultAzureCredential());

// ── Create agent ─────────────────────────────────────────────────────────────

AIAgent agent = new AIProjectClient(new Uri(endpoint), credential)
    .AsAIAgent(
        model: deploymentName,
        instructions: """
            You are a helpful assistant with access to tools provided by the Foundry Toolset.
            Use the available tools to answer user questions.
            If a tool is not available for a request, let the user know clearly.
            """,
        name: Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-toolbox-agent",
        description: "Hosted agent backed by Foundry Toolset MCP tools");

// ── Build the host ────────────────────────────────────────────────────────────

var builder = WebApplication.CreateBuilder(args);

// Register the agent and response handler
builder.Services.AddFoundryResponses(agent);

// Register Foundry Toolbox: connects to the MCP proxy at startup and makes tools available.
// The toolset name must match a toolset registered in your Foundry project.
// When FOUNDRY_AGENT_TOOLSET_ENDPOINT is absent (e.g., in local development without Foundry
// infrastructure), startup succeeds without error and no toolbox tools are loaded.
builder.Services.AddFoundryToolboxes(toolboxName);

var app = builder.Build();
app.MapFoundryResponses();

if (app.Environment.IsDevelopment())
{
    app.MapFoundryResponses("openai/v1");
}

app.Run();

// ── DevTemporaryTokenCredential ───────────────────────────────────────────────

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

        return new AccessToken(this._token, DateTimeOffset.MaxValue);
    }
}
