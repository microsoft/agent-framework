// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using Hosted_Shared_Contributor_Setup;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;

// Load .env file if present (for local development)
Env.TraversePath().Load();

var projectEndpoint = new Uri(Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set."));

var agentName = Environment.GetEnvironmentVariable("AGENT_NAME")
    ?? throw new InvalidOperationException("AGENT_NAME is not set.");

var deployment = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o";

// Use a chained credential: try a temporary dev token first (for local Docker debugging),
// then fall back to DefaultAzureCredential (for local dev via dotnet run / managed identity running in foundry).
TokenCredential credential = new ChainedTokenCredential(
    new DevTemporaryTokenCredential(),
    new DefaultAzureCredential());

// Create the agent via the AI project client using the Responses API.
AIAgent agent = new AIProjectClient(projectEndpoint, credential)
    .AsAIAgent(
        model: deployment,
        instructions: """
            You are a helpful AI assistant hosted as a Foundry Hosted Agent.
            You can help with a wide range of tasks including answering questions,
            providing explanations, brainstorming ideas, and offering guidance.
            Be concise, clear, and helpful in your responses.
            """,
        name: agentName,
        description: "A simple general-purpose AI assistant");

// Host the agent as a Foundry Hosted Agent using the Responses API.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);
builder.Services.AddDevTemporaryLocalContributorSetup(); // Local Docker debugging only - must not be used in production.

var app = builder.Build();
app.MapFoundryResponses();

// In Development, also map the OpenAI-compatible route that AIProjectClient uses.
if (app.Environment.IsDevelopment())
{
    app.MapFoundryResponses("openai/v1");
}

app.Run();
