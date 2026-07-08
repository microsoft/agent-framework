// Copyright (c) Microsoft. All rights reserved.

// Foundry Toolbox Auth Paths Agent — A hosted agent backed by a single Foundry Toolbox
// that bundles MCP tools using THREE different authentication paths.
//
// This sample demonstrates the same hosting bones as Hosted-Toolbox/, but the toolbox
// (provisioned by the user out-of-band) contains three MCP tool entries each authenticated
// differently. The agent code itself is agnostic to authentication — the educational
// surface lives in the toolbox configuration in the Foundry portal and in this sample's
// README.md.
//
// Required environment variables:
//   AZURE_AI_PROJECT_ENDPOINT (local-dev) OR FOUNDRY_PROJECT_ENDPOINT (hosted runtime)
//                                     - Foundry project endpoint. The Foundry hosted
//                                       runtime auto-injects FOUNDRY_PROJECT_ENDPOINT; locally
//                                       set AZURE_AI_PROJECT_ENDPOINT (the AF-repo convention).
//   TOOLBOX_NAME                      - Name of the Foundry Toolbox to load
//                                       (default: auth-paths-toolbox)
//
// Optional:
//   AZURE_AI_MODEL_DEPLOYMENT_NAME    - Model deployment name (default: gpt-4o)
//   AGENT_NAME                        - Defaults to "hosted-toolbox-auth-paths-agent".
//
// The Foundry.Hosting package builds the toolbox proxy URL from FOUNDRY_PROJECT_ENDPOINT
// per tools-integration-spec.md §2–§3, so the sample does not need to plumb any
// toolbox-specific URL env var.
//
// NOTE: All FOUNDRY_* and AGENT_* env-var prefixes (other than the platform-injected ones
// listed above) are reserved by the Foundry container platform and rejected by the
// agent-create API. Use TOOLBOX_NAME, not FOUNDRY_TOOLBOX_NAME, for sample-owned config.

#pragma warning disable OPENAI001 // FoundryAITool.CreateHostedMcpToolbox is experimental

using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using Hosted_Shared_Contributor_Setup;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;

// Load .env file if present (for local development)
Env.TraversePath().Load();

// Project endpoint resolution order:
//   1. FOUNDRY_PROJECT_ENDPOINT — auto-injected by the Foundry hosted runtime.
//   2. AZURE_AI_PROJECT_ENDPOINT — the convention developers set locally for `dotnet run`.
// When deployed, only (1) is available; the AF-repo sample convention to set (2) at
// deploy time fails silently because the platform reserves all FOUNDRY_* env-var names
// and rejects them at agent-create time. Read both, prefer the platform-injected one.
string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException(
        "Neither FOUNDRY_PROJECT_ENDPOINT (platform-injected in hosted runtime) " +
        "nor AZURE_AI_PROJECT_ENDPOINT (local-dev convention) is set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o";
string toolboxName = Environment.GetEnvironmentVariable("TOOLBOX_NAME") ?? "auth-paths-toolbox";
string agentName = Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-toolbox-auth-paths-agent";

TokenCredential credential = new ChainedTokenCredential(
    new DevTemporaryTokenCredential(),
    new DefaultAzureCredential());

// Notes on toolbox wiring — there are two ways to attach a Foundry Toolbox to an agent:
//   - Server-side "baked-in" (what this sample uses): calling AddFoundryToolboxes(credential, name)
//     below registers the toolbox with the Foundry.Hosting layer, which resolves that
//     toolbox's MCP tools once at startup and automatically makes them available to the
//     agent on every request. The agent code does nothing per request.
//   - Per-request / caller-driven (NOT used here): a client can attach a toolbox for a
//     single call by placing a FoundryAITool.CreateHostedMcpToolbox(name) marker in the
//     request body's tool list.
// Because this sample bakes the toolbox in on the server, it uses AddFoundryToolboxes and
// does NOT put the CreateHostedMcpToolbox marker in the agent's `tools:` array.
AIAgent agent = new AIProjectClient(new Uri(endpoint), credential)
    .AsAIAgent(
        model: deploymentName,
        instructions: """
            You are a helpful assistant with access to several tools, each provided by a different
            upstream service authenticated through a distinct mechanism (API key, agent managed
            identity, and a literal token
            shipped with the tool definition). Pick the tool that best fits the user's question
            and explain which upstream service answered when you respond.
            """,
        name: agentName,
        description: "Hosted agent demonstrating three MCP-tool authentication paths via a Foundry Toolbox.");

// Tier 3 spine (WebApplication.CreateBuilder + AddFoundryResponses + MapFoundryResponses):
// the Foundry.Hosting package auto-maps the spec-required GET /readiness probe inside
// MapFoundryResponses (idempotent — skipped when AgentHost or the developer already
// mapped it), so the sample stays free of platform plumbing.
var builder = WebApplication.CreateBuilder(args);

builder.Services.AddFoundryResponses(agent);
// Pre-register the toolbox name so FoundryToolboxService resolves the foundry-toolbox://
// marker at request time. With FOUNDRY_PROJECT_ENDPOINT injected by the platform, startup
// MCP tools/list against the toolbox proxy is typically <100ms in-region.
builder.Services.AddFoundryToolboxes(credential, toolboxName);

var app = builder.Build();
app.MapFoundryResponses();

// Contributor-only: in Development, also map the per-agent OpenAI route shape that live Foundry
// uses so a local REPL client can target this server via AIProjectClient.AsAIAgent(Uri agentEndpoint).
// Do not use this in production. Hosted Foundry agents only support the agent-endpoint path.
app.MapDevTemporaryLocalAgentEndpoint();

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
