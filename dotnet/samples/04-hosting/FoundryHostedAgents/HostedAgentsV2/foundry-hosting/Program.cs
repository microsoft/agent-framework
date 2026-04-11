// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Agents.AI.Foundry.Hosting;

// Load .env file if present (for local development)
Env.TraversePath().Load();

var projectEndpoint = new Uri(Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set."));
var agentName = Environment.GetEnvironmentVariable("AGENT_NAME")
    ?? throw new InvalidOperationException("AGENT_NAME is not set.");

var aiProjectClient = new AIProjectClient(projectEndpoint, new DefaultAzureCredential());

// Retrieve the Foundry-managed agent by name (latest version).
ProjectsAgentRecord agentRecord = await aiProjectClient
    .AgentAdministrationClient.GetAgentAsync(agentName);

FoundryAgent agent = aiProjectClient.AsAIAgent(agentRecord);

// Host the agent as a Foundry Hosted Agent using the Responses API.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();
app.Run();
