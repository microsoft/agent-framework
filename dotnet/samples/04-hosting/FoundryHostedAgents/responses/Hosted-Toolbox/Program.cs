// Copyright (c) Microsoft. All rights reserved.

// Foundry Toolbox Agent - A hosted agent that uses Foundry Toolbox MCP tools.
//
// Demonstrates how to register one or more Foundry toolboxes so the agent can
// call tools provided by the Foundry platform's managed MCP proxy.
//
// Required environment variables:
//   AZURE_AI_PROJECT_ENDPOINT (local-dev) OR FOUNDRY_PROJECT_ENDPOINT (hosted runtime)
//                                     - Azure AI Foundry project endpoint. The Foundry hosted
//                                       runtime auto-injects FOUNDRY_PROJECT_ENDPOINT; locally
//                                       set AZURE_AI_PROJECT_ENDPOINT.
//   AZURE_AI_MODEL_DEPLOYMENT_NAME    - Model deployment name (default: gpt-4o)
//
// Optional:
//   TOOLBOX_NAME                      - Name of the toolbox to load (default: my-toolbox)
//   FOUNDRY_AGENT_NAME                - Client name reported to MCP server (auto-injected in hosted runtime)
//   FOUNDRY_AGENT_VERSION             - Client version reported to MCP server (auto-injected in hosted runtime)
//   FOUNDRY_AGENT_TOOLSET_FEATURES    - Additional Foundry-Features header flags (the mandatory
//                                       Toolboxes=V1Preview flag is always sent; this env var
//                                       appends additional flags if present).
//
// The Foundry.Hosting package builds the toolbox proxy URL from FOUNDRY_PROJECT_ENDPOINT
// per tools-integration-spec.md §2–§3.

using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using Hosted_Shared_Contributor_Setup;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;

// Load .env file if present (for local development)
Env.TraversePath().Load();

string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException(
        "Neither FOUNDRY_PROJECT_ENDPOINT (platform-injected in hosted runtime) " +
        "nor AZURE_AI_PROJECT_ENDPOINT (local-dev convention) is set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o";
string toolboxName = Environment.GetEnvironmentVariable("TOOLBOX_NAME") ?? "my-toolbox";

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
            You are a helpful assistant with access to tools provided by the Foundry Toolbox.
            Use the available tools to answer user questions.
            If a tool is not available for a request, let the user know clearly.
            """,
        name: Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-toolbox-agent",
        description: "Hosted agent backed by Foundry Toolbox MCP tools");

// ── Build the host ────────────────────────────────────────────────────────────

var builder = WebApplication.CreateBuilder(args);

// Register the agent and response handler
builder.Services.AddFoundryResponses(agent);
builder.Services.AddDevTemporaryLocalContributorSetup(); // Local Docker debugging only - must not be used in production.

// Register Foundry Toolbox: connects to the MCP proxy at startup and makes tools available.
// The toolbox name must match a toolbox registered in your Foundry project.
// When FOUNDRY_PROJECT_ENDPOINT is absent (e.g., in local development without Foundry
// infrastructure), startup succeeds without error and no toolbox tools are loaded.
builder.Services.AddFoundryToolboxes(toolboxName);

var app = builder.Build();
app.MapFoundryResponses();

// Contributor-only: in Development, also map the per-agent OpenAI route shape that live Foundry uses
// so a local REPL client can target this server via AIProjectClient.AsAIAgent(Uri agentEndpoint).
// Do not use this in production. Hosted Foundry agents only support the agent-endpoint path.
app.MapDevTemporaryLocalAgentEndpoint();

app.Run();

// ── DevTemporaryTokenCredential ───────────────────────────────────────────────
