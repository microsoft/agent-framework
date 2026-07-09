// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using Hosted_Shared_Contributor_Setup;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Agents.AI.Foundry.Hosting;

// Load .env file if present (for local development)
Env.TraversePath().Load();

var projectEndpoint = new Uri(Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set."));
var agentName = Environment.GetEnvironmentVariable("AGENT_NAME")
    ?? throw new InvalidOperationException("AGENT_NAME is not set.");

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
// Use a chained credential: try a temporary dev token first (for local Docker debugging),
// then fall back to DefaultAzureCredential (for local dev via dotnet run / managed identity running in foundry).
TokenCredential credential = new ChainedTokenCredential(
    new DevTemporaryTokenCredential(),
    new DefaultAzureCredential());

var aiProjectClient = new AIProjectClient(projectEndpoint, credential);

// Retrieve the Foundry-managed agent by name (latest version).
ProjectsAgentRecord agentRecord = await aiProjectClient
    .AgentAdministrationClient.GetAgentAsync(agentName);

FoundryAgent agent = aiProjectClient.AsAIAgent(agentRecord);

// Host the agent as a Foundry Hosted Agent using the Responses API.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();

// Contributor-only: in Development, also map the per-agent OpenAI route shape that live Foundry uses
// so a local REPL client can target this server via AIProjectClient.AsAIAgent(Uri agentEndpoint).
// Do not use this in production. Hosted Foundry agents only support the agent-endpoint path.
app.MapDevTemporaryLocalAgentEndpoint();

app.Run();
